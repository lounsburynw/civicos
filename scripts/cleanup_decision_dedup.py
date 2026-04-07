#!/usr/bin/env python3
"""
Cleanup duplicate decisions in production Postgres (Option A — semantic dedup).

Backfill for the launch.json:fix_decision_storage_dedup bug. Existing rows in
the decisions table that were inserted with non-deterministic LLM-ordinal IDs
are duplicates of each other (same jurisdiction_id, same meeting, same title)
but have different IDs and so weren't merged by the temporal-versioning UPDATE
in store_decisions(). This script identifies those groups and closes the
duplicates by setting valid_to on all but the earliest version per group —
preserving full audit history rather than destructively deleting.

Dedup key: the new stable decision ID (compute_stable_decision_id) — i.e.,
the ID this row *would have* under the forward fix. Two open rows that
collapse to the same stable ID are true duplicates of the same logical
decision; everything else is a legitimately distinct decision.

This is critical because the LLM frequently produces multiple decisions
in the same meeting that share a generic title (e.g., 4 different housing
project approvals all titled "Authorizing funding for affordable housing
projects"). These are NOT duplicates — they have different agenda_items.
A naive (jurisdiction, meeting, title) dedup would destroy them. The
stable-ID hash correctly disambiguates them via item_ref.

Strategy:
  1. SELECT all open (valid_to IS NULL) decisions
  2. For each row, compute the stable ID it WOULD have had under the fix
  3. Group rows by computed stable ID
  4. For each group with > 1 row:
     - Sort by extracted_at ascending (keep earliest)
     - For all rows after the first: UPDATE decisions SET valid_to = NOW()
  5. In --dry-run mode, print per-jurisdiction counts and example titles

Usage:
    # Dry run (default): print what would change, no writes
    python scripts/cleanup_decision_dedup.py

    # Filter to a single jurisdiction
    python scripts/cleanup_decision_dedup.py --jurisdiction county-alameda

    # Apply changes
    python scripts/cleanup_decision_dedup.py --apply

    # Apply to a single jurisdiction
    python scripts/cleanup_decision_dedup.py --apply --jurisdiction county-alameda
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# Re-use the same hash that the forward fix uses, so cleanup is exactly
# consistent with what new extractions will produce.
from civicos.storage.integrity import (
    compute_stable_decision_id,
    has_stable_decision_id_inputs,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment", file=sys.stderr)
    sys.exit(1)


def fetch_open_decisions(conn, jurisdiction_filter: Optional[str]) -> list[dict]:
    """Fetch all open (valid_to IS NULL) decisions, optionally filtered by jurisdiction."""
    query = """
        SELECT id, jurisdiction_id, meeting_id, meeting_date, agenda_item,
               title, outcome, item_type, financial_impact_cents,
               extracted_at, valid_from
        FROM decisions
        WHERE valid_to IS NULL
    """
    params: tuple = ()
    if jurisdiction_filter:
        query += " AND jurisdiction_id = %s"
        params = (jurisdiction_filter,)
    query += " ORDER BY jurisdiction_id, meeting_id, extracted_at"

    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def compute_would_be_stable_id(row: dict) -> Optional[str]:
    """
    Compute the stable ID a row WOULD have under the forward fix.

    Returns None if the row has neither agenda_item nor title — those rows
    can't be safely deduped because we have no stable content to hash.
    """
    if not has_stable_decision_id_inputs(row.get("agenda_item"), row.get("title")):
        return None

    cents = row.get("financial_impact_cents")
    budget = (cents / 100.0) if cents else None
    meeting_ref = (
        row.get("meeting_id")
        or (row.get("meeting_date") and str(row["meeting_date"]))
        or ""
    )
    return compute_stable_decision_id(
        jurisdiction_id=row["jurisdiction_id"],
        meeting_ref=meeting_ref,
        item_ref=row.get("agenda_item"),
        title=row.get("title"),
        item_type=row.get("item_type") or "action",
        outcome=row.get("outcome"),
        budget_amount=budget,
    )


def group_by_stable_id(rows: list[dict]) -> dict[str, list[dict]]:
    """
    Group decisions by what their stable ID would be under the forward fix.

    Rows with no stable inputs are dropped — they can't be safely deduped
    without risking false merges of legitimately distinct decisions that
    happen to share a generic title.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    skipped = 0
    for row in rows:
        stable_id = compute_would_be_stable_id(row)
        if stable_id is None:
            skipped += 1
            continue
        groups[stable_id].append(row)
    if skipped:
        print(f"  (skipped {skipped} rows with no stable inputs — can't safely dedup)")
    return groups


def find_duplicate_groups(groups: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Return only groups with more than one row — the dupes."""
    return {k: v for k, v in groups.items() if len(v) > 1}


def report_dry_run(dupe_groups: dict[str, list[dict]]) -> None:
    """Print a summary of what would change without writing."""
    if not dupe_groups:
        print("No duplicate decisions found. Nothing to clean up.")
        return

    # Per-jurisdiction stats
    per_jurisdiction: dict[str, dict] = defaultdict(lambda: {"groups": 0, "extra_rows": 0, "examples": []})
    for stable_id, rows in dupe_groups.items():
        jid = rows[0]["jurisdiction_id"]
        stats = per_jurisdiction[jid]
        stats["groups"] += 1
        stats["extra_rows"] += len(rows) - 1  # -1 because we keep the earliest
        if len(stats["examples"]) < 3:
            stats["examples"].append({
                "title": rows[0]["title"],
                "agenda_item": rows[0].get("agenda_item"),
                "meeting_ref": rows[0].get("meeting_id") or str(rows[0].get("meeting_date") or ""),
                "duplicate_count": len(rows),
            })

    print("=" * 70)
    print("DRY RUN — DECISION DEDUP CLEANUP REPORT")
    print("=" * 70)
    print()

    total_extra = 0
    for jid in sorted(per_jurisdiction.keys()):
        stats = per_jurisdiction[jid]
        total_extra += stats["extra_rows"]
        print(f"  {jid}")
        print(f"    Duplicate groups: {stats['groups']}")
        print(f"    Rows that would be closed: {stats['extra_rows']}")
        print(f"    Example duplicates:")
        for ex in stats["examples"]:
            title = ex["title"] or "(no title)"
            if len(title) > 55:
                title = title[:52] + "..."
            agenda = ex.get("agenda_item") or "(no item)"
            print(f"      - \"{title}\" item={agenda!r} ({ex['duplicate_count']}x in {ex['meeting_ref'][:30]})")
        print()

    print("-" * 70)
    print(f"TOTAL: would close {total_extra} duplicate rows across {len(per_jurisdiction)} jurisdictions")
    print()
    print("Re-run with --apply to actually close these duplicates.")


def apply_cleanup(conn, dupe_groups: dict[str, list[dict]]) -> int:
    """For each duplicate group, close all rows except the earliest."""
    if not dupe_groups:
        print("No duplicates to clean up.")
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    closed_count = 0

    with conn.cursor() as cur:
        for stable_id, rows in dupe_groups.items():
            # Sort by extracted_at ascending — keep the first, close the rest
            sorted_rows = sorted(rows, key=lambda r: r["extracted_at"] or r["valid_from"])
            keeper = sorted_rows[0]
            to_close = sorted_rows[1:]

            for row in to_close:
                cur.execute(
                    """
                    UPDATE decisions
                    SET valid_to = %s
                    WHERE id = %s
                      AND jurisdiction_id = %s
                      AND valid_from = %s
                      AND valid_to IS NULL
                    """,
                    (now, row["id"], row["jurisdiction_id"], row["valid_from"]),
                )
                closed_count += cur.rowcount

    conn.commit()
    return closed_count


def main():
    parser = argparse.ArgumentParser(
        description="Clean up duplicate decisions in production Postgres",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the cleanup (default is dry-run)",
    )
    parser.add_argument(
        "--jurisdiction",
        type=str,
        default=None,
        help="Limit cleanup to a single jurisdiction (e.g. county-alameda)",
    )
    args = parser.parse_args()

    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)

    try:
        print(f"Fetching open decisions{' for ' + args.jurisdiction if args.jurisdiction else ''}...")
        rows = fetch_open_decisions(conn, args.jurisdiction)
        print(f"Found {len(rows)} open decision rows.")
        print()

        groups = group_by_stable_id(rows)
        dupe_groups = find_duplicate_groups(groups)

        if not args.apply:
            report_dry_run(dupe_groups)
            return

        print("APPLYING CLEANUP...")
        report_dry_run(dupe_groups)  # show what we're about to do
        print()
        closed = apply_cleanup(conn, dupe_groups)
        print(f"Closed {closed} duplicate rows. Cleanup complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

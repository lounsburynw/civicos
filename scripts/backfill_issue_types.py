#!/usr/bin/env python3
"""
Backfill issue_type for existing 311 issues using LLM classification.

Reads issues from PostgreSQL, classifies them with Claude Haiku using the
taxonomy from civicos.issues.classify, and updates the issue_type column.

Usage:
    python3 scripts/backfill_issue_types.py --dry-run
    python3 scripts/backfill_issue_types.py
    python3 scripts/backfill_issue_types.py --jurisdiction city-san-rafael
    python3 scripts/backfill_issue_types.py --limit 50  # test with small batch
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos" / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_env():
    """Load .env file manually."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def backfill_issue_types(
    jurisdiction_id: str,
    dry_run: bool = False,
    limit: int = 0,
    batch_size: int = 50,
):
    """
    Classify and update issue_type for all issues with unclassified types.
    """
    import psycopg2
    from civicos.issues.classify import classify_issue_types_batch, ISSUE_TYPE_TAXONOMY

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Fetch issues needing classification
    query = """
        SELECT id, external_id, title, description, issue_type
        FROM issues
        WHERE jurisdiction_id = %s
          AND valid_to IS NULL
          AND deleted_at IS NULL
          AND (issue_type IS NULL OR issue_type = '' OR issue_type = 'operational' OR issue_type = 'Unknown')
        ORDER BY created_at DESC
    """
    params: list = [jurisdiction_id]
    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()

    logger.info(f"Found {len(rows)} issues needing classification")
    if not rows:
        conn.close()
        return 0

    # Prepare batch input
    issues_for_classification = []
    row_lookup: dict = {}  # external_id -> row_id for UPDATE
    for row in rows:
        row_id, external_id, title, description, current_type = row
        issues_for_classification.append({
            "id": external_id,
            "title": title or "",
            "description": description or "",
        })
        row_lookup[str(external_id)] = row_id

    # Classify
    logger.info(f"Classifying {len(issues_for_classification)} issues with LLM...")
    classifications = classify_issue_types_batch(
        issues_for_classification,
        batch_size=batch_size,
    )

    # Summarize results
    type_counts: dict = {}
    for issue_type in classifications.values():
        type_counts[issue_type] = type_counts.get(issue_type, 0) + 1

    logger.info("Classification results:")
    for issue_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        desc = ISSUE_TYPE_TAXONOMY.get(issue_type, "")
        pct = (count / len(classifications)) * 100
        logger.info(f"  {issue_type:25s} {count:>5} ({pct:5.1f}%)  {desc}")

    if dry_run:
        logger.info("DRY RUN - no changes made")
        logger.info("\nSample classifications:")
        for issue in issues_for_classification[:10]:
            ext_id = str(issue["id"])
            classified = classifications.get(ext_id, "?")
            logger.info(f"  [{classified:20s}] {issue['title'][:70]}")
        conn.close()
        return 0

    # Update database
    logger.info("Updating issue_type in database...")
    updated = 0
    update_batch = []

    for ext_id, issue_type in classifications.items():
        row_id = row_lookup.get(ext_id)
        if row_id:
            update_batch.append((issue_type, row_id, jurisdiction_id))

    # Batch update in chunks
    chunk_size = 100
    for i in range(0, len(update_batch), chunk_size):
        chunk = update_batch[i : i + chunk_size]
        for issue_type, row_id, jid in chunk:
            cur.execute(
                """UPDATE issues
                SET issue_type = %s
                WHERE id = %s AND jurisdiction_id = %s
                  AND valid_to IS NULL AND deleted_at IS NULL""",
                (issue_type, row_id, jid),
            )
            updated += cur.rowcount

        conn.commit()
        logger.info(f"  Updated {min(i + chunk_size, len(update_batch))}/{len(update_batch)}")

    logger.info(f"Updated {updated} issues with classified issue_type")
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill issue_type using LLM classification")
    parser.add_argument("--jurisdiction", default="city-san-rafael")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating")
    parser.add_argument("--limit", type=int, default=0, help="Max issues to classify (0 = all)")
    parser.add_argument("--batch-size", type=int, default=50, help="Issues per LLM call")
    args = parser.parse_args()

    load_env()

    if not os.environ.get("DATABASE_URL"):
        logger.error("DATABASE_URL not set. Check .env file.")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set. Check .env file.")
        sys.exit(1)

    updated = backfill_issue_types(
        jurisdiction_id=args.jurisdiction,
        dry_run=args.dry_run,
        limit=args.limit,
        batch_size=args.batch_size,
    )

    if not args.dry_run:
        logger.info(f"Backfill complete: {updated} issues updated")


if __name__ == "__main__":
    main()

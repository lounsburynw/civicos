#!/usr/bin/env python3
"""
Migrate decision IDs to meeting-scoped ordinal format.

Old format: decision:{jurisdiction}:{date}:{item_ref}
New format: decision:{jurisdiction}:{meeting_id}:{ordinal}

Groups decisions by (jurisdiction_id, meeting_id), sorts deterministically,
and assigns ordinals 01, 02, 03... Updates both decisions and vector_embeddings.

Usage:
    # Dry run (default) — show what would change
    python scripts/migrate_decision_ids.py

    # Apply changes
    python scripts/migrate_decision_ids.py --apply

    # Specific jurisdiction
    python scripts/migrate_decision_ids.py --jurisdiction city-mill-valley
"""

import argparse
import os
import sys
from collections import defaultdict

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'civicos', 'src'))

from dotenv import load_dotenv
load_dotenv()

from civicos.storage.postgres_backend import PostgresBackend


def migrate_decision_ids(jurisdiction_id: str = None, apply: bool = False):
    """Migrate all decision IDs to meeting-scoped ordinal format."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return

    backend = PostgresBackend(db_url)
    conn = backend._get_connection()
    cursor = conn.cursor()

    # Fetch all active decisions with their meeting_id
    sql = """
        SELECT id, jurisdiction_id, meeting_id, meeting_date
        FROM decisions
        WHERE valid_to IS NULL
    """
    params = []
    if jurisdiction_id:
        sql += " AND jurisdiction_id = %s"
        params.append(jurisdiction_id)
    sql += " ORDER BY jurisdiction_id, meeting_id, meeting_date, id"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Group by (jurisdiction_id, meeting_id)
    groups = defaultdict(list)
    for old_id, jur, meeting_id, meeting_date in rows:
        if not meeting_id:
            print(f"  SKIP (no meeting_id): {old_id}")
            continue
        groups[(jur, meeting_id)].append((old_id, meeting_date))

    changes = []
    collisions = 0

    for (jur, meeting_id), decisions in sorted(groups.items()):
        # Sort deterministically: by meeting_date then by existing ID
        decisions.sort(key=lambda x: (str(x[1] or ''), x[0]))

        for ordinal, (old_id, meeting_date) in enumerate(decisions, start=1):
            new_id = f"decision:{jur}:{meeting_id}:{ordinal:02d}"
            if new_id != old_id:
                changes.append((old_id, new_id, jur))

    if not changes:
        print("No decision IDs need migration.")
        conn.close()
        return

    # Check for collisions (new IDs that already exist)
    new_ids = {new_id for _, new_id, _ in changes}
    old_ids = {old_id for old_id, _, _ in changes}
    # Only flag if a new_id matches an existing ID that isn't being migrated itself
    existing_ids = {row[0] for row in rows}
    blocking = new_ids & existing_ids - old_ids
    if blocking:
        print(f"ERROR: {len(blocking)} new IDs collide with existing IDs not in migration set:")
        for bid in sorted(blocking)[:10]:
            print(f"  {bid}")
        conn.close()
        return

    print(f"Found {len(changes)} decisions to migrate:\n")
    for old_id, new_id, jur in changes[:20]:
        print(f"  {old_id}")
        print(f"  → {new_id}")
        print()
    if len(changes) > 20:
        print(f"  ... and {len(changes) - 20} more\n")

    if not apply:
        print(f"Dry run: {len(changes)} changes. Use --apply to execute.")
        conn.close()
        return

    # Apply in two passes: first rename to temp IDs to avoid conflicts, then to final IDs
    print("Pass 1: Renaming to temporary IDs...")
    for old_id, new_id, jur in changes:
        temp_id = f"_migrating_{new_id}"
        cursor.execute(
            "UPDATE decisions SET id = %s WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL",
            (temp_id, old_id, jur),
        )
        cursor.execute(
            "UPDATE vector_embeddings SET id = %s WHERE id = %s AND jurisdiction_id = %s AND corpus_type = 'decisions'",
            (temp_id, old_id, jur),
        )

    print("Pass 2: Renaming to final IDs...")
    for old_id, new_id, jur in changes:
        temp_id = f"_migrating_{new_id}"
        cursor.execute(
            "UPDATE decisions SET id = %s WHERE id = %s AND jurisdiction_id = %s AND valid_to IS NULL",
            (new_id, temp_id, jur),
        )
        cursor.execute(
            "UPDATE vector_embeddings SET id = %s WHERE id = %s AND jurisdiction_id = %s AND corpus_type = 'decisions'",
            (new_id, temp_id, jur),
        )

    conn.commit()
    conn.close()
    print(f"\nMigrated {len(changes)} decision IDs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate decision IDs to meeting-scoped ordinal format")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--jurisdiction", type=str, help="Filter to specific jurisdiction")
    args = parser.parse_args()

    migrate_decision_ids(jurisdiction_id=args.jurisdiction, apply=args.apply)

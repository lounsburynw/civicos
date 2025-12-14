#!/usr/bin/env python3
"""
Backfill missing issue_type values for existing complaints.

Complaints filed before auto-detection was added have NULL issue_type,
which prevents them from appearing in related complaints matching.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from complaint_detector import ComplaintDetector
from complaint_storage import ComplaintStorage


def backfill_issue_types(dry_run=True):
    """Backfill missing issue_type values"""

    storage = ComplaintStorage()
    detector = ComplaintDetector()

    # Get all complaints with NULL issue_type
    import sqlite3
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, description, jurisdiction_id, issue_type
            FROM complaints
            WHERE issue_type IS NULL OR issue_type = ''
            ORDER BY created_at DESC
        """)

        null_complaints = [dict(row) for row in cursor.fetchall()]

    print(f"Found {len(null_complaints)} complaints with NULL issue_type")
    print()

    if len(null_complaints) == 0:
        print("✅ All complaints already have issue_type!")
        return

    # Auto-detect issue_type for each
    updates = []
    for complaint in null_complaints:
        try:
            user_context = {'jurisdiction_id': complaint['jurisdiction_id']}
            intent = detector.detect_complaint(complaint['description'], user_context)

            if intent and intent.issue_type:
                detected_type = intent.issue_type
            else:
                detected_type = 'other'

            updates.append({
                'id': complaint['id'],
                'description': complaint['description'][:60] + '...',
                'detected_type': detected_type
            })

            print(f"  {complaint['id'][:8]}... → {detected_type}")
            print(f"    \"{complaint['description'][:60]}...\"")

        except Exception as e:
            print(f"  ERROR for {complaint['id']}: {e}")
            updates.append({
                'id': complaint['id'],
                'description': complaint['description'][:60] + '...',
                'detected_type': 'other'
            })

    print()
    print(f"{'[DRY RUN] ' if dry_run else ''}Updating {len(updates)} complaints...")

    if not dry_run:
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            for update in updates:
                cursor.execute("""
                    UPDATE complaints
                    SET issue_type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (update['detected_type'], update['id']))
            conn.commit()

        print(f"✅ Updated {len(updates)} complaints!")
    else:
        print()
        print("Run with --apply to actually update the database")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Backfill missing issue_type values')
    parser.add_argument('--apply', action='store_true', help='Actually update the database (default is dry-run)')
    args = parser.parse_args()

    backfill_issue_types(dry_run=not args.apply)

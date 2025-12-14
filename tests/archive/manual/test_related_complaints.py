#!/usr/bin/env python3
"""
Test script to verify related complaints are being populated correctly.
"""

import sys
import sqlite3
from pathlib import Path

DB_PATH = Path("data/civic_participation.db")

def test_related_complaints():
    """Test related complaints logic"""

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the most recent housing complaint from demo_user
    complaint_id = "0a8a3a0b-5f64-4c8e-892a-fdcddbe4d8aa"

    cursor.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,))
    complaint = dict(cursor.fetchone())

    print("=" * 80)
    print(f"Testing Complaint: {complaint_id}")
    print(f"User: {complaint['user_id']}")
    print(f"Issue Type: {complaint['issue_type']}")
    print(f"Jurisdiction: {complaint['jurisdiction_id']}")
    print("=" * 80)
    print()

    # Find similar complaints
    cursor.execute("""
        SELECT * FROM complaints
        WHERE jurisdiction_id = ?
          AND issue_type = ?
          AND status IN ('open', 'matched')
          AND created_at >= datetime('now', '-30 days')
        ORDER BY created_at DESC
        LIMIT 20
    """, (complaint['jurisdiction_id'], complaint['issue_type']))

    similar = [dict(row) for row in cursor.fetchall()]

    print(f"Found {len(similar)} similar complaints (before filtering):")
    for s in similar:
        print(f"  - {s['id'][:8]}... user={s['user_id']} (same user: {s['user_id'] == complaint['user_id']})")
    print()

    # Filter out the current complaint and same-user complaints
    related = [
        s['id'] for s in similar
        if s['id'] != complaint['id'] and s['user_id'] != complaint['user_id']
    ]

    print(f"Related complaints (after filtering): {len(related)}")
    for r_id in related:
        # Get user_id for this related complaint
        cursor.execute("SELECT user_id, substr(description, 1, 50) as desc FROM complaints WHERE id = ?", (r_id,))
        r = cursor.fetchone()
        print(f"  ✓ {r_id[:8]}... user={r[0]} desc={r[1]}")
    print()

    if len(related) > 0:
        print("✅ SUCCESS: Related complaints should be showing in the UI!")
    else:
        print("❌ PROBLEM: No related complaints found after filtering")
        print("   This means all similar complaints are from the same user (demo_user)")

    conn.close()

if __name__ == "__main__":
    test_related_complaints()

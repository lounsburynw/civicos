#!/usr/bin/env python3
"""
Backfill AI-generated titles and summaries for existing issues.
Run this once after adding the ai_title and ai_summary columns.
"""

import sqlite3
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from issue_storage import generate_ai_title_and_summary

DB_PATH = Path(__file__).parent.parent / "data" / "civic_participation.db"

def backfill_ai_content():
    """Generate AI titles and summaries for all issues without them"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Find issues without AI content
        cursor.execute("""
            SELECT id, description, issue_type
            FROM issues
            WHERE ai_title IS NULL OR ai_summary IS NULL
        """)

        issues = cursor.fetchall()

        if not issues:
            print("✅ All issues already have AI content")
            return

        print(f"📝 Generating AI content for {len(issues)} issues...")

        for issue_id, description, issue_type in issues:
            try:
                # Generate AI content
                ai_title, ai_summary = generate_ai_title_and_summary(description, issue_type)

                # Update database
                cursor.execute("""
                    UPDATE issues
                    SET ai_title = ?, ai_summary = ?, ai_generated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (ai_title, ai_summary, issue_id))

                print(f"✅ {issue_id[:8]}: {ai_title[:50]}")

            except Exception as e:
                print(f"❌ {issue_id[:8]}: Error - {e}")

        conn.commit()
        print(f"\n✅ Backfill complete! Updated {len(issues)} issues")

if __name__ == "__main__":
    backfill_ai_content()

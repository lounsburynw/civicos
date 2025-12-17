#!/usr/bin/env python3
"""
Seed San Rafael data for Civic platform pilot deployment.

Loads initial data into civic_state.db:
- City state registration (jurisdiction config)
- Meetings from enhanced manifest (114 meetings)
- Issues from SeeClickFix (1,340 issues)

Usage:
    python scripts/seed_san_rafael.py              # Run full seed
    python scripts/seed_san_rafael.py --dry-run    # Show what would be seeded
    python scripts/seed_san_rafael.py --status     # Show current data state
    python scripts/seed_san_rafael.py --force      # Re-seed even if data exists
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PILOT_DIR = DATA_DIR / "pilot"

# Database path
DB_PATH = DATA_DIR / "civic_state.db"

# Data source files
MEETINGS_FILE = PILOT_DIR / "san_rafael_meetings_enhanced.json"
ISSUES_FILE = PILOT_DIR / "seeclickfix_sanrafael_fresh_20251210.json"
JURISDICTION_FILE = DATA_DIR / "jurisdiction_overrides" / "city-san-rafael.json"

# Canonical jurisdiction ID
JURISDICTION_ID = "city-san-rafael"


def load_json(filepath: Path) -> dict | list:
    """Load and parse a JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def get_db_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def show_status():
    """Display current data state in the database."""
    print(f"\n{'=' * 60}")
    print("San Rafael Seed Data Status")
    print(f"{'=' * 60}")
    print(f"\nDatabase: {DB_PATH}")
    print(f"Exists: {DB_PATH.exists()}")

    if not DB_PATH.exists():
        print("\n⚠️  Database does not exist. Run migrations first:")
        print("   python scripts/migrate.py")
        return

    conn = get_db_connection()

    # City states
    cursor = conn.execute(
        "SELECT jurisdiction_id, jurisdiction_name, as_of, data_sources "
        "FROM city_states WHERE jurisdiction_id LIKE '%san-rafael%'"
    )
    city_states = cursor.fetchall()
    print(f"\n📍 City States ({len(city_states)} San Rafael entries):")
    for row in city_states:
        print(f"   - {row['jurisdiction_id']}: {row['jurisdiction_name']} (as_of: {row['as_of'][:19] if row['as_of'] else 'None'})")

    # Meetings
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt, meeting_type FROM meetings "
        "WHERE jurisdiction_id = ? AND valid_to IS NULL "
        "GROUP BY meeting_type ORDER BY cnt DESC",
        (JURISDICTION_ID,)
    )
    meetings = cursor.fetchall()
    total_meetings = sum(row['cnt'] for row in meetings)
    print(f"\n📅 Meetings ({total_meetings} current records):")
    for row in meetings:
        print(f"   - {row['meeting_type'] or 'unknown'}: {row['cnt']}")

    # Issues
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt, status FROM issues "
        "WHERE jurisdiction_id = ? "
        "GROUP BY status ORDER BY cnt DESC",
        (JURISDICTION_ID,)
    )
    issues = cursor.fetchall()
    total_issues = sum(row['cnt'] for row in issues)
    print(f"\n🎯 Issues ({total_issues} records):")
    for row in issues:
        print(f"   - {row['status']}: {row['cnt']}")

    # Date ranges
    if total_meetings > 0:
        cursor = conn.execute(
            "SELECT MIN(meeting_datetime) as earliest, MAX(meeting_datetime) as latest "
            "FROM meetings WHERE jurisdiction_id = ? AND valid_to IS NULL",
            (JURISDICTION_ID,)
        )
        row = cursor.fetchone()
        if row['earliest']:
            print(f"\n📆 Meeting date range: {row['earliest'][:10]} to {row['latest'][:10]}")

    if total_issues > 0:
        cursor = conn.execute(
            "SELECT MIN(created_at) as earliest, MAX(created_at) as latest "
            "FROM issues WHERE jurisdiction_id = ?",
            (JURISDICTION_ID,)
        )
        row = cursor.fetchone()
        if row['earliest']:
            print(f"📆 Issue date range: {row['earliest'][:10]} to {row['latest'][:10]}")

    conn.close()

    # Source files
    print(f"\n📁 Source Files:")
    print(f"   - Meetings: {MEETINGS_FILE.name} ({MEETINGS_FILE.exists()})")
    print(f"   - Issues: {ISSUES_FILE.name} ({ISSUES_FILE.exists()})")
    print(f"   - Jurisdiction: {JURISDICTION_FILE.name} ({JURISDICTION_FILE.exists()})")


def seed_city_state(conn: sqlite3.Connection, dry_run: bool = False) -> tuple[int, list[str]]:
    """
    Seed the city_states table with San Rafael entry.

    Returns (count, messages).
    """
    messages = []

    # Load jurisdiction config for enrichment
    jurisdiction_data = {}
    if JURISDICTION_FILE.exists():
        jurisdiction_data = load_json(JURISDICTION_FILE)

    # Check if entry exists
    cursor = conn.execute(
        "SELECT jurisdiction_id FROM city_states WHERE jurisdiction_id = ?",
        (JURISDICTION_ID,)
    )
    exists = cursor.fetchone() is not None

    if exists:
        messages.append(f"City state {JURISDICTION_ID} already exists, updating...")
        if not dry_run:
            conn.execute(
                """
                UPDATE city_states SET
                    jurisdiction_name = ?,
                    as_of = ?,
                    data_sources = ?,
                    extraction_version = ?,
                    updated_at = ?
                WHERE jurisdiction_id = ?
                """,
                (
                    "San Rafael, CA",
                    datetime.now().isoformat(),
                    json.dumps(["proudcity", "seeclickfix", "youtube", "municode"]),
                    "pilot-2025-12",
                    datetime.now().isoformat(),
                    JURISDICTION_ID,
                )
            )
        return 1, messages

    # Insert new entry
    messages.append(f"Creating city state {JURISDICTION_ID}")
    if not dry_run:
        conn.execute(
            """
            INSERT INTO city_states (
                jurisdiction_id, jurisdiction_name, as_of,
                active_residents, pending_comments, coordination_threads,
                completeness_score, data_sources, extraction_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                JURISDICTION_ID,
                "San Rafael, CA",
                datetime.now().isoformat(),
                0,  # active_residents - to be updated as users onboard
                0,  # pending_comments
                0,  # coordination_threads
                0.0,  # completeness_score - to be calculated
                json.dumps(["proudcity", "seeclickfix", "youtube", "municode"]),
                "pilot-2025-12",
                datetime.now().isoformat(),
                datetime.now().isoformat(),
            )
        )

    return 1, messages


def seed_meetings(conn: sqlite3.Connection, dry_run: bool = False, force: bool = False) -> tuple[int, list[str]]:
    """
    Seed meetings from enhanced manifest.

    Returns (count, messages).
    """
    messages = []

    if not MEETINGS_FILE.exists():
        messages.append(f"⚠️  Meetings file not found: {MEETINGS_FILE}")
        return 0, messages

    data = load_json(MEETINGS_FILE)
    meetings_by_type = data.get("meetings", {})

    # Check existing count
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM meetings WHERE jurisdiction_id = ? AND valid_to IS NULL",
        (JURISDICTION_ID,)
    )
    existing_count = cursor.fetchone()['cnt']

    if existing_count > 10 and not force:
        messages.append(f"⚠️  {existing_count} meetings already exist. Use --force to re-seed.")
        return 0, messages

    # Flatten all meetings
    all_meetings = []
    for meeting_type, meetings in meetings_by_type.items():
        for meeting in meetings:
            meeting['_type'] = meeting_type
            all_meetings.append(meeting)

    messages.append(f"Processing {len(all_meetings)} meetings from {len(meetings_by_type)} types")

    inserted = 0
    skipped = 0

    for meeting in all_meetings:
        # Generate ID from slug or date
        meeting_id = meeting.get('meeting_slug', f"{meeting['_type']}-{meeting.get('date_parsed', 'unknown')}")

        # Parse date
        date_str = meeting.get('date_parsed', '')
        if date_str:
            # Add default time (7pm for evening meetings)
            meeting_datetime = f"{date_str}T19:00:00"
        else:
            meeting_datetime = datetime.now().isoformat()

        # Check if already exists
        cursor = conn.execute(
            "SELECT id FROM meetings WHERE id = ? AND valid_to IS NULL",
            (meeting_id,)
        )
        if cursor.fetchone() and not force:
            skipped += 1
            continue

        if not dry_run:
            # If forcing, mark old version as superseded
            if force:
                conn.execute(
                    "UPDATE meetings SET valid_to = ? WHERE id = ? AND valid_to IS NULL",
                    (datetime.now().isoformat(), meeting_id)
                )

            conn.execute(
                """
                INSERT INTO meetings (
                    id, jurisdiction_id, title, meeting_datetime, meeting_type,
                    status, agenda_url, minutes_url, video_url,
                    source_platform, source_url, valid_from, valid_to, full_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    meeting_id,
                    JURISDICTION_ID,
                    meeting.get('title', 'Untitled Meeting'),
                    meeting_datetime,
                    meeting.get('meeting_type', meeting['_type']),
                    'completed' if date_str and date_str < datetime.now().strftime('%Y-%m-%d') else 'upcoming',
                    meeting.get('agenda_packet_pdf_url') or meeting.get('agenda_url'),
                    meeting.get('minutes_pdf_url'),
                    None,  # video_url - not in this manifest
                    'proudcity',
                    meeting.get('meeting_url'),
                    datetime.now().isoformat(),
                    json.dumps(meeting),
                )
            )
        inserted += 1

    messages.append(f"Inserted {inserted} meetings, skipped {skipped} existing")
    return inserted, messages


def seed_issues(conn: sqlite3.Connection, dry_run: bool = False, force: bool = False) -> tuple[int, list[str]]:
    """
    Seed issues from SeeClickFix JSON.

    Returns (count, messages).
    """
    messages = []

    if not ISSUES_FILE.exists():
        messages.append(f"⚠️  Issues file not found: {ISSUES_FILE}")
        return 0, messages

    issues = load_json(ISSUES_FILE)
    messages.append(f"Processing {len(issues)} issues from SeeClickFix")

    # Check existing count
    cursor = conn.execute(
        "SELECT COUNT(*) as cnt FROM issues WHERE jurisdiction_id = ?",
        (JURISDICTION_ID,)
    )
    existing_count = cursor.fetchone()['cnt']

    if existing_count > 100 and not force:
        messages.append(f"⚠️  {existing_count} issues already exist. Use --force to re-seed.")
        return 0, messages

    inserted = 0
    updated = 0
    skipped = 0

    for issue in issues:
        issue_id = issue.get('id', f"scf-{issue.get('external_id', 'unknown')}")

        # Extract location data
        location = issue.get('location', {})

        # Check if exists
        cursor = conn.execute("SELECT id FROM issues WHERE id = ?", (issue_id,))
        exists = cursor.fetchone() is not None

        if exists and not force:
            skipped += 1
            continue

        if not dry_run:
            if exists and force:
                # Update existing
                conn.execute(
                    """
                    UPDATE issues SET
                        title = ?, description = ?, issue_type = ?,
                        address = ?, latitude = ?, longitude = ?,
                        status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        issue.get('title', 'Untitled Issue'),
                        issue.get('description', ''),
                        issue.get('issue_type', 'operational'),
                        location.get('address'),
                        location.get('lat'),
                        location.get('lng'),
                        issue.get('status', 'open'),
                        issue.get('updated_at') or datetime.now().isoformat(),
                        issue_id,
                    )
                )
                updated += 1
            else:
                # Insert new
                conn.execute(
                    """
                    INSERT INTO issues (
                        id, jurisdiction_id, source, source_id,
                        title, description, issue_type,
                        address, latitude, longitude,
                        status, created_at, updated_at, valid_from
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue_id,
                        JURISDICTION_ID,
                        'seeclickfix',
                        str(issue.get('external_id', '')),
                        issue.get('title', 'Untitled Issue'),
                        issue.get('description', ''),
                        issue.get('issue_type', 'operational'),
                        location.get('address'),
                        location.get('lat'),
                        location.get('lng'),
                        issue.get('status', 'open'),
                        issue.get('created_at') or datetime.now().isoformat(),
                        issue.get('updated_at') or datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    )
                )
                inserted += 1

    messages.append(f"Inserted {inserted}, updated {updated}, skipped {skipped}")
    return inserted + updated, messages


def generate_report(conn: sqlite3.Connection) -> dict:
    """Generate verification report after seeding."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "jurisdiction_id": JURISDICTION_ID,
        "tables": {}
    }

    # City states
    cursor = conn.execute(
        "SELECT * FROM city_states WHERE jurisdiction_id = ?",
        (JURISDICTION_ID,)
    )
    row = cursor.fetchone()
    if row:
        report["tables"]["city_states"] = {
            "count": 1,
            "jurisdiction_name": row['jurisdiction_name'],
            "data_sources": row['data_sources'],
        }

    # Meetings
    cursor = conn.execute(
        """
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
               COUNT(CASE WHEN status = 'upcoming' THEN 1 END) as upcoming,
               MIN(meeting_datetime) as earliest,
               MAX(meeting_datetime) as latest
        FROM meetings WHERE jurisdiction_id = ? AND valid_to IS NULL
        """,
        (JURISDICTION_ID,)
    )
    row = cursor.fetchone()
    report["tables"]["meetings"] = {
        "count": row['total'],
        "completed": row['completed'],
        "upcoming": row['upcoming'],
        "date_range": f"{row['earliest'][:10] if row['earliest'] else 'N/A'} to {row['latest'][:10] if row['latest'] else 'N/A'}",
    }

    # Issues
    cursor = conn.execute(
        """
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN status = 'open' THEN 1 END) as open,
               COUNT(CASE WHEN status = 'acknowledged' THEN 1 END) as acknowledged,
               COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed,
               MIN(created_at) as earliest,
               MAX(created_at) as latest
        FROM issues WHERE jurisdiction_id = ?
        """,
        (JURISDICTION_ID,)
    )
    row = cursor.fetchone()
    report["tables"]["issues"] = {
        "count": row['total'],
        "by_status": {
            "open": row['open'],
            "acknowledged": row['acknowledged'],
            "closed": row['closed'],
        },
        "date_range": f"{row['earliest'][:10] if row['earliest'] else 'N/A'} to {row['latest'][:10] if row['latest'] else 'N/A'}",
    }

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Seed San Rafael data for Civic platform pilot"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be seeded without making changes",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current data status",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-seed even if data already exists",
    )
    parser.add_argument(
        "--only",
        type=str,
        choices=["city_state", "meetings", "issues"],
        help="Seed only a specific data type",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return 0

    # Validate database exists
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        print("   Run migrations first: python scripts/migrate.py")
        return 1

    print(f"\n{'=' * 60}")
    print("Civic San Rafael Seed Data")
    print(f"{'=' * 60}")

    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)\n")
    if args.force:
        print("Mode: FORCE (will overwrite existing data)\n")

    conn = get_db_connection()
    total_count = 0
    all_messages = []

    try:
        # Seed city state
        if not args.only or args.only == "city_state":
            print("\n→ Seeding city_states...")
            count, messages = seed_city_state(conn, args.dry_run)
            total_count += count
            all_messages.extend(messages)
            for msg in messages:
                print(f"  {msg}")

        # Seed meetings
        if not args.only or args.only == "meetings":
            print("\n→ Seeding meetings...")
            count, messages = seed_meetings(conn, args.dry_run, args.force)
            total_count += count
            all_messages.extend(messages)
            for msg in messages:
                print(f"  {msg}")

        # Seed issues
        if not args.only or args.only == "issues":
            print("\n→ Seeding issues...")
            count, messages = seed_issues(conn, args.dry_run, args.force)
            total_count += count
            all_messages.extend(messages)
            for msg in messages:
                print(f"  {msg}")

        if not args.dry_run:
            conn.commit()

            # Generate report
            print(f"\n{'=' * 60}")
            print("Verification Report")
            print(f"{'=' * 60}")
            report = generate_report(conn)
            print(json.dumps(report, indent=2))

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        return 1

    finally:
        conn.close()

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"Dry run complete: {total_count} records would be affected")
    else:
        print(f"Seed complete: {total_count} records affected")

    return 0


if __name__ == "__main__":
    sys.exit(main())

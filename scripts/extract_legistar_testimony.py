#!/usr/bin/env python3
"""
Extract testimony data from Legistar cities and store in SQLite database

For cities using Legistar API, this script:
1. Reads high-stakes decisions from retrospective analysis
2. Maps decisions to Legistar EventItemIds
3. Fetches testimony data via Legistar API
4. Stores in testimony table for coalition discovery

Limitations:
- Only works for cities using Legistar platform
- San Rafael uses HTML-based system (requires minutes parsing)
- Legistar API provides speaker names but not positions/testimony text
"""

import sys
import os
import json
import argparse
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from legistar_client import LegistarClient, KNOWN_LEGISTAR_CLIENTS


def get_db_connection(db_path: str = "data/civic_participation.db") -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_decisions_into_db(
    conn: sqlite3.Connection,
    decisions_file: str,
    jurisdiction_id: str
) -> int:
    """
    Load decisions from JSON file into database

    Args:
        conn: Database connection
        decisions_file: Path to high_stakes_decisions.json
        jurisdiction_id: Jurisdiction identifier

    Returns:
        Number of decisions loaded
    """
    with open(decisions_file, 'r') as f:
        data = json.load(f)

    decisions = data['decisions']
    loaded_count = 0

    for decision in decisions:
        # Extract Legistar EventItemId if available
        legistar_event_item_id = None
        legistar_metadata = decision.get('_legistar_metadata', {})
        if legistar_metadata:
            legistar_event_item_id = legistar_metadata.get('EventItemId')

        # Convert arrays to JSON strings
        project_types_json = json.dumps(decision.get('project_types', []))
        keywords_json = json.dumps(decision.get('keywords_for_matching', []))

        # Insert or update decision
        cursor = conn.execute("""
            INSERT OR REPLACE INTO decisions (
                jurisdiction_id,
                item_ref,
                title,
                description,
                meeting_date,
                meeting_type,
                is_high_stakes,
                stakes_score,
                decision_type,
                budget_amount,
                budget_description,
                affected_population_estimate,
                geographic_scope,
                project_types,
                keywords_for_matching,
                agenda_url,
                minutes_url,
                meeting_title,
                meeting_url,
                legistar_event_item_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            jurisdiction_id,
            decision.get('item_ref'),
            decision['title'],
            decision.get('description'),
            decision['meeting_date'],
            decision.get('meeting_type'),
            decision.get('is_high_stakes'),
            decision.get('stakes_score'),
            decision.get('decision_type'),
            decision.get('budget_amount'),
            decision.get('budget_description'),
            decision.get('affected_population_estimate'),
            decision.get('geographic_scope'),
            project_types_json,
            keywords_json,
            decision.get('agenda_url'),
            decision.get('minutes_url'),
            decision.get('meeting_title'),
            decision.get('meeting_url'),
            legistar_event_item_id
        ])

        loaded_count += 1

    conn.commit()
    return loaded_count


def get_decision_id_by_meeting_and_item(
    conn: sqlite3.Connection,
    meeting_date: str,
    item_ref: str,
    jurisdiction_id: str
) -> Optional[int]:
    """
    Find decision_id in decisions table by meeting_date and item_ref

    Args:
        conn: Database connection
        meeting_date: ISO date (2024-10-06)
        item_ref: Item reference number (e.g., "4.1")
        jurisdiction_id: Jurisdiction identifier

    Returns:
        decision_id or None if not found
    """
    cursor = conn.execute("""
        SELECT id FROM decisions
        WHERE jurisdiction_id = ?
        AND DATE(meeting_date) = DATE(?)
        AND item_ref = ?
        LIMIT 1
    """, [jurisdiction_id, meeting_date, item_ref])

    row = cursor.fetchone()
    return row['id'] if row else None


def insert_testimony_record(
    conn: sqlite3.Connection,
    decision_id: int,
    speaker_data: Dict
) -> int:
    """
    Insert testimony record into database

    Args:
        conn: Database connection
        decision_id: FK to decisions table
        speaker_data: Normalized speaker data from Legistar

    Returns:
        testimony_id
    """
    cursor = conn.execute("""
        INSERT INTO testimony (
            decision_id,
            speaker_name,
            speaking_order,
            position,
            organization,
            testimony_text,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        decision_id,
        speaker_data['speaker_name'],
        speaker_data.get('speaking_order'),
        speaker_data.get('position'),  # Will be None from Legistar API
        speaker_data.get('organization'),  # Will be None from Legistar API
        speaker_data.get('testimony_text'),  # Will be None from Legistar API
        datetime.now().isoformat()
    ])

    conn.commit()
    return cursor.lastrowid


def extract_testimony_for_city(
    jurisdiction_id: str,
    decisions_file: str,
    db_path: str = "data/civic_participation.db",
    dry_run: bool = False
) -> Dict:
    """
    Extract testimony for all decisions from a Legistar city

    Args:
        jurisdiction_id: City identifier (e.g., "oakland")
        decisions_file: Path to high_stakes_decisions.json
        db_path: Path to SQLite database
        dry_run: If True, don't insert into database

    Returns:
        Stats dict
    """
    print("🗣️  LEGISTAR TESTIMONY EXTRACTION")
    print("=" * 70)
    print(f"Jurisdiction: {jurisdiction_id}")
    print(f"Decisions file: {decisions_file}")
    print(f"Database: {db_path}")

    if dry_run:
        print("🔍 DRY RUN MODE - No database changes")

    print()

    # Check if this is a Legistar city
    client_config = KNOWN_LEGISTAR_CLIENTS.get(jurisdiction_id.lower())
    if not client_config:
        print(f"❌ {jurisdiction_id} is not a known Legistar city")
        print(f"Available cities: {', '.join(KNOWN_LEGISTAR_CLIENTS.keys())}")
        return {"error": "not_legistar_city"}

    # Create Legistar client
    client_name = client_config['client_name']
    client = LegistarClient(client_name)

    # Connect to database
    conn = get_db_connection(db_path)

    # Load decisions from JSON into database first
    print("📥 Loading decisions into database...")
    with open(decisions_file, 'r') as f:
        data = json.load(f)

    decisions = data['decisions']
    loaded_count = load_decisions_into_db(conn, decisions_file, jurisdiction_id)
    print(f"✅ Loaded {loaded_count} decisions into database\n")

    # Stats
    stats = {
        'decisions_total': len(decisions),
        'decisions_with_legistar_metadata': 0,
        'decisions_matched_to_db': 0,
        'testimony_records_inserted': 0,
        'speakers_found': 0,
        'api_errors': 0
    }

    # Process each decision
    for i, decision in enumerate(decisions, 1):
        print(f"[{i}/{len(decisions)}] {decision['item_ref']}: {decision['title'][:60]}...")

        # Check if this decision has Legistar metadata
        legistar_metadata = decision.get('_legistar_metadata')
        if not legistar_metadata:
            print(f"   ⚠️  No Legistar metadata found")
            continue

        stats['decisions_with_legistar_metadata'] += 1

        # Get EventItemId from metadata
        event_item_id = legistar_metadata.get('EventItemId')
        if not event_item_id:
            print(f"   ⚠️  No EventItemId in metadata")
            continue

        # Find corresponding decision_id in database
        meeting_date = decision['meeting_date'].split('T')[0]
        item_ref = decision['item_ref']

        decision_id = get_decision_id_by_meeting_and_item(conn, meeting_date, item_ref, jurisdiction_id)
        if not decision_id:
            print(f"   ⚠️  Decision not found in database (date={meeting_date}, item={item_ref})")
            continue

        stats['decisions_matched_to_db'] += 1

        # Fetch testimony from Legistar API
        print(f"   🔍 Fetching testimony for EventItemId={event_item_id}")

        try:
            testimony = client.get_event_item_persons(event_item_id)

            if not testimony:
                print(f"   📭 No speakers found")
                continue

            print(f"   ✅ Found {len(testimony)} speakers")
            stats['speakers_found'] += len(testimony)

            # Insert each speaker into database
            if not dry_run:
                for speaker in testimony:
                    testimony_id = insert_testimony_record(conn, decision_id, speaker)
                    stats['testimony_records_inserted'] += 1
                    print(f"      - {speaker['speaker_name']} (order: {speaker['speaking_order']})")
            else:
                for speaker in testimony:
                    print(f"      - [DRY RUN] {speaker['speaker_name']} (order: {speaker['speaking_order']})")

        except Exception as e:
            print(f"   ❌ API Error: {e}")
            stats['api_errors'] += 1

        print()

    # Close database
    conn.close()

    # Print summary
    print("=" * 70)
    print("📊 EXTRACTION SUMMARY")
    print(f"   Total decisions: {stats['decisions_total']}")
    print(f"   Decisions with Legistar metadata: {stats['decisions_with_legistar_metadata']}")
    print(f"   Decisions matched to database: {stats['decisions_matched_to_db']}")
    print(f"   Speakers found: {stats['speakers_found']}")
    print(f"   Testimony records inserted: {stats['testimony_records_inserted']}")
    print(f"   API errors: {stats['api_errors']}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Extract testimony from Legistar cities and store in database'
    )
    parser.add_argument('jurisdiction', help='Jurisdiction ID (e.g., oakland, santa-rosa)')
    parser.add_argument('decisions_file', help='Path to high_stakes_decisions.json')
    parser.add_argument('--db', default='data/civic_participation.db',
                        help='Path to SQLite database')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without inserting into database')

    args = parser.parse_args()

    extract_testimony_for_city(
        jurisdiction_id=args.jurisdiction,
        decisions_file=args.decisions_file,
        db_path=args.db,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Coalition Discovery Queries for Testimony Data

Provides queries for discovering:
- Advocacy leaders (repeat speakers)
- Active organizations by topic
- Testimony for specific decisions
- Coordination gaps (complaints vs testimony)

Usage:
    python scripts/query_testimony.py leaders --min-appearances 3
    python scripts/query_testimony.py orgs --topic housing
    python scripts/query_testimony.py decision --id 123
    python scripts/query_testimony.py stats
"""

import sys
import os
import json
import argparse
import sqlite3
from typing import List, Dict, Tuple
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def get_db_connection(db_path: str = "data/civic_participation.db") -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_advocacy_leaders(
    db_path: str = "data/civic_participation.db",
    min_appearances: int = 3,
    jurisdiction_id: str = None
) -> List[Dict]:
    """
    Find repeat speakers (advocacy leaders)

    Args:
        db_path: Path to SQLite database
        min_appearances: Minimum number of testimony appearances
        jurisdiction_id: Optional filter by jurisdiction

    Returns:
        List of advocacy leaders with stats
    """
    conn = get_db_connection(db_path)

    query = """
        SELECT
            t.speaker_name,
            COUNT(DISTINCT t.decision_id) as appearances,
            COUNT(DISTINCT t.organization) as orgs,
            GROUP_CONCAT(DISTINCT t.organization) as org_list,
            COUNT(DISTINCT d.jurisdiction_id) as jurisdictions,
            GROUP_CONCAT(DISTINCT d.jurisdiction_id) as jurisdiction_list
        FROM testimony t
        JOIN decisions d ON t.decision_id = d.id
        WHERE t.speaker_name IS NOT NULL
    """

    params = []
    if jurisdiction_id:
        query += " AND d.jurisdiction_id = ?"
        params.append(jurisdiction_id)

    query += """
        GROUP BY t.speaker_name
        HAVING appearances >= ?
        ORDER BY appearances DESC
    """
    params.append(min_appearances)

    cursor = conn.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return results


def get_active_orgs_by_topic(
    topic: str,
    db_path: str = "data/civic_participation.db",
    jurisdiction_id: str = None
) -> List[Dict]:
    """
    Find organizations active on a specific topic

    Args:
        topic: Topic keyword (e.g., "housing", "environment")
        db_path: Path to SQLite database
        jurisdiction_id: Optional filter by jurisdiction

    Returns:
        List of organizations with stats
    """
    conn = get_db_connection(db_path)

    query = """
        SELECT
            t.organization,
            COUNT(DISTINCT t.decision_id) as appearances,
            COUNT(DISTINCT t.speaker_name) as unique_speakers,
            GROUP_CONCAT(DISTINCT d.title, '; ') as decision_titles
        FROM testimony t
        JOIN decisions d ON t.decision_id = d.id
        WHERE t.organization IS NOT NULL
        AND d.project_types LIKE ?
    """

    params = [f'%{topic}%']

    if jurisdiction_id:
        query += " AND d.jurisdiction_id = ?"
        params.append(jurisdiction_id)

    query += """
        GROUP BY t.organization
        ORDER BY appearances DESC
    """

    cursor = conn.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return results


def get_testimony_for_decision(
    decision_id: int,
    db_path: str = "data/civic_participation.db"
) -> Tuple[Dict, List[Dict]]:
    """
    Get all testimony for a specific decision

    Args:
        decision_id: Decision ID
        db_path: Path to SQLite database

    Returns:
        Tuple of (decision_info, testimony_list)
    """
    conn = get_db_connection(db_path)

    # Get decision info
    decision_cursor = conn.execute("""
        SELECT
            id,
            jurisdiction_id,
            title,
            meeting_date,
            decision_type,
            budget_amount,
            project_types
        FROM decisions
        WHERE id = ?
    """, [decision_id])

    decision = decision_cursor.fetchone()
    if not decision:
        conn.close()
        return None, []

    decision_info = dict(decision)

    # Get testimony
    testimony_cursor = conn.execute("""
        SELECT
            speaker_name,
            organization,
            speaking_order,
            position,
            testimony_text
        FROM testimony
        WHERE decision_id = ?
        ORDER BY speaking_order
    """, [decision_id])

    testimony_list = [dict(row) for row in testimony_cursor.fetchall()]
    conn.close()

    return decision_info, testimony_list


def get_testimony_stats(
    db_path: str = "data/civic_participation.db",
    jurisdiction_id: str = None
) -> Dict:
    """
    Get overall testimony statistics

    Args:
        db_path: Path to SQLite database
        jurisdiction_id: Optional filter by jurisdiction

    Returns:
        Statistics dict
    """
    conn = get_db_connection(db_path)

    query_filter = ""
    params = []
    if jurisdiction_id:
        query_filter = "WHERE d.jurisdiction_id = ?"
        params = [jurisdiction_id]

    # Total stats
    cursor = conn.execute(f"""
        SELECT
            COUNT(DISTINCT t.id) as total_testimony_records,
            COUNT(DISTINCT t.decision_id) as decisions_with_testimony,
            COUNT(DISTINCT t.speaker_name) as unique_speakers,
            COUNT(DISTINCT t.organization) as unique_organizations,
            COUNT(DISTINCT d.jurisdiction_id) as jurisdictions_covered
        FROM testimony t
        JOIN decisions d ON t.decision_id = d.id
        {query_filter}
    """, params)

    stats = dict(cursor.fetchone())

    # Decisions without testimony
    cursor = conn.execute(f"""
        SELECT COUNT(*) as decisions_without_testimony
        FROM decisions d
        LEFT JOIN testimony t ON d.id = t.decision_id
        WHERE t.id IS NULL
        {query_filter if query_filter else ''}
    """, params)

    stats['decisions_without_testimony'] = cursor.fetchone()['decisions_without_testimony']

    # Top speakers
    cursor = conn.execute(f"""
        SELECT speaker_name, COUNT(*) as count
        FROM testimony t
        JOIN decisions d ON t.decision_id = d.id
        {query_filter}
        WHERE speaker_name IS NOT NULL
        GROUP BY speaker_name
        ORDER BY count DESC
        LIMIT 5
    """, params)

    stats['top_speakers'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return stats


def get_coordination_gap_analysis(
    db_path: str = "data/civic_participation.db",
    jurisdiction_id: str = None
) -> Dict:
    """
    Analyze gap between SeeClickFix complaints and testimony

    Identifies decisions where there were operational complaints
    but no public testimony (coordination opportunity)

    Args:
        db_path: Path to SQLite database
        jurisdiction_id: Optional filter by jurisdiction

    Returns:
        Gap analysis dict
    """
    conn = get_db_connection(db_path)

    # This would require joining with issues/complaints table
    # For now, return placeholder structure

    query_filter = ""
    params = []
    if jurisdiction_id:
        query_filter = "WHERE d.jurisdiction_id = ?"
        params = [jurisdiction_id]

    # Find decisions with no testimony
    cursor = conn.execute(f"""
        SELECT
            d.id,
            d.jurisdiction_id,
            d.title,
            d.meeting_date,
            d.decision_type
        FROM decisions d
        LEFT JOIN testimony t ON d.id = t.decision_id
        {query_filter}
        GROUP BY d.id
        HAVING COUNT(t.id) = 0
        ORDER BY d.meeting_date DESC
        LIMIT 20
    """, params)

    decisions_without_testimony = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        'decisions_without_testimony': decisions_without_testimony,
        'count': len(decisions_without_testimony),
        'note': 'Future: Link with SeeClickFix complaints for full gap analysis'
    }


def print_advocacy_leaders(results: List[Dict]):
    """Pretty print advocacy leaders"""
    print("\n🎤 ADVOCACY LEADERS (Repeat Speakers)")
    print("=" * 70)

    if not results:
        print("No advocacy leaders found with specified criteria")
        return

    for i, leader in enumerate(results, 1):
        print(f"\n{i}. {leader['speaker_name']}")
        print(f"   Appearances: {leader['appearances']}")
        print(f"   Jurisdictions: {leader['jurisdiction_list']}")
        if leader['org_list']:
            print(f"   Organizations: {leader['org_list']}")


def print_active_orgs(results: List[Dict], topic: str):
    """Pretty print active organizations"""
    print(f"\n🏢 ORGANIZATIONS ACTIVE ON: {topic.upper()}")
    print("=" * 70)

    if not results:
        print(f"No organizations found testifying on {topic}")
        return

    for i, org in enumerate(results, 1):
        print(f"\n{i}. {org['organization']}")
        print(f"   Appearances: {org['appearances']}")
        print(f"   Unique speakers: {org['unique_speakers']}")


def print_decision_testimony(decision_info: Dict, testimony_list: List[Dict]):
    """Pretty print testimony for a decision"""
    print("\n📋 DECISION TESTIMONY")
    print("=" * 70)

    if not decision_info:
        print("Decision not found")
        return

    print(f"\nDecision: {decision_info['title']}")
    print(f"Date: {decision_info['meeting_date']}")
    print(f"Type: {decision_info['decision_type']}")
    if decision_info['budget_amount']:
        print(f"Budget: ${decision_info['budget_amount']:,}")

    print(f"\nTestimony: {len(testimony_list)} speakers")
    print("-" * 70)

    if not testimony_list:
        print("No testimony recorded")
        return

    for speaker in testimony_list:
        print(f"\n{speaker['speaking_order']}. {speaker['speaker_name']}")
        if speaker['organization']:
            print(f"   Organization: {speaker['organization']}")
        if speaker['position']:
            print(f"   Position: {speaker['position']}")


def print_stats(stats: Dict, jurisdiction_id: str = None):
    """Pretty print testimony statistics"""
    title = f"📊 TESTIMONY STATISTICS"
    if jurisdiction_id:
        title += f" - {jurisdiction_id.upper()}"

    print(f"\n{title}")
    print("=" * 70)

    print(f"\nCoverage:")
    print(f"  Decisions with testimony: {stats['decisions_with_testimony']}")
    print(f"  Decisions without testimony: {stats['decisions_without_testimony']}")
    print(f"  Total testimony records: {stats['total_testimony_records']}")

    if stats['decisions_with_testimony'] > 0:
        coverage_pct = stats['decisions_with_testimony'] / (stats['decisions_with_testimony'] + stats['decisions_without_testimony']) * 100
        print(f"  Coverage rate: {coverage_pct:.1f}%")

    print(f"\nParticipation:")
    print(f"  Unique speakers: {stats['unique_speakers']}")
    print(f"  Unique organizations: {stats['unique_organizations']}")
    print(f"  Jurisdictions: {stats['jurisdictions_covered']}")

    if stats['top_speakers']:
        print(f"\nTop 5 Speakers:")
        for speaker in stats['top_speakers']:
            print(f"  - {speaker['speaker_name']}: {speaker['count']} appearances")


def main():
    parser = argparse.ArgumentParser(
        description='Coalition discovery queries for testimony data'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Leaders command
    leaders_parser = subparsers.add_parser('leaders', help='Find advocacy leaders')
    leaders_parser.add_argument('--min-appearances', type=int, default=3,
                                help='Minimum testimony appearances (default: 3)')
    leaders_parser.add_argument('--jurisdiction', help='Filter by jurisdiction')

    # Orgs command
    orgs_parser = subparsers.add_parser('orgs', help='Find active organizations')
    orgs_parser.add_argument('--topic', required=True,
                             help='Topic keyword (e.g., housing, environment)')
    orgs_parser.add_argument('--jurisdiction', help='Filter by jurisdiction')

    # Decision command
    decision_parser = subparsers.add_parser('decision', help='Show testimony for decision')
    decision_parser.add_argument('--id', type=int, required=True,
                                 help='Decision ID')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show testimony statistics')
    stats_parser.add_argument('--jurisdiction', help='Filter by jurisdiction')

    # Gap command
    gap_parser = subparsers.add_parser('gap', help='Analyze coordination gaps')
    gap_parser.add_argument('--jurisdiction', help='Filter by jurisdiction')

    # Database path (common to all)
    parser.add_argument('--db', default='data/civic_participation.db',
                        help='Path to SQLite database')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Execute command
    if args.command == 'leaders':
        results = get_advocacy_leaders(
            db_path=args.db,
            min_appearances=args.min_appearances,
            jurisdiction_id=args.jurisdiction
        )
        print_advocacy_leaders(results)

    elif args.command == 'orgs':
        results = get_active_orgs_by_topic(
            topic=args.topic,
            db_path=args.db,
            jurisdiction_id=args.jurisdiction
        )
        print_active_orgs(results, args.topic)

    elif args.command == 'decision':
        decision_info, testimony_list = get_testimony_for_decision(
            decision_id=args.id,
            db_path=args.db
        )
        print_decision_testimony(decision_info, testimony_list)

    elif args.command == 'stats':
        stats = get_testimony_stats(
            db_path=args.db,
            jurisdiction_id=args.jurisdiction
        )
        print_stats(stats, args.jurisdiction)

    elif args.command == 'gap':
        results = get_coordination_gap_analysis(
            db_path=args.db,
            jurisdiction_id=args.jurisdiction
        )
        print(f"\n🔍 COORDINATION GAP ANALYSIS")
        print("=" * 70)
        print(f"\nDecisions without testimony: {results['count']}")
        print(f"Note: {results['note']}")


if __name__ == "__main__":
    main()

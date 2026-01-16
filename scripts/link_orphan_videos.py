#!/usr/bin/env python3
"""
Link orphan videos to meetings by parsing date and body type from video titles.

This is a one-time data quality script for the San Rafael pilot.
For videos that don't have meeting_url, we match by date + body type.

Usage:
    python3 scripts/link_orphan_videos.py --dry-run    # Preview matches
    python3 scripts/link_orphan_videos.py              # Execute linkage
    python3 scripts/link_orphan_videos.py --verbose    # Show all including unmatched
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'civic', 'src'))

from dotenv import load_dotenv

import psycopg2


# Body type mapping: keywords in video titles -> meeting_type values
BODY_TYPE_MAPPING = [
    # More specific patterns first (order matters)
    ('City Council Closed Session', 'city_council'),
    ('City Council', 'city_council'),
    ('Council Meeting', 'city_council'),
    ('Planning Commission', 'planning_commission'),
    ('Zoning Administrator', 'zoning_administrator'),
    ('Design Review', 'design_review_board'),
    ('Library', 'board_of_library_trustees'),
    ('Park', 'park_and_recreation_commission'),
    ('Recreation', 'park_and_recreation_commission'),
    ('Police Advisory', 'paac'),
    ('PAAC', 'paac'),
    ('Fire Commission', 'fire_commission'),
    ('Finance Subcommittee', 'council_subcommittees'),
    ('Finance', 'council_subcommittees'),
    ('Tax Oversight', 'tax_oversight'),
    ('Economic Development', 'council_subcommittees'),
    ('Sea Level Rise', 'council_subcommittees'),
    ('Homelessness', 'council_subcommittees'),
    ('Housing Subcommittee', 'council_subcommittees'),
    ('Bicycle', 'bicycle_pedestrian_advisory_committee'),
    ('Pedestrian', 'bicycle_pedestrian_advisory_committee'),
    ('ADA', 'ada_access_advisory_committee'),
    ('Pickleweed', 'pickleweed_advisory_committee'),
    ('Public Art', 'public_art_review_board'),
]

# Month name mapping for text date parsing
MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}


def parse_date_from_title(title: str) -> Optional[datetime]:
    """
    Extract meeting date from video title.

    Handles formats:
    - MM/DD/YYYY (e.g., "12/09/2025")
    - MM-DD-YYYY (e.g., "9-6-2023")
    - Month DD, YYYY (e.g., "Dec. 16, 2025", "October 14, 2025")
    """
    # Try MM/DD/YYYY format
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', title)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            pass

    # Try MM-DD-YYYY format (e.g., "Design Review Board 9-6-2023")
    match = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', title)
    if match:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(year, month, day)
        except ValueError:
            pass

    # Try Month DD, YYYY format (with optional period after month abbreviation)
    pattern = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z.]*[,\s]+(\d{1,2})[,\s]+(\d{4})'
    match = re.search(pattern, title, re.IGNORECASE)
    if match:
        month_str = match.group(1).lower()
        month = MONTH_MAP.get(month_str)
        day = int(match.group(2))
        year = int(match.group(3))
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    return None


def extract_body_type(title: str) -> Optional[str]:
    """
    Extract meeting body type from video title using keyword matching.
    Returns the meeting_type value to use for matching.
    """
    title_lower = title.lower()
    for keyword, meeting_type in BODY_TYPE_MAPPING:
        if keyword.lower() in title_lower:
            return meeting_type
    return None


def is_school_district_video(title: str) -> bool:
    """Check if video is from school district (not city meetings)."""
    school_keywords = ['SRCS', 'Board of Education', 'School District']
    return any(kw.lower() in title.lower() for kw in school_keywords)


def find_matching_meeting(
    cur, parsed_date: datetime, body_type: str, jurisdiction: str
) -> Optional[Tuple[str, str, datetime]]:
    """
    Find a meeting matching the date and body type.

    Returns (meeting_id, meeting_title, meeting_datetime) or None.
    """
    # Match by date (exact day) and body type
    cur.execute("""
        SELECT id, title, meeting_datetime
        FROM meetings
        WHERE valid_to IS NULL
          AND jurisdiction_id = %s
          AND DATE(meeting_datetime) = %s
          AND meeting_type = %s
        LIMIT 1
    """, (jurisdiction, parsed_date.date(), body_type))

    result = cur.fetchone()
    if result:
        return result

    # Try +/- 1 day (meetings sometimes scheduled day before/after)
    cur.execute("""
        SELECT id, title, meeting_datetime
        FROM meetings
        WHERE valid_to IS NULL
          AND jurisdiction_id = %s
          AND DATE(meeting_datetime) BETWEEN %s AND %s
          AND meeting_type = %s
        LIMIT 1
    """, (jurisdiction,
          (parsed_date - timedelta(days=1)).date(),
          (parsed_date + timedelta(days=1)).date(),
          body_type))

    return cur.fetchone()


def main():
    parser = argparse.ArgumentParser(description='Link orphan videos to meetings')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all videos including unmatched')
    parser.add_argument('--jurisdiction', default='city-san-rafael', help='Jurisdiction ID')
    args = parser.parse_args()

    # Load environment from project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(project_root, '.env'))

    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print('ERROR: DATABASE_URL not set in environment')
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # Get orphan videos for this jurisdiction
    cur.execute("""
        SELECT id, title, date
        FROM videos
        WHERE meeting_id IS NULL
          AND valid_to IS NULL
          AND jurisdiction_id = %s
        ORDER BY date DESC
    """, (args.jurisdiction,))
    orphan_videos = cur.fetchall()

    print(f'Found {len(orphan_videos)} orphan videos in {args.jurisdiction}')
    print('=' * 60)

    # Categorize results
    matched = []
    unmatched_school = []
    unmatched_no_date = []
    unmatched_no_body = []
    unmatched_no_meeting = []

    for video_id, title, published_date in orphan_videos:
        # Skip school district videos
        if is_school_district_video(title):
            unmatched_school.append((video_id, title, 'School district (not city)'))
            continue

        # Parse date from title
        parsed_date = parse_date_from_title(title)
        if not parsed_date:
            unmatched_no_date.append((video_id, title, 'Could not parse date'))
            continue

        # Extract body type
        body_type = extract_body_type(title)
        if not body_type:
            unmatched_no_body.append((video_id, title, f'Unknown body type (date: {parsed_date.date()})'))
            continue

        # Find matching meeting
        meeting = find_matching_meeting(cur, parsed_date, body_type, args.jurisdiction)
        if not meeting:
            unmatched_no_meeting.append((video_id, title, f'No meeting found ({body_type} on {parsed_date.date()})'))
            continue

        meeting_id, meeting_title, meeting_datetime = meeting
        matched.append((video_id, title, meeting_id, meeting_title, body_type))

    # Print results
    print(f'\nMATCHED: {len(matched)} videos')
    print('-' * 60)
    for video_id, video_title, meeting_id, meeting_title, body_type in matched[:20]:
        print(f'  Video: {video_title[:50]}...')
        print(f'  → Meeting: {meeting_title[:50]}')
        print()
    if len(matched) > 20:
        print(f'  ... and {len(matched) - 20} more')

    if args.verbose or unmatched_no_meeting:
        print(f'\nNO MEETING FOUND: {len(unmatched_no_meeting)} videos')
        print('-' * 60)
        for video_id, title, reason in unmatched_no_meeting[:10]:
            print(f'  {title[:60]}')
            print(f'    Reason: {reason}')
        if len(unmatched_no_meeting) > 10:
            print(f'  ... and {len(unmatched_no_meeting) - 10} more')

    if args.verbose:
        print(f'\nSCHOOL DISTRICT (not linkable): {len(unmatched_school)} videos')
        print(f'COULD NOT PARSE DATE: {len(unmatched_no_date)} videos')
        for video_id, title, reason in unmatched_no_date:
            print(f'  {title}')
        print(f'UNKNOWN BODY TYPE: {len(unmatched_no_body)} videos')
        for video_id, title, reason in unmatched_no_body:
            print(f'  {title}')

    # Summary
    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'  Total orphan videos:     {len(orphan_videos)}')
    print(f'  Matched to meetings:     {len(matched)}')
    print(f'  School district (skip):  {len(unmatched_school)}')
    print(f'  No date parsed:          {len(unmatched_no_date)}')
    print(f'  Unknown body type:       {len(unmatched_no_body)}')
    print(f'  No matching meeting:     {len(unmatched_no_meeting)}')

    # Execute updates if not dry run
    if not args.dry_run and matched:
        print('\n' + '=' * 60)
        print('EXECUTING UPDATES')
        print('=' * 60)

        updated = 0
        for video_id, video_title, meeting_id, meeting_title, body_type in matched:
            cur.execute("""
                UPDATE videos
                SET meeting_id = %s,
                    meeting_type = %s
                WHERE id = %s AND valid_to IS NULL
            """, (meeting_id, body_type, video_id))
            updated += cur.rowcount

        conn.commit()
        print(f'Updated {updated} video records')
    elif args.dry_run:
        print('\n[DRY RUN] No changes made. Run without --dry-run to apply.')

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()

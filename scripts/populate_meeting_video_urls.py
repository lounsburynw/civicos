#!/usr/bin/env python3
"""
Populate meetings.video_url by scraping embedded YouTube videos from meeting pages.

This script scrapes each meeting's source_url (ProudCity page) to extract the
embedded YouTube video ID, then updates meetings.video_url.

Once video_url is populated, we can link videos to meetings by matching
videos.youtube_url to meetings.video_url.

Usage:
    python3 scripts/populate_meeting_video_urls.py --dry-run    # Preview
    python3 scripts/populate_meeting_video_urls.py              # Execute
    python3 scripts/populate_meeting_video_urls.py --verbose    # Show all results
"""

import argparse
import os
import sys
import time

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'civic-extraction', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'civic', 'src'))

from dotenv import load_dotenv
import psycopg2

from civic_extraction.cli.youtube import extract_video_id


def main():
    parser = argparse.ArgumentParser(description='Populate meeting video URLs from source pages')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show all meetings including those without videos')
    parser.add_argument('--jurisdiction', default='city-san-rafael', help='Jurisdiction ID')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between requests (seconds)')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of meetings to process')
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

    # Get meetings with source_url but no video_url
    query = """
        SELECT id, title, source_url, meeting_datetime
        FROM meetings
        WHERE valid_to IS NULL
          AND jurisdiction_id = %s
          AND source_url IS NOT NULL
          AND video_url IS NULL
        ORDER BY meeting_datetime DESC
    """
    params = [args.jurisdiction]

    if args.limit:
        query = query.replace('ORDER BY', 'ORDER BY') + ' LIMIT %s'
        params.append(args.limit)

    cur.execute(query, params)
    meetings = cur.fetchall()

    print(f'Found {len(meetings)} meetings with source_url but no video_url')
    print('=' * 60)

    found_videos = []
    no_video = []
    errors = []

    for i, (meeting_id, title, source_url, _) in enumerate(meetings):
        print(f'[{i+1}/{len(meetings)}] {title[:50]}...', end=' ', flush=True)

        try:
            video_id = extract_video_id(source_url)

            if video_id:
                video_url = f'https://www.youtube.com/watch?v={video_id}'
                found_videos.append((meeting_id, title, video_url, source_url))
                print(f'Found: {video_id}')
            else:
                no_video.append((meeting_id, title, source_url))
                print('No video')

        except Exception as e:
            errors.append((meeting_id, title, source_url, str(e)))
            print(f'Error: {e}')

        # Rate limiting
        if args.delay and i < len(meetings) - 1:
            time.sleep(args.delay)

    # Summary
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)
    print(f'  Found video:    {len(found_videos)}')
    print(f'  No video:       {len(no_video)}')
    print(f'  Errors:         {len(errors)}')

    if args.verbose and no_video:
        print(f'\nMeetings without videos:')
        for meeting_id, title, source_url in no_video[:10]:
            print(f'  - {title}')
        if len(no_video) > 10:
            print(f'  ... and {len(no_video) - 10} more')

    if errors:
        print(f'\nErrors:')
        for meeting_id, title, source_url, error in errors:
            print(f'  - {title}: {error}')

    # Execute updates
    if not args.dry_run and found_videos:
        print('\n' + '=' * 60)
        print('UPDATING DATABASE')
        print('=' * 60)

        updated = 0
        for meeting_id, title, video_url, source_url in found_videos:
            cur.execute("""
                UPDATE meetings
                SET video_url = %s
                WHERE id = %s AND valid_to IS NULL
            """, (video_url, meeting_id))
            updated += cur.rowcount

        conn.commit()
        print(f'Updated {updated} meeting records with video_url')
    elif args.dry_run:
        print('\n[DRY RUN] No changes made. Run without --dry-run to apply.')

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()

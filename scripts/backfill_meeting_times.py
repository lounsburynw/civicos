#!/usr/bin/env python3
"""
Backfill meeting times from ProudCity source pages.

All 98 meetings in PostgreSQL have T00:00:00 because times were never
extracted during initial ingestion. This script scrapes each meeting's
source_url using ProudCityClient._extract_date_from_meeting_page() to
get the actual time, then updates meeting_datetime in PostgreSQL.

Usage:
    python3 scripts/backfill_meeting_times.py --dry-run    # Preview changes
    python3 scripts/backfill_meeting_times.py               # Apply changes
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civicos-extraction" / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_env():
    """Load .env file manually (avoids dotenv frame issues)."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def backfill_meeting_times(jurisdiction_id: str, dry_run: bool = False):
    """Scrape meeting times from ProudCity pages and update PostgreSQL."""
    import psycopg2
    from civicos_extraction.clients.proudcity import ProudCityClient

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Get all meetings with source_url and midnight time
    cur.execute("""
        SELECT id, meeting_datetime, source_url, title
        FROM meetings
        WHERE jurisdiction_id = %s
          AND deleted_at IS NULL
          AND (valid_to IS NULL)
          AND source_url IS NOT NULL
          AND (source_url LIKE '%%proudcity%%' OR source_url LIKE '%%cityofsanrafael%%')
        ORDER BY meeting_datetime
    """, (jurisdiction_id,))
    rows = cur.fetchall()
    logger.info(f"Found {len(rows)} meetings with source URLs")

    # Filter to meetings with midnight time (T00:00:00)
    midnight_meetings = []
    for row in rows:
        meeting_id, meeting_dt, source_url, title = row
        if meeting_dt is not None:
            dt = meeting_dt if isinstance(meeting_dt, datetime) else datetime.fromisoformat(str(meeting_dt))
            if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                midnight_meetings.append((meeting_id, dt, source_url, title))

    logger.info(f"  {len(midnight_meetings)} meetings have midnight time (need backfill)")

    if not midnight_meetings:
        logger.info("Nothing to backfill!")
        return

    # Create a ProudCity client for page scraping
    client = ProudCityClient(
        base_url="https://www.cityofsanrafael.org",
        jurisdiction_id=jurisdiction_id,
    )

    updated = 0
    skipped = 0
    failed = 0

    for meeting_id, meeting_dt, source_url, title in midnight_meetings:
        short_title = (title or "Untitled")[:60]
        logger.info(f"  Scraping: {short_title} ({meeting_dt.date()}) ...")

        try:
            _date_str, time_str = client._extract_date_from_meeting_page(
                source_url,
                fallback_date=meeting_dt.strftime('%Y-%m-%d'),
            )
        except Exception as e:
            logger.warning(f"    FAILED to scrape {source_url}: {e}")
            failed += 1
            time.sleep(1)
            continue

        if not time_str:
            logger.info(f"    No time found on page, skipping")
            skipped += 1
            time.sleep(1)
            continue

        # Parse time and combine with existing date
        hour, minute = map(int, time_str.split(':'))
        new_dt = meeting_dt.replace(hour=hour, minute=minute)

        if dry_run:
            logger.info(f"    [DRY RUN] Would update: {meeting_dt} -> {new_dt}")
        else:
            cur.execute("""
                UPDATE meetings
                SET meeting_datetime = %s
                WHERE id = %s AND jurisdiction_id = %s
            """, (new_dt, meeting_id, jurisdiction_id))
            logger.info(f"    Updated: {meeting_dt} -> {new_dt}")

        updated += 1
        time.sleep(1)  # Rate limit: 1 req/sec

    if not dry_run:
        conn.commit()

    conn.close()

    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(f"\n{prefix}Backfill complete:")
    logger.info(f"  Updated: {updated}")
    logger.info(f"  Skipped (no time on page): {skipped}")
    logger.info(f"  Failed (scrape error): {failed}")
    logger.info(f"  Total: {updated + skipped + failed}")


def main():
    parser = argparse.ArgumentParser(description="Backfill meeting times from ProudCity pages")
    parser.add_argument("--jurisdiction", default="city-san-rafael", help="Jurisdiction ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    load_env()

    if "DATABASE_URL" not in os.environ:
        logger.error("DATABASE_URL not set. Check .env file.")
        sys.exit(1)

    backfill_meeting_times(args.jurisdiction, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

"""
YouTube video discovery command for civic-extract CLI.

Extracts YouTube video IDs from meeting pages by scraping the source website.

Usage:
    civic-extract youtube --jurisdiction city-san-rafael
    civic-extract youtube --jurisdiction city-san-rafael --schedule
    civic-extract youtube --jurisdiction city-san-rafael --dry-run
    civic-extract youtube --jurisdiction city-san-rafael --cloud  # Store in Supabase
"""

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

from civicos_extraction.clients.proudcity import ProudCitySource

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class VideoResult:
    """Result of YouTube video extraction from a meeting page."""

    video_id: str
    meeting_url: str
    title: str
    date: str
    youtube_url: str


@dataclass
class YouTubeCheckpoint:
    """Checkpoint for YouTube discovery progress."""

    jurisdiction_id: str
    last_meeting_url: str
    items_processed: int
    items_found: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "YouTubeCheckpoint":
        return cls(**data)


def add_youtube_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the youtube subcommand to the parser."""
    parser = subparsers.add_parser(
        "youtube",
        help="Discover YouTube videos from meeting pages",
        description="Extract YouTube video IDs from meeting pages by scraping the source website",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--days-past",
        type=int,
        default=90,
        help="Days into past to search (default: 90)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=30,
        help="Days into future to search (default: 30)",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory for output files (default: data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show meetings that would be processed, don't fetch pages",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 7am) instead of once",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store results in cloud storage (requires DATABASE_URL)",
    )


def run_youtube(args: argparse.Namespace) -> int:
    """Run the youtube command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            args.days_past,
            args.days_ahead,
            args.output_dir,
            args.checkpoint_dir,
            args.timeout,
            cloud=args.cloud,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        results = run_youtube_discovery(
            args.jurisdiction,
            days_past=args.days_past,
            days_ahead=args.days_ahead,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            timeout=args.timeout,
            dry_run=args.dry_run,
            cloud=args.cloud,
        )

        if results is None and not args.dry_run:
            return 1

        return 0


def extract_video_id(meeting_url: str, timeout: int = 10) -> Optional[str]:
    """
    Extract YouTube video ID from a meeting page.

    Args:
        meeting_url: URL of the meeting page
        timeout: Request timeout in seconds

    Returns:
        YouTube video ID or None if not found
    """
    try:
        response = requests.get(meeting_url, timeout=timeout)
        response.raise_for_status()

        html = response.text

        # Method 1: Look for videoId in JavaScript
        match = re.search(r"videoId:\s*['\"]([^'\"]+)['\"]", html)
        if match:
            return match.group(1)

        # Method 2: Look for YouTube embed URL
        match = re.search(r"youtube\.com/embed/([^\"?]+)", html)
        if match:
            return match.group(1)

        # Method 3: Look for YouTube watch URL
        match = re.search(r"youtube\.com/watch\?v=([^\"&]+)", html)
        if match:
            return match.group(1)

        # Method 4: Look for youtu.be short URL
        match = re.search(r"youtu\.be/([^\"?]+)", html)
        if match:
            return match.group(1)

        return None

    except requests.RequestException as e:
        logger.warning(f"Error fetching {meeting_url}: {e}")
        return None


def load_meetings_from_source(
    jurisdiction_id: str, days_past: int, days_ahead: int
) -> List[dict]:
    """
    Load meetings directly from the source (e.g., ProudCity website).

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        days_past: Days into past to search
        days_ahead: Days into future to search

    Returns:
        List of meetings with source_url, title, and datetime
    """
    try:
        source = ProudCitySource.from_jurisdiction(jurisdiction_id)
        logger.info(f"Loaded source: {source.source_id}")
    except Exception as e:
        logger.error(f"Failed to load source config: {e}")
        return []

    # Validate source
    logger.info("Validating source configuration...")
    validation = source.validate()
    if not validation.is_valid:
        logger.error(f"Validation failed: {validation.errors}")
        return []

    if validation.warnings:
        for warning in validation.warnings:
            logger.warning(warning)

    logger.info(f"Validation passed in {validation.check_duration_ms:.0f}ms")

    # Get meetings from source
    logger.info(f"Fetching meetings ({days_past} days past to {days_ahead} days ahead)...")
    try:
        meetings = source.get_meetings(days_ahead=days_ahead, days_past=days_past)
    except Exception as e:
        logger.error(f"Failed to fetch meetings: {e}")
        return []

    # Convert to simple dicts with the fields we need
    result = []
    seen_urls = set()
    for meeting in meetings:
        source_url = meeting.source_url
        if source_url and source_url not in seen_urls:
            result.append({
                "source_url": source_url,
                "title": meeting.title,
                "datetime": meeting.meeting_datetime.isoformat() if meeting.meeting_datetime else "",
            })
            seen_urls.add(source_url)

    logger.info(f"Found {len(result)} unique meetings with source URLs")
    return result


def checkpoint_path_for_youtube(
    jurisdiction_id: str, checkpoint_dir: str
) -> Path:
    """Get checkpoint file path for YouTube discovery."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"youtube_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: YouTubeCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[YouTubeCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return YouTubeCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def run_youtube_discovery(
    jurisdiction_id: str,
    days_past: int = 90,
    days_ahead: int = 30,
    output_dir: str = "data",
    checkpoint_dir: str = "data/checkpoints",
    timeout: int = 10,
    dry_run: bool = False,
    cloud: bool = False,
) -> Optional[List[VideoResult]]:
    """
    Run YouTube video discovery for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        days_past: Days into past to search
        days_ahead: Days into future to search
        output_dir: Directory for output files
        checkpoint_dir: Directory for checkpoint files
        timeout: Request timeout in seconds
        dry_run: If True, validate only - don't fetch pages
        cloud: If True, store results in cloud storage (requires DATABASE_URL)

    Returns:
        List of VideoResult if successful, None if failed
    """
    logger.info(f"Starting YouTube discovery for {jurisdiction_id}")

    # Load meetings from source
    meetings = load_meetings_from_source(jurisdiction_id, days_past, days_ahead)
    if not meetings:
        logger.error("No meetings found to process")
        return None

    logger.info(f"Found {len(meetings)} unique meetings")

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_youtube(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    start_index = 0

    if resume_from:
        logger.info(f"Found checkpoint: {resume_from.items_processed} items processed")
        # Find the index to resume from
        for i, meeting in enumerate(meetings):
            source_url = meeting.get("source_url")
            if source_url == resume_from.last_meeting_url:
                start_index = i + 1
                break
        if start_index > 0:
            logger.info(f"Resuming from meeting {start_index}")

    if dry_run:
        logger.info("Dry-run mode - showing meetings to process:")
        for i, meeting in enumerate(meetings[start_index:], start=start_index + 1):
            source_url = meeting.get("source_url")
            title = meeting.get("title", "Unknown")
            when = meeting.get("datetime", "Unknown")
            logger.info(f"  [{i}/{len(meetings)}] {title} ({when})")
            logger.info(f"    URL: {source_url}")
        logger.info(f"Would process {len(meetings) - start_index} meetings")
        return None

    # Load existing results to merge with
    output_path = Path(output_dir)
    output_file = output_path / f"{jurisdiction_id.replace('-', '_')}_videos.json"
    existing_results = []
    existing_video_ids = set()

    if output_file.exists():
        try:
            with open(output_file) as f:
                existing_results = json.load(f)
            existing_video_ids = {r["video_id"] for r in existing_results}
            logger.info(f"Loaded {len(existing_results)} existing video results")
        except Exception as e:
            logger.warning(f"Error loading existing results: {e}")

    # Process meetings
    results = []
    items_processed = start_index
    items_found = len(existing_video_ids)

    for i, meeting in enumerate(meetings[start_index:], start=start_index + 1):
        source_url = meeting.get("source_url")
        if not source_url:
            continue

        title = meeting.get("title", "Unknown")
        when = meeting.get("datetime", "Unknown")

        logger.info(f"[{i}/{len(meetings)}] Checking: {title}")

        video_id = extract_video_id(source_url, timeout=timeout)

        if video_id:
            if video_id not in existing_video_ids:
                logger.info(f"  ✓ New video: {video_id}")
                result = VideoResult(
                    video_id=video_id,
                    meeting_url=source_url,
                    title=title,
                    date=when,
                    youtube_url=f"https://www.youtube.com/watch?v={video_id}",
                )
                results.append(result)
                existing_video_ids.add(video_id)
                items_found += 1
            else:
                logger.debug(f"  - Skipping (already have): {video_id}")
        else:
            logger.debug(f"  - No video found")

        items_processed = i

        # Save checkpoint every 10 meetings
        if i % 10 == 0:
            checkpoint = YouTubeCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_meeting_url=source_url,
                items_processed=items_processed,
                items_found=items_found,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Save final results
    if results:
        all_results = existing_results + [asdict(r) for r in results]

        # Try cloud storage first if enabled
        cloud_success = False
        if cloud or os.environ.get("DATABASE_URL"):
            try:
                from civicos.storage import get_storage_backend
                backend = get_storage_backend()
                if backend.backend_type == "postgres":
                    # Store all videos (upsert semantics handles duplicates)
                    count = backend.store_videos(jurisdiction_id, all_results)
                    logger.info(f"Stored {count} videos in cloud storage ({backend.backend_type})")
                    cloud_success = True
                else:
                    logger.info(f"Cloud storage not postgres ({backend.backend_type}), using JSON fallback")
            except ImportError:
                logger.warning("civic.storage not available, using JSON fallback")
            except Exception as e:
                logger.warning(f"Cloud storage failed: {e}, using JSON fallback")

        # Always save local JSON as backup/cache (unless --cloud only mode in future)
        output_path.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(all_results, f, indent=2)
        logger.info(f"Saved {len(all_results)} total videos to {output_file}")

        # Also create a URLs text file
        urls_file = output_path / f"{jurisdiction_id.replace('-', '_')}_youtube_urls.txt"
        with open(urls_file, "w") as f:
            for r in all_results:
                f.write(f"{r['youtube_url']}\n")
        logger.info(f"Saved YouTube URLs to {urls_file}")

    # Final checkpoint
    if meetings:
        last_url = meetings[-1].get("source_url")
        checkpoint = YouTubeCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_meeting_url=last_url or "",
            items_processed=items_processed,
            items_found=items_found,
            timestamp=datetime.now().isoformat(),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Summary
    logger.info("=" * 50)
    logger.info(f"YouTube Discovery Complete for {jurisdiction_id}")
    logger.info(f"Meetings processed: {items_processed}")
    logger.info(f"New videos found: {len(results)}")
    logger.info(f"Total videos: {items_found}")
    logger.info("=" * 50)

    return results


def run_scheduled(
    jurisdiction_id: str,
    days_past: int,
    days_ahead: int,
    output_dir: str,
    checkpoint_dir: str,
    timeout: int,
    cloud: bool = False,
) -> None:
    """
    Run YouTube discovery on a schedule.

    Uses the schedule library to run daily at 7am (after discover at 6am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting YouTube scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 07:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_youtube_discovery(
            jurisdiction_id,
            days_past=days_past,
            days_ahead=days_ahead,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
            timeout=timeout,
            cloud=cloud,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 7am daily (after discover at 6am)
    schedule.every().day.at("07:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial YouTube discovery...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

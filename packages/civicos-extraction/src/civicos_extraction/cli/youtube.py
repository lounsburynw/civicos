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
    parser.add_argument(
        "--channel",
        action="store_true",
        help="Discover videos from YouTube channel/playlist (uses yt-dlp, matches by date)",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill video_url on meetings from linked videos in the videos table",
    )


def run_youtube(args: argparse.Namespace) -> int:
    """Run the youtube command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.backfill:
        return run_backfill_video_urls(args.jurisdiction)

    if args.channel:
        return run_channel_discovery(
            args.jurisdiction,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
        )

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


def _parse_date_from_title(title: str) -> Optional[str]:
    """Extract a date from a video title like 'Town Council March 4, 2026'.

    Returns ISO date string (YYYY-MM-DD) or None.
    """
    from dateutil import parser as dateparser

    match = re.search(r"(\w+ \d{1,2},? \d{4})$", title)
    if not match:
        return None
    try:
        dt = dateparser.parse(match.group(1))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _get_youtube_source(jurisdiction_id: str) -> Optional[dict]:
    """Load YouTube channel/playlist config from jurisdiction YAML."""
    try:
        import yaml
        from civicos_config import paths

        yaml_path = paths.JURISDICTIONS_DIR / f"{jurisdiction_id}.yaml"
        if not yaml_path.exists():
            logger.error(f"YAML not found: {yaml_path}")
            return None

        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        transcripts = config.get("data_sources", {}).get("transcripts") or {}
        channel_id = transcripts.get("channel_id")
        playlist_id = transcripts.get("playlist_id")
        if not channel_id and not playlist_id:
            return None

        return {
            "channel_id": channel_id,
            "playlist_id": playlist_id,
            "channel_title": transcripts.get("channel_title"),
        }
    except ImportError:
        logger.error("civicos_config not available")
        return None


def discover_from_channel(
    jurisdiction_id: str,
    dry_run: bool = False,
) -> List[dict]:
    """Discover YouTube videos from a channel or playlist using yt-dlp.

    Reads channel_id/playlist_id from jurisdiction YAML config,
    lists all videos via yt-dlp, and returns video metadata.

    Args:
        jurisdiction_id: Target jurisdiction
        dry_run: If True, just list videos without storing

    Returns:
        List of video dicts with video_id, title, youtube_url
    """
    import subprocess

    source = _get_youtube_source(jurisdiction_id)
    if not source:
        logger.error(f"No YouTube channel/playlist configured for {jurisdiction_id}")
        return []

    # Prefer playlist over channel (more targeted)
    if source["playlist_id"]:
        url = f"https://www.youtube.com/playlist?list={source['playlist_id']}"
        logger.info(f"Discovering from playlist: {source['playlist_id']}")
    else:
        url = f"https://www.youtube.com/channel/{source['channel_id']}/videos"
        logger.info(f"Discovering from channel: {source['channel_id']}")

    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "%(id)s|%(title)s", url],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error(f"yt-dlp failed: {result.stderr[:200]}")
            return []
    except FileNotFoundError:
        logger.error("yt-dlp not installed")
        return []
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp timed out")
        return []

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            videos.append({
                "video_id": parts[0],
                "title": parts[1],
                "youtube_url": f"https://www.youtube.com/watch?v={parts[0]}",
            })

    logger.info(f"Found {len(videos)} videos on YouTube")
    return videos


def match_videos_to_meetings(
    jurisdiction_id: str,
    videos: List[dict],
) -> List[dict]:
    """Match YouTube videos to meetings by date.

    For each video, parses the date from the title and looks up
    meetings on that date. Returns video dicts enriched with
    meeting_id for matched videos.

    Args:
        jurisdiction_id: Target jurisdiction
        videos: List of video dicts from discover_from_channel()

    Returns:
        List of matched video dicts with meeting_id set
    """
    from civicos.storage import get_storage_backend

    backend = get_storage_backend()
    db_meetings = backend.get_meetings(jurisdiction_id)

    # Build date -> meetings lookup
    date_meetings: dict = {}
    for m in db_meetings:
        dt = m.get("meeting_datetime")
        if not dt:
            continue
        if hasattr(dt, "strftime"):
            date_key = dt.strftime("%Y-%m-%d")
        else:
            date_key = str(dt)[:10]
        if date_key not in date_meetings:
            date_meetings[date_key] = []
        date_meetings[date_key].append(m)

    # Get already-stored video IDs
    try:
        stored_videos = backend.get_videos(jurisdiction_id)
        stored_ids = {v.get("id") for v in stored_videos}
    except Exception:
        stored_ids = set()

    matched = []
    already_stored = 0
    no_date = 0
    no_meeting = 0

    for v in videos:
        if v["video_id"] in stored_ids:
            already_stored += 1
            continue

        date_key = _parse_date_from_title(v["title"])
        if not date_key:
            no_date += 1
            continue

        if date_key not in date_meetings:
            no_meeting += 1
            continue

        meeting = date_meetings[date_key][0]
        matched.append({
            "video_id": v["video_id"],
            "meeting_url": meeting.get("source_url"),
            "meeting_id": meeting.get("id"),
            "title": v["title"],
            "date": f"{date_key}T00:00:00",
            "youtube_url": v["youtube_url"],
        })

    logger.info(
        f"Matched: {len(matched)} new, "
        f"{already_stored} already stored, "
        f"{no_date} no date in title, "
        f"{no_meeting} no matching meeting"
    )
    return matched


def backfill_video_urls(jurisdiction_id: str) -> int:
    """Backfill video_url on meetings from linked videos.

    Reads the videos table for a jurisdiction, finds videos with
    meeting_id set, and updates the meeting's video_url field.
    Prefers regular meetings over special/closed sessions when
    multiple videos exist for the same date.

    Returns:
        Number of meetings updated
    """
    from collections import defaultdict
    from civicos.storage import get_storage_backend

    backend = get_storage_backend()

    # Get videos with meeting linkage
    all_videos = backend.get_videos(jurisdiction_id)
    linked = [v for v in all_videos if v.get("meeting_id")]

    if not linked:
        logger.info(f"No linked videos found for {jurisdiction_id}")
        return 0

    # Group by meeting_id, pick best video per meeting
    by_meeting: dict = defaultdict(list)
    for v in linked:
        by_meeting[v["meeting_id"]].append(v)

    updated = 0
    for meeting_id, vids in by_meeting.items():
        # Prefer regular/plain over special/closed
        best = vids[0]
        for v in vids:
            title = (v.get("title") or "").lower()
            if "regular" in title:
                best = v
                break
            if "special" not in title and "closed" not in title:
                best = v

        youtube_url = best.get("youtube_url")
        if not youtube_url:
            continue

        try:
            result = backend.update_meeting(
                jurisdiction_id, meeting_id, {"video_url": youtube_url}
            )
            if result:
                updated += 1
                logger.debug(f"Updated {meeting_id} -> {youtube_url}")
        except Exception as e:
            logger.warning(f"Failed to update {meeting_id}: {e}")

    logger.info(f"Backfilled video_url on {updated}/{len(by_meeting)} meetings")
    return updated


def run_channel_discovery(
    jurisdiction_id: str,
    dry_run: bool = False,
    output_dir: str = "data",
) -> int:
    """Run YouTube channel/playlist discovery and store results.

    Uses yt-dlp to list videos, matches to meetings by date,
    stores in DB, and backfills video_url on meetings.

    Args:
        jurisdiction_id: Target jurisdiction
        dry_run: If True, show matches without storing
        output_dir: Directory for JSON output

    Returns:
        0 on success, 1 on failure
    """
    videos = discover_from_channel(jurisdiction_id, dry_run=dry_run)
    if not videos:
        return 1

    matched = match_videos_to_meetings(jurisdiction_id, videos)

    if dry_run:
        logger.info("Dry run - would store these matches:")
        for m in matched[:20]:
            logger.info(f"  {m['date'][:10]} | {m['title'][:50]} -> {m['meeting_id'][-40:]}")
        if len(matched) > 20:
            logger.info(f"  ... and {len(matched) - 20} more")
        return 0

    if matched:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        count = backend.store_videos(jurisdiction_id, matched)
        logger.info(f"Stored {count} videos in database")

        # Save JSON backup
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_file = output_path / f"{jurisdiction_id.replace('-', '_')}_videos.json"

        # Merge with existing
        existing = []
        if json_file.exists():
            try:
                with open(json_file) as f:
                    existing = json.load(f)
            except Exception:
                pass

        existing_ids = {v.get("video_id") for v in existing}
        new_entries = [m for m in matched if m["video_id"] not in existing_ids]
        all_entries = existing + new_entries

        with open(json_file, "w") as f:
            json.dump(all_entries, f, indent=2)
        logger.info(f"Saved {len(all_entries)} videos to {json_file}")

    # Backfill video_url on meetings
    updated = backfill_video_urls(jurisdiction_id)

    logger.info("=" * 50)
    logger.info(f"Channel Discovery Complete for {jurisdiction_id}")
    logger.info(f"Videos found: {len(videos)}")
    logger.info(f"New matches: {len(matched)}")
    logger.info(f"Meetings updated: {updated}")
    logger.info("=" * 50)

    return 0


def run_backfill_video_urls(jurisdiction_id: str) -> int:
    """CLI entry point for --backfill mode."""
    updated = backfill_video_urls(jurisdiction_id)
    if updated > 0:
        logger.info(f"Done: {updated} meetings updated")
    else:
        logger.info("No meetings needed updating")
    return 0


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

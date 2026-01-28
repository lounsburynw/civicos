"""
Audio download command for civic-extract CLI.

Downloads audio from YouTube videos discovered by the youtube command.

Usage:
    civic-extract audio --jurisdiction city-san-rafael
    civic-extract audio --jurisdiction city-san-rafael --schedule
    civic-extract audio --jurisdiction city-san-rafael --dry-run
    civic-extract audio --jurisdiction city-san-rafael --limit 5
    civic-extract audio --jurisdiction city-san-rafael --cloud  # Store in R2
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Result of an audio download."""

    video_id: str
    status: str  # "success", "skipped", "error"
    file_path: Optional[str] = None
    file_size_mb: Optional[float] = None
    duration_minutes: Optional[int] = None
    error: Optional[str] = None
    r2_key: Optional[str] = None  # Cloud storage key if uploaded to R2


@dataclass
class AudioCheckpoint:
    """Checkpoint for audio download progress."""

    jurisdiction_id: str
    last_video_id: str
    items_processed: int
    items_downloaded: int
    items_skipped: int
    items_failed: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AudioCheckpoint":
        return cls(**data)


def add_audio_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the audio subcommand to the parser."""
    parser = subparsers.add_parser(
        "audio",
        help="Download audio from YouTube videos",
        description="Download audio from YouTube videos discovered by the youtube command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--input-dir",
        default="data",
        help="Directory containing videos JSON (default: data)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/youtube_audio",
        help="Directory for audio files (default: data/youtube_audio)",
    )
    parser.add_argument(
        "--cookies",
        default="~/Downloads/www.youtube.com_cookies.txt",
        help="Path to YouTube cookies file (default: ~/Downloads/www.youtube.com_cookies.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show videos that would be downloaded, don't actually download",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 8am) instead of once",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of videos to download (0 = no limit, default: 0)",
    )
    parser.add_argument(
        "--quality",
        default="128",
        help="Audio quality in kbps (default: 128)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store audio in cloud storage (requires BLOB_STORAGE_URL)",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="Proxy URL for yt-dlp (e.g., http://user:pass@host:port)",
    )


def run_audio(args: argparse.Namespace) -> int:
    """Run the audio command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            args.input_dir,
            args.output_dir,
            args.cookies,
            args.checkpoint_dir,
            args.quality,
            cloud=args.cloud,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        results = run_audio_download(
            args.jurisdiction,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            cookies_path=args.cookies,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
            limit=args.limit,
            quality=args.quality,
            cloud=args.cloud,
            proxy=args.proxy,
        )

        if results is None and not args.dry_run:
            return 1

        return 0


def load_videos(
    jurisdiction_id: str,
    input_dir: str,
    cloud: bool = False,
    meeting_type: Optional[str] = None,
    since_days: Optional[int] = None,
) -> Optional[List[Dict]]:
    """
    Load videos from cloud storage or local JSON file.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing the videos JSON (fallback)
        cloud: If True, try cloud storage first
        meeting_type: Filter by meeting type (e.g., "planning_commission")
        since_days: Only return videos discovered within this many days

    Returns:
        List of video dicts or None if not found
    """
    # Try cloud storage first if enabled
    if cloud or os.environ.get("DATABASE_URL"):
        try:
            from civicos.storage import get_storage_backend

            backend = get_storage_backend()
            if backend.backend_type == "postgres":
                videos = backend.get_videos(jurisdiction_id, meeting_type=meeting_type, since_days=since_days)
                if videos:
                    type_msg = f" (meeting_type={meeting_type})" if meeting_type else ""
                    since_msg = f", since_days={since_days}" if since_days else ""
                    logger.info(
                        f"Loaded {len(videos)} videos from cloud storage ({backend.backend_type}){type_msg}{since_msg}"
                    )
                    return videos
                else:
                    logger.info("No videos in cloud storage, trying local fallback")
        except ImportError:
            logger.debug("civic.storage not available, using local fallback")
        except Exception as e:
            logger.warning(f"Cloud storage read failed: {e}, using local fallback")

    # Fallback to local JSON file
    input_path = Path(input_dir)
    videos_file = input_path / f"{jurisdiction_id.replace('-', '_')}_videos.json"

    if not videos_file.exists():
        logger.error(f"Videos file not found: {videos_file}")
        logger.error("Run 'civic-extract youtube' first to discover videos")
        return None

    try:
        with open(videos_file) as f:
            videos = json.load(f)
        logger.info(f"Loaded {len(videos)} videos from {videos_file}")
        return videos
    except Exception as e:
        logger.error(f"Error loading videos file: {e}")
        return None


def checkpoint_path_for_audio(jurisdiction_id: str, checkpoint_dir: str) -> Path:
    """Get checkpoint file path for audio downloads."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"audio_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: AudioCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[AudioCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return AudioCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def download_audio(
    video_id: str,
    output_dir: str,
    cookies_file: Optional[str] = None,
    quality: str = "128",
    cloud: bool = False,
    jurisdiction_id: Optional[str] = None,
    proxy: Optional[str] = None,
) -> DownloadResult:
    """
    Download audio from a YouTube video using yt-dlp.

    Args:
        video_id: YouTube video ID
        output_dir: Directory to save audio files (local fallback)
        cookies_file: Path to cookies file (optional)
        quality: Audio quality in kbps
        cloud: If True, upload to R2 cloud storage
        jurisdiction_id: Jurisdiction ID for cloud storage key
        proxy: Proxy URL for yt-dlp (e.g., "http://user:pass@host:port")

    Returns:
        DownloadResult with status and details
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp not installed. Run: pip install yt-dlp")
        return DownloadResult(
            video_id=video_id,
            status="error",
            error="yt-dlp not installed",
        )

    # Check if already in cloud storage
    r2_key = None
    if cloud or os.environ.get("BLOB_STORAGE_URL"):
        try:
            from civicos.storage import get_blob_storage

            blob = get_blob_storage()
            r2_key = f"audio/{jurisdiction_id}/{video_id}.mp3"
            if blob.exists(r2_key):
                logger.info(f"  Skipping (already in cloud): {r2_key}")
                return DownloadResult(
                    video_id=video_id,
                    status="skipped",
                    r2_key=r2_key,
                )
        except ImportError:
            logger.debug("civic.storage not available for cloud check")
        except Exception as e:
            logger.debug(f"Cloud check failed: {e}")

    output_path = os.path.join(output_dir, f"{video_id}.mp3")

    # Skip if already downloaded locally (and not using cloud)
    if not (cloud or os.environ.get("BLOB_STORAGE_URL")) and os.path.exists(output_path):
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"  Skipping (already exists): {video_id}.mp3 ({file_size_mb:.1f} MB)")
        return DownloadResult(
            video_id=video_id,
            status="skipped",
            file_path=output_path,
            file_size_mb=file_size_mb,
        )

    try:
        url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": quality,
                }
            ],
            "outtmpl": os.path.join(output_dir, video_id),
            "quiet": True,
            "no_warnings": True,
        }

        # Add cookies if provided
        if cookies_file and os.path.exists(cookies_file):
            ydl_opts["cookiefile"] = cookies_file
            logger.debug(f"  Using cookies from: {cookies_file}")

        # Add proxy if provided (residential proxy to bypass datacenter IP blocks)
        if proxy:
            ydl_opts["proxy"] = proxy
            logger.debug(f"  Using proxy: {proxy.split('@')[-1]}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            duration_mins = info.get("duration", 0) // 60

        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        logger.info(f"  Downloaded: {video_id}.mp3 ({duration_mins} min, {file_size_mb:.1f} MB)")

        # Upload to cloud storage if enabled
        r2_key = None
        if cloud or os.environ.get("BLOB_STORAGE_URL"):
            try:
                from civicos.storage import get_blob_storage

                blob = get_blob_storage()
                r2_key = f"audio/{jurisdiction_id}/{video_id}.mp3"

                with open(output_path, "rb") as f:
                    audio_data = f.read()

                blob.upload(r2_key, audio_data, content_type="audio/mpeg")
                logger.info(f"  Uploaded to cloud: {r2_key}")

                # Remove local file after successful upload
                os.remove(output_path)
                logger.debug(f"  Removed local file: {output_path}")

            except ImportError:
                logger.warning("civic.storage not available, keeping local file")
            except Exception as e:
                logger.warning(f"Cloud upload failed: {e}, keeping local file")
                r2_key = None

        return DownloadResult(
            video_id=video_id,
            status="success",
            file_path=output_path if r2_key is None else None,
            file_size_mb=file_size_mb,
            duration_minutes=duration_mins,
            r2_key=r2_key,
        )

    except Exception as e:
        logger.error(f"  Error downloading {video_id}: {e}")
        return DownloadResult(
            video_id=video_id,
            status="error",
            error=str(e),
        )


def run_audio_download(
    jurisdiction_id: str,
    input_dir: str = "data",
    output_dir: str = "data/youtube_audio",
    cookies_path: str = "~/Downloads/www.youtube.com_cookies.txt",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    quality: str = "128",
    cloud: bool = False,
    meeting_type: Optional[str] = None,
    since_days: Optional[int] = None,
    proxy: Optional[str] = None,
) -> Optional[List[DownloadResult]]:
    """
    Run audio download for videos from a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing videos JSON
        output_dir: Directory for audio files
        cookies_path: Path to cookies file
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, show what would be downloaded without downloading
        limit: Maximum videos to download (0 = no limit)
        quality: Audio quality in kbps
        cloud: If True, upload audio to R2 cloud storage
        meeting_type: Filter by meeting type (e.g., "planning_commission")
        since_days: Only process videos discovered within this many days
        proxy: Proxy URL for yt-dlp (e.g., "http://user:pass@host:port")

    Returns:
        List of DownloadResult if successful, None if failed
    """
    logger.info(f"Starting audio download for {jurisdiction_id}")
    if meeting_type:
        logger.info(f"Filtering by meeting_type: {meeting_type}")

    if cloud or os.environ.get("BLOB_STORAGE_URL"):
        logger.info("Cloud storage mode enabled")

    if proxy:
        # Log proxy host without credentials
        proxy_display = proxy.split("@")[-1] if "@" in proxy else proxy
        logger.info(f"Using proxy: {proxy_display}")

    # Load videos (tries cloud first if enabled)
    videos = load_videos(jurisdiction_id, input_dir, cloud=cloud, meeting_type=meeting_type, since_days=since_days)
    if not videos:
        return None

    # Expand cookies path
    cookies_file = os.path.expanduser(cookies_path)
    if not os.path.exists(cookies_file):
        logger.warning(f"Cookies file not found: {cookies_file}")
        logger.warning("Downloads may fail due to YouTube bot detection")
        cookies_file = None
    else:
        logger.info(f"Using cookies: {cookies_file}")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_audio(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    start_index = 0

    if resume_from:
        logger.info(f"Found checkpoint: {resume_from.items_processed} items processed")
        # Find the index to resume from
        for i, video in enumerate(videos):
            if video.get("video_id") == resume_from.last_video_id:
                start_index = i + 1
                break
        if start_index > 0:
            logger.info(f"Resuming from video {start_index}")

    # Apply limit
    videos_to_process = videos[start_index:]
    if limit > 0:
        videos_to_process = videos_to_process[:limit]
        logger.info(f"Limited to {limit} videos")

    if dry_run:
        logger.info("Dry-run mode - showing videos to download:")
        for i, video in enumerate(videos_to_process, start=1):
            video_id = video.get("video_id")
            title = video.get("title", "Unknown")
            date = video.get("date", "Unknown")

            # Check if already downloaded
            output_path = os.path.join(output_dir, f"{video_id}.mp3")
            exists = os.path.exists(output_path)
            status = "(already downloaded)" if exists else ""

            logger.info(f"  [{i}/{len(videos_to_process)}] {video_id} {status}")
            logger.info(f"    Title: {title}")
            logger.info(f"    Date: {date}")

        # Count already downloaded
        already_downloaded = sum(
            1 for v in videos_to_process
            if os.path.exists(os.path.join(output_dir, f"{v.get('video_id')}.mp3"))
        )
        logger.info(f"Would process {len(videos_to_process)} videos")
        logger.info(f"Already downloaded: {already_downloaded}")
        logger.info(f"To download: {len(videos_to_process) - already_downloaded}")
        return None

    # Download videos
    results = []
    items_processed = start_index
    items_downloaded = 0
    items_skipped = 0
    items_failed = 0

    for i, video in enumerate(videos_to_process, start=start_index + 1):
        video_id = video.get("video_id")
        if not video_id:
            continue

        title = video.get("title", "Unknown")
        logger.info(f"[{i}/{len(videos)}] {title}")

        result = download_audio(
            video_id,
            output_dir,
            cookies_file,
            quality,
            cloud=cloud,
            jurisdiction_id=jurisdiction_id,
            proxy=proxy,
        )
        results.append(result)

        if result.status == "success":
            items_downloaded += 1
        elif result.status == "skipped":
            items_skipped += 1
        else:
            items_failed += 1

        items_processed = i

        # Save checkpoint every 5 videos
        if i % 5 == 0:
            checkpoint = AudioCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_video_id=video_id,
                items_processed=items_processed,
                items_downloaded=items_downloaded,
                items_skipped=items_skipped,
                items_failed=items_failed,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Final checkpoint
    if videos_to_process:
        last_video_id = videos_to_process[-1].get("video_id", "")
        checkpoint = AudioCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_video_id=last_video_id,
            items_processed=items_processed,
            items_downloaded=items_downloaded,
            items_skipped=items_skipped,
            items_failed=items_failed,
            timestamp=datetime.now().isoformat(),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Save manifest
    manifest_path = os.path.join(output_dir, f"{jurisdiction_id.replace('-', '_')}_manifest.json")
    manifest_data = [asdict(r) for r in results]
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
    logger.info(f"Saved manifest to {manifest_path}")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Audio Download Complete for {jurisdiction_id}")
    logger.info(f"Processed: {len(results)}")
    logger.info(f"Downloaded: {items_downloaded}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"Failed: {items_failed}")
    logger.info("=" * 50)

    return results


def run_scheduled(
    jurisdiction_id: str,
    input_dir: str,
    output_dir: str,
    cookies_path: str,
    checkpoint_dir: str,
    quality: str,
    cloud: bool = False,
) -> None:
    """
    Run audio download on a schedule.

    Uses the schedule library to run daily at 8am (after youtube at 7am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting audio download scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 08:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_audio_download(
            jurisdiction_id,
            input_dir=input_dir,
            output_dir=output_dir,
            cookies_path=cookies_path,
            checkpoint_dir=checkpoint_dir,
            quality=quality,
            cloud=cloud,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 8am daily (after youtube at 7am)
    schedule.every().day.at("08:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial audio download...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

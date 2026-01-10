"""
CLI for extracting school board meetings from YouTube playlists.

Uses YouTube Data API v3 to extract meeting metadata directly from playlists.
Designed for school boards that upload meetings to YouTube (e.g., SRCS).

Usage:
    civic-extract youtube-boards --jurisdiction school-san-rafael
    civic-extract youtube-boards --jurisdiction school-san-rafael --dry-run
    civic-extract youtube-boards --jurisdiction school-san-rafael --cloud
    civic-extract youtube-boards --jurisdiction school-san-rafael --validate
"""

import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def add_youtube_boards_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the youtube-boards subcommand to the parser."""
    parser = subparsers.add_parser(
        "youtube-boards",
        help="Extract school board meetings from YouTube playlists",
        description="Use YouTube Data API v3 to extract meeting metadata from playlists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., school-san-rafael)",
    )
    parser.add_argument(
        "--days-past",
        type=int,
        default=365,
        help="Days into past to include (default: 365)",
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory for output files (default: data)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be extracted without saving",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration and API access only",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store results in cloud storage (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )


def run_youtube_boards(args: argparse.Namespace) -> int:
    """Run youtube-boards command."""
    from civic_extraction.clients.youtube_boards import (
        YouTubeBoardsSource,
        create_srcs_youtube_client,
    )

    jurisdiction_id = args.jurisdiction
    checkpoint_dir = args.checkpoint_dir

    logger.info(f"YouTube Boards extraction for {jurisdiction_id}")

    # Check for API key early (YOUTUBE_API_KEY or GOOGLE_API_KEY)
    api_key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error(
            "No API key found. Set YOUTUBE_API_KEY or GOOGLE_API_KEY "
            "(with YouTube Data API v3 enabled) in your .env file."
        )
        return 1

    try:
        # Load source from config
        source = YouTubeBoardsSource.from_jurisdiction(jurisdiction_id)
    except FileNotFoundError as e:
        logger.error(f"Config not found: {e}")
        return 1
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return 1

    # Validate mode
    if args.validate:
        logger.info("Running validation...")
        result = source.validate()
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.is_valid else 1

    # Health check
    health = source.health()
    if not health.is_available:
        logger.error(f"Source unavailable: {health.errors}")
        return 1

    logger.info(
        f"Playlist accessible: {health.metadata.get('playlist_title')} "
        f"({health.available_count} videos)"
    )

    # Dry run mode
    if args.dry_run:
        logger.info("DRY RUN - showing what would be extracted")
        meetings = source.get_meetings(days_past=args.days_past)
        print(f"\nFound {len(meetings)} meetings:")
        for meeting in meetings[:10]:  # Show first 10
            print(f"  - {meeting.meeting_datetime.strftime('%Y-%m-%d')} {meeting.title[:60]}")
        if len(meetings) > 10:
            print(f"  ... and {len(meetings) - 10} more")
        return 0

    # Extract meetings
    logger.info(f"Extracting meetings from last {args.days_past} days...")
    meetings = source.get_meetings(days_past=args.days_past)
    logger.info(f"Found {len(meetings)} meetings")

    if not meetings:
        logger.info("No meetings to extract")
        return 0

    # Save to checkpoint
    checkpoint_path = os.path.join(
        checkpoint_dir, f"youtube_boards_{jurisdiction_id.replace('-', '_')}.json"
    )
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Include raw_data in checkpoint (video_id, duration, etc.)
    def meeting_with_raw(m):
        d = m.to_dict()
        d["raw_data"] = m.raw_data
        return d

    checkpoint_data = {
        "jurisdiction_id": jurisdiction_id,
        "source_type": "youtube_boards",
        "extracted_at": datetime.now().isoformat(),
        "meeting_count": len(meetings),
        "meetings": [meeting_with_raw(m) for m in meetings],
    }

    with open(checkpoint_path, "w") as f:
        json.dump(checkpoint_data, f, indent=2)
    logger.info(f"Saved checkpoint to {checkpoint_path}")

    # Cloud storage mode
    if args.cloud:
        logger.info("Storing meetings to cloud database...")
        try:
            from dotenv import load_dotenv
            load_dotenv()

            from civic.storage import get_storage_backend

            storage = get_storage_backend()
            if storage is None:
                logger.error("DATABASE_URL not configured for cloud storage")
                return 1

            # Store meetings
            stored_count = 0
            for meeting in meetings:
                try:
                    storage.store_meeting(meeting.to_dict())
                    stored_count += 1
                except Exception as e:
                    logger.warning(f"Failed to store meeting {meeting.id}: {e}")

            logger.info(f"Stored {stored_count}/{len(meetings)} meetings to database")

        except ImportError as e:
            logger.error(f"Missing dependency for cloud storage: {e}")
            return 1
        except Exception as e:
            logger.error(f"Cloud storage failed: {e}")
            return 1

    logger.info("YouTube boards extraction complete")
    return 0

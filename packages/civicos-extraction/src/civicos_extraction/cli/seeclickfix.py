"""
SeeClickFix refresh command for civic-extract CLI.

Fetches operational issues (potholes, stormwater, etc.) from SeeClickFix API
and stores them in the Civic database for bridging 311 -> policy engagement.

Usage:
    civic-extract seeclickfix --jurisdiction city-san-rafael
    civic-extract seeclickfix --jurisdiction city-san-rafael --schedule
    civic-extract seeclickfix --jurisdiction city-san-rafael --dry-run
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class SeeClickFixCheckpoint:
    """Checkpoint for SeeClickFix refresh progress."""

    jurisdiction_id: str
    last_page: int
    issues_fetched: int
    issues_new: int
    issues_updated: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SeeClickFixCheckpoint":
        return cls(**data)


def add_seeclickfix_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the seeclickfix subcommand to the parser."""
    parser = subparsers.add_parser(
        "seeclickfix",
        help="Refresh SeeClickFix operational issues",
        description="Fetch operational issues from SeeClickFix API and store in Civic database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--place-url",
        help="SeeClickFix place URL override (default: derived from jurisdiction)",
    )
    parser.add_argument(
        "--status",
        default=None,
        choices=["open", "closed", "acknowledged", None],
        help="Filter by status (default: all)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
        help="Maximum pages to fetch (default: 50)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Issues per page (default: 100, max: 100)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/pilot",
        help="Directory for output files (default: data/pilot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration only - don't fetch issues",
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


def run_seeclickfix(args: argparse.Namespace) -> int:
    """Run the seeclickfix command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            place_url=args.place_url,
            status=args.status,
            max_pages=args.max_pages,
            per_page=args.per_page,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        result = run_seeclickfix_refresh(
            args.jurisdiction,
            place_url=args.place_url,
            status=args.status,
            max_pages=args.max_pages,
            per_page=args.per_page,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
        )

        if result is None and not args.dry_run:
            return 1

        return 0


def derive_place_url(jurisdiction_id: str) -> str:
    """
    Derive SeeClickFix place_url from jurisdiction ID.

    Examples:
        city-san-rafael -> san-rafael
        city-new-york -> new-york
    """
    # Remove common prefixes
    place_url = jurisdiction_id
    for prefix in ["city-", "county-", "town-"]:
        if place_url.startswith(prefix):
            place_url = place_url[len(prefix):]
            break
    return place_url


def checkpoint_path_for_seeclickfix(
    jurisdiction_id: str, checkpoint_dir: str
) -> Path:
    """Get checkpoint file path for SeeClickFix refresh."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"seeclickfix_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: SeeClickFixCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[SeeClickFixCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return SeeClickFixCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def run_seeclickfix_refresh(
    jurisdiction_id: str,
    place_url: Optional[str] = None,
    status: Optional[str] = None,
    max_pages: int = 50,
    per_page: int = 100,
    output_dir: str = "data/pilot",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Run SeeClickFix refresh for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        place_url: SeeClickFix place URL (default: derived from jurisdiction)
        status: Filter by status (default: all)
        max_pages: Maximum pages to fetch
        per_page: Issues per page (max 100)
        output_dir: Directory for output files
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, validate only - don't fetch issues

    Returns:
        Result dict with counts if successful, None if failed
    """
    logger.info(f"Starting SeeClickFix refresh for {jurisdiction_id}")

    # Derive place_url if not provided
    if not place_url:
        place_url = derive_place_url(jurisdiction_id)
    logger.info(f"Using place_url: {place_url}")

    # Import SeeClickFix client from local clients module
    from civicos_extraction.clients.seeclickfix import SeeClickFixClient

    # Initialize client
    client = SeeClickFixClient()

    if dry_run:
        logger.info("Dry-run mode - validating configuration...")
        # Test API with single page
        test_result = client.get_issues(
            place_url=place_url,
            per_page=1,
            page=1,
            status=status,
        )
        if test_result.get("metadata", {}).get("error"):
            logger.error(f"API test failed: {test_result['metadata']['error']}")
            return None
        logger.info(f"API test successful - SeeClickFix accessible for {place_url}")
        logger.info(f"Would fetch up to {max_pages} pages of {per_page} issues each")
        return {"dry_run": True, "status": "validated"}

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_seeclickfix(jurisdiction_id, checkpoint_dir)
    resume_checkpoint = load_checkpoint(checkpoint_path)
    start_page = 1

    if resume_checkpoint:
        # Only resume if from today (otherwise start fresh)
        checkpoint_date = resume_checkpoint.timestamp[:10]
        today = datetime.now().strftime("%Y-%m-%d")
        if checkpoint_date == today:
            start_page = resume_checkpoint.last_page + 1
            logger.info(f"Resuming from checkpoint: page {start_page}")
        else:
            logger.info("Checkpoint from previous day - starting fresh")

    # Fetch issues
    all_issues: List[Dict[str, Any]] = []
    issues_fetched = 0
    current_page = start_page

    while current_page <= max_pages:
        logger.info(f"Fetching page {current_page}/{max_pages}...")

        result = client.get_issues(
            place_url=place_url,
            per_page=per_page,
            page=current_page,
            status=status,
        )

        issues = result.get("issues", [])
        metadata = result.get("metadata", {})

        if metadata.get("error"):
            logger.error(f"API error: {metadata['error']}")
            break

        if not issues:
            logger.info("No more issues to fetch")
            break

        all_issues.extend(issues)
        issues_fetched += len(issues)
        logger.info(f"  Fetched {len(issues)} issues (total: {issues_fetched})")

        # Save checkpoint every 5 pages
        if current_page % 5 == 0:
            checkpoint = SeeClickFixCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_page=current_page,
                issues_fetched=issues_fetched,
                issues_new=0,  # Will be calculated at the end
                issues_updated=0,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: page {current_page}")

        # Check if more pages - use len(issues) == per_page as fallback
        # The SeeClickFix API returns full pages until the last page
        has_more = metadata.get("has_more", len(issues) == per_page)
        if not has_more:
            logger.info("Reached last page")
            break

        current_page += 1

    if not all_issues:
        logger.warning("No issues fetched")
        return None

    # Load existing issues for comparison
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_file = output_path / f"seeclickfix_{jurisdiction_id.replace('-', '_')}.json"

    existing_issues: Dict[str, Dict] = {}
    if output_file.exists():
        try:
            with open(output_file) as f:
                existing_data = json.load(f)
                if isinstance(existing_data, list):
                    existing_issues = {
                        issue.get("id", issue.get("external_id", "")): issue
                        for issue in existing_data
                    }
                elif isinstance(existing_data, dict) and "issues" in existing_data:
                    existing_issues = {
                        issue.get("id", issue.get("external_id", "")): issue
                        for issue in existing_data.get("issues", [])
                    }
            logger.info(f"Loaded {len(existing_issues)} existing issues")
        except Exception as e:
            logger.warning(f"Error loading existing issues: {e}")

    # Calculate new vs updated
    issues_new = 0
    issues_updated = 0

    for issue in all_issues:
        issue_id = issue.get("id", issue.get("external_id", ""))
        if issue_id in existing_issues:
            # Check if updated
            old_updated = existing_issues[issue_id].get("updated_at", "")
            new_updated = issue.get("updated_at", "")
            if new_updated != old_updated:
                issues_updated += 1
        else:
            issues_new += 1

    # Save results
    output_data = {
        "jurisdiction_id": jurisdiction_id,
        "place_url": place_url,
        "fetched_at": datetime.now().isoformat(),
        "count": len(all_issues),
        "issues_new": issues_new,
        "issues_updated": issues_updated,
        "issues": all_issues,
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    logger.info(f"Saved {len(all_issues)} issues to {output_file}")

    # Final checkpoint
    checkpoint = SeeClickFixCheckpoint(
        jurisdiction_id=jurisdiction_id,
        last_page=current_page,
        issues_fetched=issues_fetched,
        issues_new=issues_new,
        issues_updated=issues_updated,
        timestamp=datetime.now().isoformat(),
    )
    save_checkpoint(checkpoint, checkpoint_path)

    # Summary
    logger.info("=" * 50)
    logger.info(f"SeeClickFix Refresh Complete for {jurisdiction_id}")
    logger.info(f"Total issues fetched: {issues_fetched}")
    logger.info(f"New issues: {issues_new}")
    logger.info(f"Updated issues: {issues_updated}")
    logger.info(f"Output file: {output_file}")
    logger.info("=" * 50)

    return {
        "jurisdiction_id": jurisdiction_id,
        "issues_fetched": issues_fetched,
        "issues_new": issues_new,
        "issues_updated": issues_updated,
        "output_file": str(output_file),
    }


def run_scheduled(
    jurisdiction_id: str,
    place_url: Optional[str] = None,
    status: Optional[str] = None,
    max_pages: int = 50,
    per_page: int = 100,
    output_dir: str = "data/pilot",
    checkpoint_dir: str = "data/checkpoints",
) -> None:
    """
    Run SeeClickFix refresh on a schedule.

    Uses the schedule library to run daily at 8am.
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting SeeClickFix scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 08:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_seeclickfix_refresh(
            jurisdiction_id,
            place_url=place_url,
            status=status,
            max_pages=max_pages,
            per_page=per_page,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 8am daily
    schedule.every().day.at("08:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial SeeClickFix refresh...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

"""
Meeting discovery command for civic-extract CLI.

Usage:
    civic-extract discover --jurisdiction city-san-rafael
    civic-extract discover --jurisdiction city-san-rafael --schedule
    civic-extract discover --jurisdiction city-san-rafael --dry-run
"""

import argparse
import logging
import sys
from typing import Optional

from civic_extraction.pipeline import (
    Pipeline,
    PipelineResult,
    StageStatus,
    IngestCheckpoint,
    save_checkpoint,
    load_checkpoint,
    checkpoint_path_for_jurisdiction,
)
from civic_extraction.clients.proudcity import ProudCitySource
from civic.storage import get_storage_backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def add_discover_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the discover subcommand to the parser."""
    parser = subparsers.add_parser(
        "discover",
        help="Discover meetings from municipal sources",
        description="Run meeting discovery pipeline for a jurisdiction",
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
        default=30,
        help="Days into past to search (default: 30)",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=90,
        help="Days into future to search (default: 90)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config only, don't run pipeline",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 6am) instead of once",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default="data/checkpoints",
        help="Directory for checkpoint files (default: data/checkpoints)",
    )


def run_discover(args: argparse.Namespace) -> int:
    """Run the discover command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(args.jurisdiction, args.days_past, args.days_ahead, args.checkpoint_dir)
        return 0  # Never reached (scheduler runs forever)
    else:
        result = run_meeting_discovery(
            args.jurisdiction,
            days_past=args.days_past,
            days_ahead=args.days_ahead,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
        )

        if result is None and not args.dry_run:
            return 1
        elif result and not result.success:
            return 1

        return 0


def run_meeting_discovery(
    jurisdiction_id: str,
    days_past: int = 30,
    days_ahead: int = 90,
    checkpoint_dir: str = "data/checkpoints",
    skip_index: bool = True,
    dry_run: bool = False,
) -> Optional[PipelineResult]:
    """
    Run meeting discovery for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        days_past: Days into past to search
        days_ahead: Days into future to search
        checkpoint_dir: Directory for checkpoint files
        skip_index: Skip index stage (for cron, we just discover/ingest)
        dry_run: If True, validate only - don't run pipeline

    Returns:
        PipelineResult if successful, None if failed
    """
    logger.info(f"Starting meeting discovery for {jurisdiction_id}")
    logger.info(f"Date range: {days_past} days past to {days_ahead} days ahead")

    # Load source from config
    try:
        source = ProudCitySource.from_jurisdiction(jurisdiction_id)
        logger.info(f"Loaded source: {source.source_id}")
    except Exception as e:
        logger.error(f"Failed to load source config: {e}")
        return None

    # Validate before running
    logger.info("Validating source configuration...")
    validation = source.validate()
    if not validation.is_valid:
        logger.error(f"Validation failed: {validation.errors}")
        return None

    if validation.warnings:
        for warning in validation.warnings:
            logger.warning(warning)

    logger.info(f"Validation passed in {validation.check_duration_ms:.0f}ms")

    if dry_run:
        logger.info("Dry-run mode - skipping pipeline execution")
        return None

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_jurisdiction(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    if resume_from:
        logger.info(f"Resuming from checkpoint: {resume_from.last_meeting_id}")
        logger.info(f"Last processed: {resume_from.last_meeting_datetime.isoformat()}")

    # Create pipeline with storage backend from environment
    # Uses DATABASE_URL env var: postgres:// -> PostgresBackend, else SQLiteBackend
    storage = get_storage_backend()
    logger.info(f"Using storage backend: {storage.backend_type}")
    pipeline = Pipeline(source, jurisdiction_id, storage_target=storage)

    # Define callbacks for logging
    def on_stage_start(stage: str) -> None:
        logger.info(f"[{stage.upper()}] Starting...")

    def on_stage_complete(stage: str, status: StageStatus) -> None:
        if status.errors:
            logger.warning(f"[{stage.upper()}] Completed with errors: {status.errors}")
        else:
            logger.info(
                f"[{stage.upper()}] Completed: "
                f"{status.items_processed}/{status.items_found} items "
                f"in {status.duration_ms:.0f}ms"
            )

    def on_error(stage: str, error: Exception) -> None:
        logger.error(f"[{stage.upper()}] Error: {error}")

    def on_checkpoint(checkpoint: IngestCheckpoint) -> None:
        save_checkpoint(checkpoint, checkpoint_path)
        logger.info(f"Checkpoint saved: {checkpoint.items_processed} items processed")

    # Run pipeline
    logger.info("Running pipeline...")
    result = pipeline.run(
        on_stage_start=on_stage_start,
        on_stage_complete=on_stage_complete,
        on_error=on_error,
        on_checkpoint=on_checkpoint,
        days_ahead=days_ahead,
        days_past=days_past,
        skip_index=skip_index,
        resume_from=resume_from,
    )

    # Log results
    if result.success:
        logger.info(
            f"Pipeline completed successfully in {result.total_duration_ms:.0f}ms"
        )
        # Summary
        discover = result.stages.get("discover")
        ingest = result.stages.get("ingest")
        if discover and ingest:
            logger.info(
                f"Summary: discovered {discover.items_found} meetings, "
                f"ingested {ingest.items_processed} meetings"
            )
    else:
        logger.error("Pipeline failed")
        for stage_name, stage in result.stages.items():
            if stage.errors:
                logger.error(f"  {stage_name}: {stage.errors}")

    return result


def run_scheduled(
    jurisdiction_id: str,
    days_past: int,
    days_ahead: int,
    checkpoint_dir: str,
) -> None:
    """
    Run the discovery pipeline on a schedule.

    Uses the schedule library to run daily at 6am.
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 06:00")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_meeting_discovery(
            jurisdiction_id,
            days_past=days_past,
            days_ahead=days_ahead,
            checkpoint_dir=checkpoint_dir,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 6am daily
    schedule.every().day.at("06:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial discovery...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

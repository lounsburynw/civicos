"""
Decision extraction command for civic-extract CLI.

Extracts high-stakes decisions from meeting agendas/minutes using LLM analysis.

Usage:
    civic-extract decisions --jurisdiction city-san-rafael
    civic-extract decisions --jurisdiction city-san-rafael --schedule
    civic-extract decisions --jurisdiction city-san-rafael --dry-run
    civic-extract decisions --jurisdiction city-san-rafael --limit 5
    civic-extract decisions --jurisdiction city-san-rafael --cloud

Cloud mode (--cloud):
    - Reads meetings from Postgres (requires DATABASE_URL)
    - Stores decisions in Postgres via store_decisions()
    - Falls back to local storage if cloud unavailable

Cost: Uses Gemini 2.5 Pro for extraction (~$0.50/meeting for large agendas)
"""

import argparse
import json
import logging
import os
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
class DecisionResult:
    """Result of a decision extraction."""

    meeting_id: str
    meeting_date: str
    status: str  # "success", "skipped", "error"
    decisions_count: int = 0
    error: Optional[str] = None


@dataclass
class DecisionCheckpoint:
    """Checkpoint for decision extraction progress."""

    jurisdiction_id: str
    last_meeting_id: str
    items_processed: int
    items_extracted: int
    items_skipped: int
    items_failed: int
    total_decisions: int
    timestamp: str
    succeeded_meeting_ids: Optional[List[str]] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DecisionCheckpoint":
        # Handle old checkpoints without succeeded_meeting_ids
        if "succeeded_meeting_ids" not in data:
            data["succeeded_meeting_ids"] = []
        return cls(**data)


def add_decisions_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the decisions subcommand to the parser."""
    parser = subparsers.add_parser(
        "decisions",
        help="Extract decisions from meeting agendas/minutes",
        description="Extract high-stakes decisions using LLM analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--input-dir",
        default="data/meetings",
        help="Directory containing meeting data (default: data/meetings)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/decisions",
        help="Directory for decision files (default: data/decisions)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show meetings that would be processed, don't actually extract",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 10am) instead of once",
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
        help="Limit number of meetings to process (0 = no limit, default: 0)",
    )
    parser.add_argument(
        "--min-stakes",
        type=int,
        default=6,
        help="Minimum stakes score (1-10) for decisions (default: 6)",
    )
    parser.add_argument(
        "--min-budget",
        type=int,
        default=100000,
        help="Minimum budget threshold for auto-flagging (default: 100000)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Store decisions in cloud storage (requires DATABASE_URL)",
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Process meetings since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        type=str,
        help="Process meetings until this date (YYYY-MM-DD)",
    )


def run_decisions(args: argparse.Namespace) -> int:
    """Run the decisions command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            args.input_dir,
            args.output_dir,
            args.checkpoint_dir,
            args.min_stakes,
            args.min_budget,
            cloud=args.cloud,
            since=args.since,
            until=args.until,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        results = run_decision_extraction(
            args.jurisdiction,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
            limit=args.limit,
            min_stakes=args.min_stakes,
            min_budget=args.min_budget,
            cloud=args.cloud,
            since=args.since,
            until=args.until,
        )

        if results is None and not args.dry_run:
            return 1

        return 0


def find_meetings(
    jurisdiction_id: str, input_dir: str, cloud: bool = False,
    since: Optional[str] = None, until: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Find meetings with agenda URLs for decision extraction.

    In cloud mode, returns meetings from Postgres.
    In local mode, returns meetings from local JSON files.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing meeting data (local mode)
        cloud: If True, try cloud storage first
        since: Filter meetings since this date (YYYY-MM-DD)
        until: Filter meetings until this date (YYYY-MM-DD)

    Returns:
        List of meeting dictionaries, or None if none found
    """
    # Try cloud storage first if enabled
    if cloud or os.environ.get("DATABASE_URL"):
        try:
            from civicos.storage import get_storage_backend
            from datetime import datetime as dt

            backend = get_storage_backend()
            if backend.backend_type == "postgres":
                # Build datetime filters
                since_dt = dt.fromisoformat(since) if since else None
                until_dt = dt.fromisoformat(until) if until else None

                meetings = backend.get_meetings(
                    jurisdiction_id,
                    since=since_dt,
                    until=until_dt,
                )
                if meetings:
                    # Filter to meetings with agenda URLs
                    meetings_with_agendas = [
                        m for m in meetings
                        if m.get("agenda_url")
                    ]
                    if meetings_with_agendas:
                        logger.info(
                            f"Found {len(meetings_with_agendas)} meetings with agendas in cloud storage"
                        )
                        return meetings_with_agendas
                    else:
                        logger.info("No meetings with agendas in cloud, trying local fallback")
        except ImportError:
            logger.debug("civic.storage not available, using local fallback")
        except Exception as e:
            logger.warning(f"Cloud storage check failed: {e}, using local fallback")

    # Local mode fallback - load from JSON files
    input_path = Path(input_dir)

    if not input_path.exists():
        logger.error(f"Input directory not found: {input_dir}")
        logger.error("Run 'civic-extract discover' first to extract meetings")
        return None

    # Look for jurisdiction-specific meeting files
    pattern = f"{jurisdiction_id.replace('-', '_')}*.json"
    meeting_files = sorted(input_path.glob(pattern))

    if not meeting_files:
        # Try checkpoint file
        checkpoint_file = Path("data/checkpoints") / f"{jurisdiction_id}.json"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    checkpoint = json.load(f)
                meetings = checkpoint.get("events", [])
                if meetings:
                    # Filter by date if specified
                    if since:
                        meetings = [m for m in meetings if m.get("meeting_date", "") >= since]
                    if until:
                        meetings = [m for m in meetings if m.get("meeting_date", "") <= until]
                    # Filter to meetings with agendas
                    meetings_with_agendas = [m for m in meetings if m.get("agenda_url")]
                    if meetings_with_agendas:
                        logger.info(f"Loaded {len(meetings_with_agendas)} meetings from checkpoint")
                        return meetings_with_agendas
            except Exception as e:
                logger.warning(f"Error loading checkpoint: {e}")

        logger.error(f"No meeting files found in {input_dir}")
        logger.error("Run 'civic-extract discover' first to extract meetings")
        return None

    # Load meetings from files
    all_meetings = []
    for meeting_file in meeting_files:
        try:
            with open(meeting_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                all_meetings.extend(data)
            elif isinstance(data, dict):
                if "events" in data:
                    all_meetings.extend(data["events"])
                else:
                    all_meetings.append(data)
        except Exception as e:
            logger.warning(f"Error loading {meeting_file}: {e}")

    # Filter by date and agenda URL
    if since:
        all_meetings = [m for m in all_meetings if m.get("meeting_date", "") >= since]
    if until:
        all_meetings = [m for m in all_meetings if m.get("meeting_date", "") <= until]

    meetings_with_agendas = [m for m in all_meetings if m.get("agenda_url")]

    if not meetings_with_agendas:
        logger.error("No meetings with agenda URLs found")
        return None

    logger.info(f"Found {len(meetings_with_agendas)} meetings with agendas in {input_dir}")
    return meetings_with_agendas


def checkpoint_path_for_decisions(jurisdiction_id: str, checkpoint_dir: str) -> Path:
    """Get checkpoint file path for decision extraction."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"decisions_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: DecisionCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[DecisionCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return DecisionCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def decisions_exist(meeting_id: str, output_dir: str) -> bool:
    """Check if decisions already exist for a meeting."""
    output_path = Path(output_dir) / f"decisions_{meeting_id}.json"
    return output_path.exists()


def decisions_exist_in_cloud(jurisdiction_id: str, meeting_id: str) -> bool:
    """Check if decisions exist in cloud storage for a specific meeting."""
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            decisions = backend.get_decisions(
                jurisdiction_id,
                meeting_id=meeting_id,
                limit=1,
            )
            return len(decisions) > 0
    except ImportError:
        logger.debug("civic.storage not available for cloud check")
    except Exception as e:
        logger.debug(f"Cloud check failed: {e}")
    return False


def extract_decisions_from_meeting(
    meeting: Dict[str, Any],
    output_dir: str,
    jurisdiction_id: str,
    min_stakes: int = 6,
    min_budget: int = 100000,
    cloud: bool = False,
    analyzer: Optional[Any] = None,
) -> DecisionResult:
    """
    Extract decisions from a meeting using RetrospectiveAnalyzer.

    Args:
        meeting: Meeting dictionary with agenda_url
        output_dir: Directory to save decisions (local mode)
        jurisdiction_id: Jurisdiction ID
        min_stakes: Minimum stakes score (1-10)
        min_budget: Minimum budget threshold
        cloud: If True, store to cloud
        analyzer: Optional RetrospectiveAnalyzer instance (reuse for cost tracking)

    Returns:
        DecisionResult with status and details
    """
    meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
    meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]

    cloud_mode = cloud or os.environ.get("DATABASE_URL")

    # Check if already extracted (local first, then cloud)
    output_path = Path(output_dir) / f"decisions_{meeting_id}.json"
    if output_path.exists():
        logger.info(f"  Skipping (already extracted locally): {meeting_id}")
        return DecisionResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="skipped",
        )

    if cloud_mode and decisions_exist_in_cloud(jurisdiction_id, meeting_id):
        logger.info(f"  Skipping (already extracted in cloud): {meeting_id}")
        return DecisionResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="skipped",
        )

    try:
        # Use provided analyzer or create new one
        if analyzer is None:
            from civicos_extraction.processing.retrospective_analyzer import RetrospectiveAnalyzer

            # Import LLM provider from civicos_services (CLI entry point can orchestrate between packages)
            try:
                from civicos_services.core.llm_provider import get_model_for_task
                provider = get_model_for_task('long_document')
            except ImportError:
                logger.error("civic_services package not available for LLM provider")
                return DecisionResult(
                    meeting_id=meeting_id,
                    meeting_date=meeting_date,
                    status="error",
                    error="civic_services not installed (needed for LLM provider)",
                )
            analyzer = RetrospectiveAnalyzer(provider=provider)

        # Skip meetings without minutes — decisions can't be reliably extracted
        # from agendas alone (no outcomes, votes, or actual actions taken).
        # These meetings will be retried when minutes become available.
        if not meeting.get('minutes_url'):
            logger.info(f"  Skipping (no minutes available yet): {meeting_id}")
            return DecisionResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="no_minutes",
            )

        logger.info(f"  Extracting decisions from minutes...")

        # Extract decisions — AgendaDownloadError is raised when the
        # PDF cannot be fetched, distinguishing it from "no decisions found"
        high_stakes_decisions = analyzer.extract_high_stakes_decisions(
            event=meeting,
            min_budget=min_budget,
            min_stakes_score=min_stakes,
        )

        if not high_stakes_decisions:
            logger.info(f"  No high-stakes decisions found")
            return DecisionResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="success",
                decisions_count=0,
            )

        # Convert to storage format
        decisions_data = []
        for i, decision in enumerate(high_stakes_decisions):
            decision_dict = decision.to_dict()
            # Add required fields for storage
            # Namespaced ID format: decision:{jurisdiction}:{meeting_id}:{ordinal}
            # Ordinal is 1-based extraction position, zero-padded to 2 digits
            decision_dict["id"] = f"decision:{jurisdiction_id}:{meeting_id}:{i + 1:02d}"
            decision_dict["meeting_date"] = meeting_date
            decision_dict["meeting_id"] = meeting_id
            decision_dict["agenda_item"] = decision.item_number or decision.item_ref
            decision_dict["summary"] = decision.description
            # Outcome mapping: prefer LLM-extracted outcome, fall back to item_type heuristics
            valid_outcomes = {"approved", "denied", "continued", "withdrawn", "received", "adopted", "other"}
            if decision.extracted_outcome and decision.extracted_outcome in valid_outcomes:
                decision_dict["outcome"] = decision.extracted_outcome
            elif decision.item_type in ("presentation", "discussion"):
                decision_dict["outcome"] = "received"
            elif decision.passed is True:
                decision_dict["outcome"] = "approved"
            elif decision.passed is False:
                decision_dict["outcome"] = "denied"
            else:
                decision_dict["outcome"] = "other"
            decision_dict["item_type"] = getattr(decision, 'item_type', 'action')
            decision_dict["vote"] = decision.vote_results
            decision_dict["topics"] = decision.project_types + decision.keywords_for_matching
            decision_dict["source_documents"] = [
                {"url": decision.agenda_url, "type": "agenda"} if decision.agenda_url else None,
                {"url": decision.minutes_url, "type": "minutes"} if decision.minutes_url else None,
            ]
            decision_dict["source_documents"] = [d for d in decision_dict["source_documents"] if d]
            decision_dict["extraction_method"] = "retrospective_analyzer_gemini"
            decisions_data.append(decision_dict)

        # Store decisions (cloud or local)
        stored_to_cloud = False
        if cloud_mode:
            stored_to_cloud = store_decisions_to_cloud(jurisdiction_id, decisions_data)

        # Also save to local file if not using cloud, or as fallback
        if not stored_to_cloud:
            os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(decisions_data, f, indent=2)

        logger.info(f"  ✓ Extracted {len(decisions_data)} high-stakes decisions")

        return DecisionResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="success",
            decisions_count=len(decisions_data),
        )

    except Exception as e:
        # AgendaDownloadError distinguishes download failures from extraction errors
        from civicos_extraction.processing.retrospective_analyzer import AgendaDownloadError
        if isinstance(e, AgendaDownloadError):
            logger.warning(f"  Agenda download failed: {e}")
        else:
            logger.error(f"  Error extracting decisions: {e}")
        return DecisionResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="error",
            error=str(e),
        )


def store_decisions_to_cloud(
    jurisdiction_id: str, decisions: List[Dict[str, Any]]
) -> bool:
    """
    Store decisions to cloud storage (Postgres).

    Args:
        jurisdiction_id: Jurisdiction ID
        decisions: List of decision dictionaries

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            count = backend.store_decisions(jurisdiction_id, decisions)
            if count > 0:
                logger.info(f"  Stored {count} decisions in cloud storage")
                return True
    except ImportError:
        logger.warning("civic.storage not available, keeping local file only")
    except Exception as e:
        logger.warning(f"Cloud storage failed: {e}, keeping local file only")
    return False


def run_decision_extraction(
    jurisdiction_id: str,
    input_dir: str = "data/meetings",
    output_dir: str = "data/decisions",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    min_stakes: int = 6,
    min_budget: int = 100000,
    cloud: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
    meeting_ids: Optional[List[str]] = None,
) -> Optional[List[DecisionResult]]:
    """
    Run decision extraction for meetings from a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing meeting data
        output_dir: Directory for decision files
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, show what would be processed without extracting
        limit: Maximum meetings to process (0 = no limit)
        min_stakes: Minimum stakes score (1-10)
        min_budget: Minimum budget threshold
        cloud: If True, use cloud storage
        since: Process meetings since this date (YYYY-MM-DD)
        until: Process meetings until this date (YYYY-MM-DD)
        meeting_ids: If set, only process these specific meetings (targeted mode).
            Used by reactive pipeline when minutes appear on specific meetings.

    Returns:
        List of DecisionResult if successful, None if failed
    """
    logger.info(f"Starting decision extraction for {jurisdiction_id}")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")
    if cloud_mode:
        logger.info("Cloud storage mode enabled")

    # Find meetings with agendas
    meetings = find_meetings(jurisdiction_id, input_dir, cloud=cloud_mode, since=since, until=until)

    # Filter to specific meeting IDs if targeted mode
    if meetings and meeting_ids:
        meeting_id_set = set(meeting_ids)
        meetings = [m for m in meetings if (m.get("id") or m.get("meeting_id")) in meeting_id_set]
        logger.info(f"Targeted mode: filtered to {len(meetings)} of {len(meeting_ids)} requested meetings")
    if not meetings:
        return None

    # Sort by date (oldest first for chronological processing)
    meetings = sorted(meetings, key=lambda m: m.get("meeting_date", "") or m.get("meeting_datetime", "")[:10])

    # Check for existing checkpoint (ID-based, not index-based)
    checkpoint_path = checkpoint_path_for_decisions(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    succeeded_ids = set()

    if resume_from:
        logger.info(f"Found checkpoint: {resume_from.items_processed} items processed")
        if resume_from.succeeded_meeting_ids:
            succeeded_ids = set(resume_from.succeeded_meeting_ids)
            logger.info(f"  {len(succeeded_ids)} meetings already succeeded")

    # Filter out already-succeeded meetings
    meetings_to_process = [
        m for m in meetings
        if (m.get("id") or m.get("meeting_id")) not in succeeded_ids
    ]
    logger.info(f"  {len(meetings) - len(meetings_to_process)} meetings skipped (checkpoint)")

    start_index = len(succeeded_ids)

    # Apply limit

    if limit > 0:
        meetings_to_process = meetings_to_process[:limit]
        logger.info(f"Limited to {limit} meetings")

    if dry_run:
        logger.info("Dry-run mode - showing meetings to process:")
        already_extracted = 0
        total_to_extract = 0

        for i, meeting in enumerate(meetings_to_process, start=1):
            meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
            meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
            title = meeting.get("title", "Unknown")[:50]

            # Check both local and cloud
            exists = decisions_exist(meeting_id, output_dir)
            if cloud_mode and not exists:
                exists = decisions_exist_in_cloud(jurisdiction_id, meeting_id)
            status = "(already extracted)" if exists else ""

            if exists:
                already_extracted += 1
            else:
                total_to_extract += 1

            logger.info(f"  [{i}/{len(meetings_to_process)}] {meeting_date} - {title} {status}")

        logger.info(f"Would process {len(meetings_to_process)} meetings")
        logger.info(f"Already extracted: {already_extracted}")
        logger.info(f"To extract: {total_to_extract}")
        logger.info(f"Estimated cost: ${total_to_extract * 0.50:.2f} (assuming ~$0.50/meeting)")
        return None

    # Create shared analyzer for cost tracking across all meetings
    from civicos_extraction.processing.retrospective_analyzer import RetrospectiveAnalyzer

    # Import LLM provider from civicos_services (CLI entry point can orchestrate between packages)
    try:
        from civicos_services.core.llm_provider import get_model_for_task
        provider = get_model_for_task('long_document')
    except ImportError:
        logger.error("civic_services package not available for LLM provider")
        return None
    analyzer = RetrospectiveAnalyzer(provider=provider)

    # Extract decisions
    results = []
    items_processed = start_index
    items_extracted = 0
    items_skipped = 0
    items_failed = 0
    total_decisions = 0

    for i, meeting in enumerate(meetings_to_process, start=start_index + 1):
        meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
        meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
        title = meeting.get("title", "Unknown")[:50]

        logger.info(f"[{i}/{len(meetings)}] {meeting_date} - {title}")

        result = extract_decisions_from_meeting(
            meeting,
            output_dir,
            jurisdiction_id,
            min_stakes=min_stakes,
            min_budget=min_budget,
            cloud=cloud_mode,
            analyzer=analyzer,  # Reuse for cost tracking
        )
        results.append(result)

        if result.status == "success":
            items_extracted += 1
            total_decisions += result.decisions_count
            succeeded_ids.add(meeting_id)
        elif result.status in ("skipped", "no_minutes"):
            items_skipped += 1
            succeeded_ids.add(meeting_id)  # Don't re-process skipped meetings
        else:
            items_failed += 1

        items_processed = i

        # Save checkpoint every 5 meetings (extraction is expensive)
        if i % 5 == 0:
            checkpoint = DecisionCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_meeting_id=meeting_id,
                items_processed=items_processed,
                items_extracted=items_extracted,
                items_skipped=items_skipped,
                items_failed=items_failed,
                total_decisions=total_decisions,
                timestamp=datetime.now().isoformat(),
                succeeded_meeting_ids=sorted(succeeded_ids),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Final checkpoint
    if meetings_to_process:
        last_meeting = meetings_to_process[-1]
        last_meeting_id = last_meeting.get("id") or last_meeting.get("meeting_id", "unknown")
        checkpoint = DecisionCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_meeting_id=last_meeting_id,
            items_processed=items_processed,
            items_extracted=items_extracted,
            items_skipped=items_skipped,
            items_failed=items_failed,
            total_decisions=total_decisions,
            timestamp=datetime.now().isoformat(),
            succeeded_meeting_ids=sorted(succeeded_ids),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Store ETL cost record using actual cost from analyzer
    actual_cost = analyzer.total_cost
    total_tokens = analyzer.total_tokens

    if items_extracted > 0 and cloud_mode:
        try:
            from civicos.storage import get_storage_backend

            backend = get_storage_backend()
            if backend.backend_type == "postgres":
                cost_id = backend.store_etl_cost(
                    pipeline="decisions",
                    jurisdiction_id=jurisdiction_id,
                    items_processed=items_extracted,
                    cost_usd=actual_cost,
                    notes=f"Extracted {total_decisions} decisions from {items_extracted} meetings via {analyzer._model_name} ({total_tokens:,} tokens)",
                )
                logger.info(f"ETL cost recorded (id={cost_id}): ${actual_cost:.4f}")
        except ImportError:
            logger.debug("civic.storage not available for cost tracking")
        except Exception as e:
            logger.warning(f"Failed to record ETL cost: {e}")

    # Summary
    logger.info("=" * 50)
    logger.info(f"Decision Extraction Complete for {jurisdiction_id}")
    logger.info(f"Meetings processed: {len(results)}")
    logger.info(f"Meetings with decisions: {items_extracted}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"Failed: {items_failed}")
    logger.info(f"Total decisions extracted: {total_decisions}")
    logger.info(f"Total tokens: {total_tokens:,}")
    logger.info(f"Total cost: ${actual_cost:.4f}")
    if cloud_mode:
        logger.info("Decisions stored in: cloud (Postgres)")
    else:
        logger.info(f"Decisions stored in: {output_dir}")
    logger.info("=" * 50)

    # Sanity check: flag degraded runs where LLM was never invoked
    non_skipped = items_extracted + items_failed
    if non_skipped > 0 and total_tokens == 0:
        logger.error(
            f"DEGRADED RUN: {non_skipped} meetings processed but 0 LLM tokens used. "
            f"Agenda downloads may be failing silently. "
            f"Failed: {items_failed}, Extracted (0 decisions): {items_extracted}"
        )

    return results


def run_scheduled(
    jurisdiction_id: str,
    input_dir: str,
    output_dir: str,
    checkpoint_dir: str,
    min_stakes: int,
    min_budget: int,
    cloud: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> None:
    """
    Run decision extraction on a schedule.

    Uses the schedule library to run daily at 10am (after transcribe at 9am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting decision extraction scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 10:00")
    if cloud:
        logger.info("Cloud storage mode enabled")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_decision_extraction(
            jurisdiction_id,
            input_dir=input_dir,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
            min_stakes=min_stakes,
            min_budget=min_budget,
            cloud=cloud,
            since=since,
            until=until,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 10am daily (after transcribe at 9am)
    schedule.every().day.at("10:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial decision extraction...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

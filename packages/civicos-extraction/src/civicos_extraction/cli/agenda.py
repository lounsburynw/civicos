"""
Agenda item extraction command for civic-extract CLI.

Extracts actionable agenda items from meeting agendas using LLM analysis.

Usage:
    civic-extract agenda --jurisdiction city-san-rafael
    civic-extract agenda --jurisdiction city-san-rafael --dry-run
    civic-extract agenda --jurisdiction city-san-rafael --limit 5
    civic-extract agenda --jurisdiction city-san-rafael --cloud

Cloud mode (--cloud):
    - Reads meetings from Postgres (requires DATABASE_URL)
    - Stores agenda items in Postgres via store_agenda_items()
    - Falls back to local storage if cloud unavailable

Cost: Uses Gemini for extraction (~$0.10-0.50/meeting depending on agenda size)
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
class AgendaResult:
    """Result of agenda extraction for a meeting."""

    meeting_id: str
    meeting_date: str
    status: str  # "success", "skipped", "error", "no_items"
    items_count: int = 0
    actionable_count: int = 0
    error: Optional[str] = None
    # URLs for post-hoc validation of failures
    meeting_title: Optional[str] = None
    meeting_page_url: Optional[str] = None
    pdf_url: Optional[str] = None
    parse_failure_reason: Optional[str] = None


@dataclass
class AgendaCheckpoint:
    """Checkpoint for agenda extraction progress."""

    jurisdiction_id: str
    last_meeting_id: str
    items_processed: int
    items_extracted: int
    items_skipped: int
    items_failed: int
    total_agenda_items: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgendaCheckpoint":
        return cls(**data)


def add_agenda_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the agenda subcommand to the parser."""
    parser = subparsers.add_parser(
        "agenda",
        help="Extract agenda items from meeting agendas",
        description="Extract actionable agenda items using LLM analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        help="Jurisdiction ID (e.g., city-san-rafael)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show meetings that would be processed, don't actually extract",
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
        "--cloud",
        action="store_true",
        help="Store agenda items in cloud storage (requires DATABASE_URL)",
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


def run_agenda(args: argparse.Namespace) -> int:
    """Run the agenda command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    results = run_agenda_extraction(
        args.jurisdiction,
        checkpoint_dir=args.checkpoint_dir,
        dry_run=args.dry_run,
        limit=args.limit,
        cloud=args.cloud,
        since=args.since,
        until=args.until,
    )

    if results is None and not args.dry_run:
        return 1

    return 0


def find_meetings(
    jurisdiction_id: str, cloud: bool = False,
    since: Optional[str] = None, until: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Find meetings with agenda URLs for agenda item extraction.

    In cloud mode, returns meetings from Postgres.
    In local mode, returns meetings from checkpoint file.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
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

    # Local mode fallback - load from checkpoint file
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

    logger.error(f"No meetings found for {jurisdiction_id}")
    logger.error("Run 'civic-extract discover --cloud' first to ingest meetings")
    return None


def checkpoint_path_for_agenda(jurisdiction_id: str, checkpoint_dir: str) -> Path:
    """Get checkpoint file path for agenda extraction."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"agenda_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: AgendaCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[AgendaCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return AgendaCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def save_extraction_failures(
    failures: List[AgendaResult],
    jurisdiction_id: str,
    checkpoint_dir: str
) -> None:
    """
    Save extraction failures/no-items to a log file for post-hoc validation.

    Creates a JSON file with all meetings that failed to extract items,
    including URLs for manual investigation.
    """
    if not failures:
        return

    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / f"agenda_failures_{jurisdiction_id}.json"

    # Load existing failures
    existing = []
    if log_file.exists():
        try:
            with open(log_file) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    # Add new failures (avoid duplicates by meeting_id)
    existing_ids = {f.get('meeting_id') for f in existing}
    for result in failures:
        if result.meeting_id not in existing_ids:
            existing.append({
                'meeting_id': result.meeting_id,
                'meeting_title': result.meeting_title,
                'meeting_date': result.meeting_date,
                'meeting_page_url': result.meeting_page_url,
                'pdf_url': result.pdf_url,
                'status': result.status,
                'parse_failure_reason': result.parse_failure_reason,
                'error': result.error,
                'timestamp': datetime.now().isoformat()
            })

    # Save updated failures
    with open(log_file, 'w') as f:
        json.dump(existing, f, indent=2)

    logger.info(f"Saved {len(failures)} extraction failures to {log_file}")


def agenda_items_exist_in_cloud(meeting_id: str) -> bool:
    """Check if agenda items exist in cloud storage for a meeting."""
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            items = backend.get_agenda_items(meeting_id=meeting_id, limit=1)
            return len(items) > 0
    except ImportError:
        logger.debug("civic.storage not available for cloud check")
    except Exception as e:
        logger.debug(f"Cloud check failed: {e}")
    return False


def extract_agenda_items_from_meeting(
    meeting: Dict[str, Any],
    jurisdiction_id: str,
    cloud: bool = False,
) -> AgendaResult:
    """
    Extract agenda items from a meeting using AgendaIntegrator.

    Args:
        meeting: Meeting dictionary with agenda_url
        jurisdiction_id: Jurisdiction ID
        cloud: If True, store to cloud

    Returns:
        AgendaResult with status and details
    """
    meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
    meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
    meeting_title = meeting.get("title", "Unknown")
    meeting_page_url = meeting.get("agenda_url")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")

    # Check if already extracted in cloud
    if cloud_mode and agenda_items_exist_in_cloud(meeting_id):
        logger.info(f"  Skipping (already extracted in cloud): {meeting_id}")
        return AgendaResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            meeting_title=meeting_title,
            meeting_page_url=meeting_page_url,
            status="skipped",
        )

    try:
        # Import AgendaIntegrator from local processing module
        from civicos_extraction.processing.agenda_integration import AgendaIntegrator

        # Import LLM provider from civicos_services (CLI entry point can orchestrate between packages)
        try:
            from civicos_services.core.llm_provider import get_model_for_task
            provider = get_model_for_task('long_document')
        except ImportError:
            logger.error("civic_services package not available for LLM provider")
            return AgendaResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="error",
                error="civic_services not installed (needed for LLM provider)",
            )

        if not meeting_page_url:
            logger.info(f"  Skipping (no agenda URL): {meeting_id}")
            return AgendaResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                meeting_title=meeting_title,
                status="skipped",
            )

        logger.info(f"  Extracting agenda items...")

        # Initialize integrator with injected provider
        integrator = AgendaIntegrator(provider=provider)

        # Determine if the agenda_url is already a content URL (HTML agenda or PDF)
        # vs a meeting page that requires discovery of the actual agenda
        content_url = None
        if meeting_page_url:
            url_lower = meeting_page_url.lower()
            is_content_url = (
                url_lower.endswith('.pdf')
                or 'agendaviewer' in url_lower  # Granicus AgendaViewer HTML
                or 'api.civicclerk.com' in url_lower  # CivicClerk API
            )
            if is_content_url:
                content_url = meeting_page_url
                logger.info(f"  Agenda URL is content (skipping discovery): {content_url[:80]}...")

        if not content_url:
            # agenda_url is a meeting page — discover the actual PDF/content URL
            event_for_discovery = meeting.copy()
            event_for_discovery['source_url'] = meeting_page_url

            # Promote _granicus_metadata from full_data if not at top level
            if '_granicus_metadata' not in event_for_discovery:
                full_data = event_for_discovery.get('full_data')
                if full_data:
                    if isinstance(full_data, str):
                        try:
                            full_data = json.loads(full_data)
                        except (json.JSONDecodeError, TypeError):
                            full_data = {}
                    for meta_key in ('_granicus_metadata', '_legistar_metadata', '_civicclerk_metadata'):
                        if meta_key in full_data and meta_key not in event_for_discovery:
                            event_for_discovery[meta_key] = full_data[meta_key]

            event_for_discovery.pop('agenda_url', None)  # Clear so discovery runs

            content_url, content_available = integrator.discover_agenda_url(event_for_discovery)

            if not content_available or not content_url:
                logger.info(f"  No agenda content found at {meeting_page_url[:60]}...")
                return AgendaResult(
                    meeting_id=meeting_id,
                    meeting_date=meeting_date,
                    meeting_title=meeting_title,
                    meeting_page_url=meeting_page_url,
                    status="no_items",
                    parse_failure_reason="No agenda content discovered from meeting page",
                )

        logger.info(f"  Agenda content: {content_url[:80]}...")

        # Extract agenda items from content (PDF or HTML)
        agenda_items = integrator.parse_agenda_content(content_url, meeting)

        if not agenda_items:
            # Get parse failure reason from integrator if available
            parse_reason = getattr(integrator, '_last_parse_error', None)
            if parse_reason:
                logger.info(f"  No agenda items extracted: {parse_reason}")
            else:
                logger.info(f"  No agenda items extracted")
            return AgendaResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                meeting_title=meeting_title,
                meeting_page_url=meeting_page_url,
                pdf_url=pdf_url,
                status="no_items",
                items_count=0,
                actionable_count=0,
                parse_failure_reason=parse_reason or "LLM returned no actionable items",
            )

        # Filter out cancellation notices
        real_items = [item for item in agenda_items if item.item_ref != "CANCELLATION_NOTICE"]

        if not real_items:
            logger.info(f"  Meeting cancelled or no real items")
            return AgendaResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                meeting_title=meeting_title,
                meeting_page_url=meeting_page_url,
                pdf_url=pdf_url,
                status="cancelled",
                items_count=0,
                actionable_count=0,
                parse_failure_reason="Meeting cancelled or only cancellation notice",
            )

        # Convert AgendaItem objects to dictionaries for storage
        items_data = []
        for item in real_items:
            item_dict = {
                "item_ref": item.item_ref,
                "item_number": item.item_ref,
                "title": item.title,
                "description": item.description,
                "actionable": item.actionable,
                "actionable_reason": item.actionable_reason,
                "project_types": item.project_types,
                "participation_mechanisms": item.participation_mechanisms,
                "related_agenda_items": item.related_agenda_items,
                "follows_from": item.follows_from,
                "addresses_issues": item.addresses_issues,
                "policy_chain": item.policy_chain,
            }
            items_data.append(item_dict)

        # Classify stance/comment eligibility via LLM
        try:
            from civicos.storage.actionability import classify_agenda_items
            classifications = classify_agenda_items(items_data)
            for item_dict, classification in zip(items_data, classifications):
                item_dict['stance_eligible'] = classification['stance_eligible']
                item_dict['comment_eligible'] = classification['comment_eligible']
            logger.info(f"  Classified eligibility: {sum(1 for c in classifications if c['stance_eligible'])} stance, {sum(1 for c in classifications if c['comment_eligible'])} comment")
        except Exception as e:
            logger.warning(f"  Eligibility classification failed (items will have NULL flags): {e}")

        # Store agenda items (cloud or local)
        stored_to_cloud = False
        if cloud_mode:
            stored_to_cloud = store_agenda_items_to_cloud(meeting_id, items_data)

        actionable_count = sum(1 for item in real_items if item.actionable)
        logger.info(f"  Extracted {len(items_data)} items ({actionable_count} actionable)")

        return AgendaResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            meeting_title=meeting_title,
            meeting_page_url=meeting_page_url,
            pdf_url=content_url,
            status="success",
            items_count=len(items_data),
            actionable_count=actionable_count,
        )

    except Exception as e:
        logger.error(f"  Error extracting agenda items: {e}")
        return AgendaResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            meeting_title=meeting_title,
            meeting_page_url=meeting_page_url,
            pdf_url=content_url if 'content_url' in dir() else None,
            status="error",
            error=str(e),
        )


def store_agenda_items_to_cloud(
    meeting_id: str, agenda_items: List[Dict[str, Any]]
) -> bool:
    """
    Store agenda items to cloud storage (Postgres).

    Args:
        meeting_id: Meeting ID these items belong to
        agenda_items: List of agenda item dictionaries

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        from civicos.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            count = backend.store_agenda_items(meeting_id, agenda_items)
            if count > 0:
                logger.info(f"  Stored {count} agenda items in cloud storage")
                return True
    except ImportError:
        logger.warning("civic.storage not available, skipping cloud storage")
    except Exception as e:
        logger.warning(f"Cloud storage failed: {e}")
    return False


def run_agenda_extraction(
    jurisdiction_id: str,
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    cloud: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Optional[List[AgendaResult]]:
    """
    Run agenda item extraction for meetings from a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, show what would be processed without extracting
        limit: Maximum meetings to process (0 = no limit)
        cloud: If True, use cloud storage
        since: Process meetings since this date (YYYY-MM-DD)
        until: Process meetings until this date (YYYY-MM-DD)

    Returns:
        List of AgendaResult if successful, None if failed
    """
    logger.info(f"Starting agenda extraction for {jurisdiction_id}")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")
    if cloud_mode:
        logger.info("Cloud storage mode enabled")

    # Find meetings with agendas
    meetings = find_meetings(jurisdiction_id, cloud=cloud_mode, since=since, until=until)
    if not meetings:
        return None

    # Sort by date (oldest first for chronological processing)
    meetings = sorted(meetings, key=lambda m: m.get("meeting_date", "") or m.get("meeting_datetime", "")[:10])

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_agenda(jurisdiction_id, checkpoint_dir)
    resume_from = load_checkpoint(checkpoint_path)
    start_index = 0

    if resume_from:
        logger.info(f"Found checkpoint: {resume_from.items_processed} items processed")
        # Find the index to resume from
        for i, meeting in enumerate(meetings):
            meeting_id = meeting.get("id") or meeting.get("meeting_id")
            if meeting_id == resume_from.last_meeting_id:
                start_index = i + 1
                break
        if start_index > 0:
            logger.info(f"Resuming from meeting {start_index}")

    # Apply limit
    meetings_to_process = meetings[start_index:]
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

            # Check cloud
            exists = False
            if cloud_mode:
                exists = agenda_items_exist_in_cloud(meeting_id)
            status = "(already extracted)" if exists else ""

            if exists:
                already_extracted += 1
            else:
                total_to_extract += 1

            logger.info(f"  [{i}/{len(meetings_to_process)}] {meeting_date} - {title} {status}")

        logger.info(f"Would process {len(meetings_to_process)} meetings")
        logger.info(f"Already extracted: {already_extracted}")
        logger.info(f"To extract: {total_to_extract}")
        logger.info(f"Estimated cost: ${total_to_extract * 0.25:.2f} (assuming ~$0.25/meeting)")
        return None

    # Extract agenda items
    results = []
    failures = []  # Track failures for post-hoc validation
    items_processed = start_index
    items_extracted = 0
    items_skipped = 0
    items_failed = 0
    items_no_items = 0
    items_cancelled = 0
    total_agenda_items = 0

    for i, meeting in enumerate(meetings_to_process, start=start_index + 1):
        meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
        meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
        title = meeting.get("title", "Unknown")[:50]

        logger.info(f"[{i}/{len(meetings)}] {meeting_date} - {title}")

        result = extract_agenda_items_from_meeting(
            meeting,
            jurisdiction_id,
            cloud=cloud_mode,
        )
        results.append(result)

        if result.status == "success":
            items_extracted += 1
            total_agenda_items += result.items_count
        elif result.status == "skipped":
            items_skipped += 1
        elif result.status == "no_items":
            items_no_items += 1
            failures.append(result)  # Track for validation
        elif result.status == "cancelled":
            items_cancelled += 1
        else:  # error
            items_failed += 1
            failures.append(result)  # Track for validation

        items_processed = i

        # Save checkpoint every 5 meetings
        if i % 5 == 0:
            checkpoint = AgendaCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_meeting_id=meeting_id,
                items_processed=items_processed,
                items_extracted=items_extracted,
                items_skipped=items_skipped,
                items_failed=items_failed,
                total_agenda_items=total_agenda_items,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Final checkpoint
    if meetings_to_process:
        last_meeting = meetings_to_process[-1]
        last_meeting_id = last_meeting.get("id") or last_meeting.get("meeting_id", "unknown")
        checkpoint = AgendaCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_meeting_id=last_meeting_id,
            items_processed=items_processed,
            items_extracted=items_extracted,
            items_skipped=items_skipped,
            items_failed=items_failed,
            total_agenda_items=total_agenda_items,
            timestamp=datetime.now().isoformat(),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Save failures for post-hoc validation
    if failures:
        save_extraction_failures(failures, jurisdiction_id, checkpoint_dir)

    # Summary
    logger.info("=" * 50)
    logger.info(f"Agenda Extraction Complete for {jurisdiction_id}")
    logger.info(f"Meetings processed: {len(results)}")
    logger.info(f"Meetings with items: {items_extracted}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"No items extracted: {items_no_items}")
    logger.info(f"Cancelled meetings: {items_cancelled}")
    logger.info(f"Errors: {items_failed}")
    logger.info(f"Total agenda items extracted: {total_agenda_items}")
    if cloud_mode:
        logger.info("Agenda items stored in: cloud (Postgres)")
    if failures:
        logger.info(f"Failures logged to: {checkpoint_dir}/agenda_failures_{jurisdiction_id}.json")
    logger.info("=" * 50)

    return results

"""
Chunk extraction command for civic-extract CLI.

Extracts text chunks from meeting agenda PDFs for RAG search.

Usage:
    civic-extract chunks --jurisdiction city-san-rafael
    civic-extract chunks --jurisdiction city-san-rafael --schedule
    civic-extract chunks --jurisdiction city-san-rafael --dry-run
    civic-extract chunks --jurisdiction city-san-rafael --limit 5
    civic-extract chunks --jurisdiction city-san-rafael --cloud

Cloud mode (--cloud):
    - Reads meetings from Postgres (requires DATABASE_URL)
    - Stores chunks in Postgres via store_chunks()
    - Falls back to local storage if cloud unavailable
"""

import argparse
import concurrent.futures
import json
import logging
import os
import signal
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests

# Default timeout for PDF parsing (5 minutes)
PDF_PARSE_TIMEOUT_SECONDS = 300

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class ChunksResult:
    """Result of a chunk extraction."""

    meeting_id: str
    meeting_date: str
    status: str  # "success", "skipped", "error"
    chunks_count: int = 0
    error: Optional[str] = None


@dataclass
class ChunksCheckpoint:
    """Checkpoint for chunk extraction progress."""

    jurisdiction_id: str
    last_meeting_id: str
    items_processed: int
    items_extracted: int
    items_skipped: int
    items_failed: int
    total_chunks: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChunksCheckpoint":
        return cls(**data)


def add_chunks_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add the chunks subcommand to the parser."""
    parser = subparsers.add_parser(
        "chunks",
        help="Extract text chunks from meeting agenda PDFs",
        description="Extract PDF chunks for RAG search",
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
        default="data/chunks",
        help="Directory for chunk files (default: data/chunks)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show meetings that would be processed, don't actually extract",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on schedule (daily at 11am) instead of once",
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
        help="Store chunks in cloud storage (requires DATABASE_URL)",
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
    parser.add_argument(
        "--timeout",
        type=int,
        default=PDF_PARSE_TIMEOUT_SECONDS,
        help=f"PDF parsing timeout in seconds (default: {PDF_PARSE_TIMEOUT_SECONDS})",
    )


def run_chunks(args: argparse.Namespace) -> int:
    """Run the chunks command."""
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.schedule:
        run_scheduled(
            args.jurisdiction,
            args.input_dir,
            args.output_dir,
            args.checkpoint_dir,
            cloud=args.cloud,
            since=args.since,
            until=args.until,
        )
        return 0  # Never reached (scheduler runs forever)
    else:
        results = run_chunk_extraction(
            args.jurisdiction,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            checkpoint_dir=args.checkpoint_dir,
            dry_run=args.dry_run,
            limit=args.limit,
            cloud=args.cloud,
            since=args.since,
            until=args.until,
            timeout=args.timeout,
        )

        if results is None and not args.dry_run:
            return 1

        return 0


def find_meetings(
    jurisdiction_id: str, input_dir: str, cloud: bool = False,
    since: Optional[str] = None, until: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Find meetings with agenda URLs for chunk extraction.

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
            from civic.storage import get_storage_backend
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


def checkpoint_path_for_chunks(jurisdiction_id: str, checkpoint_dir: str) -> Path:
    """Get checkpoint file path for chunk extraction."""
    path = Path(checkpoint_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chunks_{jurisdiction_id}.json"


def save_checkpoint(checkpoint: ChunksCheckpoint, path: Path) -> None:
    """Save checkpoint to file."""
    with open(path, "w") as f:
        json.dump(checkpoint.to_dict(), f, indent=2)


def load_checkpoint(path: Path) -> Optional[ChunksCheckpoint]:
    """Load checkpoint from file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        return ChunksCheckpoint.from_dict(data)
    except Exception as e:
        logger.warning(f"Error loading checkpoint: {e}")
        return None


def chunks_exist(meeting_id: str, output_dir: str) -> bool:
    """Check if chunks already exist for a meeting."""
    output_path = Path(output_dir) / f"chunks_{meeting_id}.json"
    return output_path.exists()


def chunks_exist_in_cloud(jurisdiction_id: str, meeting_id: str) -> bool:
    """Check if chunks exist in cloud storage for a meeting."""
    try:
        from civic.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            chunks = backend.get_chunks(
                jurisdiction_id,
                meeting_id=meeting_id,
                limit=1,
            )
            return len(chunks) > 0
    except ImportError:
        logger.debug("civic.storage not available for cloud check")
    except Exception as e:
        logger.debug(f"Cloud check failed: {e}")
    return False


class DownloadResult:
    """Result of downloading a file with validation info."""

    def __init__(
        self,
        content: Optional[bytes],
        content_type: str = "",
        is_valid_pdf: bool = False,
        validation_warnings: Optional[list] = None,
    ):
        self.content = content
        self.content_type = content_type
        self.is_valid_pdf = is_valid_pdf
        self.validation_warnings = validation_warnings or []


def validate_pdf_content(content: bytes, content_type: str, url: str) -> tuple[bool, list]:
    """
    Validate that downloaded content is actually a PDF.

    Detects degenerate case where HTML meeting pages are downloaded
    instead of actual PDF documents.

    Args:
        content: Downloaded bytes
        content_type: HTTP Content-Type header
        url: Source URL (for logging)

    Returns:
        Tuple of (is_valid_pdf, list of warning messages)
    """
    warnings = []
    is_valid = True

    # Check 1: Content-Type header
    if "pdf" not in content_type.lower():
        if "html" in content_type.lower():
            warnings.append(
                f"DEGENERATE CASE: Content-Type is HTML ({content_type}), not PDF. "
                "URL may be a meeting page, not a direct PDF link."
            )
            is_valid = False
        elif content_type:
            warnings.append(f"Unexpected Content-Type: {content_type}")

    # Check 2: PDF magic bytes (should start with %PDF-)
    if content[:5] != b"%PDF-":
        # Check if it looks like HTML
        content_start = content[:100].lower()
        if b"<!doctype" in content_start or b"<html" in content_start:
            warnings.append(
                "DEGENERATE CASE: Content starts with HTML, not PDF magic bytes. "
                "Downloaded HTML page instead of PDF document."
            )
            is_valid = False
        else:
            warnings.append(
                f"Content does not start with PDF magic bytes. First 20 bytes: {content[:20]}"
            )
            is_valid = False

    # Check 3: File size (agenda packets are typically > 100KB, HTML pages are < 200KB)
    size_kb = len(content) / 1024
    if size_kb < 50:
        warnings.append(
            f"DEGENERATE CASE: File size ({size_kb:.1f}KB) is suspiciously small for an agenda packet. "
            "Real agenda PDFs are typically 100KB-15MB."
        )
        # Don't mark invalid just for size, but flag it

    return is_valid, warnings


def download_pdf(url: str, timeout: int = 60) -> Optional[bytes]:
    """
    Download a PDF from URL.

    Args:
        url: URL of the PDF
        timeout: Request timeout in seconds

    Returns:
        PDF bytes if successful, None otherwise

    Note:
        Use download_and_validate_pdf() for full validation with degenerate case detection.
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.warning(f"URL may not be a PDF (content-type: {content_type})")

        return response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download PDF: {e}")
        return None


def extract_pdf_urls_from_meeting_page(meeting_page_url: str) -> dict[str, Optional[str]]:
    """
    Parse an HTML meeting page to extract actual PDF URLs.

    When agenda_url points to an HTML meeting page (not a direct PDF),
    this function scrapes the page to find links to actual PDFs.

    Args:
        meeting_page_url: URL of the meeting page (HTML)

    Returns:
        Dict with 'agenda_packet_url' and 'minutes_url' (both may be None)
    """
    from bs4 import BeautifulSoup

    result = {
        'agenda_packet_url': None,
        'minutes_url': None,
    }

    try:
        response = requests.get(meeting_page_url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch meeting page: {e}")
        return result

    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract all PDF URLs from the page
    pdf_urls = []

    # Links with .pdf in href
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if '.pdf' in href.lower():
            # Make absolute URL
            if href.startswith('http'):
                pdf_urls.append(href)
            elif href.startswith('/'):
                # Extract base URL from meeting_page_url
                from urllib.parse import urlparse
                parsed = urlparse(meeting_page_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                pdf_urls.append(f"{base_url}{href}")

    # Embeds and iframes
    for tag in soup.find_all(['embed', 'iframe']):
        src = tag.get('src', '')
        if '.pdf' in src.lower():
            if src.startswith('http'):
                pdf_urls.append(src)
            elif src.startswith('/'):
                from urllib.parse import urlparse
                parsed = urlparse(meeting_page_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                pdf_urls.append(f"{base_url}{src}")

    logger.debug(f"Found {len(pdf_urls)} PDF links on meeting page")

    # Pattern match for agenda packet
    import re
    agenda_packet_patterns = [
        r'agenda-packet.*\.pdf',
        r'full.*packet.*\.pdf',
        r'complete.*agenda.*\.pdf',
        r'packet.*\d{4}-\d{2}-\d{2}.*\.pdf',
    ]

    for pattern in agenda_packet_patterns:
        for url in pdf_urls:
            if re.search(pattern, url, re.I):
                result['agenda_packet_url'] = url
                logger.info(f"  Found agenda packet: {url[:80]}...")
                break
        if result['agenda_packet_url']:
            break

    # Try #tab-agenda-packet section (ProudCity pattern)
    if not result['agenda_packet_url']:
        agenda_packet_tab = soup.find('div', {'id': 'tab-agenda-packet'})
        if agenda_packet_tab:
            for link in agenda_packet_tab.find_all('a', href=True):
                href = link.get('href', '')
                if '.pdf' in href.lower():
                    if href.startswith('http'):
                        result['agenda_packet_url'] = href
                    elif href.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(meeting_page_url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        result['agenda_packet_url'] = f"{base_url}{href}"
                    logger.info(f"  Found agenda packet in tab: {result['agenda_packet_url'][:80]}...")
                    break

    # Pattern match for minutes
    minutes_patterns = [
        r'cc-minutes.*\d{4}-\d{2}-\d{2}.*\.pdf',
        r'minutes-\d{4}-\d{2}-\d{2}.*\.pdf',
        r'\d{8}-cc-minutes.*\.pdf',
    ]

    for pattern in minutes_patterns:
        for url in pdf_urls:
            if re.search(pattern, url, re.I):
                result['minutes_url'] = url
                break
        if result['minutes_url']:
            break

    # Try #tab-minutes section
    if not result['minutes_url']:
        minutes_tab = soup.find('div', {'id': 'tab-minutes'})
        if minutes_tab:
            for link in minutes_tab.find_all('a', href=True):
                href = link.get('href', '')
                if '.pdf' in href.lower():
                    if href.startswith('http'):
                        result['minutes_url'] = href
                    elif href.startswith('/'):
                        from urllib.parse import urlparse
                        parsed = urlparse(meeting_page_url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"
                        result['minutes_url'] = f"{base_url}{href}"
                    break

    return result


def download_and_validate_pdf(url: str, timeout: int = 60) -> DownloadResult:
    """
    Download a PDF from URL with full validation.

    Detects degenerate cases where HTML pages are downloaded instead of PDFs.

    Args:
        url: URL of the PDF
        timeout: Request timeout in seconds

    Returns:
        DownloadResult with content, validation status, and any warnings
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        content = response.content

        is_valid, warnings = validate_pdf_content(content, content_type, url)

        # Log warnings
        for warning in warnings:
            if "DEGENERATE CASE" in warning:
                logger.error(warning)
            else:
                logger.warning(warning)

        return DownloadResult(
            content=content,
            content_type=content_type,
            is_valid_pdf=is_valid,
            validation_warnings=warnings,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download PDF: {e}")
        return DownloadResult(content=None, validation_warnings=[str(e)])


class PDFParseTimeoutError(Exception):
    """Raised when PDF parsing exceeds the timeout."""
    pass


def _parse_pdf_with_timeout(
    parser,
    temp_path: str,
    source_metadata: dict,
    timeout_seconds: int = PDF_PARSE_TIMEOUT_SECONDS,
) -> list:
    """
    Parse a PDF with timeout protection.

    Uses concurrent.futures for cross-platform timeout handling.
    Falls back to signal-based timeout on Unix if available.

    Args:
        parser: AgendaPacketParser instance
        temp_path: Path to the temporary PDF file
        source_metadata: Metadata to attach to chunks
        timeout_seconds: Maximum time to allow for parsing

    Returns:
        List of AgendaChunk objects

    Raises:
        PDFParseTimeoutError: If parsing exceeds timeout
        Exception: Any exception from the parser
    """
    def parse_pdf():
        return parser.parse_to_chunks(temp_path, source_metadata=source_metadata)

    # Use ThreadPoolExecutor for timeout (works on all platforms)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(parse_pdf)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            # Cancel the future (won't actually stop the thread, but marks it)
            future.cancel()
            raise PDFParseTimeoutError(
                f"PDF parsing timed out after {timeout_seconds} seconds"
            )


def extract_chunks_from_meeting(
    meeting: Dict[str, Any],
    output_dir: str,
    jurisdiction_id: str,
    cloud: bool = False,
    timeout: int = PDF_PARSE_TIMEOUT_SECONDS,
) -> ChunksResult:
    """
    Extract chunks from a meeting's agenda PDF.

    Args:
        meeting: Meeting dictionary with agenda_url
        output_dir: Directory to save chunks (local mode)
        jurisdiction_id: Jurisdiction ID
        cloud: If True, store to cloud
        timeout: PDF parsing timeout in seconds

    Returns:
        ChunksResult with status and details
    """
    meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
    meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
    agenda_url = meeting.get("agenda_url")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")

    # Check if already extracted (local first, then cloud)
    output_path = Path(output_dir) / f"chunks_{meeting_id}.json"
    if output_path.exists():
        logger.info(f"  Skipping (already extracted locally): {meeting_id}")
        return ChunksResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="skipped",
        )

    if cloud_mode and chunks_exist_in_cloud(jurisdiction_id, meeting_id):
        logger.info(f"  Skipping (already extracted in cloud): {meeting_id}")
        return ChunksResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="skipped",
        )

    if not agenda_url:
        logger.warning(f"  No agenda URL for meeting: {meeting_id}")
        return ChunksResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="error",
            error="No agenda URL",
        )

    try:
        # Import PDF parser
        try:
            from civic._internal.meetings.pdf_parser import AgendaPacketParser
        except ImportError:
            logger.error("civic package not available for PDF parsing")
            return ChunksResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="error",
                error="civic package not installed",
            )

        logger.info(f"  Downloading PDF from {agenda_url[:60]}...")

        # Download PDF with validation
        download_result = download_and_validate_pdf(agenda_url)
        if not download_result.content:
            return ChunksResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="error",
                error="Failed to download PDF",
            )

        # Check for degenerate case (HTML instead of PDF)
        if not download_result.is_valid_pdf:
            degenerate_warnings = [w for w in download_result.validation_warnings if "DEGENERATE" in w]
            if degenerate_warnings:
                logger.info(
                    f"  Detected HTML meeting page (not direct PDF). "
                    "Parsing page to find actual PDF links..."
                )

                # Parse the meeting page to extract actual PDF URLs
                pdf_urls = extract_pdf_urls_from_meeting_page(agenda_url)

                actual_pdf_url = pdf_urls.get('agenda_packet_url')
                if not actual_pdf_url:
                    # Try minutes as fallback
                    actual_pdf_url = pdf_urls.get('minutes_url')
                    if actual_pdf_url:
                        logger.info(f"  No agenda packet found, using minutes PDF")

                if not actual_pdf_url:
                    logger.warning(
                        f"  No PDF links found on meeting page: {agenda_url[:60]}..."
                    )
                    return ChunksResult(
                        meeting_id=meeting_id,
                        meeting_date=meeting_date,
                        status="error",
                        error="No PDF links found on meeting page",
                    )

                # Download the actual PDF
                logger.info(f"  Downloading actual PDF: {actual_pdf_url[:60]}...")
                download_result = download_and_validate_pdf(actual_pdf_url)
                if not download_result.content:
                    return ChunksResult(
                        meeting_id=meeting_id,
                        meeting_date=meeting_date,
                        status="error",
                        error=f"Failed to download PDF from {actual_pdf_url[:60]}",
                    )

                if not download_result.is_valid_pdf:
                    logger.warning(
                        f"  Downloaded content still not a valid PDF"
                    )
                    return ChunksResult(
                        meeting_id=meeting_id,
                        meeting_date=meeting_date,
                        status="error",
                        error="Extracted PDF URL did not return valid PDF content",
                    )

                # Update agenda_url for source tracking
                agenda_url = actual_pdf_url

        pdf_bytes = download_result.content

        # Save to temp file for parsing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = temp_file.name

        try:
            pdf_size_mb = len(pdf_bytes) / (1024 * 1024)
            logger.info(f"  Parsing PDF ({len(pdf_bytes):,} bytes / {pdf_size_mb:.1f} MB)...")

            # Parse PDF into chunks with timeout protection
            parser = AgendaPacketParser()
            source_metadata = {
                "source_file": agenda_url,
                "source_type": "agenda_packet",
            }

            try:
                agenda_chunks = _parse_pdf_with_timeout(
                    parser,
                    temp_path,
                    source_metadata,
                    timeout_seconds=timeout,
                )
            except PDFParseTimeoutError as e:
                logger.warning(f"  ⏱ PDF parsing timed out ({pdf_size_mb:.1f} MB PDF)")
                return ChunksResult(
                    meeting_id=meeting_id,
                    meeting_date=meeting_date,
                    status="error",
                    error=f"Timeout: PDF too large/complex ({pdf_size_mb:.1f} MB)",
                )

            if not agenda_chunks:
                logger.info(f"  No chunks extracted from PDF")
                return ChunksResult(
                    meeting_id=meeting_id,
                    meeting_date=meeting_date,
                    status="success",
                    chunks_count=0,
                )

            # Convert to storage format
            chunks_data = []
            for i, chunk in enumerate(agenda_chunks):
                chunk_dict = chunk.to_dict()
                # Add required fields for storage
                chunk_dict["id"] = f"chunk-{meeting_id}-{i}"
                chunk_dict["meeting_id"] = meeting_id
                chunks_data.append(chunk_dict)

            # Store chunks (cloud or local)
            stored_to_cloud = False
            if cloud_mode:
                stored_to_cloud = store_chunks_to_cloud(jurisdiction_id, chunks_data, meeting_id=meeting_id)

            # Also save to local file if not using cloud, or as fallback
            if not stored_to_cloud:
                os.makedirs(output_dir, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(chunks_data, f, indent=2)

            logger.info(f"  ✓ Extracted {len(chunks_data)} chunks")

            return ChunksResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="success",
                chunks_count=len(chunks_data),
            )

        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    except Exception as e:
        logger.error(f"  Error extracting chunks: {e}")
        return ChunksResult(
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            status="error",
            error=str(e),
        )


def store_chunks_to_cloud(
    jurisdiction_id: str, chunks: List[Dict[str, Any]], meeting_id: Optional[str] = None
) -> bool:
    """
    Store chunks to cloud storage (Postgres).

    Args:
        jurisdiction_id: Jurisdiction ID
        chunks: List of chunk dictionaries
        meeting_id: If provided, only replace chunks for this meeting (incremental mode)

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        from civic.storage import get_storage_backend

        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            count = backend.store_chunks(jurisdiction_id, chunks, meeting_id=meeting_id)
            if count > 0:
                logger.info(f"  Stored {count} chunks in cloud storage")
                return True
    except ImportError:
        logger.warning("civic.storage not available, keeping local file only")
    except Exception as e:
        logger.warning(f"Cloud storage failed: {e}, keeping local file only")
    return False


def run_chunk_extraction(
    jurisdiction_id: str,
    input_dir: str = "data/meetings",
    output_dir: str = "data/chunks",
    checkpoint_dir: str = "data/checkpoints",
    dry_run: bool = False,
    limit: int = 0,
    cloud: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
    timeout: int = PDF_PARSE_TIMEOUT_SECONDS,
) -> Optional[List[ChunksResult]]:
    """
    Run chunk extraction for meetings from a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-san-rafael")
        input_dir: Directory containing meeting data
        output_dir: Directory for chunk files
        checkpoint_dir: Directory for checkpoint files
        dry_run: If True, show what would be processed without extracting
        limit: Maximum meetings to process (0 = no limit)
        cloud: If True, use cloud storage
        since: Process meetings since this date (YYYY-MM-DD)
        until: Process meetings until this date (YYYY-MM-DD)
        timeout: PDF parsing timeout in seconds

    Returns:
        List of ChunksResult if successful, None if failed
    """
    logger.info(f"Starting chunk extraction for {jurisdiction_id}")

    cloud_mode = cloud or os.environ.get("DATABASE_URL")
    if cloud_mode:
        logger.info("Cloud storage mode enabled")

    # Find meetings with agendas
    meetings = find_meetings(jurisdiction_id, input_dir, cloud=cloud_mode, since=since, until=until)
    if not meetings:
        return None

    # Sort by date (oldest first for chronological processing)
    meetings = sorted(meetings, key=lambda m: m.get("meeting_date", "") or m.get("meeting_datetime", "")[:10])

    # Check for existing checkpoint
    checkpoint_path = checkpoint_path_for_chunks(jurisdiction_id, checkpoint_dir)
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

            # Check both local and cloud
            exists = chunks_exist(meeting_id, output_dir)
            if cloud_mode and not exists:
                exists = chunks_exist_in_cloud(jurisdiction_id, meeting_id)
            status = "(already extracted)" if exists else ""

            if exists:
                already_extracted += 1
            else:
                total_to_extract += 1

            logger.info(f"  [{i}/{len(meetings_to_process)}] {meeting_date} - {title} {status}")

        logger.info(f"Would process {len(meetings_to_process)} meetings")
        logger.info(f"Already extracted: {already_extracted}")
        logger.info(f"To extract: {total_to_extract}")
        return None

    # Extract chunks
    results = []
    items_processed = start_index
    items_extracted = 0
    items_skipped = 0
    items_failed = 0
    total_chunks = 0

    for i, meeting in enumerate(meetings_to_process, start=start_index + 1):
        meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
        meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
        title = meeting.get("title", "Unknown")[:50]

        logger.info(f"[{i}/{len(meetings)}] {meeting_date} - {title}")

        result = extract_chunks_from_meeting(
            meeting,
            output_dir,
            jurisdiction_id,
            cloud=cloud_mode,
            timeout=timeout,
        )
        results.append(result)

        if result.status == "success":
            items_extracted += 1
            total_chunks += result.chunks_count
        elif result.status == "skipped":
            items_skipped += 1
        else:
            items_failed += 1

        items_processed = i

        # Save checkpoint every 3 meetings (PDFs can be slow)
        if i % 3 == 0:
            checkpoint = ChunksCheckpoint(
                jurisdiction_id=jurisdiction_id,
                last_meeting_id=meeting_id,
                items_processed=items_processed,
                items_extracted=items_extracted,
                items_skipped=items_skipped,
                items_failed=items_failed,
                total_chunks=total_chunks,
                timestamp=datetime.now().isoformat(),
            )
            save_checkpoint(checkpoint, checkpoint_path)
            logger.debug(f"Checkpoint saved: {items_processed} processed")

    # Final checkpoint
    if meetings_to_process:
        last_meeting = meetings_to_process[-1]
        last_meeting_id = last_meeting.get("id") or last_meeting.get("meeting_id", "unknown")
        checkpoint = ChunksCheckpoint(
            jurisdiction_id=jurisdiction_id,
            last_meeting_id=last_meeting_id,
            items_processed=items_processed,
            items_extracted=items_extracted,
            items_skipped=items_skipped,
            items_failed=items_failed,
            total_chunks=total_chunks,
            timestamp=datetime.now().isoformat(),
        )
        save_checkpoint(checkpoint, checkpoint_path)

    # Summary
    logger.info("=" * 50)
    logger.info(f"Chunk Extraction Complete for {jurisdiction_id}")
    logger.info(f"Meetings processed: {len(results)}")
    logger.info(f"Meetings with chunks: {items_extracted}")
    logger.info(f"Skipped (already exist): {items_skipped}")
    logger.info(f"Failed: {items_failed}")
    logger.info(f"Total chunks extracted: {total_chunks}")
    if cloud_mode:
        logger.info("Chunks stored in: cloud (Postgres)")
    else:
        logger.info(f"Chunks stored in: {output_dir}")
    logger.info("=" * 50)

    return results


def run_scheduled(
    jurisdiction_id: str,
    input_dir: str,
    output_dir: str,
    checkpoint_dir: str,
    cloud: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> None:
    """
    Run chunk extraction on a schedule.

    Uses the schedule library to run daily at 11am (after decisions at 10am).
    """
    try:
        import schedule
        import time as time_module
    except ImportError:
        logger.error("schedule library not installed. Run: pip install schedule")
        sys.exit(1)

    logger.info(f"Starting chunk extraction scheduler for {jurisdiction_id}")
    logger.info("Will run daily at 11:00")
    if cloud:
        logger.info("Cloud storage mode enabled")

    def job():
        logger.info("=" * 50)
        logger.info("Scheduled run starting")
        run_chunk_extraction(
            jurisdiction_id,
            input_dir=input_dir,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
            cloud=cloud,
            since=since,
            until=until,
        )
        logger.info("Scheduled run complete")
        logger.info("=" * 50)

    # Schedule for 11am daily (after decisions at 10am)
    schedule.every().day.at("11:00").do(job)

    # Also run once immediately on startup
    logger.info("Running initial chunk extraction...")
    job()

    logger.info("Scheduler active. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time_module.sleep(60)  # Check every minute

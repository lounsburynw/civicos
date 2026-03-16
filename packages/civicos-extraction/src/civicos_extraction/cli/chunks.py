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
import re
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
    succeeded_meeting_ids: List[str] = None  # Track which meetings succeeded

    def __post_init__(self):
        if self.succeeded_meeting_ids is None:
            self.succeeded_meeting_ids = []

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChunksCheckpoint":
        # Handle old checkpoints without succeeded_meeting_ids
        if "succeeded_meeting_ids" not in data:
            data["succeeded_meeting_ids"] = []
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
        from civicos.storage import get_storage_backend

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


def extract_chunks_from_html_agenda(
    agenda_url: str,
    meeting_id: str,
    max_chunk_chars: int = 1500,
) -> List[Dict[str, Any]]:
    """
    Extract text chunks from an HTML agenda page (e.g., Granicus AgendaViewer).

    Falls back to this when no PDF is available. Parses the HTML page for
    structured agenda content and splits into chunks compatible with the
    storage format.

    Returns list of chunk dicts ready for storage, or empty list if extraction fails.
    """
    from bs4 import BeautifulSoup

    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    })

    try:
        resp = session.get(agenda_url, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.warning(f"  Failed to fetch HTML agenda: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script/style tags
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    # Strategy 1: Try structured table extraction (Granicus AgendaViewer uses tables)
    sections = _extract_agenda_sections_from_html(soup)

    # Strategy 2: Fall back to body text if no structured sections found
    if not sections:
        body_text = soup.get_text(separator="\n", strip=True)
        # Filter out very short pages (nav-only, error pages, etc.)
        if len(body_text) < 200:
            logger.warning(f"  HTML agenda page has too little text ({len(body_text)} chars)")
            return []
        sections = [{"item": "1", "title": "Meeting Agenda", "text": body_text}]

    # Convert sections to chunks
    chunks = []
    chunk_idx = 0
    for section in sections:
        text = section["text"].strip()
        if not text or len(text) < 20:
            continue

        # Split large sections into multiple chunks
        if len(text) <= max_chunk_chars:
            text_parts = [text]
        else:
            text_parts = _split_text_into_chunks(text, max_chunk_chars)

        for i, part in enumerate(text_parts):
            chunks.append({
                "id": f"chunk-{meeting_id}-{chunk_idx}",
                "meeting_id": meeting_id,
                "text": part,
                "agenda_item": section["item"],
                "agenda_title": section["title"],
                "page_start": 0,
                "page_end": 0,
                "chunk_index": chunk_idx,
                "total_chunks": len(text_parts),
                "metadata": {
                    "source_file": agenda_url,
                    "source_type": "html_agenda",
                },
            })
            chunk_idx += 1

    return chunks


def _extract_agenda_sections_from_html(soup) -> List[Dict[str, str]]:
    """Extract structured agenda sections from HTML.

    Handles Granicus AgendaViewer table format and generic heading-based
    structures. Returns list of dicts with 'item', 'title', 'text' keys.
    """
    sections = []

    # Granicus AgendaViewer: content is in nested tables with class patterns
    # Look for rows that represent agenda items
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                # Heuristic: first cell is item number, rest is content
                first_text = cells[0].get_text(strip=True)
                rest_text = " ".join(c.get_text(separator=" ", strip=True) for c in cells[1:])

                # Check if first cell looks like an agenda item number
                if re.match(r"^[A-Z]?\d+\.?[a-z]?\.?$", first_text) and len(rest_text) > 20:
                    sections.append({
                        "item": first_text,
                        "title": rest_text[:120],
                        "text": rest_text,
                    })

    # If table extraction found items, return them
    if sections:
        return sections

    # Fallback: look for heading-based structure (h2, h3, h4 followed by content)
    item_counter = 1
    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = heading.get_text(strip=True)
        if not title:
            continue

        # Collect text until next heading
        content_parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h2", "h3", "h4"]:
                break
            text = sibling.get_text(separator=" ", strip=True)
            if text:
                content_parts.append(text)

        if content_parts:
            sections.append({
                "item": str(item_counter),
                "title": title[:120],
                "text": f"{title}\n\n" + "\n".join(content_parts),
            })
            item_counter += 1

    return sections


def _split_text_into_chunks(text: str, max_chars: int, overlap: int = 200) -> List[str]:
    """Split text into chunks at paragraph boundaries with overlap."""
    paragraphs = text.split("\n")
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para) + 1  # +1 for newline
        if current_len + para_len > max_chars and current:
            chunks.append("\n".join(current))
            # Keep last paragraph(s) for overlap
            overlap_parts = []
            overlap_len = 0
            for p in reversed(current):
                if overlap_len + len(p) > overlap:
                    break
                overlap_parts.insert(0, p)
                overlap_len += len(p)
            current = overlap_parts
            current_len = overlap_len
        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n".join(current))

    return chunks if chunks else [text[:max_chars]]


def _classify_agenda_link(
    links: List[Dict[str, str]],
) -> Optional[str]:
    """Identify the main agenda PDF from a list of document links.

    Uses simple keyword heuristics first (free, fast), then falls back to
    LLM classification if no match is found.

    Args:
        links: List of {'url': str, 'label': str}

    Returns:
        URL of the main agenda PDF, or None
    """
    labels = [(l['label'].lower(), l['url']) for l in links]

    # Heuristic: label starts with "agenda" (Mill Valley pattern)
    for label, url in labels:
        if label.startswith('agenda'):
            logger.info(f"  Found agenda PDF via label: {url[:80]}...")
            return url

    # Heuristic: label contains "full agenda" or "agenda packet"
    for label, url in labels:
        if 'full agenda' in label or 'agenda packet' in label:
            logger.info(f"  Found agenda PDF via label: {url[:80]}...")
            return url

    # LLM fallback: ask which link is the main meeting agenda
    if len(links) > 1:
        try:
            from civicos_services.core.llm_provider import get_model_for_task

            model = get_model_for_task("fast")
            link_list = "\n".join(
                f"{i}: {l['label']}" for i, l in enumerate(links)
            )
            prompt = (
                "Given these document links from a government meeting page, "
                "which ONE is most likely the main meeting agenda document? "
                "Return ONLY the number (0-indexed). If none is an agenda, "
                "return -1.\n\n"
                f"{link_list}"
            )
            resp = model.generate(prompt)
            text = resp.strip().strip('.')
            # Extract just the number
            import re
            match = re.search(r'-?\d+', text)
            if match:
                idx = int(match.group())
                if 0 <= idx < len(links):
                    url = links[idx]['url']
                    logger.info(
                        f"  LLM identified agenda: {links[idx]['label'][:50]} → {url[:60]}..."
                    )
                    return url
        except (ImportError, Exception) as e:
            logger.debug(f"LLM agenda classification unavailable: {e}")

    return None


def _llm_classify_pdf_links(
    pdf_urls: List[str],
) -> Optional[Dict[str, Optional[str]]]:
    """Use LLM to classify PDF URLs by purpose (agenda, minutes, etc.).

    Called as a fallback when regex patterns fail to identify agenda/minutes
    PDFs from their filenames. Works across different naming conventions
    and languages.

    Args:
        pdf_urls: List of PDF URLs to classify

    Returns:
        Dict with 'agenda_packet_url' and 'minutes_url', or None if LLM unavailable
    """
    if not pdf_urls:
        return None

    try:
        from civicos_services.core.llm_provider import get_model_for_task
    except ImportError:
        return None

    try:
        model = get_model_for_task("fast")

        # Extract just filenames for classification (cheaper, less noise)
        from urllib.parse import urlparse, unquote
        filenames = []
        for url in pdf_urls:
            path = unquote(urlparse(url).path)
            filename = path.split('/')[-1] if '/' in path else path
            filenames.append(filename)

        file_list = "\n".join(
            f"{i}: {fn}" for i, fn in enumerate(filenames)
        )
        prompt = (
            "Classify these PDF filenames from a government meeting page.\n"
            "Return JSON with two keys:\n"
            '  "agenda": index of the main agenda/agenda packet (-1 if none)\n'
            '  "minutes": index of the meeting minutes (-1 if none)\n\n'
            f"{file_list}\n\n"
            "Return ONLY the JSON object."
        )

        import json
        resp = model.generate(prompt)
        # Extract JSON from response
        text = resp.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0]
        result = json.loads(text)

        classified = {}
        agenda_idx = result.get('agenda', -1)
        minutes_idx = result.get('minutes', -1)
        if isinstance(agenda_idx, int) and 0 <= agenda_idx < len(pdf_urls):
            classified['agenda_packet_url'] = pdf_urls[agenda_idx]
        if isinstance(minutes_idx, int) and 0 <= minutes_idx < len(pdf_urls):
            classified['minutes_url'] = pdf_urls[minutes_idx]

        return classified if classified else None

    except Exception as e:
        logger.debug(f"LLM PDF classification failed: {e}")
        return None


def extract_pdf_urls_from_meeting_page(meeting_page_url: str) -> dict[str, Optional[str]]:
    """
    Parse an HTML meeting page to extract actual PDF URLs.

    When agenda_url points to an HTML meeting page (not a direct PDF),
    this function scrapes the page to find links to actual PDFs.

    Handles redirects (e.g., Granicus AgendaViewer.php → city Drupal site)
    by tracking the final URL for correct relative link resolution.
    Uses a session with browser-like headers to handle cookie-gated sites.

    Args:
        meeting_page_url: URL of the meeting page (HTML)

    Returns:
        Dict with 'agenda_packet_url' and 'minutes_url' (both may be None)
    """
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse

    result = {
        'agenda_packet_url': None,
        'minutes_url': None,
    }

    # Use a session to persist cookies across redirects (some city sites
    # require cookies set during the redirect chain to serve PDFs)
    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
    })

    try:
        response = session.get(meeting_page_url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch meeting page: {e}")
        return result

    # Use the final URL after redirects for resolving relative links
    # (e.g., Granicus AgendaViewer.php redirects to berkeleyca.gov)
    final_url = response.url
    if final_url != meeting_page_url:
        logger.info(f"  Redirected to: {final_url[:80]}")
    parsed_final = urlparse(final_url)
    base_url = f"{parsed_final.scheme}://{parsed_final.netloc}"

    soup = BeautifulSoup(response.content, 'html.parser')

    def make_absolute(href: str) -> Optional[str]:
        """Resolve a potentially relative URL against the final base URL."""
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            return f"{base_url}{href}"
        return None

    # Extract all PDF URLs from the page
    pdf_urls = []

    # Links with .pdf in href
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if '.pdf' in href.lower():
            abs_url = make_absolute(href)
            if abs_url:
                pdf_urls.append(abs_url)

    # Granicus MetaViewer.php links (serve PDFs directly without .pdf in URL)
    # GeneratedAgendaViewer.php pages list per-item PDFs via MetaViewer.php.
    meta_viewer_urls = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if 'MetaViewer' in href:
            abs_url = make_absolute(href)
            if abs_url:
                link_text = link.get_text(strip=True)
                meta_viewer_urls.append({'url': abs_url, 'label': link_text})

    if meta_viewer_urls:
        result['granicus_item_pdfs'] = meta_viewer_urls
        logger.info(f"  Found {len(meta_viewer_urls)} Granicus MetaViewer PDF links")

        # Identify the main agenda PDF — try simple heuristic first, LLM fallback
        if not result['agenda_packet_url']:
            result['agenda_packet_url'] = _classify_agenda_link(meta_viewer_urls)

    if not pdf_urls and meta_viewer_urls:
        # Use MetaViewer links as PDF sources for fallback pattern matching
        pdf_urls = [m['url'] for m in meta_viewer_urls]

    # Embeds and iframes
    for tag in soup.find_all(['embed', 'iframe']):
        src = tag.get('src', '')
        if '.pdf' in src.lower():
            abs_url = make_absolute(src)
            if abs_url:
                pdf_urls.append(abs_url)

    logger.debug(f"Found {len(pdf_urls)} PDF links on meeting page")

    # Pattern match for agenda packet (ordered by specificity)
    import re
    agenda_packet_patterns = [
        r'agenda-packet.*\.pdf',
        r'full.*packet.*\.pdf',
        r'complete.*agenda.*\.pdf',
        r'packet.*\d{4}-\d{2}-\d{2}.*\.pdf',
        # City website patterns (e.g., "2026-02-24 Agenda - Council.pdf")
        # Handles URL-encoded spaces (%20) in hrefs
        r'\d{4}-\d{2}-\d{2}[%20\s_-]+(?:Special[%20\s_-]+)?Agenda',
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
                    abs_url = make_absolute(href)
                    if abs_url:
                        result['agenda_packet_url'] = abs_url
                        logger.info(f"  Found agenda packet in tab: {abs_url[:80]}...")
                        break

    # Fallback: LLM classification of PDF links when regex patterns fail
    if not result['agenda_packet_url'] and pdf_urls:
        classified = _llm_classify_pdf_links(pdf_urls)
        if classified:
            result['agenda_packet_url'] = classified.get('agenda_packet_url')
            if not result['minutes_url']:
                result['minutes_url'] = classified.get('minutes_url')
            if result['agenda_packet_url']:
                logger.info(f"  LLM classified agenda: {result['agenda_packet_url'][:80]}...")

    # Final fallback: first PDF link
    if not result['agenda_packet_url'] and pdf_urls:
        result['agenda_packet_url'] = pdf_urls[0]
        logger.info(f"  Using first PDF link as agenda: {pdf_urls[0][:80]}...")

    # Pattern match for minutes (fast regex first)
    if not result['minutes_url']:
        minutes_patterns = [
            r'cc-minutes.*\d{4}-\d{2}-\d{2}.*\.pdf',
            r'minutes-\d{4}-\d{2}-\d{2}.*\.pdf',
            r'\d{8}-cc-minutes.*\.pdf',
            r'\d{4}-\d{2}-\d{2}[%20\s_-]*(?:.*?)[Mm]inutes.*\.pdf',
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
                    abs_url = make_absolute(href)
                    if abs_url:
                        result['minutes_url'] = abs_url
                        break

    # Store the session for downstream PDF downloads
    result['_session'] = session

    return result


def download_and_validate_pdf(
    url: str,
    timeout: int = 60,
    session: Optional[requests.Session] = None,
) -> DownloadResult:
    """
    Download a PDF from URL with full validation.

    Detects degenerate cases where HTML pages are downloaded instead of PDFs.

    Args:
        url: URL of the PDF
        timeout: Request timeout in seconds
        session: Optional requests.Session with cookies/headers from prior
                 page scraping (needed for cookie-gated city sites)

    Returns:
        DownloadResult with content, validation status, and any warnings
    """
    try:
        requester = session or requests
        # Granicus S3 bucket has broken SSL cert (underscores in hostname)
        # Disable verify only for this known-broken host
        verify = True
        if "granicus_production_attachments.s3.amazonaws.com" in url:
            verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requester.get(url, timeout=timeout, verify=verify)

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
    except requests.exceptions.SSLError as e:
        # SSL errors may be caused by Granicus S3 redirect — retry without verify
        if "granicus" in url.lower() or "CERTIFICATE_VERIFY_FAILED" in str(e):
            logger.warning(f"SSL error, retrying without verification: {e}")
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            try:
                requester = session or requests
                response = requester.get(url, timeout=timeout, verify=False)
                content_type = response.headers.get("Content-Type", "")
                content = response.content
                is_valid, warnings = validate_pdf_content(content, content_type, url)
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
            except requests.exceptions.RequestException as retry_e:
                logger.error(f"Failed to download PDF even without SSL verify: {retry_e}")
                return DownloadResult(content=None, validation_warnings=[str(retry_e)])
        logger.error(f"Failed to download PDF: {e}")
        return DownloadResult(content=None, validation_warnings=[str(e)])
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


def _extract_granicus_multi_pdf(
    item_pdfs: List[Dict[str, str]],
    meeting_id: str,
    meeting_date: str,
    jurisdiction_id: str,
    cloud_mode: bool,
    output_dir: str,
    output_path: str,
    timeout: int = PDF_PARSE_TIMEOUT_SECONDS,
) -> Optional["ChunksResult"]:
    """
    Download and parse multiple Granicus MetaViewer PDFs for a single meeting.

    Granicus GeneratedAgendaViewer pages list individual item PDFs (staff reports,
    attachments) via MetaViewer.php links. This downloads each one and combines
    the chunks, producing much richer coverage than a single agenda PDF.

    Args:
        item_pdfs: List of {'url': str, 'label': str} from extract_pdf_urls_from_meeting_page
        meeting_id: Meeting ID for chunk namespacing
        jurisdiction_id: Jurisdiction ID
        cloud_mode: Store to cloud if True
        output_dir: Local output directory
        output_path: Local output file path
        timeout: PDF parsing timeout per PDF

    Returns:
        ChunksResult if extraction succeeds, None to fall back to single-PDF path
    """
    from civicos._internal.meetings.pdf_parser import AgendaPacketParser

    parser = AgendaPacketParser()
    all_chunks_data = []
    pdfs_processed = 0
    pdfs_failed = 0

    for item_pdf in item_pdfs:
        pdf_url = item_pdf['url']
        label = item_pdf.get('label', '')

        try:
            dl = download_and_validate_pdf(pdf_url, timeout=30)
            if not dl.content or not dl.is_valid_pdf:
                pdfs_failed += 1
                continue

            pdfs_processed += 1

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(dl.content)
                temp_path = f.name

            try:
                source_metadata = {
                    "source_file": pdf_url,
                    "source_type": "agenda_packet",
                }
                chunks = _parse_pdf_with_timeout(
                    parser, temp_path, source_metadata, timeout_seconds=timeout
                )

                # Compute PDF hash
                try:
                    from civicos.storage.integrity import compute_pdf_hash
                    pdf_hash = compute_pdf_hash(dl.content)
                except ImportError:
                    pdf_hash = None

                for chunk in chunks:
                    chunk_dict = chunk.to_dict()
                    # Use label to provide better agenda_item context
                    if label and not chunk_dict.get('agenda_title'):
                        chunk_dict['agenda_title'] = label
                    chunk_dict["meeting_id"] = meeting_id
                    chunk_dict["pdf_hash"] = pdf_hash
                    all_chunks_data.append(chunk_dict)

            except PDFParseTimeoutError:
                logger.warning(f"  Timeout parsing {label[:40]}")
                pdfs_failed += 1
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        except Exception as e:
            logger.debug(f"  Failed to process {label[:40]}: {e}")
            pdfs_failed += 1

    if not all_chunks_data:
        logger.info(f"  No chunks from {pdfs_processed} Granicus PDFs")
        return None  # Fall back to single-PDF path

    # Assign sequential chunk IDs
    for i, chunk_dict in enumerate(all_chunks_data):
        chunk_dict["id"] = f"chunk-{meeting_id}-{i}"

    # Store
    stored_to_cloud = False
    if cloud_mode:
        stored_to_cloud = store_chunks_to_cloud(
            jurisdiction_id, all_chunks_data, meeting_id=meeting_id
        )
    if not stored_to_cloud:
        os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(all_chunks_data, f, indent=2)

    logger.info(
        f"  ✓ Extracted {len(all_chunks_data)} chunks from "
        f"{pdfs_processed} Granicus PDFs ({pdfs_failed} failed)"
    )

    return ChunksResult(
        meeting_id=meeting_id,
        meeting_date=meeting_date,
        status="success",
        chunks_count=len(all_chunks_data),
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
            from civicos._internal.meetings.pdf_parser import AgendaPacketParser
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
            # Download failed (SSL error, timeout, etc.)
            # Try HTML extraction from the agenda URL as fallback
            logger.info(
                f"  PDF download failed. Trying HTML text extraction from agenda URL..."
            )
            html_chunks = extract_chunks_from_html_agenda(
                agenda_url, meeting_id
            )
            if html_chunks:
                logger.info(
                    f"  Extracted {len(html_chunks)} chunks from HTML agenda"
                )
                stored_to_cloud = False
                if cloud_mode:
                    stored_to_cloud = store_chunks_to_cloud(
                        jurisdiction_id, html_chunks, meeting_id=meeting_id
                    )
                if not stored_to_cloud:
                    os.makedirs(output_dir, exist_ok=True)
                    with open(output_path, "w") as f:
                        json.dump(html_chunks, f, indent=2)

                return ChunksResult(
                    meeting_id=meeting_id,
                    meeting_date=meeting_date,
                    status="success",
                    chunks_count=len(html_chunks),
                )

            return ChunksResult(
                meeting_id=meeting_id,
                meeting_date=meeting_date,
                status="error",
                error="Failed to download PDF and no HTML content available",
            )

        # Check for degenerate case (HTML instead of PDF)
        if not download_result.is_valid_pdf:
            degenerate_warnings = [w for w in download_result.validation_warnings if "DEGENERATE" in w]
            if degenerate_warnings:
                logger.info(
                    f"  Detected HTML meeting page (not direct PDF). "
                    "Looking for actual PDF URL..."
                )

                actual_pdf_url = None

                # Strategy 1: Check raw_data/full_data for packet_url (Granicus stores this)
                for data_key in ("raw_data", "full_data"):
                    src = meeting.get(data_key) or {}
                    if isinstance(src, str):
                        try:
                            src = json.loads(src)
                        except (json.JSONDecodeError, TypeError):
                            src = {}
                    # Direct packet_url
                    pkt = src.get("packet_url")
                    if pkt:
                        actual_pdf_url = pkt
                        logger.info(f"  Found packet_url in {data_key}")
                        break
                    # Nested in raw_data within full_data
                    nested = src.get("raw_data") or {}
                    if isinstance(nested, str):
                        try:
                            nested = json.loads(nested)
                        except (json.JSONDecodeError, TypeError):
                            nested = {}
                    pkt = nested.get("packet_url")
                    if pkt:
                        actual_pdf_url = pkt
                        logger.info(f"  Found packet_url in {data_key}.raw_data")
                        break

                # Strategy 2: Scrape the HTML meeting page for PDF links
                # (handles redirects, e.g. Granicus → city Drupal site)
                scrape_session = None
                granicus_item_pdfs = None
                if not actual_pdf_url:
                    pdf_urls = extract_pdf_urls_from_meeting_page(agenda_url)
                    scrape_session = pdf_urls.pop('_session', None)
                    granicus_item_pdfs = pdf_urls.get('granicus_item_pdfs')
                    actual_pdf_url = pdf_urls.get('agenda_packet_url')
                    if not actual_pdf_url:
                        actual_pdf_url = pdf_urls.get('minutes_url')
                        if actual_pdf_url:
                            logger.info(f"  No agenda packet found, using minutes PDF")

                # Strategy 2b: Granicus multi-PDF extraction
                # GeneratedAgendaViewer pages list individual item PDFs via MetaViewer.
                # Download and parse all of them for comprehensive chunk coverage.
                if granicus_item_pdfs and len(granicus_item_pdfs) > 1:
                    all_chunks = _extract_granicus_multi_pdf(
                        granicus_item_pdfs, meeting_id, meeting_date,
                        jurisdiction_id, cloud_mode, output_dir, output_path,
                        timeout=timeout,
                    )
                    if all_chunks is not None:
                        return all_chunks

                if not actual_pdf_url:
                    # Strategy 3: Extract text chunks directly from HTML agenda
                    logger.info(
                        f"  No PDF links found. Trying HTML text extraction..."
                    )
                    html_chunks = extract_chunks_from_html_agenda(
                        agenda_url, meeting_id
                    )
                    if html_chunks:
                        logger.info(
                            f"  Extracted {len(html_chunks)} chunks from HTML agenda"
                        )
                        # Store HTML chunks (same path as PDF chunks)
                        stored_to_cloud = False
                        if cloud_mode:
                            stored_to_cloud = store_chunks_to_cloud(
                                jurisdiction_id, html_chunks, meeting_id=meeting_id
                            )
                        if not stored_to_cloud:
                            os.makedirs(output_dir, exist_ok=True)
                            with open(output_path, "w") as f:
                                json.dump(html_chunks, f, indent=2)

                        return ChunksResult(
                            meeting_id=meeting_id,
                            meeting_date=meeting_date,
                            status="success",
                            chunks_count=len(html_chunks),
                        )

                    logger.warning(
                        f"  No PDF links or HTML content on meeting page: {agenda_url[:60]}..."
                    )
                    return ChunksResult(
                        meeting_id=meeting_id,
                        meeting_date=meeting_date,
                        status="error",
                        error="No PDF links or extractable HTML content on meeting page",
                    )

                # Download the actual PDF (pass session for cookie-gated sites)
                logger.info(f"  Downloading actual PDF: {actual_pdf_url[:60]}...")
                download_result = download_and_validate_pdf(
                    actual_pdf_url, session=scrape_session
                )
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

            # Compute PDF hash for provenance tracking
            try:
                from civicos.storage.integrity import compute_pdf_hash
                pdf_hash = compute_pdf_hash(pdf_bytes)
            except ImportError:
                pdf_hash = None

            # Convert to storage format
            chunks_data = []
            for i, chunk in enumerate(agenda_chunks):
                chunk_dict = chunk.to_dict()
                # Add required fields for storage
                chunk_dict["id"] = f"chunk-{meeting_id}-{i}"
                chunk_dict["meeting_id"] = meeting_id
                # Add pdf_hash for provenance (all chunks from same PDF share hash)
                chunk_dict["pdf_hash"] = pdf_hash
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
        from civicos.storage import get_storage_backend

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

    succeeded_ids = set()
    if resume_from:
        succeeded_ids = set(resume_from.succeeded_meeting_ids or [])
        if succeeded_ids:
            logger.info(
                f"Found checkpoint: {len(succeeded_ids)} meetings succeeded, "
                f"{resume_from.items_failed} failed (will retry failures)"
            )
        else:
            # Legacy checkpoint without succeeded_meeting_ids — fall back to
            # index-based resume but only if there were no failures
            if resume_from.items_failed == 0:
                for i, meeting in enumerate(meetings):
                    meeting_id = meeting.get("id") or meeting.get("meeting_id")
                    if meeting_id == resume_from.last_meeting_id:
                        start_index = i + 1
                        break
                if start_index > 0:
                    logger.info(f"Resuming from meeting {start_index} (legacy checkpoint, no failures)")
            else:
                logger.info(
                    f"Found checkpoint with {resume_from.items_failed} failures "
                    "but no success tracking — re-processing all meetings"
                )

    # Filter out already-succeeded meetings
    meetings_to_process = meetings[start_index:]
    if succeeded_ids:
        meetings_to_process = [
            m for m in meetings
            if (m.get("id") or m.get("meeting_id")) not in succeeded_ids
        ]
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
    items_processed = 0
    items_extracted = 0
    items_skipped = 0
    items_failed = 0
    total_chunks = 0

    for i, meeting in enumerate(meetings_to_process, start=1):
        meeting_id = meeting.get("id") or meeting.get("meeting_id", "unknown")
        meeting_date = meeting.get("meeting_date") or meeting.get("meeting_datetime", "")[:10]
        title = meeting.get("title", "Unknown")[:50]

        logger.info(f"[{i}/{len(meetings_to_process)}] {meeting_date} - {title}")

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
            succeeded_ids.add(meeting_id)
        elif result.status == "skipped":
            items_skipped += 1
            succeeded_ids.add(meeting_id)  # Don't retry skipped meetings
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
                succeeded_meeting_ids=list(succeeded_ids),
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
            succeeded_meeting_ids=list(succeeded_ids),
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

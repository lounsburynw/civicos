"""
BoardDocs School Board Meeting Client

Extracts board meeting data from BoardDocs-hosted school board portals.
BoardDocs runs on IBM Lotus Domino and exposes undocumented POST endpoints
that return JSON (meeting lists) and HTML (agendas). No authentication required.

Supports both LT and Pro editions — identical API endpoints.

Usage:
    client = BoardDocsClient("ca/rova", "school-ross-valley", committee_id="AB9A2R259AF0")
    meetings = client.get_meetings()
    agenda = client.get_agenda("DMYPDZ643003")

District-specific config (app_path, committee_id) lives in extraction config
files under data/extraction/, not hardcoded here.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable

import requests
from bs4 import BeautifulSoup

from civicos_extraction.clients.base import (
    BaseExtractor,
    HealthStatus,
    Meeting,
    ValidationResult,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://go.boarddocs.com"

# Default headers required by BoardDocs endpoints
_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


@dataclass
class BoardDocsMeeting:
    """Meeting extracted from BoardDocs."""

    unique: str  # Short ID used in all subsequent API calls
    title: str  # Meeting title
    meeting_date: date  # Date of meeting (no time available from list endpoint)
    unid: str  # Domino document UNID (32-char hex)
    is_current: bool = False  # Whether this is the current/featured meeting

    # Populated by get_agenda()
    agenda_items: Optional[List[Dict[str, Any]]] = field(default=None)
    file_attachments: Optional[List[Dict[str, str]]] = field(default=None)

    def to_meeting(self, jurisdiction_id: str, app_path: str) -> Meeting:
        """Convert to standard Meeting format."""
        source_url = f"{BASE_URL}/{app_path}/Board.nsf/goto?open&id={self.unique}"
        raw_data: Dict[str, Any] = {
            "boarddocs_unique": self.unique,
            "boarddocs_unid": self.unid,
        }
        if self.agenda_items:
            raw_data["agenda_item_count"] = len(self.agenda_items)
        if self.file_attachments:
            raw_data["attachments"] = self.file_attachments

        return Meeting(
            id=f"boarddocs-{self.unique}",
            title=self.title,
            meeting_datetime=datetime.combine(self.meeting_date, datetime.min.time()),
            jurisdiction_id=jurisdiction_id,
            meeting_type=_infer_meeting_type(self.title),
            status="confirmed",
            source_platform="boarddocs",
            source_url=source_url,
            raw_data=raw_data,
        )


def _infer_meeting_type(title: str) -> str:
    """Infer meeting type from title."""
    title_lower = title.lower()
    if "special" in title_lower:
        return "special"
    if "study" in title_lower or "workshop" in title_lower:
        return "study_session"
    if "closed" in title_lower:
        return "closed_session"
    if "retreat" in title_lower:
        return "retreat"
    if "committee" in title_lower:
        return "committee"
    return "regular"


@dataclass
class AgendaItem:
    """A single item from a BoardDocs agenda."""

    category: str  # E.g., "A. CALL TO ORDER"
    subject: str  # Item subject line
    item_type: Optional[str] = None  # Procedural, Action, Discussion, etc.
    body_html: Optional[str] = None  # Full HTML body text
    body_text: Optional[str] = None  # Plain text body
    attachments: Optional[List[Dict[str, str]]] = None  # [{name, url, size}]


class BoardDocsClient(BaseExtractor):
    """
    BoardDocs school board meeting client.

    Uses undocumented POST endpoints to fetch meeting lists (JSON) and
    agendas (HTML). No authentication required. Works with both LT and
    Pro editions.

    Features:
    - Meeting list retrieval (all meetings, no pagination)
    - Full agenda extraction with item categorization
    - File attachment URL extraction
    - Committee ID discovery from main page
    - Rate limiting between requests
    """

    def __init__(
        self,
        app_path: str,
        jurisdiction_id: str,
        committee_id: Optional[str] = None,
        request_delay: float = 1.0,
    ):
        """
        Initialize BoardDocs client.

        Args:
            app_path: BoardDocs site path (e.g., "ca/rova" for Ross Valley SD).
                     Format is "{state}/{site_code}".
            jurisdiction_id: Civic jurisdiction ID (e.g., "school-ross-valley")
            committee_id: Committee ID for meeting list. If None, will be
                         discovered from the main page HTML.
            request_delay: Delay between requests in seconds (default 1.0)
        """
        super().__init__(jurisdiction_id)
        self.app_path = app_path
        self.committee_id = committee_id or ""
        self.request_delay = request_delay
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    @property
    def platform_name(self) -> str:
        return "boarddocs"

    @property
    def source_id(self) -> str:
        return f"boarddocs-{self.app_path.replace('/', '-')}"

    @property
    def source_type(self) -> str:
        return "boarddocs"

    @property
    def _base_nsf_url(self) -> str:
        return f"{BASE_URL}/{self.app_path}/Board.nsf"

    def discover_committee_ids(self) -> Dict[str, str]:
        """
        Discover committee IDs by parsing the BoardDocs main page.

        Returns:
            Dict mapping committee name to committee ID.
        """
        url = f"{self._base_nsf_url}/vpublic?open"
        try:
            time.sleep(self.request_delay)
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(
                "Failed to fetch main page for committee discovery",
                extra={"app_path": self.app_path, "error": str(e)},
            )
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        committees: Dict[str, str] = {}

        for link in soup.find_all("a", class_="committee-trigger"):
            cid = link.get("committeeid", "")
            name = link.get_text(strip=True)
            if cid and name:
                committees[name] = cid

        if committees:
            logger.info(
                f"Discovered {len(committees)} committees",
                extra={"app_path": self.app_path, "committees": committees},
            )
        else:
            logger.warning(
                "No committees found on main page",
                extra={"app_path": self.app_path},
            )

        return committees

    def _ensure_committee_id(self) -> bool:
        """Ensure committee_id is set, discovering if needed."""
        if self.committee_id:
            return True

        committees = self.discover_committee_ids()
        if not committees:
            return False

        # Use the first committee found (usually the main governing board)
        first_name = next(iter(committees))
        self.committee_id = committees[first_name]
        logger.info(
            f"Auto-selected committee: {first_name} ({self.committee_id})",
            extra={"app_path": self.app_path},
        )
        return True

    def get_meetings_raw(self) -> List[Dict[str, Any]]:
        """
        Fetch raw meeting list JSON from BoardDocs.

        Returns all meetings at once (no pagination), going back to 2017-2018.
        The array ends with an empty object {} sentinel.

        Returns:
            List of raw meeting dicts with keys: unique, name, current,
            numberdate, unid.
        """
        if not self._ensure_committee_id():
            logger.error("No committee_id available", extra={"app_path": self.app_path})
            return []

        url = f"{self._base_nsf_url}/BD-GetMeetingsList?open"
        body = f"current_committee_id={self.committee_id}"

        try:
            time.sleep(self.request_delay)
            resp = self._session.post(url, data=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(
                "Failed to fetch meetings list",
                extra={"app_path": self.app_path, "error": str(e)},
            )
            return []
        except ValueError as e:
            logger.error(
                "Invalid JSON in meetings response",
                extra={"app_path": self.app_path, "error": str(e)},
            )
            return []

        if not isinstance(data, list):
            logger.error(
                "Unexpected response format (expected list)",
                extra={"app_path": self.app_path, "type": type(data).__name__},
            )
            return []

        # Filter out the empty sentinel object at the end
        meetings = [m for m in data if m and m.get("unique")]
        logger.info(
            f"Fetched {len(meetings)} meetings from BoardDocs",
            extra={"app_path": self.app_path},
        )
        return meetings

    def get_meetings(self, since: Optional[date] = None) -> List[BoardDocsMeeting]:
        """
        Get parsed meeting list.

        Args:
            since: Only return meetings on or after this date.

        Returns:
            List of BoardDocsMeeting objects, sorted by date descending.
        """
        raw_meetings = self.get_meetings_raw()
        result: List[BoardDocsMeeting] = []

        for raw in raw_meetings:
            meeting = _parse_meeting(raw)
            if meeting is None:
                continue
            if since and meeting.meeting_date < since:
                continue
            result.append(meeting)

        return result

    def get_agenda(self, meeting_unique: str) -> Optional[List[AgendaItem]]:
        """
        Fetch and parse the full agenda for a meeting.

        Uses PRINT-AgendaDetailed endpoint which returns all items in one call.

        Args:
            meeting_unique: The 'unique' field from the meeting list.

        Returns:
            List of AgendaItem objects, or None on failure.
        """
        if not self._ensure_committee_id():
            return None

        url = f"{self._base_nsf_url}/PRINT-AgendaDetailed"
        body = f"id={meeting_unique}&current_committee_id={self.committee_id}"

        try:
            time.sleep(self.request_delay)
            resp = self._session.post(url, data=body, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(
                "Failed to fetch agenda",
                extra={
                    "app_path": self.app_path,
                    "meeting_id": meeting_unique,
                    "error": str(e),
                },
            )
            return None

        return _parse_agenda_html(resp.text, self._base_nsf_url)

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get raw events for BaseExtractor compatibility."""
        since_date = date.today() - timedelta(days=days_past) if days_past > 0 else None
        meetings = self.get_meetings(since=since_date)
        return [
            {
                "unique": m.unique,
                "title": m.title,
                "meeting_date": m.meeting_date.isoformat(),
                "unid": m.unid,
                "is_current": m.is_current,
            }
            for m in meetings
        ]

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize a raw BoardDocs event dict to Meeting format."""
        meeting_date = date.today()
        dt_str = event.get("meeting_date", "")
        if dt_str:
            try:
                meeting_date = date.fromisoformat(dt_str)
            except ValueError:
                pass

        raw_data: Dict[str, Any] = {}
        if event.get("unique"):
            raw_data["boarddocs_unique"] = event["unique"]
        if event.get("unid"):
            raw_data["boarddocs_unid"] = event["unid"]

        source_url = f"{BASE_URL}/{self.app_path}/Board.nsf/goto?open&id={event.get('unique', '')}"

        return Meeting(
            id=f"boarddocs-{event.get('unique', '')}",
            title=event.get("title", "Board Meeting"),
            meeting_datetime=datetime.combine(meeting_date, datetime.min.time()),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=_infer_meeting_type(event.get("title", "")),
            status="confirmed",
            source_platform="boarddocs",
            source_url=source_url,
            raw_data=raw_data if raw_data else None,
        )

    def health(self) -> HealthStatus:
        """Check BoardDocs availability."""
        start = time.time()
        errors: List[str] = []
        count = 0

        try:
            raw = self.get_meetings_raw()
            count = len(raw)
        except Exception as e:
            errors.append(str(e))

        duration_ms = (time.time() - start) * 1000
        return HealthStatus(
            source_id=self.source_id,
            source_type="boarddocs",
            jurisdiction_id=self.jurisdiction_id,
            is_available=count > 0 and not errors,
            available_count=count,
            last_checked=datetime.now(),
            check_duration_ms=duration_ms,
            errors=errors,
            metadata={"app_path": self.app_path, "committee_id": self.committee_id},
        )

    def validate(self) -> ValidationResult:
        """Validate BoardDocs configuration and API access."""
        start = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False

        if not self.app_path:
            errors.append("app_path is required")
            config_valid = False

        if not self.committee_id:
            warnings.append("committee_id not set — will attempt discovery")

        if config_valid:
            try:
                raw = self.get_meetings_raw()
                api_reachable = len(raw) > 0
                if not api_reachable:
                    errors.append("API returned no meetings")
            except Exception as e:
                errors.append(f"API error: {e}")

        duration_ms = (time.time() - start) * 1000
        return ValidationResult(
            is_valid=config_valid and api_reachable and not errors,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=duration_ms,
            metadata={"app_path": self.app_path},
        )


# --- Parsing helpers ---


def _parse_meeting(raw: Dict[str, Any]) -> Optional[BoardDocsMeeting]:
    """Parse a raw meeting dict from BD-GetMeetingsList."""
    unique = raw.get("unique", "")
    name = raw.get("name", "")
    numberdate = raw.get("numberdate", "")
    unid = raw.get("unid", "")
    current = raw.get("current", "")

    if not unique or not numberdate:
        return None

    try:
        meeting_date = datetime.strptime(numberdate, "%Y%m%d").date()
    except ValueError:
        logger.warning(
            f"Could not parse date: {numberdate}",
            extra={"meeting_unique": unique, "meeting_name": name},
        )
        return None

    return BoardDocsMeeting(
        unique=unique,
        title=name.strip(),
        meeting_date=meeting_date,
        unid=unid,
        is_current=current == "1",
    )


def _parse_agenda_html(
    html: str, base_nsf_url: str
) -> List[AgendaItem]:
    """
    Parse PRINT-AgendaDetailed HTML into structured AgendaItem list.

    The HTML structure is:
    - Category headers: <div style="font-weight: bold; ...">A. CALL TO ORDER</div>
    - Items: <div class="container item agendaorder">
      - <dl><dt>Subject</dt><dd>...</dd></dl>
      - <dl><dt>Type</dt><dd>Procedural</dd></dl>
      - <div class="itembody">...</div>
      - <div class="print-files">...</div>
    """
    soup = BeautifulSoup(html, "html.parser")
    items: List[AgendaItem] = []
    current_category = ""

    # Find the main content area
    content = soup.find("div", id="print-top-meeting-info")
    if content:
        siblings = content.find_next_siblings()
    else:
        siblings = soup.find_all(["div"])

    for element in siblings:
        if not hasattr(element, "get"):
            continue

        # Detect category headers
        style = element.get("style", "")
        if "font-weight: bold" in style and "border-bottom" in style:
            current_category = element.get_text(strip=True)
            continue

        # Detect agenda items
        classes = element.get("class", [])
        if "item" in classes or "agendaorder" in classes:
            item = _parse_agenda_item(element, current_category, base_nsf_url)
            if item:
                items.append(item)

    return items


def _parse_agenda_item(
    element: Any, category: str, base_nsf_url: str
) -> Optional[AgendaItem]:
    """Parse a single agenda item from its container div."""
    subject = ""
    item_type = None
    body_html = None
    body_text = None
    attachments: List[Dict[str, str]] = []

    # Extract <dl> fields (Subject, Type, etc.)
    for dl in element.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue
        label = dt.get_text(strip=True).lower()
        value = dd.get_text(strip=True)
        if label == "subject":
            subject = value
        elif label == "type":
            item_type = value

    # Extract body text
    body_div = element.find("div", class_="itembody")
    if body_div:
        body_html = str(body_div)
        body_text = body_div.get_text(separator="\n", strip=True)

    # Extract file attachments
    files_div = element.find("div", class_="print-files")
    if files_div:
        for file_div in files_div.find_all("div", class_="print-file"):
            link = file_div.find("a")
            if link and link.get("href"):
                href = link["href"]
                if href.startswith("/"):
                    href = f"{BASE_URL}{href}"
                elif not href.startswith("http"):
                    href = f"{base_nsf_url}/{href}"

                name = link.get_text(strip=True)
                size_match = re.search(r"\((\d+\s*(?:KB|MB|GB))\)\s*$", name)
                size = size_match.group(1) if size_match else None
                if size_match:
                    name = name[: size_match.start()].strip()

                attachment: Dict[str, str] = {"name": name, "url": href}
                if size:
                    attachment["size"] = size
                attachments.append(attachment)

    if not subject and not body_text:
        return None

    return AgendaItem(
        category=category,
        subject=subject,
        item_type=item_type,
        body_html=body_html,
        body_text=body_text,
        attachments=attachments if attachments else None,
    )


# --- Storage mapping ---


@runtime_checkable
class MeetingStorageProtocol(Protocol):
    """Protocol for storage backends that support meeting operations."""

    def store_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Dict[str, Any]],
    ) -> int:
        """Store meetings."""
        ...


def boarddocs_meeting_to_storage(
    meeting: BoardDocsMeeting,
    jurisdiction_id: str,
    app_path: str,
) -> Dict[str, Any]:
    """
    Map BoardDocs meeting to storage format.

    Args:
        meeting: BoardDocsMeeting from BoardDocsClient
        jurisdiction_id: Target jurisdiction
        app_path: BoardDocs app path for source URL construction

    Returns:
        Meeting dict ready for storage
    """
    raw_data: Dict[str, Any] = {
        "boarddocs_unique": meeting.unique,
        "boarddocs_unid": meeting.unid,
    }
    if meeting.agenda_items:
        raw_data["agenda_item_count"] = len(meeting.agenda_items)
    if meeting.file_attachments:
        raw_data["attachments"] = meeting.file_attachments

    source_url = f"{BASE_URL}/{app_path}/Board.nsf/goto?open&id={meeting.unique}"

    return {
        "id": f"boarddocs-{meeting.unique}",
        "title": meeting.title,
        "meeting_datetime": datetime.combine(
            meeting.meeting_date, datetime.min.time()
        ).isoformat(),
        "jurisdiction_id": jurisdiction_id,
        "meeting_type": _infer_meeting_type(meeting.title),
        "status": "confirmed",
        "source_platform": "boarddocs",
        "source_url": source_url,
        "raw_data": raw_data,
    }


def extract_boarddocs_meetings_to_storage(
    client: BoardDocsClient,
    storage: MeetingStorageProtocol,
    jurisdiction_id: str,
    since: Optional[date] = None,
) -> int:
    """
    Extract meetings from BoardDocs and store them.

    Args:
        client: BoardDocsClient instance
        storage: StorageBackend with store_meetings method
        jurisdiction_id: Target jurisdiction
        since: Only extract meetings after this date

    Returns:
        Number of meetings stored
    """
    meetings = client.get_meetings(since=since)
    if not meetings:
        logger.info("No meetings returned from BoardDocs")
        return 0

    mapped = [
        boarddocs_meeting_to_storage(m, jurisdiction_id, client.app_path)
        for m in meetings
    ]
    result = storage.store_meetings(jurisdiction_id, mapped)
    stored = int(result)
    logger.info(f"Stored {stored} meetings for {jurisdiction_id} from BoardDocs")
    return stored

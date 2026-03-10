"""
Granicus ViewPublisher Client

Extracts meeting data from Granicus ViewPublisher platform, used by ~30% of
US jurisdictions including Marin County, Dublin, Campbell, and many others.

URL Pattern: https://[domain].granicus.com/ViewPublisher.php?view_id=X

Data Structure: HTML tables with columns:
- Name (meeting title)
- Date (meeting date)
- Agenda Link (AgendaViewer.php URLs)
- Agenda Packet (direct PDF URLs)

Usage:
    client = GranicusClient(
        granicus_domain="marin",
        jurisdiction_id="county-marin",
        view_ids={"board_of_supervisors": "33"},
        default_view_id="36",
    )
    events = client.get_events(days_ahead=90, days_past=30)
    meetings = client.get_meetings(days_ahead=90)
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from civicos_extraction.clients.base import (
    BaseExtractor,
    ExtractionConfig,
    HealthStatus,
    Meeting,
    ValidationResult,
)

if TYPE_CHECKING:
    from civicos_extraction.cache import SourceCache

logger = logging.getLogger(__name__)


class GranicusClient(BaseExtractor):
    """
    Granicus ViewPublisher web scraper client.

    Scrapes meeting data from Granicus ViewPublisher HTML tables.
    Supports multiple view_ids for different governing bodies.
    """

    def __init__(
        self,
        granicus_domain: str,
        jurisdiction_id: str,
        view_ids: Optional[Dict[str, str]] = None,
        default_view_id: str = "1",
    ):
        """
        Initialize Granicus client.

        Args:
            granicus_domain: Subdomain (e.g., 'marin' for marin.granicus.com)
            jurisdiction_id: Jurisdiction ID (e.g., 'county-marin')
            view_ids: Mapping of body_name → view_id string
            default_view_id: Default view_id for health checks and discovery
        """
        super().__init__(jurisdiction_id)
        self.granicus_domain = granicus_domain
        self.base_url = f"https://{granicus_domain}.granicus.com"
        self.view_ids = view_ids or {}
        self.default_view_id = default_view_id
        self._last_request_time = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CivicOS/1.0 (civic-data-extraction)"
        })

    @property
    def platform_name(self) -> str:
        return "granicus"

    @property
    def source_id(self) -> str:
        return f"granicus-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "granicus"

    def _rate_limit(self):
        """Enforce 1s minimum between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _fetch_view(self, view_id: str, timeout: int = 30) -> Optional[requests.Response]:
        """Fetch a ViewPublisher page with rate limiting."""
        self._rate_limit()
        url = f"{self.base_url}/ViewPublisher.php?view_id={view_id}"
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Failed to fetch Granicus view",
                extra={
                    "url": url,
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
                },
            )
            return None

    def _parse_table(self, html: str, view_id: str, meeting_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Parse Granicus HTML table into raw event dicts.

        Args:
            html: HTML content of ViewPublisher page
            view_id: View ID (for source tracking)
            meeting_type: Optional meeting type tag

        Returns:
            List of raw event dictionaries
        """
        soup = BeautifulSoup(html, "html.parser")
        events = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) <= 1:
                continue

            # Parse header
            header_row = rows[0]
            headers = [
                th.get_text(strip=True).lower()
                for th in header_row.find_all(["th", "td"])
            ]

            name_idx = self._find_column_index(headers, ["name", "meeting"])
            date_idx = self._find_column_index(headers, ["date", "when"])
            agenda_idx = self._find_column_index(headers, ["agenda", "agenda link"])
            minutes_idx = self._find_column_index(headers, ["minutes"])
            packet_idx = self._find_column_index(
                headers, ["packet", "agenda packet", "documents"]
            )

            for row in rows[1:]:
                cells = row.find_all("td")

                min_required = 2
                if name_idx is not None:
                    min_required = max(min_required, name_idx + 1)
                if date_idx is not None:
                    min_required = max(min_required, date_idx + 1)

                if len(cells) < min_required:
                    continue

                try:
                    title = (
                        cells[name_idx].get_text(strip=True)
                        if name_idx is not None
                        else "Unknown Meeting"
                    )
                    date_text = (
                        cells[date_idx].get_text(strip=True)
                        if date_idx is not None
                        else ""
                    )

                    parsed_date = self._parse_date(date_text)
                    if not parsed_date:
                        continue

                    # Extract links
                    agenda_url = self._extract_link(cells, agenda_idx)
                    minutes_url = self._extract_link(cells, minutes_idx)
                    packet_url = self._extract_link(cells, packet_idx)

                    event = {
                        "title": title,
                        "date_text": date_text,
                        "datetime": parsed_date.isoformat(),
                        "parsed_date": parsed_date,
                        "agenda_url": agenda_url,
                        "minutes_url": minutes_url,
                        "packet_url": packet_url,
                        "view_id": view_id,
                        "meeting_type": meeting_type,
                        "source_url": f"{self.base_url}/ViewPublisher.php?view_id={view_id}",
                    }
                    events.append(event)

                except Exception as e:
                    logger.debug("Error parsing Granicus row: %s", e)
                    continue

        return events

    def _find_column_index(
        self, headers: List[str], possible_names: List[str]
    ) -> Optional[int]:
        """Find column index by matching possible header names.

        Prefers exact matches over substring matches to avoid
        'name' matching 'month' before matching 'name'.
        """
        # First pass: exact match
        for name in possible_names:
            for i, header in enumerate(headers):
                if header == name:
                    return i
        # Second pass: substring match
        for name in possible_names:
            for i, header in enumerate(headers):
                if name in header:
                    return i
        return None

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from various Granicus date formats.

        Handles:
        - "March 4, 2026", "Feb 25, 2026" (full/abbreviated month)
        - "10/7/2025", "03/10/26" (MM/DD/YYYY or MM/DD/YY)
        - "2025-10-07" (ISO)
        - "1773156600 03/10/26" (Unix timestamp prefix)
        - "03/10/26 - 08:30 AM" (with time suffix)
        """
        # Normalize whitespace first (Granicus HTML has \r\n and extra spaces)
        date_text = re.sub(r"\s+", " ", date_text).strip()
        if not date_text:
            return None

        # Strip leading Unix timestamps (exactly 10 digits, no separator)
        # e.g., "177315660003/10/26" → "03/10/26"
        # e.g., "1758006000Sep 16, 2025" → "Sep 16, 2025"
        unix_match = re.match(r"^(\d{10})(.+)$", date_text)
        if unix_match:
            date_text = unix_match.group(2)
        # Strip trailing time/whitespace (e.g., "03/10/26 - 08:30 AM" or "03/10/26 -")
        date_text = re.sub(r"\s*-\s*$", "", date_text)  # trailing " -"
        date_text = re.sub(r"\s+-\s+\d{1,2}:\d{2}\s*(AM|PM)?.*$", "", date_text, flags=re.I)
        date_text = date_text.strip()

        date_formats = [
            "%B %d, %Y",
            "%b %d, %Y",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y-%m-%d",
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y %I:%M %p",
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_text.strip(), fmt)
            except ValueError:
                continue

        # Try extracting date substring
        date_match = re.search(r"(\w+ \d+, \d{4})", date_text)
        if date_match:
            for fmt in ["%B %d, %Y", "%b %d, %Y"]:
                try:
                    return datetime.strptime(date_match.group(1), fmt)
                except ValueError:
                    continue

        return None

    def _extract_link(self, cells, col_idx: Optional[int]) -> Optional[str]:
        """Extract first link href from a table cell."""
        if col_idx is None or col_idx >= len(cells):
            return None
        link = cells[col_idx].find("a")
        if link and link.get("href"):
            return self._make_absolute_url(link["href"])
        return None

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute."""
        if url.startswith("http"):
            return url
        elif url.startswith("//"):
            return f"https:{url}"
        elif url.startswith("/"):
            return f"{self.base_url}{url}"
        else:
            return f"{self.base_url}/{url}"

    def get_events(
        self, days_ahead: int = 90, days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Extract events from all configured view_ids.

        Args:
            days_ahead: Days into the future to include
            days_past: Days into the past to include

        Returns:
            List of event dictionaries in platform-native format
        """
        now = datetime.now()
        cutoff_past = now - timedelta(days=days_past)
        cutoff_future = now + timedelta(days=days_ahead)

        all_events = []

        # If no view_ids configured, use default_view_id
        views_to_fetch = self.view_ids if self.view_ids else {"default": self.default_view_id}

        for body_name, view_id in views_to_fetch.items():
            response = self._fetch_view(view_id)
            if not response:
                continue

            events = self._parse_table(response.text, view_id, meeting_type=body_name)

            # Apply temporal filter
            for event in events:
                dt = event.get("parsed_date")
                if dt and cutoff_past <= dt <= cutoff_future:
                    all_events.append(event)

        return all_events

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize a Granicus event to the Meeting format.

        ID format: granicus-{jurisdiction_id}-{view_id}-{date}-{title_slug}
        """
        parsed_date = event.get("parsed_date")
        if not parsed_date and event.get("datetime"):
            parsed_date = datetime.fromisoformat(event["datetime"])

        title = event.get("title", "Unknown Meeting")
        view_id = event.get("view_id", "0")
        date_str = parsed_date.strftime("%Y%m%d") if parsed_date else "00000000"
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]

        meeting_id = f"granicus-{self.jurisdiction_id}-{view_id}-{date_str}-{title_slug}"

        return Meeting(
            id=meeting_id,
            title=title,
            meeting_datetime=parsed_date or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=event.get("meeting_type"),
            status="scheduled",
            agenda_url=event.get("agenda_url"),
            minutes_url=event.get("minutes_url"),
            source_platform="granicus",
            source_url=event.get("source_url"),
            raw_data=event,
        )

    def health(self) -> HealthStatus:
        """Check source availability by fetching default view."""
        start_time = time.time()
        errors = []
        is_available = False
        available_count = 0

        try:
            response = self._fetch_view(self.default_view_id)
            if response:
                events = self._parse_table(response.text, self.default_view_id)
                is_available = True
                available_count = len(events)
            else:
                errors.append(f"Failed to fetch view_id={self.default_view_id}")
        except Exception as e:
            errors.append(str(e))

        check_duration_ms = (time.time() - start_time) * 1000

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.now(),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.now() if is_available else None,
            metadata={"default_view_id": self.default_view_id},
        )

    def validate(self) -> ValidationResult:
        """Validate config and API access."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False

        if not self.granicus_domain:
            errors.append("granicus_domain is required")
            config_valid = False

        if not self.jurisdiction_id:
            errors.append("jurisdiction_id is required")
            config_valid = False

        if config_valid:
            try:
                response = self._fetch_view(self.default_view_id)
                if response:
                    api_reachable = True
                    events = self._parse_table(response.text, self.default_view_id)
                    if not events:
                        warnings.append(
                            f"View {self.default_view_id} returned no meetings"
                        )
                else:
                    errors.append(
                        f"Cannot reach {self.base_url}/ViewPublisher.php?view_id={self.default_view_id}"
                    )
            except Exception as e:
                errors.append(f"Connection error: {e}")

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
        )

    def discover_view_ids(self) -> Dict[str, str]:
        """
        Probe view_ids 1-50 to discover available bodies.

        Stops after 5 consecutive empty responses.

        Returns:
            Dict mapping inferred body_name to view_id string
        """
        discovered = {}
        consecutive_empty = 0

        for vid in range(1, 51):
            response = self._fetch_view(str(vid))
            if not response:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            # Try to get body name from page title or h1
            body_name = None
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                # Clean up common Granicus title patterns
                title_text = re.sub(
                    r"(ViewPublisher|Granicus|Meeting List)\s*[-–|]?\s*",
                    "",
                    title_text,
                    flags=re.I,
                ).strip()
                if title_text:
                    body_name = title_text

            if not body_name:
                h1 = soup.find("h1")
                if h1:
                    body_name = h1.get_text(strip=True)

            if not body_name:
                body_name = f"view_{vid}"

            # Check if the page has actual meeting data
            events = self._parse_table(response.text, str(vid))
            if events:
                # Convert body name to key
                key = re.sub(r"[^a-z0-9]+", "_", body_name.lower()).strip("_")
                discovered[key] = str(vid)
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break

        logger.info(
            "Discovered Granicus view_ids",
            extra={
                "count": len(discovered),
                "views": discovered,
                "jurisdiction_id": self.jurisdiction_id,
            },
        )

        return discovered


class GranicusSource:
    """
    Config-driven wrapper for GranicusClient implementing DataSource protocol.

    Loads extraction configuration from JSON files and creates a properly
    configured GranicusClient.

    Usage:
        source = GranicusSource.from_jurisdiction("county-marin")
        health = source.health()
        meetings = source.get_meetings(days_ahead=90)
    """

    def __init__(self, config: ExtractionConfig):
        """
        Initialize GranicusSource from an ExtractionConfig.

        Args:
            config: ExtractionConfig with source_type="granicus"
        """
        self._config = config

        granicus_domain = config.metadata.get("granicus_domain", "")
        if not granicus_domain:
            # Try to extract from base_url
            import re as _re
            match = _re.match(r"https?://([^.]+)\.granicus\.com", config.base_url)
            granicus_domain = match.group(1) if match else ""

        default_view_id = config.metadata.get("default_view_id", "1")

        self._client = GranicusClient(
            granicus_domain=granicus_domain,
            jurisdiction_id=config.jurisdiction_id,
            view_ids=config.archives,
            default_view_id=default_view_id,
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction_id: str) -> "GranicusSource":
        """Create GranicusSource from jurisdiction ID, loading config from file."""
        config = ExtractionConfig.from_jurisdiction(jurisdiction_id)
        return cls(config)

    @classmethod
    def from_config_file(cls, path: str) -> "GranicusSource":
        """Create GranicusSource from a specific config file path."""
        config = ExtractionConfig.from_file(path)
        return cls(config)

    @property
    def client(self) -> GranicusClient:
        """Get the underlying GranicusClient."""
        return self._client

    @property
    def config(self) -> ExtractionConfig:
        """Get the extraction configuration."""
        return self._config

    @property
    def source_id(self) -> str:
        return self._client.source_id

    @property
    def source_type(self) -> str:
        return self._client.source_type

    def health(self) -> HealthStatus:
        return self._client.health()

    def validate(self) -> ValidationResult:
        return self._client.validate()

    def get_events(self, days_ahead: int = 90, days_past: int = 0):
        return self._client.get_events(days_ahead=days_ahead, days_past=days_past)

    def get_meetings(self, days_ahead: int = 90, days_past: int = 0):
        return self._client.get_meetings(days_ahead=days_ahead, days_past=days_past)


def create_marin_county_client() -> GranicusClient:
    """Create a GranicusClient configured for Marin County."""
    try:
        source = GranicusSource.from_jurisdiction("county-marin")
        return source.client
    except FileNotFoundError:
        return GranicusClient(
            granicus_domain="marin",
            jurisdiction_id="county-marin",
            view_ids={"board_of_supervisors": "33"},
            default_view_id="36",
        )


def create_marin_county_source() -> GranicusSource:
    """Create a config-driven GranicusSource for Marin County."""
    return GranicusSource.from_jurisdiction("county-marin")

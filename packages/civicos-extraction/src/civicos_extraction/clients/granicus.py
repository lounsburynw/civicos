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

# Module-level cache for LLM-learned date formats. Shared across all
# GranicusClient instances so a format discovered for one jurisdiction
# benefits all others in the same process.
_learned_date_formats: List[str] = []


def _get_llm_provider():
    """Lazy-load the LLM provider. Returns None if unavailable."""
    try:
        from civicos_services.core.llm_provider import get_model_for_task
        return get_model_for_task("fast")
    except ImportError:
        return None


def _llm_parse_date(date_text: str) -> Optional[datetime]:
    """LLM fallback for date strings that no hardcoded format can parse.

    Asks gpt-4o-mini to return both the parsed ISO date and a strptime
    format string.  The format string is cached in ``_learned_date_formats``
    so future dates in the same format skip the LLM entirely.

    Returns the parsed datetime, or None if the LLM can't parse it either.
    """
    import json as _json

    provider = _get_llm_provider()
    if provider is None:
        logger.debug("LLM provider unavailable for date fallback")
        return None
    prompt = (
        "Parse this date string from a government meeting listing page.\n"
        "Return JSON with two keys:\n"
        '  "iso": the date in ISO 8601 format (YYYY-MM-DDTHH:MM:SS), '
        "use 00:00:00 if no time is present\n"
        '  "strptime_format": a Python strptime format string that would '
        "parse the *original* text (e.g. \"%B %d, %Y\")\n\n"
        f"Date text: {date_text!r}\n\n"
        "Return ONLY the JSON object, no explanation."
    )

    try:
        response = provider.invoke(prompt)
        # Handle provider response (string or object with .content)
        raw = response if isinstance(response, str) else response.content
        payload = _json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())

        iso_str = payload.get("iso")
        fmt = payload.get("strptime_format")

        if not iso_str:
            return None

        parsed = datetime.fromisoformat(iso_str)

        # Cache the learned format for future use (if it round-trips)
        if fmt and fmt not in _learned_date_formats:
            try:
                check = datetime.strptime(date_text.strip(), fmt)
                if check.date() == parsed.date():
                    _learned_date_formats.append(fmt)
                    logger.info(
                        f"Learned new date format from LLM: {fmt!r} "
                        f"(from {date_text!r})"
                    )
            except ValueError:
                pass  # Format doesn't actually round-trip; still use iso

        return parsed

    except Exception as e:
        logger.debug(f"LLM date parsing failed for {date_text!r}: {e}")
        return None


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
        column_map: Optional[Dict[str, int]] = None,
    ):
        """
        Initialize Granicus client.

        Args:
            granicus_domain: Subdomain (e.g., 'marin' for marin.granicus.com)
            jurisdiction_id: Jurisdiction ID (e.g., 'county-marin')
            view_ids: Mapping of body_name → view_id string
            default_view_id: Default view_id for health checks and discovery
            column_map: LLM-generated column mapping (e.g., {"name": 0, "date": 1}).
                If provided, bypasses header-based detection in _parse_table.
        """
        super().__init__(jurisdiction_id)
        self.granicus_domain = granicus_domain
        self.base_url = f"https://{granicus_domain}.granicus.com"
        self.view_ids = view_ids or {}
        self.default_view_id = default_view_id
        self.column_map = column_map
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

    def generate_column_map(self, view_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Use LLM to infer column mapping from a sample HTML page.

        Fetches one ViewPublisher page, sends the first table's HTML to the LLM,
        and returns a mapping like {"name": 0, "date": 1, "agenda": 3}.

        This runs once during onboarding. The result is saved in the extraction
        config so _parse_table can use it deterministically without LLM calls.

        Args:
            view_id: View ID to sample (uses first discovered view if not given)

        Returns:
            Dict with:
              "column_map": {field_name: column_index} — the usable mapping
              "provenance": {input, prompt_template, raw_response} — for audit trail
        """
        import json as _json

        from civicos_services.core.llm_provider import get_model_for_task

        # Find a view_id with content
        vid = view_id or self.default_view_id
        if not view_id and self.view_ids:
            vid = next(iter(self.view_ids.values()))

        response = self._fetch_view(vid)
        if not response:
            raise RuntimeError(f"Could not fetch view_id={vid}")

        soup = BeautifulSoup(response.text, "html.parser")

        # Get the largest table (most likely the meeting list)
        tables = soup.find_all("table")
        if not tables:
            raise RuntimeError(f"No tables found at view_id={vid}")

        target_table = max(tables, key=lambda t: len(t.find_all("tr")))
        num_columns = max(
            len(row.find_all(["th", "td"]))
            for row in target_table.find_all("tr")
        )

        # Send first 8 rows to keep token count low
        rows = target_table.find_all("tr")[:8]
        sample_html = "<table>\n"
        for row in rows:
            sample_html += str(row) + "\n"
        sample_html += "</table>"

        provider = get_model_for_task("navigation")

        prompt = f"""Analyze this HTML table from a government meeting listing page.
Identify which zero-based column index contains each of these fields:
- "name": the meeting title/name (e.g., "City Council Meeting")
- "date": the meeting date (e.g., "Mar 10, 2026")
- "duration": meeting duration if present
- "agenda": agenda link/document
- "minutes": minutes link/document
- "video": video link

Return ONLY a JSON object mapping field names to column indices.
Only include fields that are actually present. Example:
{{"name": 0, "date": 1, "agenda": 3}}

HTML:
{sample_html}"""

        result = provider.complete(
            messages=[{"role": "user", "content": prompt}]
        )
        text = result.content.strip()

        # Provenance: record what the LLM saw and returned
        provenance = {
            "input": {"view_id": vid, "sample_html": sample_html, "num_columns": num_columns},
            "prompt_template": "generate_column_map/v1",
            "raw_response": text,
        }

        # Extract JSON from response (may be wrapped in ```json blocks)
        json_match = re.search(r"\{[^}]+\}", text)
        if not json_match:
            raise RuntimeError(f"LLM did not return valid JSON: {text[:200]}")

        column_map = _json.loads(json_match.group())

        # Validate: all values must be ints within column bounds
        valid_fields = {"name", "date", "duration", "agenda", "minutes", "video", "packet"}
        validated = {}
        for key, val in column_map.items():
            if key not in valid_fields:
                logger.warning(f"Ignoring unknown column field '{key}' from LLM")
                continue
            if not isinstance(val, int) or val < 0 or val >= num_columns:
                logger.warning(
                    f"Ignoring out-of-bounds column index {val} for '{key}' "
                    f"(table has {num_columns} columns)"
                )
                continue
            validated[key] = val

        if "name" not in validated or "date" not in validated:
            raise RuntimeError(
                f"LLM column map missing required fields (name, date): {column_map}"
            )

        provenance["parsed_map"] = column_map  # LLM's raw map before validation

        logger.info(
            f"Generated column map for {self.granicus_domain}: {validated}"
        )
        return {"column_map": validated, "provenance": provenance}

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

            # Use LLM-generated column_map if available, otherwise detect from headers
            if self.column_map:
                name_idx = self.column_map.get("name")
                date_idx = self.column_map.get("date")
                agenda_idx = self.column_map.get("agenda")
                minutes_idx = self.column_map.get("minutes")
                packet_idx = self.column_map.get("packet")
            else:
                name_idx = self._find_column_index(headers, ["name", "meeting"])
                date_idx = self._find_column_index(headers, ["date", "when"])
                agenda_idx = self._find_column_index(headers, ["agenda", "agenda link"])
                minutes_idx = self._find_column_index(headers, ["minutes"])
                packet_idx = self._find_column_index(
                    headers, ["packet", "agenda packet", "documents"]
                )

                # Positional fallback: if headers are empty/generic,
                # assume column 0 = name, column 1 = date
                if name_idx is None and date_idx is None and len(headers) >= 2:
                    if all(h == "" for h in headers[:2]):
                        name_idx = 0
                        date_idx = 1

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

                    # Extract links (header-based or fallback to URL pattern scan)
                    agenda_url = self._extract_link(cells, agenda_idx)
                    minutes_url = self._extract_link(cells, minutes_idx)
                    packet_url = self._extract_link(cells, packet_idx)

                    # Fallback: scan cells for known Granicus URL patterns
                    # when headers are empty (common in Mill Valley-style layouts)
                    if not agenda_url or not minutes_url:
                        for cell in cells:
                            for link in cell.find_all("a", href=True):
                                href = link["href"]
                                if not agenda_url and "AgendaViewer" in href:
                                    agenda_url = self._make_absolute_url(href)
                                elif not minutes_url and "MinutesViewer" in href:
                                    minutes_url = self._make_absolute_url(href)
                                elif not packet_url and "MetaViewer" in href:
                                    packet_url = self._make_absolute_url(href)

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

        Uses a three-tier strategy:
        1. Deterministic regex cleanup + hardcoded strptime formats
        2. Previously-learned formats (from LLM, cached in-process)
        3. LLM fallback (gpt-4o-mini) that also learns new format strings

        Handles:
        - "March 4, 2026", "Feb 25, 2026" (full/abbreviated month)
        - "10/7/2025", "03/10/26" (MM/DD/YYYY or MM/DD/YY)
        - "2025-10-07" (ISO)
        - "1773156600 03/10/26" (Unix timestamp prefix)
        - "03/10/26 - 08:30 AM" (with time suffix)
        - Unknown formats (via LLM fallback)
        """
        # Normalize whitespace first (Granicus HTML has \r\n and extra spaces)
        raw_text = date_text
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

        # Tier 1: Hardcoded formats (zero cost, covers ~99% of Granicus sites)
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

        # Tier 2: Try LLM-learned formats (free — cached from prior LLM calls)
        for fmt in _learned_date_formats:
            try:
                return datetime.strptime(date_text.strip(), fmt)
            except ValueError:
                continue

        # Tier 3: LLM fallback (one API call; learns format for next time)
        logger.info(f"No hardcoded format matched {date_text!r}, trying LLM")
        return _llm_parse_date(date_text)

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

        # Extract clip_id from agenda_url to construct video player URL
        video_url = None
        agenda_url = event.get("agenda_url", "")
        if agenda_url:
            clip_match = re.search(r"clip_id=(\d+)", agenda_url)
            if clip_match:
                video_url = f"{self.base_url}/player/clip/{clip_match.group(1)}"

        return Meeting(
            id=meeting_id,
            title=title,
            meeting_datetime=parsed_date or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=event.get("meeting_type"),
            status="scheduled",
            agenda_url=event.get("agenda_url"),
            minutes_url=event.get("minutes_url"),
            video_url=video_url,
            source_platform="granicus",
            source_url=event.get("source_url"),
            raw_data=event,
        )

    def get_meetings(
        self, days_ahead: int = 90, days_past: int = 0
    ) -> List[Meeting]:
        """Get normalized meetings, deduplicated across views.

        Granicus sites with multiple view_ids (e.g., view 2 and view 3)
        often list the same meeting in both. Deduplicates by (date, title)
        across all views, keeping the first occurrence (lowest view_id).
        Also deduplicates within a single view (e.g., English/Spanish rows).
        """
        events = self.get_events(days_ahead=days_ahead, days_past=days_past)
        seen: Dict[str, Meeting] = {}
        for event in events:
            meeting = self.normalize_event(event)
            # Cross-view dedup key: date + title slug (ignoring view_id)
            date_str = meeting.meeting_datetime.strftime("%Y%m%d")
            title_slug = re.sub(r"[^a-z0-9]+", "-", meeting.title.lower()).strip("-")[:50]
            dedup_key = f"{date_str}-{title_slug}"
            if dedup_key not in seen:
                seen[dedup_key] = meeting
        return list(seen.values())

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

        Stops after 5 consecutive empty responses. Returns raw view data
        keyed by view_id — body names are assigned later by
        generate_body_names() using the LLM.

        Returns:
            Dict mapping view_id to raw context dict with page_title and
            sample_titles. Pass this to generate_body_names() for final naming.
        """
        discovered: Dict[str, Dict[str, Any]] = {}
        consecutive_empty = 0

        for vid in range(1, 51):
            response = self._fetch_view(str(vid))
            if not response:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            # Extract raw page title and h1 (no filtering — LLM decides what's useful)
            page_title = ""
            title_tag = soup.find("title")
            if title_tag:
                page_title = title_tag.get_text(strip=True)

            h1_text = ""
            h1 = soup.find("h1")
            if h1:
                h1_text = h1.get_text(strip=True)

            # Check if the page has actual meeting data
            events = self._parse_table(response.text, str(vid))

            if events:
                # Collect sample meeting titles for LLM context
                sample_titles = [
                    e.get("title", "") for e in events[:8] if e.get("title")
                ]
                discovered[str(vid)] = {
                    "page_title": page_title,
                    "h1": h1_text,
                    "sample_titles": sample_titles,
                    "event_count": len(events),
                }
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                if consecutive_empty >= 5:
                    break

        logger.info(
            "Discovered Granicus view_ids",
            extra={
                "count": len(discovered),
                "view_ids": list(discovered.keys()),
                "jurisdiction_id": self.jurisdiction_id,
            },
        )

        return discovered

    def generate_body_names(self, raw_views: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Use LLM to assign descriptive body names to discovered view_ids.

        Runs once during onboarding. Sends page titles and sample meeting
        titles for each view_id. The LLM returns a clean body name per view.
        Result is saved in the extraction config (same pattern as column_map).

        Args:
            raw_views: Output of discover_view_ids() — {view_id: {page_title, h1, sample_titles}}

        Returns:
            Dict with:
              "archives": {body_name_slug: view_id} — the usable mapping
              "provenance": {input, prompt_template, raw_response} — for audit trail
        """
        if not raw_views:
            return {"archives": {}, "provenance": None}

        import json as _json

        from civicos_services.core.llm_provider import get_model_for_task

        # Build a compact description of each view for the LLM
        view_descriptions = []
        for vid, info in raw_views.items():
            desc = f"view_id={vid}"
            if info.get("page_title"):
                desc += f", page_title=\"{info['page_title']}\""
            if info.get("h1"):
                desc += f", h1=\"{info['h1']}\""
            if info.get("sample_titles"):
                titles = info["sample_titles"][:5]
                desc += f", sample_meeting_titles={titles}"
            view_descriptions.append(desc)

        views_text = "\n".join(view_descriptions)

        provider = get_model_for_task("navigation")

        prompt = f"""You are analyzing a government meeting platform. Each entry below represents a different page (view_id) that lists meetings for a specific governing body.

For each view_id, determine the name of the governing body (e.g., "City Council", "Planning Commission", "Board of Supervisors").

Use the page title, h1, and sample meeting titles as clues. Page titles are often generic (e.g., "New View", "Meeting List") — in that case, infer the body name from the meeting titles instead.

Return ONLY a JSON object mapping each view_id to the body name. Example:
{{"1": "City Council", "3": "Planning Commission", "7": "Parks and Recreation Commission"}}

Views:
{views_text}"""

        result = provider.complete(
            messages=[{"role": "user", "content": prompt}]
        )
        text = result.content.strip()

        # Provenance: record what the LLM saw and returned
        provenance = {
            "input": raw_views,
            "prompt_template": "generate_body_names/v1",
            "raw_response": text,
        }

        # Extract JSON from response
        json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not json_match:
            logger.warning(f"LLM body name response not valid JSON: {text[:200]}")
            return {
                "archives": {f"view_{vid}": vid for vid in raw_views},
                "provenance": provenance,
            }

        try:
            name_map = _json.loads(json_match.group())
        except _json.JSONDecodeError:
            logger.warning(f"LLM body name JSON parse failed: {json_match.group()[:200]}")
            return {
                "archives": {f"view_{vid}": vid for vid in raw_views},
                "provenance": provenance,
            }

        # Convert to slug keys: "City Council" → "city_council"
        result_map: Dict[str, str] = {}
        for vid, body_name in name_map.items():
            if not isinstance(body_name, str) or not body_name.strip():
                body_name = f"view_{vid}"
            key = re.sub(r"[^a-z0-9]+", "_", body_name.lower()).strip("_")
            if not key:
                key = f"view_{vid}"
            result_map[key] = str(vid)

        provenance["parsed_map"] = name_map  # LLM's raw names before slugification

        logger.info(
            f"Generated body names for {self.granicus_domain}: {result_map}"
        )
        return {"archives": result_map, "provenance": provenance}


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

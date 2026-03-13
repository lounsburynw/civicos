"""
Universal Adapter for municipal data extraction.

A generic extractor driven by a declarative config (CSS selectors, date formats,
pagination rules). The config is generated once at onboard time by an LLM
inspecting sample HTML; extraction itself is deterministic with no LLM calls.

See docs/public/decisions/universal_adapter.md for the design ADR.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from civicos_extraction.clients.base import (
    BaseExtractor,
    ExtractionConfig,
    HealthStatus,
    Meeting,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when extraction fails due to config drift or page changes."""
    pass


class UniversalExtractor(BaseExtractor):
    """
    Generic extractor driven by a declarative adapter config.

    All extraction behavior comes from the config generated at onboard time.
    No platform-specific logic lives here.
    """

    def __init__(
        self,
        jurisdiction_id: str,
        adapter_config: Dict[str, Any],
        base_url: str = "",
    ):
        super().__init__(jurisdiction_id)
        self.adapter = adapter_config
        self.base_url = base_url
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "CivicOS-UniversalAdapter/1.0"
        self._last_request_time = 0.0

    @property
    def platform_name(self) -> str:
        return "universal"

    @property
    def source_id(self) -> str:
        return f"universal-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "universal"

    def _rate_limit(self):
        """Enforce 1s minimum between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        self._last_request_time = time.time()

    def _fetch_page(self, url: str, timeout: int = 30) -> str:
        """Fetch a page, using Playwright if JavaScript is required."""
        if self.adapter.get("requires_javascript", False):
            return self._fetch_with_playwright(url)

        self._rate_limit()
        response = self._session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text

    def _fetch_with_playwright(self, url: str) -> str:
        """Fetch page using Playwright for JS-rendered content."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright required for JS-heavy pages. "
                "Install with: pip install playwright && playwright install chromium"
            )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            content = page.content()
            browser.close()
            return content

    def _extract_field(self, element, field_config: Dict[str, Any]) -> Optional[str]:
        """Extract a single field value from an element using config."""
        selector = field_config.get("selector", "")
        extract_mode = field_config.get("extract", "text")

        if selector:
            target = element.select_one(selector)
        else:
            target = element

        if target is None:
            return None

        if extract_mode == "text":
            return target.get_text(strip=True) or None
        elif extract_mode == "href":
            href = target.get("href")
            if href and self.base_url:
                return urljoin(self.base_url, href)
            return href
        elif extract_mode.startswith("attr:"):
            attr_name = extract_mode[5:]
            return target.get(attr_name)
        elif extract_mode == "html":
            return str(target)
        else:
            return target.get_text(strip=True) or None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string using configured format(s).

        Handles date ranges like "February 18-19, 2026" by extracting
        the first date from the range.
        """
        if not date_str:
            return None

        listing = self.adapter.get("listing", {})
        fields = listing.get("fields", {})
        date_config = fields.get("date", {})
        formats = date_config.get("date_formats", [])

        # Also check single format key
        single_format = date_config.get("date_format")
        if single_format and single_format not in formats:
            formats = [single_format] + formats

        # Common fallback formats
        fallbacks = [
            "%B %d, %Y",      # March 15, 2026
            "%b %d, %Y",      # Mar 15, 2026
            "%m/%d/%Y",       # 03/15/2026
            "%Y-%m-%d",       # 2026-03-15
            "%d %B %Y",       # 15 March 2026
            "%B %d %Y",       # March 15 2026
        ]

        clean = date_str.strip()

        # Handle date ranges: "February 18-19, 2026" → "February 18, 2026"
        # Also handles "January 7-14, 2026" and "February 25-26, 2026"
        range_match = re.match(
            r"(\w+ \d{1,2})-\d{1,2},?\s+(\d{4})", clean
        )
        if range_match:
            clean = f"{range_match.group(1)}, {range_match.group(2)}"

        for fmt in formats + fallbacks:
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue

        # Last resort: try dateutil if available
        try:
            from dateutil import parser as dateutil_parser
            return dateutil_parser.parse(clean, fuzzy=True)
        except (ImportError, ValueError):
            pass

        return None

    def _build_page_urls(self) -> List[str]:
        """Build list of page URLs based on pagination config."""
        listing = self.adapter.get("listing", {})
        url_template = listing.get("url_template", "")
        pagination = self.adapter.get("pagination", {})
        page_type = pagination.get("type", "none")
        max_pages = pagination.get("max_pages", 1)

        if page_type == "none" or max_pages <= 1:
            return [url_template.format(page=1)]
        elif page_type == "page_param":
            return [url_template.format(page=i) for i in range(1, max_pages + 1)]
        else:
            # For next_link and load_more, we start with page 1
            # and follow links during extraction
            return [url_template.format(page=1)]

    def _extract_rows_from_page(self, html: str) -> List[Dict[str, Any]]:
        """Extract raw event dicts from a single page's HTML."""
        listing = self.adapter.get("listing", {})
        container_selector = listing.get("container", "")
        row_selector = listing.get("row", "")
        fields = listing.get("fields", {})

        soup = BeautifulSoup(html, "html.parser")

        # Find the container element
        if container_selector:
            container = soup.select_one(container_selector)
            if container is None:
                raise ExtractionError(
                    f"Container selector '{container_selector}' matched 0 elements. "
                    f"Page may have changed since config was generated. "
                    f"Re-run config generation or inspect page manually."
                )
        else:
            container = soup

        # Find rows within the container
        if row_selector:
            rows = container.select(row_selector)
        else:
            rows = [container]

        if not rows:
            raise ExtractionError(
                f"Row selector '{row_selector}' matched 0 elements within "
                f"container '{container_selector}'. Page structure may have changed."
            )

        events = []
        date_parse_failures = 0

        for row in rows:
            event: Dict[str, Any] = {}
            for field_name, field_config in fields.items():
                value = self._extract_field(row, field_config)
                event[field_name] = value

            # Skip rows with no title (likely header rows or empty)
            if not event.get("title"):
                continue

            # Parse date if present
            if event.get("date"):
                parsed = self._parse_date(event["date"])
                if parsed:
                    event["_parsed_date"] = parsed
                else:
                    date_parse_failures += 1
                    logger.warning(
                        f"Could not parse date '{event['date']}' for "
                        f"'{event.get('title', '?')}'"
                    )

            # Combine date and time if both present
            if event.get("time") and event.get("_parsed_date"):
                time_str = event["time"].strip()
                time_match = re.match(
                    r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", time_str
                )
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    ampm = time_match.group(3)
                    if ampm and ampm.upper() == "PM" and hour < 12:
                        hour += 12
                    elif ampm and ampm.upper() == "AM" and hour == 12:
                        hour = 0
                    event["_parsed_date"] = event["_parsed_date"].replace(
                        hour=hour, minute=minute
                    )

            events.append(event)

        # Warn if too many date parse failures
        total = len(events)
        if total > 0 and date_parse_failures / total > 0.3:
            logger.warning(
                f"High date parse failure rate: {date_parse_failures}/{total} "
                f"({date_parse_failures/total:.0%}). Date format may have changed."
            )

        return events

    def _enrich_from_detail(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch a detail page and merge additional fields into the event.

        The "detail" config section specifies which listing field contains
        the detail URL, and what fields to extract from the detail page.
        Fields extracted from the detail page override listing-level values.

        Config example:
            "detail": {
                "url_field": "agenda_url",
                "fields": {
                    "time": {"selector": "time.datetime", "extract": "text"},
                    "location": {"selector": "strong", "extract": "text"},
                    "video_url": {"selector": "a[href*='youtube.com']", "extract": "href"}
                }
            }
        """
        detail_config = self.adapter.get("detail", {})
        if not detail_config:
            return event

        url_field = detail_config.get("url_field", "")
        detail_url = event.get(url_field)
        if not detail_url:
            return event

        fields = detail_config.get("fields", {})
        if not fields:
            return event

        try:
            html = self._fetch_page(detail_url)
            soup = BeautifulSoup(html, "html.parser")

            for field_name, field_config in fields.items():
                value = self._extract_field(soup, field_config)
                if value:
                    event[field_name] = value

            # Re-parse date if detail page provided a better one
            if "date" in fields and event.get("date"):
                parsed = self._parse_date(event["date"])
                if parsed:
                    event["_parsed_date"] = parsed

            # Parse time from detail page
            if event.get("time") and event.get("_parsed_date"):
                time_str = event["time"].strip()
                time_match = re.match(
                    r".*?(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", time_str
                )
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2))
                    ampm = time_match.group(3)
                    if ampm and ampm.upper() == "PM" and hour < 12:
                        hour += 12
                    elif ampm and ampm.upper() == "AM" and hour == 12:
                        hour = 0
                    event["_parsed_date"] = event["_parsed_date"].replace(
                        hour=hour, minute=minute
                    )

        except Exception as e:
            logger.warning(
                f"Failed to enrich from detail page {detail_url}: {e}"
            )

        return event

    def get_events(
        self, days_ahead: int = 90, days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """Extract events using the declarative adapter config."""
        now = datetime.now()
        start_date = now - timedelta(days=days_past)
        end_date = now + timedelta(days=days_ahead)

        all_events = []
        pagination = self.adapter.get("pagination", {})
        page_type = pagination.get("type", "none")

        urls = self._build_page_urls()

        for url in urls:
            html = self._fetch_page(url)
            events = self._extract_rows_from_page(html)
            all_events.extend(events)

            # Handle next_link pagination
            if page_type == "next_link":
                max_pages = pagination.get("max_pages", 10)
                next_selector = pagination.get("next_selector", "")
                pages_fetched = 1

                while pages_fetched < max_pages and next_selector:
                    soup = BeautifulSoup(html, "html.parser")
                    next_link = soup.select_one(next_selector)
                    if not next_link or not next_link.get("href"):
                        break
                    next_url = urljoin(url, next_link["href"])
                    html = self._fetch_page(next_url)
                    events = self._extract_rows_from_page(html)
                    if not events:
                        break
                    all_events.extend(events)
                    pages_fetched += 1

        # Filter by date range
        filtered = []
        for event in all_events:
            parsed_date = event.get("_parsed_date")
            if parsed_date:
                if start_date <= parsed_date <= end_date:
                    filtered.append(event)
            else:
                # Include events without parseable dates (let caller decide)
                filtered.append(event)

        # Enrich from detail pages (if configured)
        if self.adapter.get("detail"):
            filtered = [self._enrich_from_detail(e) for e in filtered]

        logger.info(
            f"Universal adapter extracted {len(filtered)} events "
            f"(from {len(all_events)} total) for {self.jurisdiction_id}"
        )
        return filtered

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize extracted event dict to Meeting format."""
        title = event.get("title", "Unknown Meeting")
        parsed_date = event.get("_parsed_date")

        if not parsed_date:
            # Use epoch as sentinel — caller should check
            parsed_date = datetime(1970, 1, 1)

        # Generate a stable ID from title + date
        id_source = f"{self.jurisdiction_id}:{title}:{parsed_date.isoformat()}"
        meeting_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

        return Meeting(
            id=f"universal-{meeting_id}",
            title=title,
            meeting_datetime=parsed_date,
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=event.get("meeting_type"),
            agenda_url=event.get("agenda_url"),
            minutes_url=event.get("minutes_url"),
            video_url=event.get("video_url"),
            source_platform="universal",
            source_url=self.adapter.get("listing", {}).get("url_template", ""),
            raw_data={k: v for k, v in event.items() if not k.startswith("_")},
        )

    def health(self) -> HealthStatus:
        """Check if the adapter config still works against the live page."""
        start = time.time()
        errors = []
        count = 0

        try:
            listing = self.adapter.get("listing", {})
            url = listing.get("url_template", "").format(page=1)
            html = self._fetch_page(url)
            soup = BeautifulSoup(html, "html.parser")

            container_sel = listing.get("container", "")
            row_sel = listing.get("row", "")

            if container_sel:
                container = soup.select_one(container_sel)
                if not container:
                    errors.append(
                        f"Container selector '{container_sel}' matched 0 elements"
                    )
                elif row_sel:
                    rows = container.select(row_sel)
                    count = len(rows)
                    if count == 0:
                        errors.append(
                            f"Row selector '{row_sel}' matched 0 elements"
                        )
            else:
                errors.append("No container selector configured")

        except Exception as e:
            errors.append(str(e))

        duration = (time.time() - start) * 1000
        return HealthStatus(
            source_id=self.source_id,
            source_type="universal",
            jurisdiction_id=self.jurisdiction_id,
            is_available=len(errors) == 0 and count > 0,
            available_count=count,
            last_checked=datetime.now(timezone.utc),
            check_duration_ms=round(duration, 2),
            errors=errors,
        )

    def validate(self) -> ValidationResult:
        """Validate the adapter config structure."""
        start = time.time()
        errors = []
        warnings = []

        listing = self.adapter.get("listing", {})
        if not listing:
            errors.append("Missing 'listing' in adapter config")

        if not listing.get("url_template"):
            errors.append("Missing 'listing.url_template'")

        if not listing.get("container"):
            warnings.append("No 'listing.container' — will search entire page")

        if not listing.get("row"):
            errors.append("Missing 'listing.row' selector")

        fields = listing.get("fields", {})
        if "title" not in fields:
            errors.append("Missing required field 'title' in listing.fields")
        if "date" not in fields:
            errors.append("Missing required field 'date' in listing.fields")

        duration = (time.time() - start) * 1000
        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=len(errors) == 0,
            api_reachable=True,  # Validated separately via health()
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(duration, 2),
        )


class UniversalSource:
    """
    Config-driven wrapper implementing the DataSource protocol.

    Mirrors the pattern used by GranicusSource, ProudCitySource, etc.
    """

    def __init__(self, config: ExtractionConfig):
        self._config = config
        adapter_config = config.metadata.get("adapter", {})
        if not adapter_config:
            raise ValueError(
                f"ExtractionConfig for {config.jurisdiction_id} missing "
                f"'adapter' in metadata. Run config generation first."
            )
        self._extractor = UniversalExtractor(
            jurisdiction_id=config.jurisdiction_id,
            adapter_config=adapter_config,
            base_url=config.base_url,
        )

    @classmethod
    def from_jurisdiction(cls, jurisdiction_id: str) -> "UniversalSource":
        config = ExtractionConfig.from_jurisdiction(jurisdiction_id)
        return cls(config)

    @property
    def source_id(self) -> str:
        return self._extractor.source_id

    @property
    def source_type(self) -> str:
        return self._extractor.source_type

    def health(self) -> HealthStatus:
        return self._extractor.health()

    def validate(self) -> ValidationResult:
        return self._extractor.validate()

    def get_events(self, days_ahead: int = 90, days_past: int = 0):
        return self._extractor.get_events(days_ahead=days_ahead, days_past=days_past)

    def get_meetings(self, days_ahead: int = 90, days_past: int = 0):
        return self._extractor.get_meetings(days_ahead=days_ahead, days_past=days_past)

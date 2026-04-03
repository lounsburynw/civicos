"""
CivicPlus Archive Client

Extracts meeting data from CivicPlus-powered municipal websites.
CivicPlus hosts Archive.aspx pages with document collections identified by AMID.
Each AMID is a collection of documents (agendas, minutes, etc.) for a specific body.

Usage:
    client = CivicPlusClient(
        base_url="https://www.ci.larkspur.ca.us",
        jurisdiction_id="city-larkspur",
        archives={"city_council": "49"},
    )
    meetings = client.get_meetings(days_past=365)
"""

import logging
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from civicos_extraction.clients.base import (
    BaseExtractor,
    ExtractionConfig,
    HealthStatus,
    Meeting,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Regex to extract ADID links and their text from Archive.aspx pages.
# Pattern: <a href="Archive.aspx?ADID=1234" ...><span>March 30, 2026, City Council Agenda</span></a>
_ADID_RE = re.compile(
    r'<a[^>]*href=["\'](?:.*?)Archive\.aspx\?ADID=(\d+)["\'][^>]*>\s*(?:<span>)?\s*(.*?)\s*(?:</span>)?\s*</a>',
    re.DOTALL | re.IGNORECASE,
)

# Date patterns found in CivicPlus link text.
# "March 30, 2026, City Council Agenda" or "March 30, 2026 City Council Agenda"
_DATE_RE = re.compile(
    r"^((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})[,\s]*(.*)",
    re.IGNORECASE,
)

# Alternative: "3/30/2026 City Council Agenda"
_DATE_NUMERIC_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})[,\s]*(.*)",
)

# Compact format: "02172026 Approved Corte Madera Regular Town Council Minutes"
_DATE_COMPACT_RE = re.compile(
    r"^(\d{8})\s+(.*)",
)


def _parse_entry_text(text: str) -> Optional[Dict[str, str]]:
    """Parse date and description from a CivicPlus archive entry's link text."""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    m = _DATE_RE.match(text)
    if m:
        return {"date_str": m.group(1).strip().rstrip(","), "description": m.group(2).strip()}

    m = _DATE_NUMERIC_RE.match(text)
    if m:
        return {"date_str": m.group(1).strip(), "description": m.group(2).strip()}

    m = _DATE_COMPACT_RE.match(text)
    if m:
        return {"date_str": m.group(1), "description": m.group(2).strip()}

    return None


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string from CivicPlus into a datetime."""
    for fmt in ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m%d%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


class CivicPlusClient(BaseExtractor):
    """
    CivicPlus Archive.aspx client.

    Scrapes Archive.aspx?AMID=N pages to extract document links, then groups
    by date to produce Meeting objects. Agendas and minutes from separate
    AMIDs are correlated by date.
    """

    def __init__(
        self,
        base_url: str,
        jurisdiction_id: str,
        archives: Optional[Dict[str, str]] = None,
        minutes_archives: Optional[Dict[str, str]] = None,
    ):
        super().__init__(jurisdiction_id)
        self.base_url = base_url.rstrip("/")
        self.archives = archives or {}
        self.minutes_archives = minutes_archives or {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CivicOS-Extraction/1.0",
        })
        self.last_request_time = 0.0
        self.min_request_interval = 0.5

    @property
    def platform_name(self) -> str:
        return "civicplus"

    @property
    def source_id(self) -> str:
        return f"civicplus-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "civicplus"

    def _throttle(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _fetch_archive(self, amid: str) -> List[Dict[str, Any]]:
        """Fetch and parse all entries from an Archive.aspx?AMID=N page."""
        url = f"{self.base_url}/Archive.aspx?AMID={amid}"
        self._throttle()

        resp = self.session.get(url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        entries = []
        for match in _ADID_RE.finditer(html):
            adid = match.group(1)
            raw_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            parsed = _parse_entry_text(raw_text)
            if not parsed:
                logger.debug(f"Could not parse entry text: {raw_text!r}")
                continue

            dt = _parse_date(parsed["date_str"])
            if not dt:
                logger.debug(f"Could not parse date: {parsed['date_str']!r}")
                continue

            doc_url = f"{self.base_url}/ArchiveCenter/ViewFile/Item/{adid}"
            entries.append({
                "adid": adid,
                "date": dt,
                "description": parsed["description"],
                "doc_url": doc_url,
                "raw_text": raw_text,
            })

        logger.info(f"Fetched {len(entries)} entries from AMID={amid} at {self.base_url}")
        return entries

    def get_events(
        self, days_ahead: int = 90, days_past: int = 365
    ) -> List[Dict[str, Any]]:
        """Extract meeting events from CivicPlus archive pages.

        Groups agenda and minutes entries by (body, date) to produce one
        event per meeting.
        """
        now = datetime.now()
        cutoff_past = now - timedelta(days=days_past)
        cutoff_future = now + timedelta(days=days_ahead)

        # meeting_key -> event dict
        meetings: Dict[str, Dict[str, Any]] = {}

        # Fetch agendas per body
        for body_slug, amid in self.archives.items():
            body_name = body_slug.replace("_", " ").title()
            entries = self._fetch_archive(amid)

            for entry in entries:
                dt = entry["date"]
                if dt < cutoff_past or dt > cutoff_future:
                    continue

                key = f"{body_slug}:{dt.strftime('%Y-%m-%d')}"
                if key not in meetings:
                    meetings[key] = {
                        "body_slug": body_slug,
                        "body_name": body_name,
                        "date": dt,
                        "description": entry["description"],
                        "agenda_url": entry["doc_url"],
                        "minutes_url": None,
                        "adid": entry["adid"],
                    }
                else:
                    # Multiple agenda docs for same date — keep first
                    pass

        # Fetch minutes per body (if configured)
        for body_slug, amid in self.minutes_archives.items():
            entries = self._fetch_archive(amid)
            for entry in entries:
                dt = entry["date"]
                key = f"{body_slug}:{dt.strftime('%Y-%m-%d')}"
                if key in meetings:
                    meetings[key]["minutes_url"] = entry["doc_url"]

        # Sort by date descending
        result = sorted(meetings.values(), key=lambda e: e["date"], reverse=True)
        return result

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        dt = event["date"]
        body_name = event["body_name"]
        body_slug = event.get("body_slug", "")
        description = event.get("description", "")

        # meeting_type = the governing body (not the status)
        meeting_type = body_slug or body_name.lower().replace(" ", "_")

        title = f"{body_name}"
        if description and body_name.lower() not in description.lower():
            title = f"{body_name} — {description}"

        # Determine status from date and description
        desc_lower = description.lower()
        now_utc = datetime.now(timezone.utc)
        dt_utc = dt.replace(tzinfo=timezone.utc)  # CivicPlus dates are date-only, no TZ
        if "cancel" in desc_lower:
            status = "cancelled"
        elif dt_utc < now_utc:
            status = "completed"
        else:
            status = "scheduled"

        meeting_id = f"civicplus-{self.jurisdiction_id}-{body_slug}-{dt.strftime('%Y%m%d')}"

        return Meeting(
            id=meeting_id,
            title=title,
            meeting_datetime=dt_utc,
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=meeting_type,
            status=status,
            agenda_url=event.get("agenda_url"),
            minutes_url=event.get("minutes_url"),
            source_platform="civicplus",
            source_url=f"{self.base_url}/Archive.aspx?AMID={self.archives.get(body_slug, '')}",
            raw_data=event,
        )

    def health(self) -> HealthStatus:
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            events = self.get_events(days_ahead=30, days_past=30)
            is_available = True
            available_count = len(events)
            metadata["event_count_60day"] = available_count
        except Exception as e:
            errors.append(f"Health check error: {str(e)}")

        check_duration_ms = (time.time() - start_time) * 1000
        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.now(timezone.utc),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.now(timezone.utc) if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        api_reachable = False

        if not self.base_url:
            errors.append("base_url is required")
        if not self.archives:
            errors.append("At least one archive AMID is required")

        if not errors:
            # Probe the first archive page
            first_amid = next(iter(self.archives.values()))
            try:
                url = f"{self.base_url}/Archive.aspx?AMID={first_amid}"
                resp = self.session.get(url, timeout=10, allow_redirects=True)
                api_reachable = resp.status_code == 200
                if not api_reachable:
                    errors.append(f"Archive page returned HTTP {resp.status_code}")
            except Exception as e:
                errors.append(f"Could not reach archive page: {e}")

        check_duration_ms = (time.time() - start_time) * 1000
        return ValidationResult(
            source_id=self.source_id,
            source_type=self.source_type,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            config_valid=len(errors) == 0,
            api_reachable=api_reachable,
            check_duration_ms=round(check_duration_ms, 2),
        )


class CivicPlusSource:
    """Wrapper that creates a CivicPlusClient from an ExtractionConfig."""

    def __init__(self, config: ExtractionConfig):
        self._config = config
        self._client = CivicPlusClient(
            base_url=config.base_url,
            jurisdiction_id=config.jurisdiction_id,
            archives=config.archives or {},
            minutes_archives=config.metadata.get("minutes_archives", {}),
        )

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

    def get_events(self, days_ahead: int = 90, days_past: int = 365) -> List[Dict[str, Any]]:
        return self._client.get_events(days_ahead=days_ahead, days_past=days_past)

    def get_meetings(self, days_ahead: int = 90, days_past: int = 365) -> List[Meeting]:
        return self._client.get_meetings(days_ahead=days_ahead, days_past=days_past)

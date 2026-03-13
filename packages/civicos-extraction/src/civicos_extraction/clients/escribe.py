"""
eScribe Meeting Management Client

Extracts meeting data from eScribe-powered municipal websites.
Used by Canadian municipalities (Ottawa, Hamilton, Barrie, Guelph) and
some US cities (National City, CA).

eScribe instances are hosted at pub-{instance}.escribemeetings.com and expose
a JSON API via AJAX POST endpoints.

Usage:
    client = EScribeClient("nationalcity", "city-national-city")
    events = client.get_events(days_ahead=30)
    meetings = client.get_meetings(days_ahead=30)  # Normalized
"""

import logging
import re
import requests
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from civicos_extraction.clients.base import BaseExtractor, Meeting, HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class EScribeClient(BaseExtractor):
    """
    eScribe API client.

    Uses the JSON calendar API at /MeetingsCalendarView.aspx/GetCalendarMeetings
    which returns structured meeting data without HTML scraping.
    """

    def __init__(self, instance_name: str, jurisdiction_id: str):
        """
        Initialize eScribe client.

        Args:
            instance_name: eScribe instance identifier (e.g., "nationalcity", "ottawa")
            jurisdiction_id: Jurisdiction ID (e.g., "city-national-city")
        """
        super().__init__(jurisdiction_id)
        self.instance_name = instance_name
        self.base_url = f"https://pub-{instance_name}.escribemeetings.com"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CivicOS-Extraction/1.0",
            "Content-Type": "application/json; charset=utf-8",
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5

    @property
    def platform_name(self) -> str:
        return "escribe"

    @property
    def source_id(self) -> str:
        return f"escribe-{self.instance_name}"

    @property
    def source_type(self) -> str:
        return "escribe"

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
            logger.warning(
                "Health check failed",
                extra={
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                    "instance_name": self.instance_name,
                }
            )

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
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        if not self.instance_name:
            errors.append("instance_name is required")
            config_valid = False

        if config_valid:
            try:
                # Probe the calendar page to verify instance exists
                response = self.session.get(
                    f"{self.base_url}/MeetingsCalendarView.aspx",
                    timeout=10,
                )
                if response.status_code == 200:
                    api_reachable = True
                else:
                    errors.append(
                        f"Cannot reach eScribe instance at {self.base_url} "
                        f"(status {response.status_code})"
                    )
            except Exception as e:
                errors.append(f"Cannot reach eScribe instance: {str(e)}")
                metadata["connection_error"] = str(e)

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
            metadata=metadata,
        )

    def _throttle_request(self):
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _post_json(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        retries: int = 3,
    ) -> Optional[Any]:
        """Make a JSON POST request to the eScribe AJAX API with retries."""
        self._throttle_request()
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.post(url, json=payload, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    # eScribe wraps responses in a "d" key
                    return data.get("d", data)
                elif response.status_code in [429, 500, 502, 503]:
                    logger.warning(
                        "Retryable HTTP error",
                        extra={
                            "url": url,
                            "attempt": attempt + 1,
                            "status_code": response.status_code,
                            "platform": self.platform_name,
                            "instance_name": self.instance_name,
                        }
                    )
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logger.warning(
                        "Non-retryable HTTP error",
                        extra={
                            "url": url,
                            "status_code": response.status_code,
                            "platform": self.platform_name,
                            "instance_name": self.instance_name,
                        }
                    )
                    return None

            except requests.exceptions.Timeout:
                logger.warning(
                    "Request timeout",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request error",
                    extra={
                        "url": url,
                        "attempt": attempt + 1,
                        "error": str(e),
                        "platform": self.platform_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get events from the eScribe calendar API.

        Uses the GetCalendarMeetings AJAX endpoint which returns JSON
        meeting data for a given date range.
        """
        start_date = datetime.now() - timedelta(days=days_past)
        end_date = datetime.now() + timedelta(days=days_ahead)

        payload = {
            "calendarStartDate": start_date.strftime("%Y-%m-%d"),
            "calendarEndDate": end_date.strftime("%Y-%m-%d"),
        }

        data = self._post_json(
            "MeetingsCalendarView.aspx/GetCalendarMeetings",
            payload,
        )

        if not data or not isinstance(data, list):
            return []

        return data

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize an eScribe event to the Meeting dataclass."""
        # Parse datetime from "YYYY/MM/DD HH:MM:SS" format
        # eScribe returns local times without timezone; treat as UTC
        start_str = event.get("StartDate", "")
        meeting_datetime = datetime.now(timezone.utc)
        if start_str:
            try:
                meeting_datetime = datetime.strptime(start_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                try:
                    meeting_datetime = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        title = event.get("MeetingName", "Meeting")
        meeting_type = self._infer_meeting_type(title)
        escribe_id = event.get("ID", "")

        # Build stable meeting ID
        date_str = meeting_datetime.strftime("%Y%m%d")
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        meeting_id = f"escribe-{self.jurisdiction_id}-{date_str}-{title_slug}"

        # Extract agenda/minutes URLs from MeetingDocumentLink
        agenda_url = None
        minutes_url = None
        for doc in event.get("MeetingDocumentLink", []):
            doc_type = (doc.get("Type") or "").lower()
            doc_title = (doc.get("Title") or "").lower()
            doc_url = doc.get("Url", "")
            if not doc_url:
                continue
            # Make relative URLs absolute
            if doc_url.startswith("/"):
                doc_url = f"{self.base_url}{doc_url}"

            if "agenda" in doc_type or "agenda" in doc_title:
                if not agenda_url:  # Prefer first match
                    agenda_url = doc_url
            elif "minutes" in doc_type or "minutes" in doc_title:
                if not minutes_url:
                    minutes_url = doc_url

        # Extract location from Description HTML if Location field is empty
        location = event.get("Location")
        if not location:
            desc = event.get("Description", "")
            # Description often contains address in HTML
            if desc:
                # Strip HTML tags for location
                location = re.sub(r"<[^>]+>", " ", desc).strip()
                if len(location) > 200:
                    location = location[:200]

        # Meeting page URL
        meeting_url = event.get("Url") or event.get("ShareUrl")
        if meeting_url and meeting_url.startswith("/"):
            meeting_url = f"{self.base_url}{meeting_url}"

        return Meeting(
            id=meeting_id,
            title=title,
            meeting_datetime=meeting_datetime,
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=meeting_type,
            status="scheduled" if not event.get("MeetingPassed") else "completed",
            location=location,
            agenda_url=agenda_url,
            minutes_url=minutes_url,
            video_url=None,
            source_platform="escribe",
            source_url=meeting_url,
            raw_data=event,
        )

    def _infer_meeting_type(self, title: str) -> str:
        """Infer meeting type from the meeting title."""
        title_lower = title.lower()

        if "council" in title_lower:
            return "city_council"
        elif "planning" in title_lower:
            return "planning_commission"
        elif "zoning" in title_lower:
            return "zoning_board"
        elif "school" in title_lower or "board of education" in title_lower:
            return "school_board"
        elif "commission" in title_lower:
            return "commission"
        elif "committee" in title_lower:
            return "committee"
        elif "board" in title_lower:
            return "board"
        else:
            return "other"

    def get_meeting_types(self) -> List[str]:
        """Get distinct meeting types by fetching a broad date range."""
        events = self.get_events(days_ahead=0, days_past=365)
        types = set()
        for event in events:
            mt = event.get("MeetingType") or event.get("MeetingName", "")
            if mt:
                types.add(mt)
        return sorted(types)

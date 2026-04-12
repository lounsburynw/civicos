"""
Legistar API Client

Extracts meeting data from Legistar-powered municipal websites.
Used by 6+ cities including Berkeley, Oakland, San Francisco.

Usage:
    client = LegistarClient("berkeley")
    events = client.get_events(days_ahead=30)
    meetings = client.get_meetings(days_ahead=30)  # Normalized
"""

import logging
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from civicos_extraction.clients.base import BaseExtractor, Meeting, HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


class LegistarClient(BaseExtractor):
    """
    Legistar API client with production guardrails.

    Features:
    - Request throttling to avoid rate limits
    - Exponential backoff on errors
    - Schema normalization
    """

    def __init__(self, client_name: str, jurisdiction_id: Optional[str] = None):
        """
        Initialize Legistar client.

        Args:
            client_name: Legistar client identifier (e.g., "berkeley")
            jurisdiction_id: Optional jurisdiction ID (defaults to "city-{client_name}")
        """
        super().__init__(jurisdiction_id or f"city-{client_name}")
        self.client_name = client_name
        self.base_url = f"https://webapi.legistar.com/v1/{client_name}"
        self.session = requests.Session()
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Throttle to avoid 500 errors

    @property
    def platform_name(self) -> str:
        return "legistar"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"legistar-{self.client_name}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "legistar"

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by querying events for the last 7 days.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            # Quick availability check: query last 7 days of events
            events = self.get_events(days_ahead=7, days_past=7)
            is_available = True
            available_count = len(events)

            # Get body count for metadata
            bodies = self.get_bodies()
            metadata = {
                'event_count_14day': available_count,
                'body_count': len(bodies) if bodies else 0,
            }

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "Health check failed",
                extra={
                    "error": str(e),
                    "jurisdiction_id": self.jurisdiction_id,
                    "platform": self.platform_name,
                    "client_name": self.client_name,
                }
            )

        check_duration_ms = (time.time() - start_time) * 1000

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.utcnow(),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.utcnow() if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """
        Validate source configuration and API access before running pipeline.

        Preflight check that fails fast with clear error messages for:
        - Missing client_name
        - Unreachable Legistar API endpoint

        Returns:
            ValidationResult with is_valid, errors, warnings, and timing
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check required config
        if not self.client_name:
            errors.append("client_name is required")
            config_valid = False

        # Check API reachability by hitting /bodies endpoint (lightweight)
        if config_valid:
            try:
                bodies = self._make_request("bodies", retries=1)
                if bodies is not None:
                    api_reachable = True
                    metadata["body_count"] = len(bodies) if isinstance(bodies, list) else 0
                else:
                    errors.append(f"Cannot reach Legistar API at {self.base_url}")
            except Exception as e:
                errors.append(f"Cannot reach Legistar API: {str(e)}")
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
        """Prevent burst requests that cause 5xx errors."""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        retries: int = 3
    ) -> Optional[Any]:
        """Make API request with exponential backoff."""
        self._throttle_request()
        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    logger.warning(
                        "Retryable HTTP error",
                        extra={
                            "url": url,
                            "endpoint": endpoint,
                            "attempt": attempt + 1,
                            "max_retries": retries,
                            "error_type": "http_error",
                            "status_code": response.status_code,
                            "jurisdiction_id": self.jurisdiction_id,
                            "platform": self.platform_name,
                            "client_name": self.client_name,
                        }
                    )
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        "Non-retryable HTTP error",
                        extra={
                            "url": url,
                            "endpoint": endpoint,
                            "attempt": attempt + 1,
                            "error_type": "http_error",
                            "status_code": response.status_code,
                            "jurisdiction_id": self.jurisdiction_id,
                            "platform": self.platform_name,
                            "client_name": self.client_name,
                        }
                    )
                    return None

            except requests.exceptions.Timeout as e:
                logger.warning(
                    "Request timeout",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": "timeout",
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "total_attempts": retries,
                        "error_type": "timeout",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                return None
            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    "Connection error",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": "connection_error",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "total_attempts": retries,
                        "error_type": "connection_error",
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                return None
            except Exception as e:
                logger.warning(
                    "Request exception",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "max_retries": retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(
                    "Request failed after all retries",
                    extra={
                        "url": url,
                        "endpoint": endpoint,
                        "total_attempts": retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "jurisdiction_id": self.jurisdiction_id,
                        "platform": self.platform_name,
                        "client_name": self.client_name,
                    }
                )
                return None

        # All retries exhausted for retryable status codes
        logger.error(
            "Request failed after all retries",
            extra={
                "url": url,
                "endpoint": endpoint,
                "total_attempts": retries,
                "error_type": "http_error",
                "jurisdiction_id": self.jurisdiction_id,
                "platform": self.platform_name,
                "client_name": self.client_name,
            }
        )
        return None

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get events from Legistar API.

        Args:
            days_ahead: Days into the future
            days_past: Days into the past

        Returns:
            List of event dictionaries
        """
        start_date = datetime.now() - timedelta(days=days_past)
        end_date = datetime.now() + timedelta(days=days_ahead)

        # OData filter
        filter_str = (
            f"EventDate ge datetime'{start_date.strftime('%Y-%m-%d')}' and "
            f"EventDate le datetime'{end_date.strftime('%Y-%m-%d')}'"
        )

        params = {
            "$filter": filter_str,
            "$orderby": "EventDate asc"
        }

        events = self._make_request("events", params)
        return events if events else []

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize Legistar event to Meeting format.

        Args:
            event: Raw Legistar event dictionary

        Returns:
            Normalized Meeting object
        """
        # Parse date/time
        event_date = event.get("EventDate", "")
        event_time = event.get("EventTime", "")

        meeting_datetime = None
        if event_date:
            try:
                date_str = event_date.split("T")[0]
                if event_time:
                    # Legistar returns time in various formats:
                    # ISO: "2026-03-23T13:00:00"  or  12-hour: "1:00 PM"
                    if "T" in event_time:
                        time_str = event_time.split("T")[1]
                        meeting_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
                    else:
                        parsed_time = datetime.strptime(event_time.strip(), "%I:%M %p").time()
                        meeting_datetime = datetime.fromisoformat(date_str).replace(
                            hour=parsed_time.hour, minute=parsed_time.minute
                        )
                else:
                    meeting_datetime = datetime.fromisoformat(date_str)
            except (ValueError, IndexError):
                meeting_datetime = datetime.now()

        # Build agenda URL
        agenda_url = None
        event_id = event.get("EventId")
        if event_id:
            agenda_url = f"https://{self.client_name}.legistar.com/MeetingDetail.aspx?ID={event_id}"

        # Determine meeting type from body name
        body_name = event.get("EventBodyName", "")
        meeting_type = self._infer_meeting_type(body_name)

        return Meeting(
            id=f"meeting:{self.jurisdiction_id}:legistar:{event_id}",
            title=body_name or "Meeting",
            meeting_datetime=meeting_datetime or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=meeting_type,
            status="scheduled",
            location=event.get("EventLocation"),
            agenda_url=agenda_url,
            video_url=event.get("EventVideoPath"),
            source_platform="legistar",
            source_url=agenda_url,
            raw_data=event
        )

    def _infer_meeting_type(self, body_name: str) -> str:
        """Infer meeting type from body name."""
        body_lower = body_name.lower()

        if "council" in body_lower:
            return "city_council"
        elif "planning" in body_lower:
            return "planning_commission"
        elif "zoning" in body_lower:
            return "zoning_board"
        elif "school" in body_lower or "board of education" in body_lower:
            return "school_board"
        elif "commission" in body_lower:
            return "commission"
        elif "committee" in body_lower:
            return "committee"
        else:
            return "other"

    def get_event_items(self, event_id: int) -> List[Dict[str, Any]]:
        """
        Get agenda items for a specific event from the Legistar API.

        Returns normalized items with agenda_number and matter_id for
        matching LLM-extracted decisions back to platform-internal IDs.

        Args:
            event_id: Legistar EventId

        Returns:
            List of dicts with keys: event_item_id, agenda_number, title,
            matter_id, matter_file
        """
        items = self._make_request(f"events/{event_id}/EventItems")
        if not items or not isinstance(items, list):
            return []

        normalized = []
        for item in items:
            matter_id = item.get("EventItemMatterId")
            agenda_number = (item.get("EventItemAgendaNumber") or "").strip()
            title = (item.get("EventItemTitle") or "").strip()
            if agenda_number or title:
                normalized.append({
                    "event_item_id": item.get("EventItemId"),
                    "agenda_number": agenda_number,
                    "title": title,
                    "matter_id": matter_id,
                    "matter_file": (item.get("EventItemMatterFile") or "").strip(),
                })
        return normalized

    def get_bodies(self) -> List[Dict[str, Any]]:
        """Get list of meeting bodies (councils, commissions, etc.)."""
        bodies = self._make_request("bodies")
        return bodies if bodies else []

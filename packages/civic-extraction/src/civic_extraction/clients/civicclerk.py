"""
CivicClerk API Client

Extracts meeting data from CivicClerk-powered municipal websites.
Used by 11+ cities including El Cerrito, Hayward, San Pablo.

Usage:
    client = CivicClerkClient("elcerritoca")
    events = client.get_events(days_ahead=30)
    meetings = client.get_meetings(days_ahead=30)  # Normalized
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import quote

from civic_extraction.clients.base import BaseExtractor, Meeting


class CivicClerkClient(BaseExtractor):
    """
    CivicClerk API client.

    Features:
    - OData filtering support
    - Event details enrichment (for published files)
    - Schema normalization
    """

    def __init__(self, subdomain: str, jurisdiction_id: Optional[str] = None):
        """
        Initialize CivicClerk client.

        Args:
            subdomain: CivicClerk subdomain (e.g., "elcerritoca")
            jurisdiction_id: Optional jurisdiction ID (defaults to subdomain)
        """
        super().__init__(jurisdiction_id or subdomain)
        self.subdomain = subdomain
        self.api_base = f"https://{subdomain}.api.civicclerk.com/v1"
        self.portal_base = f"https://{subdomain}.portal.civicclerk.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Civic-Platform/1.0'
        })

    @property
    def platform_name(self) -> str:
        return "civicclerk"

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0,
        has_agenda: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get events from CivicClerk API.

        Args:
            days_ahead: Days into the future
            days_past: Days into the past
            has_agenda: Filter to events with agendas only

        Returns:
            List of event dictionaries with details
        """
        start_date = datetime.now() - timedelta(days=days_past)
        end_date = datetime.now() + timedelta(days=days_ahead)

        # Build OData filter
        start_str = start_date.strftime('%Y-%m-%dT00:00:00.000Z')
        end_str = end_date.strftime('%Y-%m-%dT23:59:59.999Z')

        filter_parts = [
            f"startDateTime ge {start_str}",
            f"startDateTime le {end_str}"
        ]
        if has_agenda is not None:
            filter_parts.append(f"hasAgenda eq {'true' if has_agenda else 'false'}")

        filter_str = " and ".join(filter_parts)
        orderby_str = "startDateTime asc"

        api_url = f"{self.api_base}/Events?$filter={quote(filter_str)}&$orderby={quote(orderby_str)}"

        try:
            response = self.session.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            events = data.get('value', [])

            # Enrich with details (for published files)
            enriched = []
            for event in events:
                event_id = event.get('id')
                if event_id:
                    details = self.get_event_details(event_id)
                    enriched.append(details if details else event)
                else:
                    enriched.append(event)

            return enriched

        except Exception:
            return []

    def get_event_details(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed event information.

        Args:
            event_id: CivicClerk event ID

        Returns:
            Event dictionary with full details
        """
        try:
            response = self.session.get(
                f"{self.api_base}/Events/{event_id}",
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize CivicClerk event to Meeting format.

        Args:
            event: Raw CivicClerk event dictionary

        Returns:
            Normalized Meeting object
        """
        # Parse datetime
        start_datetime = event.get("startDateTime", "")
        meeting_datetime = None
        if start_datetime:
            try:
                meeting_datetime = datetime.fromisoformat(
                    start_datetime.replace('Z', '+00:00')
                )
            except ValueError:
                meeting_datetime = datetime.now()

        # Build URLs
        event_id = event.get("id")
        portal_url = f"{self.portal_base}/#/Event/{event_id}" if event_id else None

        # Find agenda URL from published files
        agenda_url = None
        published_files = event.get("publishedFiles", [])
        for pf in published_files:
            if pf.get("name", "").lower().startswith("agenda"):
                agenda_url = pf.get("url")
                break

        # Determine meeting type from name
        name = event.get("name", "")
        meeting_type = self._infer_meeting_type(name)

        return Meeting(
            id=f"civicclerk-{self.subdomain}-{event_id}",
            title=name or "Meeting",
            meeting_datetime=meeting_datetime or datetime.now(),
            jurisdiction_id=self.jurisdiction_id,
            meeting_type=meeting_type,
            status="scheduled",
            location=event.get("location"),
            virtual_url=event.get("virtualMeetingUrl"),
            agenda_url=agenda_url,
            video_url=event.get("videoUrl"),
            source_platform="civicclerk",
            source_url=portal_url,
            raw_data=event
        )

    def _infer_meeting_type(self, name: str) -> str:
        """Infer meeting type from event name."""
        name_lower = name.lower()

        if "council" in name_lower:
            return "city_council"
        elif "planning" in name_lower:
            return "planning_commission"
        elif "zoning" in name_lower:
            return "zoning_board"
        elif "commission" in name_lower:
            return "commission"
        elif "committee" in name_lower:
            return "committee"
        elif "board" in name_lower:
            return "board"
        else:
            return "other"

    def get_boards(self) -> List[Dict[str, Any]]:
        """Get list of meeting boards."""
        try:
            response = self.session.get(
                f"{self.api_base}/Boards",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get('value', [])
        except Exception:
            return []

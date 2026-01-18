"""
Battle-tested Legistar API client for Civic Conversational OS
Based on production gotchas and per-client probe approach

Key capabilities:
- Per-client capability detection
- Robust error handling with exponential backoff
- Schema normalization for civic-app-schema.json compliance
- Null-tolerant ETL with encoding fixes
"""

import requests
import json
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import quote_plus

class LegistarClient:
    """Battle-tested Legistar API client with production guardrails"""

    def __init__(self, client_name: str):
        self.client_name = client_name
        self.base_url = f"https://webapi.legistar.com/v1/{client_name}"
        self.session = requests.Session()
        self.capabilities = {}
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Throttling protection (increased from 0.1s to avoid 500 errors)

    def _throttle_request(self):
        """Prevent burst requests that cause 5xx errors"""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict = None, retries: int = 3) -> Any:
        """Make API request with exponential backoff"""
        self._throttle_request()

        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    # Exponential backoff for server issues
                    wait_time = 2 ** attempt
                    print(f"⚠️ Status {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ API Error {response.status_code}: {response.text[:200]}")
                    return None

            except Exception as e:
                print(f"❌ Request failed: {str(e)[:100]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def probe_capabilities(self) -> Dict[str, Any]:
        """Per-client probe to detect capabilities and quirks"""
        print(f"🔍 Probing {self.client_name} capabilities...")

        capabilities = {
            "client_name": self.client_name,
            "api_accessible": False,
            "bodies_available": False,
            "events_available": False,
            "matters_available": False,
            "timezone_detected": "America/Los_Angeles",  # Default assumption
            "null_patterns": [],
            "encoding_issues": []
        }

        # Test Bodies endpoint
        bodies = self._make_request("bodies", {"$top": 1})
        if bodies and isinstance(bodies, list):
            capabilities["api_accessible"] = True
            capabilities["bodies_available"] = True
            print(f"✅ Bodies: {len(bodies)} found")

        # Test Events endpoint
        events = self._make_request("events", {"$top": 1})
        if events and isinstance(events, list):
            capabilities["events_available"] = True
            print(f"✅ Events: {len(events)} found")

            # Detect timezone and null patterns
            if events:
                event = events[0]
                if 'EventDate' in event and event['EventDate']:
                    # Basic timezone detection logic could go here
                    pass

                # Check for null patterns
                null_fields = [k for k, v in event.items() if v is None]
                capabilities["null_patterns"] = null_fields[:5]  # Sample

        # Test Matters endpoint
        matters = self._make_request("matters", {"$top": 1})
        if matters and isinstance(matters, list):
            capabilities["matters_available"] = True
            print(f"✅ Matters: {len(matters)} found")

        self.capabilities = capabilities
        return capabilities

    def get_recent_events(self, days_back: int = 30, days_forward: int = 14) -> List[Dict]:
        """Get events in recent window with future meetings prioritized"""
        # Try to fetch events even if probe failed (probe may hit transient errors)
        # The _make_request method has proper error handling with retries

        # Date range for civic relevance
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=days_forward)).strftime('%Y-%m-%d')

        # OData filter for date range
        filter_query = f"EventDate ge datetime'{start_date}' and EventDate le datetime'{end_date}'"
        params = {
            "$filter": filter_query,
            "$orderby": "EventDate desc",
            "$top": 50  # Reasonable limit
        }

        print(f"📅 Fetching events from {start_date} to {end_date}")
        events = self._make_request("events", params)

        if events and isinstance(events, list):
            print(f"✅ Found {len(events)} recent events")
            return self._normalize_events(events)

        return []

    def _normalize_events(self, events: List[Dict]) -> List[Dict]:
        """Normalize events for civic-app-schema.json compliance"""
        normalized = []

        for event in events:
            # Handle encoding and null issues
            # Combine EventDate and EventTime for accurate meeting_datetime
            event_date = event.get("EventDate", "")
            event_time = event.get("EventTime", "")

            # Create proper datetime by combining date and time
            if event_date and event_time:
                try:
                    # Parse EventDate (e.g., "2025-10-02T00:00:00") and EventTime (e.g., "10:30 AM")
                    date_part = event_date.split('T')[0]  # "2025-10-02"

                    # Convert time to 24-hour format
                    from datetime import datetime
                    time_obj = datetime.strptime(event_time, "%I:%M %p")
                    time_24hr = time_obj.strftime("%H:%M:%S")

                    # Combine date and time
                    meeting_datetime = f"{date_part}T{time_24hr}"
                except Exception as e:
                    print(f"⚠️ Time parsing failed for {event.get('EventId')}: {e}")
                    meeting_datetime = event_date  # Fallback to date only
            else:
                meeting_datetime = event_date

            normalized_event = {
                "event_id": event.get("EventId"),
                "event_guid": event.get("EventGuid"),
                "title": self._clean_text(event.get("EventBodyName", "Unknown Meeting")),
                "date": event.get("EventDate"),
                "meeting_datetime": meeting_datetime,  # New field with proper time
                "event_time": event_time,  # Keep original time field for reference
                "status": event.get("EventAgendaStatusName", "Unknown"),
                "body_name": self._clean_text(event.get("EventBodyName", "")),
                "meeting_type": event.get("EventTypeName", "Regular"),
                "location": self._clean_text(event.get("EventLocation", "")),
                "video_url": event.get("EventVideoUrl"),
                "agenda_url": event.get("EventAgendaFile"),
                "minutes_url": event.get("EventMinutesFile")
            }

            # Filter out irrelevant meetings
            if self._is_relevant_meeting(normalized_event):
                normalized.append(normalized_event)

        return normalized

    def _clean_text(self, text: str) -> str:
        """Clean text with encoding and HTML handling"""
        if not text:
            return ""

        # Handle common encoding issues
        text = str(text).replace('\u2013', '-').replace('\u2014', '--')

        # Strip basic HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        return text.strip()

    def _is_relevant_meeting(self, event: Dict) -> bool:
        """Filter for civic-relevant meetings"""
        title = event.get("title", "").lower()
        status = event.get("status", "").lower()

        # Skip cancelled or hidden meetings
        if "cancel" in status or "hidden" in status:
            return False

        # Focus on public meetings
        relevant_keywords = [
            "city council", "planning", "committee", "commission",
            "board", "public", "hearing"
        ]

        return any(keyword in title for keyword in relevant_keywords)

    def get_event_matters(self, event_id: int) -> List[Dict]:
        """Get agenda matters for a specific event"""
        if not self.capabilities.get("matters_available"):
            return []

        params = {"$filter": f"EventId eq {event_id}"}
        matters = self._make_request("matters", params)

        if matters and isinstance(matters, list):
            return self._normalize_matters(matters)

        return []

    def _normalize_matters(self, matters: List[Dict]) -> List[Dict]:
        """Normalize matters for civic events"""
        normalized = []

        for matter in matters:
            normalized_matter = {
                "matter_id": matter.get("MatterId"),
                "matter_guid": matter.get("MatterGuid"),
                "title": self._clean_text(matter.get("MatterTitle", "")),
                "summary": self._clean_text(matter.get("MatterSummary", "")),
                "type": matter.get("MatterTypeName", ""),
                "status": matter.get("MatterStatusName", ""),
                "file_number": matter.get("MatterFile", ""),
                "attachments": []  # Would need separate API call
            }

            if normalized_matter["title"] and len(normalized_matter["title"]) > 10:
                normalized.append(normalized_matter)

        return normalized

    def get_event_item_persons(self, event_item_id: int) -> List[Dict]:
        """
        Get testimony/speakers for a specific event item (agenda item)

        Args:
            event_item_id: The EventItemId from the Legistar API

        Returns:
            List of normalized testimony records with speaker names and order
        """
        endpoint = f"EventItems/{event_item_id}/EventItemPersons"
        persons = self._make_request(endpoint)

        if persons and isinstance(persons, list):
            return self._normalize_testimony(persons)

        return []

    def _normalize_testimony(self, persons: List[Dict]) -> List[Dict]:
        """
        Normalize testimony/speaker data from Legistar API

        Legistar limitations:
        - No position field (support/oppose) - must infer from minutes
        - No testimony text - just speaker names
        - Speaker order is preserved via EventItemPersonPosition
        """
        normalized = []

        for person in persons:
            speaker_name = self._clean_text(person.get("EventItemPersonName", ""))

            # Skip empty names
            if not speaker_name or len(speaker_name) < 2:
                continue

            normalized_person = {
                "event_item_person_id": person.get("EventItemPersonId"),
                "speaker_name": speaker_name,
                "speaking_order": person.get("EventItemPersonPosition", 0),
                "agenda_sequence": person.get("EventItemAgendaSequence", 0),
                # Fields not available from API (would need minutes parsing)
                "position": None,
                "organization": None,
                "testimony_text": None
            }

            normalized.append(normalized_person)

        # Sort by speaking order
        normalized.sort(key=lambda x: x["speaking_order"])

        return normalized

# Factory for known working clients
KNOWN_LEGISTAR_CLIENTS = {
    "oakland": {
        "client_name": "oakland",
        "status": "confirmed_working",
        "expected_bodies": ["Oakland City Council", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    },
    "santa-rosa": {
        "client_name": "santa-rosa",
        "status": "discovered_api",
        "expected_bodies": ["City Council", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    },
    "sonoma-county": {
        "client_name": "sonoma-county",
        "status": "discovered_api",
        "expected_bodies": ["Board of Supervisors", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    },
    "hayward": {
        "client_name": "hayward",
        "status": "discovered_api",
        "expected_bodies": ["City Council", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    },
    "napa": {
        "client_name": "napa",
        "status": "discovered_api",
        "expected_bodies": ["City Council", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    },
    "bart": {
        "client_name": "bart",
        "status": "discovered_api",
        "expected_bodies": ["BART Board of Directors"],
        "timezone": "America/Los_Angeles"
    },
    "san_francisco": {
        "client_name": "sanfrancisco",
        "status": "requires_insite_config",
        "expected_bodies": ["Board of Supervisors"],
        "timezone": "America/Los_Angeles"
    }
}

def create_client(city_name: str) -> Optional[LegistarClient]:
    """Factory method for creating clients"""
    client_config = KNOWN_LEGISTAR_CLIENTS.get(city_name.lower())
    if not client_config:
        print(f"❌ No Legistar client configuration for {city_name}")
        return None

    client = LegistarClient(client_config["client_name"])
    return client

if __name__ == "__main__":
    print("🏛️ LEGISTAR CLIENT TEST")

    # Test Oakland
    oakland_client = create_client("oakland")
    if oakland_client:
        capabilities = oakland_client.probe_capabilities()
        if capabilities["api_accessible"]:
            events = oakland_client.get_recent_events(days_back=15, days_forward=30)
            print(f"📋 Oakland: {len(events)} relevant civic events")

            for event in events[:3]:
                print(f"  - {event['date'][:10]} | {event['title']}")

    print(f"\n📊 Summary: Legistar API {'✅ WORKING' if oakland_client and oakland_client.capabilities['api_accessible'] else '❌ FAILED'} for Oakland")
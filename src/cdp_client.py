"""
Generic Council Data Project (CDP) Client for Civic Conversational OS
Resilience Strategy Implementation - Phase 2A Priority

⚠️ IMPORTANT: CDP ACCESS DISCOVERY (2025-09-26)
CDP uses anonymous public access - no special credentials required!

Access Pattern:
```python
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore import Client
import fireo

client = Client(project="cdp-oakland-ba81c097", credentials=AnonymousCredentials())
fireo.connection(client=client)
events = db_models.Event.collection.limit(5).fetch()
```

Oakland Reality Check:
✅ Anonymous access works perfectly
❌ Data is from 2023, not current (may be archival)
✅ Historical validation useful for Legistar API cross-referencing

Key capabilities:
- Jurisdiction-agnostic CDP integration (Seattle, Oakland, San Jose, etc.)
- Anonymous public access to CDP Firestore databases
- Data normalization to civic-app-schema.json format
- Dual-source validation with Legistar API (historical vs current)
- Automatic failover and error handling
- Foundation for vendor-independent civic infrastructure
"""

import requests
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging

# CDP Backend imports for data models
try:
    from cdp_backend.database import models as db_models
    import fireo
    from google.auth.credentials import AnonymousCredentials
    from google.cloud.firestore import Client
    CDP_AVAILABLE = True
except ImportError:
    CDP_AVAILABLE = False
    logging.warning("CDP backend not available - install with: pip install cdp-backend")


@dataclass
class CDPJurisdictionConfig:
    """Configuration for a specific CDP jurisdiction"""
    jurisdiction_id: str  # e.g., "city-oakland", "city-seattle"
    jurisdiction_name: str  # e.g., "Oakland", "Seattle"
    timezone: str  # e.g., "America/Los_Angeles"
    cdp_endpoint: Optional[str] = None  # Custom CDP API endpoint if available
    project_id: Optional[str] = None  # Google Cloud project ID (e.g., "cdp-oakland-ba81c097")
    firestore_collection: str = "events"  # Default Firestore collection


class CDPClient:
    """Generic CDP client that works with any CDP deployment"""

    def __init__(self, jurisdiction_config: CDPJurisdictionConfig):
        self.config = jurisdiction_config
        self.jurisdiction_id = jurisdiction_config.jurisdiction_id
        self.jurisdiction_name = jurisdiction_config.jurisdiction_name
        self.timezone = jurisdiction_config.timezone

        # Initialize CDP connection if available
        self.cdp_available = CDP_AVAILABLE
        self.connection = None

        if CDP_AVAILABLE:
            self._initialize_cdp_connection()

        # Request throttling for API protection
        self.last_request_time = 0
        self.min_request_interval = 0.2

    def _initialize_cdp_connection(self):
        """Initialize CDP database connection using anonymous credentials"""
        try:
            if self.config.project_id:
                # Connect using anonymous credentials (public access)
                client = Client(
                    project=self.config.project_id,
                    credentials=AnonymousCredentials()
                )
                fireo.connection(client=client)
                self.connection = client
                logging.info(f"CDP anonymous connection established for {self.jurisdiction_name}")
            else:
                logging.info(f"No project_id provided for {self.jurisdiction_name}")
        except Exception as e:
            logging.warning(f"CDP connection failed for {self.jurisdiction_name}: {e}")

    def _throttle_request(self):
        """Prevent burst requests to CDP endpoints"""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def get_civic_events(self, days_forward: int = 14, days_back: int = 7) -> List[Dict]:
        """
        Extract civic events from CDP deployment
        Returns normalized data compatible with civic-app-schema.json
        """
        try:
            if not self.cdp_available:
                return self._fallback_web_scraping(days_forward, days_back)

            return self._get_cdp_events(days_forward, days_back)

        except Exception as e:
            logging.error(f"CDP event extraction failed for {self.jurisdiction_name}: {e}")
            return []

    def _get_cdp_events(self, days_forward: int, days_back: int) -> List[Dict]:
        """Get events from CDP database using anonymous access"""
        if not self.connection:
            logging.warning(f"No CDP connection available for {self.jurisdiction_name}")
            return []

        try:
            # Calculate date range
            end_date = datetime.now(timezone.utc) + timedelta(days=days_forward)
            start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

            logging.info(f"CDP database query for {self.jurisdiction_name}: {start_date.date()} to {end_date.date()}")

            # Query CDP events using FireO
            events_query = db_models.Event.collection.limit(50).fetch()

            # Convert to list and filter by date
            raw_events = []
            for event in events_query:
                if hasattr(event, 'event_datetime') and event.event_datetime:
                    # Check if event is within our date range
                    event_dt = event.event_datetime
                    if isinstance(event_dt, str):
                        event_dt = datetime.fromisoformat(event_dt.replace('Z', '+00:00'))

                    if start_date <= event_dt <= end_date:
                        raw_events.append(event)

                # Limit results to prevent excessive processing
                if len(raw_events) >= 20:
                    break

            logging.info(f"Found {len(raw_events)} CDP events in date range")

            # Normalize to civic schema format
            normalized_events = self.normalize_to_civic_schema(raw_events)

            return normalized_events

        except Exception as e:
            logging.error(f"CDP event query failed for {self.jurisdiction_name}: {e}")
            return []

    def _fallback_web_scraping(self, days_forward: int, days_back: int) -> List[Dict]:
        """Fallback to web scraping if CDP API unavailable"""
        # This would integrate with civic-scraper for web-based extraction
        logging.info(f"Web scraping fallback for {self.jurisdiction_name}")
        return []

    def normalize_to_civic_schema(self, cdp_events: List) -> List[Dict]:
        """
        Convert CDP event objects to civic-app-schema.json format
        Works with actual CDP Event model instances
        """
        normalized_events = []

        for event in cdp_events:
            try:
                # Extract body name from body reference
                body_name = "Unknown Meeting"
                try:
                    if hasattr(event, 'body_ref') and event.body_ref:
                        body = event.body_ref.get()
                        if body and hasattr(body, 'name'):
                            body_name = body.name
                except Exception:
                    pass  # Keep default if body access fails

                normalized_event = {
                    "id": getattr(event, 'id', '') or getattr(event, 'external_source_id', ''),
                    "title": self._clean_text(body_name),
                    "meeting_datetime": self._normalize_datetime(getattr(event, 'event_datetime', None)),
                    "status": "scheduled",  # CDP events are typically scheduled
                    "meeting_type": "council_meeting",
                    "jurisdiction": self.jurisdiction_name,
                    "location": "",  # Not typically available in CDP
                    "agenda_uri": getattr(event, 'agenda_uri', '') or '',
                    "minutes_uri": getattr(event, 'minutes_uri', '') or '',
                    "video_uri": "",  # Often not available in CDP
                    "source_uri": getattr(event, 'agenda_uri', '') or '',

                    # CDP-specific fields for enhanced data
                    "cdp_event_id": getattr(event, 'id', ''),
                    "transcripts_available": False,  # Would need to check sessions
                    "voting_records": [],

                    # Civic engagement fields
                    "participation_methods": self._extract_participation_methods(event),
                    "comment_deadline": self._extract_comment_deadline(event),
                    "public_comment_allowed": True,  # CDP deployments typically allow public comment

                    # Metadata
                    "source_platform": "cdp",
                    "data_source": f"cdp_{self.jurisdiction_id}",
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }

                # Only include civic-relevant meetings
                if self._is_civic_relevant(normalized_event):
                    normalized_events.append(normalized_event)

            except Exception as e:
                logging.warning(f"Failed to normalize CDP event: {e}")
                continue

        return normalized_events

    def _extract_participation_methods(self, event) -> List[str]:
        """Extract ways citizens can participate from CDP event object"""
        methods = ["public_comment"]  # Default for most CDP events

        # Check for agenda URI (implies meeting can be followed)
        if getattr(event, 'agenda_uri', None):
            methods.append("agenda_review")

        # CDP events typically allow virtual attendance
        methods.append("virtual_attendance")

        return methods

    def _extract_comment_deadline(self, event) -> Optional[str]:
        """Extract public comment deadline if available"""
        event_datetime = getattr(event, 'event_datetime', None)
        if event_datetime:
            try:
                # Most jurisdictions require comments 24 hours before meeting
                if isinstance(event_datetime, str):
                    dt = datetime.fromisoformat(event_datetime.replace('Z', '+00:00'))
                else:
                    dt = event_datetime

                deadline = dt - timedelta(hours=24)
                return deadline.isoformat()
            except Exception:
                pass
        return None

    def _clean_text(self, text: str) -> str:
        """Clean text with encoding and HTML handling"""
        if not text:
            return ""

        # Handle common encoding issues
        text = str(text).replace('\u2013', '-').replace('\u2014', '--')

        # Basic HTML tag removal
        import re
        text = re.sub(r'<[^>]+>', '', text)

        return text.strip()

    def _normalize_datetime(self, dt_str: Optional[str]) -> str:
        """Normalize datetime to ISO format with timezone"""
        if not dt_str:
            return ""

        try:
            # Parse CDP datetime format
            if dt_str.endswith('Z'):
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(dt_str)

            # Apply jurisdiction timezone if needed
            if dt.tzinfo is None:
                # Assume jurisdiction timezone for naive datetimes
                import pytz
                tz = pytz.timezone(self.timezone)
                dt = tz.localize(dt)

            return dt.isoformat()

        except Exception as e:
            logging.warning(f"Failed to parse datetime {dt_str}: {e}")
            return ""

    def _is_civic_relevant(self, event: Dict) -> bool:
        """Filter for civic-relevant meetings"""
        title = event.get("title", "").lower()
        status = event.get("status", "").lower()

        # Skip cancelled meetings
        if status in ["cancelled", "canceled"]:
            return False

        # Focus on public meetings
        relevant_keywords = [
            "city council", "planning", "committee", "commission",
            "board", "public", "hearing", "budget", "zoning"
        ]

        return any(keyword in title for keyword in relevant_keywords)

    def validate_against_legistar(self, legistar_events: List[Dict]) -> Dict[str, Any]:
        """
        Compare CDP data with Legistar API for dual-source validation
        Returns comparison metrics and data quality assessment
        """
        cdp_events = self.get_civic_events(days_forward=14, days_back=7)

        validation_results = {
            "jurisdiction": self.jurisdiction_name,
            "cdp_events_count": len(cdp_events),
            "legistar_events_count": len(legistar_events),
            "data_sources": {
                "cdp_available": len(cdp_events) > 0,
                "legistar_available": len(legistar_events) > 0,
                "dual_source_capable": len(cdp_events) > 0 and len(legistar_events) > 0
            },
            "quality_metrics": {
                "cdp_completeness": self._assess_data_completeness(cdp_events),
                "legistar_completeness": self._assess_data_completeness(legistar_events),
                "cross_reference_matches": self._find_cross_references(cdp_events, legistar_events)
            },
            "failover_recommendation": self._recommend_failover_strategy(cdp_events, legistar_events),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        return validation_results

    def _assess_data_completeness(self, events: List[Dict]) -> Dict[str, Any]:
        """Assess completeness and quality of event data"""
        if not events:
            return {"score": 0.0, "issues": ["no_events_available"]}

        total_events = len(events)
        required_fields = ["title", "meeting_datetime", "status"]
        optional_fields = ["agenda_uri", "location", "video_uri"]

        completeness_scores = []
        common_issues = []

        for event in events:
            score = 0
            # Required fields (70% weight)
            for field in required_fields:
                if event.get(field):
                    score += 0.7 / len(required_fields)

            # Optional fields (30% weight)
            for field in optional_fields:
                if event.get(field):
                    score += 0.3 / len(optional_fields)

            completeness_scores.append(score)

        avg_completeness = sum(completeness_scores) / len(completeness_scores)

        return {
            "score": round(avg_completeness, 3),
            "total_events": total_events,
            "avg_field_completion": avg_completeness,
            "issues": common_issues
        }

    def _find_cross_references(self, cdp_events: List[Dict], legistar_events: List[Dict]) -> Dict[str, Any]:
        """Find matching events between CDP and Legistar data"""
        matches = []

        for cdp_event in cdp_events:
            cdp_title = cdp_event.get("title", "").lower()
            cdp_date = cdp_event.get("meeting_datetime", "")[:10]  # Date only

            for legistar_event in legistar_events:
                leg_title = legistar_event.get("title", "").lower()
                leg_date = legistar_event.get("date", "")[:10]  # Date only

                # Simple title similarity and date match
                title_similar = any(word in leg_title for word in cdp_title.split() if len(word) > 3)
                date_match = cdp_date == leg_date

                if title_similar and date_match:
                    matches.append({
                        "cdp_event": cdp_event.get("title"),
                        "legistar_event": legistar_event.get("title"),
                        "date": cdp_date,
                        "confidence": 0.8 if title_similar and date_match else 0.6
                    })

        return {
            "total_matches": len(matches),
            "match_rate": len(matches) / max(len(cdp_events), len(legistar_events), 1),
            "matches": matches[:5]  # Show first 5 matches
        }

    def _recommend_failover_strategy(self, cdp_events: List[Dict], legistar_events: List[Dict]) -> Dict[str, str]:
        """Recommend optimal failover strategy based on data quality"""
        cdp_quality = self._assess_data_completeness(cdp_events)
        leg_quality = self._assess_data_completeness(legistar_events)

        if cdp_quality["score"] > leg_quality["score"]:
            return {
                "primary": "cdp",
                "fallback": "legistar_api",
                "reason": f"CDP higher quality ({cdp_quality['score']:.2f} vs {leg_quality['score']:.2f})"
            }
        elif leg_quality["score"] > 0.5:  # Legistar has decent quality
            return {
                "primary": "legistar_api",
                "fallback": "cdp",
                "reason": f"Legistar API reliable ({leg_quality['score']:.2f}), CDP as backup"
            }
        else:
            return {
                "primary": "html_parsing",
                "fallback": "user_contributions",
                "reason": "Both APIs low quality - fallback to web scraping and community data"
            }


# Factory for known CDP jurisdictions
KNOWN_CDP_JURISDICTIONS = {
    "oakland": CDPJurisdictionConfig(
        jurisdiction_id="city-oakland",
        jurisdiction_name="Oakland",
        timezone="America/Los_Angeles",
        project_id="cdp-oakland-ba81c097"  # Based on research
    ),
    "seattle": CDPJurisdictionConfig(
        jurisdiction_id="city-seattle",
        jurisdiction_name="Seattle",
        timezone="America/Los_Angeles",
        project_id="cdp-seattle-21723dcf"  # Estimated
    ),
    "san-jose": CDPJurisdictionConfig(
        jurisdiction_id="city-san-jose",
        jurisdiction_name="San Jose",
        timezone="America/Los_Angeles",
        project_id="cdp-san-jose-unknown"  # Would need verification
    )
}


def create_cdp_client(jurisdiction: str) -> Optional[CDPClient]:
    """Factory function to create CDP client for known jurisdictions"""
    config = KNOWN_CDP_JURISDICTIONS.get(jurisdiction.lower())
    if config:
        return CDPClient(config)
    else:
        logging.warning(f"No CDP configuration found for jurisdiction: {jurisdiction}")
        return None


# Example usage and testing
if __name__ == "__main__":
    # Test CDP client creation
    oakland_cdp = create_cdp_client("oakland")
    if oakland_cdp:
        print(f"✅ Oakland CDP client created: {oakland_cdp.jurisdiction_name}")

        # Test event extraction
        events = oakland_cdp.get_civic_events()
        print(f"📅 CDP Events found: {len(events)}")

        # Test dual-source validation (would need actual Legistar data)
        validation = oakland_cdp.validate_against_legistar([])  # Empty for now
        print(f"🔍 Validation results: {validation['data_sources']}")

    else:
        print("❌ Failed to create Oakland CDP client")
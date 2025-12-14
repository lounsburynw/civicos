#!/usr/bin/env python3
"""
CivicClerk API Client - Structured data source for municipal meetings

Similar to Legistar client, provides reliable API-based access to:
- Meeting/event listings
- Agenda metadata and files
- Published documents

Reduces vendor dependency compared to HTML scraping.
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import quote


class CivicClerkClient:
    """Client for CivicClerk API (Granicus product)"""

    def __init__(self, jurisdiction_subdomain: str):
        """
        Initialize CivicClerk client

        Args:
            jurisdiction_subdomain: CivicClerk subdomain (e.g., "elcerritoca")
        """
        self.subdomain = jurisdiction_subdomain
        self.api_base = f"https://{jurisdiction_subdomain}.api.civicclerk.com/v1"
        self.portal_base = f"https://{jurisdiction_subdomain}.portal.civicclerk.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Civic-Engagement-Platform/1.0 (Foundation-funded civic transparency tool)'
        })

    def get_events(self,
                   start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None,
                   days_ahead: int = 90,
                   has_agenda: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        Get list of events from CivicClerk API

        Args:
            start_date: Filter events starting from this date (default: today)
            end_date: Filter events up to this date (default: start_date + days_ahead)
            days_ahead: Number of days to look ahead (default: 90)
            has_agenda: Filter to only events with agendas (default: None = all events)

        Returns:
            List of event dictionaries with full details including publishedFiles
        """
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = start_date + timedelta(days=days_ahead)

        # Build OData filter
        start_str = start_date.strftime('%Y-%m-%dT00:00:00.000Z')
        end_str = end_date.strftime('%Y-%m-%dT23:59:59.999Z')

        filter_parts = [f"startDateTime ge {start_str}", f"startDateTime le {end_str}"]
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

            # Fetch individual event details to get publishedFiles
            # (list endpoint doesn't include publishedFiles array)
            enriched_events = []
            for event in events:
                event_id = event.get('id')
                if event_id:
                    detailed_event = self.get_event_details(event_id)
                    if detailed_event:
                        enriched_events.append(detailed_event)
                    else:
                        # Fallback to list data if details fetch fails
                        enriched_events.append(event)

            return enriched_events

        except Exception as e:
            print(f"⚠️ CivicClerk API error: {type(e).__name__}: {e}")
            return []

    def get_event_details(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed event information including publishedFiles

        Args:
            event_id: CivicClerk event ID

        Returns:
            Event dictionary with full details or None on error
        """
        try:
            api_url = f"{self.api_base}/Events/{event_id}"
            response = self.session.get(api_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Failed to fetch event {event_id}: {type(e).__name__}")
            return None

    def get_agenda_url(self, event: Dict[str, Any]) -> Optional[str]:
        """
        Get agenda PDF URL from event (legacy - use get_agenda_info for metadata)

        Args:
            event: Event dictionary from get_events() or get_event_details()

        Returns:
            API URL that returns blob URL to actual PDF, or None if no agenda
        """
        info = self.get_agenda_info(event)
        return info.get('url') if info else None

    def get_agenda_info(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get agenda file info with quality metadata

        Returns:
            {
                'url': str,
                'file_type': str,  # 'Agenda', 'Notice', 'Packet', etc.
                'file_id': int,
                'confidence': str,  # 'high', 'medium', 'low'
                'all_files': List[str]  # All available file types for debugging
            }
        """
        published_files = event.get('publishedFiles', [])
        all_file_types = [f.get('type') for f in published_files if f.get('type')]

        # Try 1: Find agenda/notice/packet file in publishedFiles
        # Prefer Agenda (highest confidence), then Notice, then Packet
        file_type_priority = [
            ('Agenda', 'high'),
            ('Notice', 'medium'),  # Often used for public hearings
            ('Packet', 'medium'),
            ('Agenda Packet', 'high'),
            ('Special Notice', 'medium')
        ]

        for file_type, confidence in file_type_priority:
            agenda_file = next((f for f in published_files if f.get('type') == file_type), None)
            if agenda_file:
                return {
                    'url': agenda_file.get('url'),
                    'file_type': file_type,
                    'file_id': agenda_file.get('fileId'),
                    'confidence': confidence,
                    'all_files': all_file_types
                }

        # Try 2: Check for any PDF-like files with unknown types
        # Fallback for municipalities that use custom file type names
        if published_files and not agenda_file:
            # Take first file with reasonable name, but mark low confidence
            first_file = published_files[0]
            return {
                'url': first_file.get('url'),
                'file_type': first_file.get('type', 'Unknown'),
                'file_id': first_file.get('fileId'),
                'confidence': 'low',
                'all_files': all_file_types,
                '_warning': f"Unknown file type '{first_file.get('type')}' - may not contain agenda"
            }

        # Try 3: Use agendaId if available (lowest confidence - often stale)
        agenda_id = event.get('agendaId')
        event_id = event.get('id')

        if agenda_id and event_id:
            return {
                'url': f"{self.api_base}/Meetings/GetMeetingFile(fileId={agenda_id},plainText=false)",
                'file_type': 'agendaId',
                'file_id': agenda_id,
                'confidence': 'low',
                'all_files': all_file_types,
                '_warning': 'Using agendaId field - may be stale/placeholder'
            }

        return None

    def get_portal_url(self, event_id: int, file_id: Optional[int] = None) -> str:
        """
        Get human-readable portal URL for event/agenda

        Args:
            event_id: CivicClerk event ID
            file_id: Optional file ID for specific document

        Returns:
            Portal URL for viewing in browser
        """
        if file_id:
            return f"{self.portal_base}/event/{event_id}/files/agenda/{file_id}"
        else:
            return f"{self.portal_base}/event/{event_id}"

    def convert_to_civic_schema(self, event: Dict[str, Any], jurisdiction: Dict[str, Any], contact_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Convert CivicClerk event to civic-app-schema.json format

        Args:
            event: CivicClerk event dictionary
            jurisdiction: Jurisdiction metadata
            contact_email: Optional contact email for the jurisdiction

        Returns:
            Event in civic schema format
        """
        import uuid

        event_id = event.get('id')
        event_name = event.get('eventName', 'Untitled Event')
        start_datetime = event.get('startDateTime')
        category = event.get('categoryName', 'Meeting')
        description = event.get('eventDescription', '')
        location = event.get('eventLocation', {})

        # Build location string
        location_str = None
        if location:
            parts = [
                location.get('address1'),
                location.get('city'),
                location.get('state'),
                location.get('zipCode')
            ]
            location_str = ', '.join([p for p in parts if p])

        # Parse datetime
        when_dt = None
        if start_datetime:
            try:
                when_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
            except:
                pass

        # Get agenda URL if available
        agenda_url = self.get_agenda_url(event)
        portal_url = self.get_portal_url(event_id)

        # Map to project types
        category_lower = category.lower()
        if 'council' in category_lower:
            project_type = 'governance'
            meeting_type = 'city_council'
        elif 'planning' in category_lower:
            project_type = 'building/development'
            meeting_type = 'planning_commission'
        elif 'commission' in category_lower:
            project_type = 'governance'
            meeting_type = 'commission'
        else:
            project_type = 'governance'
            meeting_type = 'public_meeting'

        return {
            'id': str(uuid.uuid4()),
            'title': event_name,
            'original_title': event_name,
            'description': description or None,
            'when': when_dt.isoformat() if when_dt else start_datetime,
            'when_human': when_dt.strftime('%a %b %d, %Y • %I:%M %p') if when_dt else start_datetime,
            'deadline': None,
            'engagement_info': 'Attend meeting or submit public comment',
            'impact_summary': description or None,
            'source_url': portal_url,
            'location': location_str,
            'meeting_type': meeting_type,
            'project_type': project_type,
            'engagement_tier': 'meeting',
            'jurisdiction': jurisdiction,
            'contact_info': {
                'email': contact_email,
                'name': None,
                'title': None,
                'phone': None,
                'office': None
            },
            'wiki_enhancement': {
                'success_strategy': 'Standard public comment procedures apply',
                'precedent_examples': [],
                'recommended_approach': None,
                'related_opportunities': []
            },
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'scraped_from': portal_url,
            'action_type': 'meeting',
            'deadline_reason': None,
            'agenda_item_number': None,
            'engagement': None,
            'agenda_page': portal_url,
            'timezone': 'America/Los_Angeles',  # TODO: Make configurable
            'participation_mechanisms': [
                {
                    'type': 'attend',
                    'location': location_str,
                    'when': when_dt.isoformat() if when_dt else start_datetime,
                    'description': 'Attend meeting for public comment',
                    'duration_minutes': None
                }
            ],
            'agenda_url': agenda_url,
            'agenda_available': bool(agenda_url),
            'agenda_expansion': {
                'available': bool(agenda_url),
                'source_url': agenda_url,
                'parsed': False,  # Will be populated by agenda integration
                'actionable_items': []
            },
            # Store CivicClerk metadata for future reference
            '_civicclerk_metadata': {
                'event_id': event_id,
                'category_id': event.get('categoryId'),
                'category_name': category,
                'has_agenda': event.get('hasAgenda', False),
                'has_media': event.get('hasMedia', False)
            }
        }


def create_client(jurisdiction_key: str) -> Optional[CivicClerkClient]:
    """
    Factory function to create CivicClerk client for known jurisdictions

    Args:
        jurisdiction_key: City identifier (e.g., 'el-cerrito')

    Returns:
        CivicClerkClient instance or None if jurisdiction not configured
    """
    # Map jurisdiction keys to CivicClerk subdomains
    jurisdiction_map = {
        'el-cerrito': 'elcerritoca',
        'los-altos': 'losaltosca',  # NEW: Top deployment candidate (86% agenda availability)
        # Add more CivicClerk jurisdictions as discovered
    }

    subdomain = jurisdiction_map.get(jurisdiction_key)
    if subdomain:
        return CivicClerkClient(subdomain)

    return None


if __name__ == '__main__':
    # Test the client
    print("🧪 Testing CivicClerk client for El Cerrito\n")

    client = create_client('el-cerrito')
    if not client:
        print("❌ Failed to create client")
        exit(1)

    print(f"📡 API Base: {client.api_base}")
    print(f"🌐 Portal Base: {client.portal_base}\n")

    # Get upcoming events
    print("📅 Fetching upcoming events (next 90 days)...\n")
    events = client.get_events(days_ahead=90)

    print(f"📋 Found {len(events)} total events")

    # Show events with agendas
    events_with_agendas = [e for e in events if e.get('hasAgenda')]
    print(f"📋 {len(events_with_agendas)} events have agendas\n")

    for i, event in enumerate(events_with_agendas[:5], 1):
        print(f"{i}. {event.get('eventName')}")
        print(f"   Date: {event.get('startDateTime')}")
        print(f"   Category: {event.get('categoryName')}")

        agenda_url = client.get_agenda_url(event)
        if agenda_url:
            print(f"   Agenda API: {agenda_url[:80]}...")

        portal_url = client.get_portal_url(event.get('id'))
        print(f"   Portal: {portal_url}")
        print()

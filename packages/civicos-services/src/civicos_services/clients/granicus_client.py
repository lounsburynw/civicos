#!/usr/bin/env python3
"""
Granicus ViewPublisher API Client

Extracts meeting data from Granicus ViewPublisher platform used by Dublin, Campbell,
and other California municipalities.

URL Pattern: https://[city].granicus.com/ViewPublisher.php?view_id=X

Data Structure: HTML tables with columns:
- Name (meeting title)
- Date (meeting date)
- Agenda Link (AgendaViewer.php URLs)
- Agenda Packet (direct PDF URLs)
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re


class GranicusClient:
    """Client for extracting meeting data from Granicus ViewPublisher"""

    def __init__(self, city_name: str, view_id: int = 1):
        """
        Initialize Granicus client

        Args:
            city_name: Subdomain name (e.g., 'dublin' for dublin.granicus.com)
            view_id: ViewPublisher view ID (default: 1)
        """
        self.city_name = city_name
        self.view_id = view_id
        self.base_url = f"https://{city_name}.granicus.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (CivicEngagement/1.0)'
        })

    def get_meetings(self, days_future: int = 90, days_past: int = 30) -> List[Dict]:
        """
        Extract meetings from ViewPublisher page

        Args:
            days_future: Number of days in future to include (default: 90)
            days_past: Number of days in past to include (default: 30)

        Returns:
            List of meeting dictionaries with schema-compatible structure
        """
        url = f"{self.base_url}/ViewPublisher.php?view_id={self.view_id}"

        try:
            print(f"🔍 Fetching Granicus meetings from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            meetings = []

            # Find all tables (ViewPublisher uses tables for meeting lists)
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                # Skip if no rows or only header row
                if len(rows) <= 1:
                    continue

                # Parse header to identify columns
                header_row = rows[0]
                headers = [th.get_text(strip=True).lower() for th in header_row.find_all(['th', 'td'])]

                # Identify column indices
                name_idx = self._find_column_index(headers, ['name', 'meeting'])
                date_idx = self._find_column_index(headers, ['date', 'when'])
                agenda_idx = self._find_column_index(headers, ['agenda', 'agenda link'])
                packet_idx = self._find_column_index(headers, ['packet', 'agenda packet', 'documents'])

                # Process data rows
                for row in rows[1:]:
                    cells = row.find_all('td')

                    # Skip rows that don't have enough cells for name and date
                    min_required = 2  # At minimum need name and date
                    if name_idx is not None:
                        min_required = max(min_required, name_idx + 1)
                    if date_idx is not None:
                        min_required = max(min_required, date_idx + 1)

                    if len(cells) < min_required:
                        continue

                    try:
                        # Extract meeting data
                        meeting_name = cells[name_idx].get_text(strip=True) if name_idx is not None else "Unknown Meeting"
                        date_text = cells[date_idx].get_text(strip=True) if date_idx is not None else ""

                        # Parse date
                        meeting_date = self._parse_date(date_text)

                        if not meeting_date:
                            print(f"⚠️ Could not parse date: {date_text}")
                            continue

                        # Apply temporal filter
                        now = datetime.now()
                        if meeting_date < now - timedelta(days=days_past):
                            continue
                        if meeting_date > now + timedelta(days=days_future):
                            continue

                        # Extract agenda link
                        agenda_url = None
                        if agenda_idx is not None and agenda_idx < len(cells):
                            agenda_link = cells[agenda_idx].find('a')
                            if agenda_link and 'href' in agenda_link.attrs:
                                agenda_url = self._make_absolute_url(agenda_link['href'])

                        # Extract packet link
                        packet_url = None
                        if packet_idx is not None and packet_idx < len(cells):
                            packet_link = cells[packet_idx].find('a')
                            if packet_link and 'href' in packet_link.attrs:
                                packet_url = self._make_absolute_url(packet_link['href'])

                        # Create meeting dict
                        meeting = {
                            'title': meeting_name,
                            'datetime': meeting_date.isoformat(),
                            'date_text': date_text,
                            'agenda_url': agenda_url,
                            'packet_url': packet_url,
                            'source_url': url,
                            'platform': 'granicus'
                        }

                        meetings.append(meeting)

                    except Exception as e:
                        print(f"⚠️ Error parsing row: {e}")
                        continue

            print(f"✅ Extracted {len(meetings)} meetings from Granicus ViewPublisher")
            return meetings

        except Exception as e:
            print(f"❌ Error fetching Granicus meetings: {e}")
            return []

    def _find_column_index(self, headers: List[str], possible_names: List[str]) -> Optional[int]:
        """Find column index by matching possible header names"""
        for name in possible_names:
            for i, header in enumerate(headers):
                if name in header:
                    return i
        return None

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from various Granicus date formats"""
        date_text = date_text.strip()

        if not date_text:
            return None

        # Campbell format: Unix timestamp + date (e.g., "1758006000Sep 16, 2025")
        # Remove Unix timestamp if present
        unix_timestamp_match = re.match(r'^\d{10,}(.+)$', date_text)
        if unix_timestamp_match:
            date_text = unix_timestamp_match.group(1)

        # Common formats:
        # "October 7, 2025"
        # "Oct 7, 2025"
        # "10/7/2025"
        # "2025-10-07"
        # "Sep 16, 2025" (from Campbell)

        date_formats = [
            "%B %d, %Y",      # October 7, 2025
            "%b %d, %Y",      # Oct 7, 2025 (also Sep 16, 2025)
            "%m/%d/%Y",       # 10/7/2025
            "%Y-%m-%d",       # 2025-10-07
            "%B %d, %Y %I:%M %p",  # October 7, 2025 6:00 PM
            "%b %d, %Y %I:%M %p",  # Oct 7, 2025 6:00 PM
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_text.strip(), fmt)
            except ValueError:
                continue

        # Try extracting just the date part if time is included
        date_match = re.search(r'(\w+ \d+, \d{4})', date_text)
        if date_match:
            try:
                return datetime.strptime(date_match.group(1), "%B %d, %Y")
            except ValueError:
                try:
                    return datetime.strptime(date_match.group(1), "%b %d, %Y")
                except ValueError:
                    pass

        return None

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if url.startswith('http'):
            return url
        elif url.startswith('//'):
            # Protocol-relative URL
            return f"https:{url}"
        elif url.startswith('/'):
            return f"{self.base_url}{url}"
        else:
            return f"{self.base_url}/{url}"


def create_client(city_name: str, view_id: int = 1) -> GranicusClient:
    """
    Factory function to create Granicus client

    Args:
        city_name: City subdomain (e.g., 'dublin', 'campbell')
        view_id: ViewPublisher view ID (default: 1)

    Returns:
        Configured GranicusClient instance
    """
    return GranicusClient(city_name, view_id)


def discover_granicus_cities() -> Dict[str, Dict]:
    """
    Discovery tool for finding Granicus cities

    Returns:
        Dict mapping city names to their Granicus configurations
    """
    # Known Granicus cities in the Bay Area
    known_cities = {
        'dublin': {
            'name': 'City of Dublin',
            'jurisdiction_id': 'city-dublin',
            'view_id': 1,
            'url': 'https://dublin.granicus.com/ViewPublisher.php?view_id=1'
        },
        'campbell': {
            'name': 'City of Campbell',
            'jurisdiction_id': 'city-campbell',
            'view_id': 1,  # Need to verify this
            'url': 'https://cityofcampbell.granicus.com/ViewPublisher.php?view_id=1'
        }
    }

    return known_cities


if __name__ == "__main__":
    """Test Granicus client with Dublin and Campbell"""
    import sys

    # Test Dublin
    print("🧪 Testing Dublin Granicus client...")
    dublin_client = create_client('dublin', view_id=1)
    dublin_meetings = dublin_client.get_meetings(days_future=90, days_past=7)

    print(f"\n📊 Dublin Results:")
    print(f"   Total meetings: {len(dublin_meetings)}")

    if dublin_meetings:
        print(f"\n   Sample meetings:")
        for i, meeting in enumerate(dublin_meetings[:5], 1):
            print(f"   {i}. {meeting['title']}")
            print(f"      Date: {meeting['date_text']}")
            print(f"      Agenda: {meeting['agenda_url']}")
            print(f"      Packet: {meeting['packet_url']}")
            print()

    # Test Campbell (need to find correct subdomain)
    print("\n🧪 Testing Campbell Granicus client...")
    print("   Trying 'cityofcampbell' subdomain...")

    campbell_client = create_client('cityofcampbell', view_id=1)
    campbell_meetings = campbell_client.get_meetings(days_future=90, days_past=7)

    print(f"\n📊 Campbell Results:")
    print(f"   Total meetings: {len(campbell_meetings)}")

    if campbell_meetings:
        print(f"\n   Sample meetings:")
        for i, meeting in enumerate(campbell_meetings[:5], 1):
            print(f"   {i}. {meeting['title']}")
            print(f"      Date: {meeting['date_text']}")
            print(f"      Agenda: {meeting['agenda_url']}")
            print(f"      Packet: {meeting['packet_url']}")
            print()

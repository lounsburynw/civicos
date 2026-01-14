"""
Integration tests for real data extraction from San Rafael.

These tests verify the san_rafael_extraction item from integration.json:
- Extract real meetings from San Rafael (ProudCity web scraper)
- Validate meeting data quality
- Verify PDF extraction works

These tests make real HTTP requests to cityofsanrafael.org.

Run: python -m pytest packages/civic/tests/test_integration_extraction.py -v
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Mark all tests in this module as integration (real HTTP requests)
pytestmark = pytest.mark.integration

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add packages to path
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic-extraction/src"))

# Set working directory for data file access
os.chdir(str(PROJECT_ROOT))

from civic_extraction import ProudCityClient, create_san_rafael_client


class TestSanRafaelExtraction:
    """
    Integration tests for San Rafael data extraction.

    Maps to integration.json > real_data_validation > data_extraction > san_rafael_extraction
    """

    @pytest.fixture
    def client(self):
        """Create ProudCityClient instance for San Rafael."""
        return create_san_rafael_client()

    # -------------------------------------------------------------------------
    # san_rafael_extraction: "Extract real meetings from San Rafael (ProudCity)"
    # -------------------------------------------------------------------------

    def test_san_rafael_extraction_city_council(self, client):
        """
        integration.json: real_data_validation > data_extraction > san_rafael_extraction
        test: "Extract real meetings from San Rafael (ProudCity web scraper)"

        Verifies:
        - City Council archive page can be scraped
        - Returns non-empty list of meetings
        - Meetings have required structure
        """
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        # Should find meetings (San Rafael has years of archives)
        assert len(meetings) > 0, "Should extract at least some meetings"
        assert len(meetings) >= 100, "Should have substantial archive (100+ meetings)"

        # First meeting should have required fields
        meeting = meetings[0]
        assert meeting.get('title'), "Meeting should have title"
        assert meeting.get('date_parsed'), "Meeting should have parsed date"
        assert meeting.get('meeting_url'), "Meeting should have URL"
        assert meeting.get('meeting_type') == 'city_council', "Should have correct meeting type"

    def test_san_rafael_extraction_all_types(self, client):
        """
        Verify extraction works across all San Rafael meeting types.

        Verifies:
        - All archive URLs are accessible
        - Multiple meeting types can be extracted
        """
        # Test a representative subset of archive types
        archive_types = {
            'city_council': 'https://www.cityofsanrafael.org/city-council-meetings/',
            'planning_commission': 'https://www.cityofsanrafael.org/planning-commission-meetings/',
            'fire_commission': 'https://www.cityofsanrafael.org/fire-commission-meetings/',
        }

        results = {}
        for meeting_type, url in archive_types.items():
            meetings = client._scrape_archive_page(url, meeting_type)
            results[meeting_type] = len(meetings)

        # Each type should have some meetings
        for meeting_type, count in results.items():
            assert count > 0, f"{meeting_type} should have meetings"

        # City council should have the most (most frequent)
        assert results['city_council'] >= results['fire_commission']

    def test_san_rafael_extraction_date_filtering(self, client):
        """
        Verify date range filtering works correctly.

        Verifies:
        - Can filter meetings by date range
        - Filtered results are within specified range
        """
        # Get all city council meetings
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        # Filter to last 90 days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

        filtered = client._filter_by_date_range(meetings, start_date, end_date)

        # Should have fewer meetings than total
        assert len(filtered) < len(meetings), "Filtering should reduce meeting count"

        # All filtered meetings should be within range
        for meeting in filtered:
            meeting_date = meeting.get('date_parsed')
            assert meeting_date is not None
            assert start_date <= meeting_date <= end_date, (
                f"Meeting date {meeting_date} should be in range [{start_date}, {end_date}]"
            )


class TestMeetingDataQuality:
    """
    Integration tests for meeting data quality.

    Maps to integration.json > real_data_validation > data_extraction > meeting_data_quality
    """

    @pytest.fixture
    def client(self):
        return create_san_rafael_client()

    def test_meeting_data_quality_required_fields(self, client):
        """
        integration.json: real_data_validation > data_extraction > meeting_data_quality
        test: "Extracted meetings have required fields (title, date, location)"

        Verifies:
        - All meetings have title
        - All meetings have date in valid format
        - All meetings have URL (serves as location reference)
        """
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        # Check first 20 meetings for quality
        sample = meetings[:20]

        for meeting in sample:
            # Title required
            assert meeting.get('title'), "Meeting must have title"
            assert len(meeting['title']) > 3, "Title should be meaningful"

            # Date required and valid format
            date_str = meeting.get('date_parsed')
            assert date_str, "Meeting must have date"
            # Validate ISO format
            try:
                datetime.fromisoformat(date_str)
            except ValueError:
                pytest.fail(f"Invalid date format: {date_str}")

            # URL required (serves as location reference)
            url = meeting.get('meeting_url')
            assert url, "Meeting must have URL"
            assert url.startswith('https://www.cityofsanrafael.org/meetings/')

    def test_meeting_data_quality_no_duplicates(self, client):
        """
        Verify no duplicate meetings in extracted data.

        Verifies:
        - Meeting slugs are unique within extraction
        """
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        slugs = [m.get('meeting_slug') for m in meetings]
        unique_slugs = set(slugs)

        assert len(slugs) == len(unique_slugs), "Should have no duplicate meetings"


class TestAgendaItemsPresent:
    """
    Integration tests for agenda/PDF extraction.

    Maps to integration.json > real_data_validation > data_extraction > agenda_items_present
    """

    @pytest.fixture
    def client(self):
        return create_san_rafael_client()

    def test_agenda_items_present_pdf_extraction(self, client):
        """
        integration.json: real_data_validation > data_extraction > agenda_items_present
        test: "Meetings include agenda items with descriptions"

        For San Rafael ProudCity, agenda items are in PDFs.
        This test verifies PDF URLs can be extracted.
        """
        # Get a recent but past meeting (more likely to have complete docs)
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        # Find a meeting from the past 60 days
        today = datetime.now().strftime('%Y-%m-%d')
        past_30_days = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        recent_past = client._filter_by_date_range(meetings, past_30_days, today)

        # Get the most recent past meeting (skip future/cancelled/closed sessions)
        test_meeting = None
        for m in recent_past:
            if m.get('date_parsed', '9999') < today:
                # Skip closed session and cancelled meetings - they often don't have public agendas
                title = m.get('title', '').lower()
                if 'closed session' in title or 'cancelled' in title or 'canceled' in title:
                    continue
                test_meeting = m
                break

        assert test_meeting, "Should find at least one recent past meeting (excluding closed sessions)"

        # Extract PDFs
        pdf_urls = client.get_meeting_pdfs(test_meeting['meeting_url'])

        # Should have agenda packet (contains agenda items)
        assert pdf_urls.get('agenda_packet_url'), (
            f"Meeting {test_meeting['title']} should have agenda packet PDF"
        )
        assert pdf_urls['agenda_packet_url'].endswith('.pdf')

    def test_minutes_extraction(self, client):
        """
        Verify minutes PDFs can be extracted for past meetings.
        """
        # Get meetings from 2-4 months ago (definitely should have minutes)
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        start = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
        end = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
        older_meetings = client._filter_by_date_range(meetings, start, end)

        if not older_meetings:
            pytest.skip("No meetings in test range")

        # Test first meeting in range
        test_meeting = older_meetings[0]
        pdf_urls = client.get_meeting_pdfs(test_meeting['meeting_url'])

        # Minutes should be available for older meetings
        assert pdf_urls.get('minutes_url'), (
            f"Past meeting {test_meeting['title']} should have minutes PDF"
        )


class TestHistoricalDataDepth:
    """
    Integration tests for historical data availability.

    Maps to integration.json > real_data_validation > data_extraction > historical_data_depth
    """

    @pytest.fixture
    def client(self):
        return create_san_rafael_client()

    def test_historical_data_depth(self, client):
        """
        integration.json: real_data_validation > data_extraction > historical_data_depth
        test: "At least 6 months of historical data available"

        Verifies:
        - Can extract meetings from 6 months ago
        - Archive goes back at least 6 months
        """
        # Get all city council meetings
        meetings = client._scrape_archive_page(
            'https://www.cityofsanrafael.org/city-council-meetings/',
            'city_council'
        )

        # Filter to meetings at least 6 months old
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        older_meetings = [
            m for m in meetings
            if m.get('date_parsed') and m['date_parsed'] < six_months_ago
        ]

        assert len(older_meetings) > 0, "Should have meetings from 6+ months ago"
        assert len(older_meetings) >= 10, "Should have substantial historical data (10+ meetings)"

    def test_historical_data_12_months(self, client):
        """
        Verify at least 12 months of data available for comprehensive analysis.
        """
        # Use the get_events method with date range
        events = client.get_events(days_ahead=0, days_past=365)

        assert len(events) >= 50, f"Should have 50+ meetings in 12 months, got {len(events)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

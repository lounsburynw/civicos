"""
Tests for civic-extraction clients.
"""

import pytest
from datetime import datetime

from civic_extraction import LegistarClient, CivicClerkClient, ProudCityClient, Meeting
from civic_extraction import create_san_rafael_client
from civic_extraction.clients.base import BaseExtractor, Extractor


class TestMeetingDataclass:
    """Test the Meeting dataclass."""

    def test_meeting_creation(self):
        """Test basic Meeting creation."""
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test"
        )
        assert meeting.id == "test-001"
        assert meeting.title == "City Council Meeting"
        assert meeting.source_platform == "unknown"

    def test_meeting_to_dict(self):
        """Test Meeting serialization."""
        meeting = Meeting(
            id="test-001",
            title="City Council Meeting",
            meeting_datetime=datetime(2025, 12, 1, 18, 0),
            jurisdiction_id="city-test",
            meeting_type="city_council"
        )
        d = meeting.to_dict()
        assert d["id"] == "test-001"
        assert d["meeting_type"] == "city_council"
        assert "2025-12-01" in d["meeting_datetime"]


class TestLegistarClient:
    """Test LegistarClient."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = LegistarClient("berkeley")
        assert client.client_name == "berkeley"
        assert client.jurisdiction_id == "city-berkeley"
        assert client.platform_name == "legistar"

    def test_custom_jurisdiction_id(self):
        """Test custom jurisdiction ID override."""
        client = LegistarClient("berkeley", jurisdiction_id="custom-id")
        assert client.jurisdiction_id == "custom-id"

    def test_infer_meeting_type_council(self):
        """Test meeting type inference for council."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("City Council") == "city_council"
        assert client._infer_meeting_type("CITY COUNCIL Regular Meeting") == "city_council"

    def test_infer_meeting_type_planning(self):
        """Test meeting type inference for planning."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("Planning Commission") == "planning_commission"

    def test_infer_meeting_type_other(self):
        """Test meeting type inference for unknown."""
        client = LegistarClient("berkeley")
        assert client._infer_meeting_type("Special Session") == "other"

    def test_normalize_event(self):
        """Test event normalization."""
        client = LegistarClient("berkeley")
        event = {
            "EventId": 12345,
            "EventBodyName": "City Council",
            "EventDate": "2025-12-01T00:00:00",
            "EventTime": "18:00:00",
            "EventLocation": "City Hall"
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "legistar-berkeley-12345"
        assert meeting.meeting_type == "city_council"
        assert meeting.source_platform == "legistar"


class TestCivicClerkClient:
    """Test CivicClerkClient."""

    def test_client_initialization(self):
        """Test client creates with correct defaults."""
        client = CivicClerkClient("elcerritoca")
        assert client.subdomain == "elcerritoca"
        assert client.jurisdiction_id == "elcerritoca"
        assert client.platform_name == "civicclerk"

    def test_custom_jurisdiction_id(self):
        """Test custom jurisdiction ID override."""
        client = CivicClerkClient("elcerritoca", jurisdiction_id="city-el-cerrito")
        assert client.jurisdiction_id == "city-el-cerrito"

    def test_infer_meeting_type(self):
        """Test meeting type inference."""
        client = CivicClerkClient("elcerritoca")
        assert client._infer_meeting_type("City Council Meeting") == "city_council"
        assert client._infer_meeting_type("Planning Commission") == "planning_commission"
        assert client._infer_meeting_type("Parks Board") == "board"

    def test_normalize_event(self):
        """Test event normalization."""
        client = CivicClerkClient("elcerritoca", jurisdiction_id="city-el-cerrito")
        event = {
            "id": 789,
            "name": "City Council Regular Meeting",
            "startDateTime": "2025-12-01T18:00:00Z",
            "location": "Council Chambers",
            "publishedFiles": [
                {"name": "Agenda", "url": "https://example.com/agenda.pdf"}
            ]
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "civicclerk-elcerritoca-789"
        assert meeting.meeting_type == "city_council"
        assert meeting.agenda_url == "https://example.com/agenda.pdf"
        assert meeting.jurisdiction_id == "city-el-cerrito"


class TestProudCityClient:
    """Test ProudCityClient."""

    def test_client_initialization(self):
        """Test client creates with correct configuration."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.base_url == "https://www.cityofsanrafael.org"
        assert client.platform_name == "proudcity"

    def test_default_archives(self):
        """Test default archive paths are set."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        assert 'city_council' in client.archives
        assert 'planning_commission' in client.archives
        assert client.archives['city_council'] == '/city-council-meetings/'

    def test_custom_archives(self):
        """Test custom archive paths override defaults."""
        custom_archives = {'special_meetings': '/special/'}
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example",
            archives=custom_archives
        )
        assert client.archives == custom_archives
        assert 'city_council' not in client.archives

    def test_extract_date_from_slug(self):
        """Test date extraction from meeting slugs."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        # Standard format
        assert client._extract_date_from_slug("city-council-october-6-2025") == "2025-10-06"
        # With suffix
        assert client._extract_date_from_slug("planning-commission-november-4-2025-special-meeting") == "2025-11-04"
        # Invalid
        assert client._extract_date_from_slug("no-date-here") is None

    def test_normalize_event(self):
        """Test event normalization."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        event = {
            'title': 'City Council Meeting October 6, 2025',
            'meeting_slug': 'city-council-october-6-2025',
            'meeting_url': 'https://www.cityofsanrafael.org/meetings/city-council-october-6-2025/',
            'date_parsed': '2025-10-06',
            'meeting_type': 'city_council'
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "proudcity-city-san-rafael-city-council-october-6-2025"
        assert meeting.meeting_type == "city_council"
        assert meeting.source_platform == "proudcity"
        assert meeting.jurisdiction_id == "city-san-rafael"

    def test_filter_by_date_range(self):
        """Test date filtering."""
        client = ProudCityClient(
            base_url="https://www.example.org",
            jurisdiction_id="city-example"
        )
        meetings = [
            {'date_parsed': '2025-10-01'},
            {'date_parsed': '2025-10-15'},
            {'date_parsed': '2025-11-01'},
        ]
        filtered = client._filter_by_date_range(meetings, '2025-10-01', '2025-10-31')
        assert len(filtered) == 2
        assert filtered[0]['date_parsed'] == '2025-10-01'
        assert filtered[1]['date_parsed'] == '2025-10-15'

    def test_make_absolute_url(self):
        """Test URL absolutization."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        # Already absolute
        assert client._make_absolute_url("https://example.com/file.pdf") == "https://example.com/file.pdf"
        # Relative
        assert client._make_absolute_url("/uploads/file.pdf") == "https://www.cityofsanrafael.org/uploads/file.pdf"


class TestSanRafaelFactory:
    """Test the San Rafael convenience factory."""

    def test_create_san_rafael_client(self):
        """Test convenience factory creates correct client."""
        client = create_san_rafael_client()
        assert client.jurisdiction_id == "city-san-rafael"
        assert client.base_url == "https://www.cityofsanrafael.org"
        assert client.platform_name == "proudcity"


class TestExtractorProtocol:
    """Test the Extractor protocol."""

    def test_legistar_implements_protocol(self):
        """Test LegistarClient implements Extractor protocol."""
        client = LegistarClient("berkeley")
        assert isinstance(client, Extractor)

    def test_civicclerk_implements_protocol(self):
        """Test CivicClerkClient implements Extractor protocol."""
        client = CivicClerkClient("elcerritoca")
        assert isinstance(client, Extractor)

    def test_proudcity_implements_protocol(self):
        """Test ProudCityClient implements Extractor protocol."""
        client = ProudCityClient(
            base_url="https://www.cityofsanrafael.org",
            jurisdiction_id="city-san-rafael"
        )
        assert isinstance(client, Extractor)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Tests for Granicus ViewPublisher client, source, and platform detection.

All tests use mocked HTTP responses — no live network calls.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.clients.base import ExtractionConfig, Meeting
from civicos_extraction.clients.granicus import GranicusClient, GranicusSource


# ============================================================================
# Fixtures / Sample HTML
# ============================================================================

SAMPLE_GRANICUS_HTML = """
<html>
<head><title>Marin County - Meeting List</title></head>
<body>
<table>
<tr><th>Name</th><th>Date</th><th>Agenda</th><th>Agenda Packet</th></tr>
<tr>
    <td>BOS Meeting</td>
    <td>March 4, 2026</td>
    <td><a href="/AgendaViewer.php?view_id=33&event_id=1001">Agenda</a></td>
    <td><a href="/docs/packet-2026-03-04.pdf">Packet</a></td>
</tr>
<tr>
    <td>BOS Special Meeting</td>
    <td>Feb 25, 2026</td>
    <td><a href="/AgendaViewer.php?view_id=33&event_id=1002">Agenda</a></td>
    <td></td>
</tr>
<tr>
    <td>Planning Commission Meeting</td>
    <td>February 18, 2026</td>
    <td></td>
    <td></td>
</tr>
</table>
</body>
</html>
"""

SAMPLE_GRANICUS_HTML_UNIX_TS = """
<html><body>
<table>
<tr><th>Name</th><th>Date</th></tr>
<tr><td>Council Meeting</td><td>1758006000Sep 16, 2025</td></tr>
</table>
</body></html>
"""

SAMPLE_EMPTY_HTML = """
<html><body><table><tr><th>Name</th><th>Date</th></tr></table></body></html>
"""

SAMPLE_NO_TABLE_HTML = """
<html><body><p>No meetings found.</p></body></html>
"""


@pytest.fixture
def client():
    """Create a GranicusClient with mocked session."""
    c = GranicusClient(
        granicus_domain="marin",
        jurisdiction_id="county-marin",
        view_ids={"board_of_supervisors": "33"},
        default_view_id="36",
    )
    c._last_request_time = 999999999.0  # Skip rate limiting in tests
    return c


@pytest.fixture
def config():
    """Create a sample ExtractionConfig for Granicus."""
    return ExtractionConfig(
        source_id="granicus-county-marin",
        source_type="granicus",
        jurisdiction_id="county-marin",
        base_url="https://marin.granicus.com",
        archives={"board_of_supervisors": "33"},
        metadata={"granicus_domain": "marin", "default_view_id": "36"},
    )


# ============================================================================
# TestGranicusClient
# ============================================================================


class TestGranicusClient:
    """Tests for GranicusClient HTML parsing and normalization."""

    def test_parse_table_basic(self, client):
        """Parse standard Granicus HTML table."""
        events = client._parse_table(SAMPLE_GRANICUS_HTML, "33", meeting_type="board_of_supervisors")
        assert len(events) == 3

        # Check first event
        assert events[0]["title"] == "BOS Meeting"
        assert events[0]["view_id"] == "33"
        assert events[0]["meeting_type"] == "board_of_supervisors"
        assert "2026-03-04" in events[0]["datetime"]

    def test_parse_table_extracts_links(self, client):
        """Agenda and packet URLs are extracted correctly."""
        events = client._parse_table(SAMPLE_GRANICUS_HTML, "33")

        # First row has both links
        assert events[0]["agenda_url"] == "https://marin.granicus.com/AgendaViewer.php?view_id=33&event_id=1001"
        assert events[0]["packet_url"] == "https://marin.granicus.com/docs/packet-2026-03-04.pdf"

        # Second row has agenda but no packet
        assert events[1]["agenda_url"] is not None
        assert events[1]["packet_url"] is None

        # Third row has neither
        assert events[2]["agenda_url"] is None
        assert events[2]["packet_url"] is None

    def test_parse_date_formats(self, client):
        """Multiple date formats are handled."""
        # Full month name
        assert client._parse_date("March 4, 2026") == datetime(2026, 3, 4)
        # Abbreviated
        assert client._parse_date("Feb 25, 2026") == datetime(2026, 2, 25)
        # Numeric
        assert client._parse_date("10/7/2025") == datetime(2025, 10, 7)
        # ISO
        assert client._parse_date("2025-10-07") == datetime(2025, 10, 7)
        # Empty
        assert client._parse_date("") is None
        # Garbage
        assert client._parse_date("not a date") is None

    def test_parse_date_unix_timestamp_prefix(self, client):
        """Unix timestamp prefix is stripped before parsing."""
        events = client._parse_table(SAMPLE_GRANICUS_HTML_UNIX_TS, "1")
        assert len(events) == 1
        assert "2025-09-16" in events[0]["datetime"]

    def test_parse_table_empty(self, client):
        """Empty table returns no events."""
        events = client._parse_table(SAMPLE_EMPTY_HTML, "1")
        assert events == []

    def test_parse_table_no_table(self, client):
        """Page with no tables returns no events."""
        events = client._parse_table(SAMPLE_NO_TABLE_HTML, "1")
        assert events == []

    def test_normalize_event(self, client):
        """Raw event dict normalizes to Meeting dataclass."""
        event = {
            "title": "BOS Meeting",
            "datetime": "2026-03-04T00:00:00",
            "parsed_date": datetime(2026, 3, 4),
            "view_id": "33",
            "meeting_type": "board_of_supervisors",
            "agenda_url": "https://marin.granicus.com/AgendaViewer.php?view_id=33&event_id=1001",
            "source_url": "https://marin.granicus.com/ViewPublisher.php?view_id=33",
        }

        meeting = client.normalize_event(event)

        assert isinstance(meeting, Meeting)
        assert meeting.id.startswith("granicus-county-marin-33-20260304-")
        assert meeting.title == "BOS Meeting"
        assert meeting.jurisdiction_id == "county-marin"
        assert meeting.meeting_type == "board_of_supervisors"
        assert meeting.source_platform == "granicus"
        assert meeting.meeting_datetime == datetime(2026, 3, 4)

    def test_get_events_with_mock(self, client):
        """get_events iterates view_ids and applies date filter."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.status_code = 200

        with patch.object(client, "_fetch_view", return_value=mock_response):
            events = client.get_events(days_ahead=90, days_past=365)

        # All 3 events from sample HTML should be returned (within date range)
        assert len(events) >= 1

    def test_health_check(self, client):
        """Health check returns HealthStatus."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.status_code = 200

        with patch.object(client, "_fetch_view", return_value=mock_response):
            health = client.health()

        assert health.is_available is True
        assert health.available_count == 3
        assert health.source_id == "granicus-county-marin"
        assert health.source_type == "granicus"

    def test_health_check_failure(self, client):
        """Health check handles failures gracefully."""
        with patch.object(client, "_fetch_view", return_value=None):
            health = client.health()

        assert health.is_available is False
        assert len(health.errors) > 0

    def test_validate_success(self, client):
        """Validate returns valid when API is reachable."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.status_code = 200

        with patch.object(client, "_fetch_view", return_value=mock_response):
            result = client.validate()

        assert result.is_valid is True
        assert result.config_valid is True
        assert result.api_reachable is True

    def test_validate_unreachable(self, client):
        """Validate returns invalid when API is unreachable."""
        with patch.object(client, "_fetch_view", return_value=None):
            result = client.validate()

        assert result.is_valid is False
        assert result.api_reachable is False

    def test_make_absolute_url(self, client):
        """Relative URLs are converted to absolute."""
        assert client._make_absolute_url("/foo.pdf") == "https://marin.granicus.com/foo.pdf"
        assert client._make_absolute_url("//cdn.example.com/foo.pdf") == "https://cdn.example.com/foo.pdf"
        assert client._make_absolute_url("https://example.com/foo.pdf") == "https://example.com/foo.pdf"
        assert client._make_absolute_url("foo.pdf") == "https://marin.granicus.com/foo.pdf"

    def test_platform_name(self, client):
        assert client.platform_name == "granicus"

    def test_source_id_format(self, client):
        assert client.source_id == "granicus-county-marin"


# ============================================================================
# TestGranicusSource
# ============================================================================


class TestGranicusSource:
    """Tests for GranicusSource config-driven wrapper."""

    def test_from_config(self, config):
        """GranicusSource initializes from ExtractionConfig."""
        source = GranicusSource(config)

        assert source.source_id == "granicus-county-marin"
        assert source.source_type == "granicus"
        assert source.client.granicus_domain == "marin"
        assert source.client.default_view_id == "36"
        assert source.client.view_ids == {"board_of_supervisors": "33"}

    def test_from_config_infers_domain_from_url(self):
        """Domain is inferred from base_url when not in metadata."""
        config = ExtractionConfig(
            source_id="granicus-county-test",
            source_type="granicus",
            jurisdiction_id="county-test",
            base_url="https://testcounty.granicus.com",
            metadata={},
        )
        source = GranicusSource(config)
        assert source.client.granicus_domain == "testcounty"

    def test_validate_delegates_to_client(self, config):
        """Validate calls through to client."""
        source = GranicusSource(config)

        mock_response = MagicMock()
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.status_code = 200

        with patch.object(source.client, "_fetch_view", return_value=mock_response):
            result = source.validate()

        assert result.is_valid is True

    def test_health_delegates_to_client(self, config):
        """Health calls through to client."""
        source = GranicusSource(config)

        mock_response = MagicMock()
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.status_code = 200

        with patch.object(source.client, "_fetch_view", return_value=mock_response):
            health = source.health()

        assert health.is_available is True


# ============================================================================
# TestGranicusDetection
# ============================================================================


class TestGranicusDetection:
    """Tests for Granicus platform detection."""

    def test_detect_direct_granicus_url(self):
        """Direct *.granicus.com URL is detected with high confidence."""
        from civicos_extraction.platform_detection import _detect_granicus

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_GRANICUS_HTML

        with patch("civicos_extraction.platform_detection.requests.get", return_value=mock_response):
            confidence, meta = _detect_granicus("https://marin.granicus.com", "marin", 10)

        assert confidence == 0.95
        assert meta["detection_mode"] == "direct"
        assert meta["granicus_domain"] == "marin"

    def test_detect_indirect_via_city_website(self):
        """Granicus links found on city website get 0.85 confidence."""
        from civicos_extraction.platform_detection import _detect_granicus

        city_html = '<html><body><a href="https://marin.granicus.com/ViewPublisher.php?view_id=33">Meetings</a></body></html>'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = city_html

        with patch("civicos_extraction.platform_detection.requests.get", return_value=mock_response):
            confidence, meta = _detect_granicus("https://www.marincounty.gov", "marin", 10)

        assert confidence == 0.85
        assert meta["detection_mode"] == "indirect"

    def test_no_false_positive_on_unrelated_site(self):
        """Non-Granicus sites don't trigger detection."""
        from civicos_extraction.platform_detection import _detect_granicus

        city_html = "<html><body><p>City of Test</p></body></html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = city_html

        with patch("civicos_extraction.platform_detection.requests.get", return_value=mock_response):
            confidence, meta = _detect_granicus("https://www.cityoftest.org", "test", 10)

        assert confidence == 0.0

    def test_detect_platform_integration(self):
        """detect_platform finds Granicus for *.granicus.com URLs."""
        from civicos_extraction.platform_detection import detect_platform

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_GRANICUS_HTML
        mock_response.content = SAMPLE_GRANICUS_HTML.encode("utf-8")

        # Mock all HTTP calls to return Granicus HTML for granicus.com,
        # and 404 for everything else
        def side_effect(url, **kwargs):
            if "granicus.com" in url:
                return mock_response
            resp = MagicMock()
            resp.status_code = 404
            resp.content = b"<html><body>Not found</body></html>"
            return resp

        with patch("civicos_extraction.platform_detection.requests.get", side_effect=side_effect):
            result = detect_platform("https://marin.granicus.com", jurisdiction_id="county-marin")

        assert result.source_type == "granicus"
        assert result.confidence >= 0.9


# ============================================================================
# TestGranicusDiscovery
# ============================================================================


class TestGranicusDiscovery:
    """Tests for view_id discovery."""

    def test_discover_view_ids(self, client):
        """discover_view_ids probes sequential IDs and returns raw view data."""
        call_count = 0

        def mock_fetch(view_id):
            nonlocal call_count
            call_count += 1
            if view_id in ("1", "2"):
                resp = MagicMock()
                if view_id == "1":
                    resp.text = '<html><head><title>Board of Supervisors</title></head><body>' + \
                        '<table><tr><th>Name</th><th>Date</th></tr>' + \
                        '<tr><td>BOS Meeting</td><td>March 1, 2026</td></tr></table></body></html>'
                else:
                    resp.text = '<html><head><title>Planning Commission</title></head><body>' + \
                        '<table><tr><th>Name</th><th>Date</th></tr>' + \
                        '<tr><td>PC Meeting</td><td>March 2, 2026</td></tr></table></body></html>'
                resp.status_code = 200
                return resp
            return None

        with patch.object(client, "_fetch_view", side_effect=mock_fetch):
            raw_views = client.discover_view_ids()

        # Returns raw data keyed by view_id
        assert "1" in raw_views
        assert "2" in raw_views
        assert raw_views["1"]["page_title"] == "Board of Supervisors"
        assert raw_views["2"]["page_title"] == "Planning Commission"
        assert "BOS Meeting" in raw_views["1"]["sample_titles"]

    def test_discover_stops_after_consecutive_empty(self, client):
        """Discovery stops after 5 consecutive empty responses."""
        call_count = 0

        def mock_fetch(view_id):
            nonlocal call_count
            call_count += 1
            if view_id == "1":
                resp = MagicMock()
                resp.text = '<html><head><title>BOS</title></head><body>' + \
                    '<table><tr><th>Name</th><th>Date</th></tr>' + \
                    '<tr><td>Meeting</td><td>March 1, 2026</td></tr></table></body></html>'
                resp.status_code = 200
                return resp
            return None

        with patch.object(client, "_fetch_view", side_effect=mock_fetch):
            raw_views = client.discover_view_ids()

        # Should have view 1 + 5 consecutive empty (2-6) = 6 calls
        assert call_count == 6
        assert len(raw_views) == 1


# ============================================================================
# TestExtractionConfigCountyPrefix
# ============================================================================


class TestExtractionConfigCountyPrefix:
    """Tests for ExtractionConfig.from_jurisdiction with county- prefix."""

    def test_county_prefix_config_loading(self, tmp_path):
        """county- prefix resolves to county-marin.json."""
        config_data = {
            "source_id": "granicus-county-marin",
            "source_type": "granicus",
            "jurisdiction_id": "county-marin",
            "base_url": "https://marin.granicus.com",
        }
        config_file = tmp_path / "county-marin.json"
        config_file.write_text(json.dumps(config_data))

        with patch("civicos_extraction.config.get_config_dir", return_value=tmp_path):
            config = ExtractionConfig.from_jurisdiction("county-marin")

        assert config.jurisdiction_id == "county-marin"
        assert config.source_type == "granicus"

    def test_state_prefix_config_loading(self, tmp_path):
        """state- prefix resolves to state-california.json."""
        config_data = {
            "source_id": "test-state-california",
            "source_type": "test",
            "jurisdiction_id": "state-california",
            "base_url": "https://example.com",
        }
        config_file = tmp_path / "state-california.json"
        config_file.write_text(json.dumps(config_data))

        with patch("civicos_extraction.config.get_config_dir", return_value=tmp_path):
            config = ExtractionConfig.from_jurisdiction("state-california")

        assert config.jurisdiction_id == "state-california"


# ============================================================================
# TestGranicusBodyNameInference
# ============================================================================


class TestGenerateBodyNames:
    """Tests for LLM-based body name generation."""

    def test_generate_body_names_success(self, client):
        """LLM assigns descriptive names from raw view data."""
        raw_views = {
            "1": {
                "page_title": "Board of Supervisors",
                "h1": "",
                "sample_titles": ["BOS Regular Meeting", "BOS Special Session"],
                "event_count": 10,
            },
            "3": {
                "page_title": "New View",  # Generic — LLM should use sample titles
                "h1": "",
                "sample_titles": ["Parks Commission - Regular Meeting", "Parks Commission - Special Meeting"],
                "event_count": 5,
            },
        }

        mock_provider = MagicMock()
        mock_provider.complete.return_value = MagicMock(
            content='{"1": "Board of Supervisors", "3": "Parks and Recreation Commission"}'
        )

        mock_module = MagicMock()
        mock_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"civicos_services.core.llm_provider": mock_module}):
            result = client.generate_body_names(raw_views)

        assert result["archives"]["board_of_supervisors"] == "1"
        assert result["archives"]["parks_and_recreation_commission"] == "3"
        # Provenance records what the LLM saw and returned
        assert result["provenance"]["prompt_template"] == "generate_body_names/v1"
        assert result["provenance"]["input"] == raw_views
        assert "Board of Supervisors" in result["provenance"]["raw_response"]

    def test_generate_body_names_fallback_on_bad_json(self, client):
        """Falls back to view_N naming when LLM returns invalid JSON."""
        raw_views = {"1": {"page_title": "", "h1": "", "sample_titles": [], "event_count": 2}}

        mock_provider = MagicMock()
        mock_provider.complete.return_value = MagicMock(content="I don't know")

        mock_module = MagicMock()
        mock_module.get_model_for_task.return_value = mock_provider
        with patch.dict("sys.modules", {"civicos_services.core.llm_provider": mock_module}):
            result = client.generate_body_names(raw_views)

        assert result["archives"] == {"view_1": "1"}
        assert result["provenance"]["raw_response"] == "I don't know"

    def test_generate_body_names_empty_input(self, client):
        """Empty raw_views returns empty dict without calling LLM."""
        result = client.generate_body_names({})
        assert result == {"archives": {}, "provenance": None}

    def test_discover_returns_raw_data_for_llm(self, client):
        """discover_view_ids returns raw context including generic titles for LLM to interpret."""
        def mock_fetch(view_id):
            if view_id == "1":
                resp = MagicMock()
                resp.text = (
                    '<html><head><title>New View</title></head><body>'
                    '<table><tr><th>Name</th><th>Date</th></tr>'
                    '<tr><td>Parks Commission - Regular Meeting</td><td>March 1, 2026</td></tr>'
                    '</table></body></html>'
                )
                resp.status_code = 200
                return resp
            return None

        with patch.object(client, "_fetch_view", side_effect=mock_fetch):
            raw_views = client.discover_view_ids()

        # Raw data preserves the generic title — LLM decides what to do with it
        assert raw_views["1"]["page_title"] == "New View"
        assert "Parks Commission - Regular Meeting" in raw_views["1"]["sample_titles"]


# ============================================================================
# generate_column_map Tests
# ============================================================================


class TestGenerateColumnMap:
    """Tests for LLM-based column mapping with provenance."""

    def test_generate_column_map_success(self, client):
        """LLM infers column indices and provenance is recorded."""
        mock_response = MagicMock()
        mock_response.text = (
            '<html><body><table>'
            '<tr><th>Name</th><th>Date</th><th>Duration</th><th>Agenda</th></tr>'
            '<tr><td>City Council</td><td>March 10, 2026</td><td>2h</td><td><a href="/agenda">View</a></td></tr>'
            '</table></body></html>'
        )

        mock_provider = MagicMock()
        mock_provider.complete.return_value = MagicMock(
            content='{"name": 0, "date": 1, "agenda": 3}'
        )

        mock_module = MagicMock()
        mock_module.get_model_for_task.return_value = mock_provider

        with patch.object(client, "_fetch_view", return_value=mock_response):
            with patch.dict("sys.modules", {"civicos_services.core.llm_provider": mock_module}):
                result = client.generate_column_map(view_id="1")

        assert result["column_map"] == {"name": 0, "date": 1, "agenda": 3}
        assert result["provenance"]["prompt_template"] == "generate_column_map/v1"
        assert result["provenance"]["input"]["view_id"] == "1"
        assert result["provenance"]["input"]["num_columns"] == 4
        assert '{"name": 0, "date": 1, "agenda": 3}' in result["provenance"]["raw_response"]

    def test_generate_column_map_filters_invalid_fields(self, client):
        """Unknown fields and out-of-bounds indices are excluded; provenance preserves raw map."""
        mock_response = MagicMock()
        mock_response.text = (
            '<html><body><table>'
            '<tr><th>Name</th><th>Date</th></tr>'
            '<tr><td>Meeting</td><td>Jan 1, 2026</td></tr>'
            '</table></body></html>'
        )

        mock_provider = MagicMock()
        mock_provider.complete.return_value = MagicMock(
            content='{"name": 0, "date": 1, "bogus_field": 0, "agenda": 99}'
        )

        mock_module = MagicMock()
        mock_module.get_model_for_task.return_value = mock_provider

        with patch.object(client, "_fetch_view", return_value=mock_response):
            with patch.dict("sys.modules", {"civicos_services.core.llm_provider": mock_module}):
                result = client.generate_column_map(view_id="1")

        # Only valid, in-bounds fields survive
        assert result["column_map"] == {"name": 0, "date": 1}
        # Provenance preserves the raw LLM output before validation
        assert result["provenance"]["parsed_map"]["bogus_field"] == 0
        assert result["provenance"]["parsed_map"]["agenda"] == 99

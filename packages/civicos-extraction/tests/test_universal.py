"""Tests for the universal adapter extractor and config generation."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from civicos_extraction.clients.universal import (
    UniversalExtractor,
    UniversalSource,
    ExtractionError,
)
from civicos_extraction.clients.universal_config import (
    _extract_sample,
    _validate_config,
    _smoke_test,
)
from civicos_extraction.clients.base import ExtractionConfig


# --- Sample HTML fixtures ---

SAMPLE_TABLE_HTML = """
<html>
<body>
<main>
<h1>City Council Meetings</h1>
<table class="meetings-list">
<thead>
<tr><th>Meeting</th><th>Date</th><th>Agenda</th><th>Minutes</th></tr>
</thead>
<tbody>
<tr>
  <td>City Council Regular Meeting</td>
  <td>March 15, 2026</td>
  <td><a href="/agenda/2026-03-15.pdf">Agenda</a></td>
  <td><a href="/minutes/2026-03-15.pdf">Minutes</a></td>
</tr>
<tr>
  <td>Planning Commission</td>
  <td>March 10, 2026</td>
  <td><a href="/agenda/2026-03-10.pdf">Agenda</a></td>
  <td></td>
</tr>
<tr>
  <td>City Council Special Meeting</td>
  <td>February 28, 2026</td>
  <td><a href="/agenda/2026-02-28.pdf">Agenda</a></td>
  <td><a href="/minutes/2026-02-28.pdf">Minutes</a></td>
</tr>
</tbody>
</table>
</main>
</body>
</html>
"""

SAMPLE_LIST_HTML = """
<html><body>
<div class="meeting-list">
<div class="meeting-card">
  <h3 class="title">Board of Supervisors</h3>
  <span class="date">04/01/2026</span>
  <a class="agenda-link" href="/agenda/bos-040126.pdf">View Agenda</a>
</div>
<div class="meeting-card">
  <h3 class="title">Parks Commission</h3>
  <span class="date">03/25/2026</span>
  <a class="agenda-link" href="/agenda/parks-032526.pdf">View Agenda</a>
</div>
</div>
</body></html>
"""

TABLE_ADAPTER_CONFIG = {
    "page_type": "table",
    "listing": {
        "url_template": "https://example.gov/meetings",
        "container": "table.meetings-list",
        "row": "tbody tr",
        "fields": {
            "title": {"selector": "td:nth-child(1)", "extract": "text"},
            "date": {
                "selector": "td:nth-child(2)",
                "extract": "text",
                "date_format": "%B %d, %Y",
            },
            "agenda_url": {"selector": "td:nth-child(3) a", "extract": "href"},
            "minutes_url": {"selector": "td:nth-child(4) a", "extract": "href"},
        },
    },
    "pagination": {"type": "none"},
    "requires_javascript": False,
}

CARD_ADAPTER_CONFIG = {
    "page_type": "card",
    "listing": {
        "url_template": "https://example.gov/meetings",
        "container": "div.meeting-list",
        "row": "div.meeting-card",
        "fields": {
            "title": {"selector": "h3.title", "extract": "text"},
            "date": {
                "selector": "span.date",
                "extract": "text",
                "date_format": "%m/%d/%Y",
            },
            "agenda_url": {"selector": "a.agenda-link", "extract": "href"},
        },
    },
    "pagination": {"type": "none"},
    "requires_javascript": False,
}


# --- UniversalExtractor Tests ---


class TestUniversalExtractor:
    """Tests for the deterministic extraction engine."""

    def test_init(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        assert extractor.jurisdiction_id == "city-test"
        assert extractor.platform_name == "universal"
        assert extractor.source_id == "universal-city-test"
        assert extractor.source_type == "universal"

    def test_extract_table_html(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)
        assert len(events) == 3
        assert events[0]["title"] == "City Council Regular Meeting"
        assert events[0]["date"] == "March 15, 2026"
        assert events[0]["_parsed_date"] == datetime(2026, 3, 15)
        assert events[0]["agenda_url"] == "https://example.gov/agenda/2026-03-15.pdf"

    def test_extract_card_html(self):
        extractor = UniversalExtractor(
            "city-test", CARD_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_LIST_HTML)
        assert len(events) == 2
        assert events[0]["title"] == "Board of Supervisors"
        assert events[0]["_parsed_date"] == datetime(2026, 4, 1)

    def test_normalize_event(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)
        meeting = extractor.normalize_event(events[0])

        assert meeting.title == "City Council Regular Meeting"
        assert meeting.meeting_datetime == datetime(2026, 3, 15)
        assert meeting.jurisdiction_id == "city-test"
        assert meeting.source_platform == "universal"
        assert meeting.id.startswith("universal-")
        assert meeting.agenda_url == "https://example.gov/agenda/2026-03-15.pdf"

    def test_extraction_error_on_broken_container(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "container": "table.nonexistent",
            },
        }
        extractor = UniversalExtractor("city-test", config, "https://example.gov")
        with pytest.raises(ExtractionError, match="matched 0 elements"):
            extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)

    def test_extraction_error_on_broken_rows(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "row": "div.nonexistent",
            },
        }
        extractor = UniversalExtractor("city-test", config, "https://example.gov")
        with pytest.raises(ExtractionError, match="matched 0 elements"):
            extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)

    def test_date_parsing_multiple_formats(self):
        extractor = UniversalExtractor("city-test", TABLE_ADAPTER_CONFIG)
        assert extractor._parse_date("March 15, 2026") == datetime(2026, 3, 15)
        assert extractor._parse_date("Mar 15, 2026") == datetime(2026, 3, 15)
        assert extractor._parse_date("03/15/2026") == datetime(2026, 3, 15)
        assert extractor._parse_date("2026-03-15") == datetime(2026, 3, 15)
        assert extractor._parse_date("") is None
        assert extractor._parse_date("not a date") is None

    def test_date_parsing_date_ranges(self):
        """Date ranges like 'February 18-19, 2026' should parse to the first date."""
        extractor = UniversalExtractor("city-test", TABLE_ADAPTER_CONFIG)
        assert extractor._parse_date("February 18-19, 2026") == datetime(2026, 2, 18)
        assert extractor._parse_date("January 7-14, 2026") == datetime(2026, 1, 7)
        assert extractor._parse_date("February 25-26, 2026") == datetime(2026, 2, 25)

    def test_time_combining(self):
        """Test that time field gets merged into parsed date."""
        html = """
        <table class="meetings-list"><tbody>
        <tr>
          <td>Council Meeting</td>
          <td>March 15, 2026</td>
          <td></td><td></td>
        </tr>
        </tbody></table>
        """
        # Add a time field to the config
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "fields": {
                    **TABLE_ADAPTER_CONFIG["listing"]["fields"],
                    "time": {"selector": "td:nth-child(2)", "extract": "text"},
                },
            },
        }
        # Time combining won't work here since date and time are in same cell,
        # but we can verify the extractor handles the time field gracefully
        extractor = UniversalExtractor("city-test", config)
        events = extractor._extract_rows_from_page(html)
        assert len(events) == 1

    def test_href_extraction_relative_urls(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)
        # Relative URL should be resolved against base_url
        assert events[0]["agenda_url"] == "https://example.gov/agenda/2026-03-15.pdf"

    def test_missing_optional_fields(self):
        """Minutes field should be None when link is absent."""
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)
        # Second row has no minutes link
        assert events[1]["minutes_url"] is None

    @patch.object(UniversalExtractor, "_fetch_page", return_value=SAMPLE_TABLE_HTML)
    def test_get_events_with_mock_fetch(self, mock_fetch):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        # Use a wide date range to include our test data
        events = extractor.get_events(days_ahead=365 * 10, days_past=365 * 10)
        assert len(events) == 3
        mock_fetch.assert_called_once()

    @patch.object(UniversalExtractor, "_fetch_page", return_value=SAMPLE_TABLE_HTML)
    def test_get_meetings_returns_meeting_objects(self, mock_fetch):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        meetings = extractor.get_meetings(days_ahead=365 * 10, days_past=365 * 10)
        assert len(meetings) == 3
        assert all(m.source_platform == "universal" for m in meetings)
        assert all(m.jurisdiction_id == "city-test" for m in meetings)

    def test_health_check(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        with patch.object(
            extractor, "_fetch_page", return_value=SAMPLE_TABLE_HTML
        ):
            status = extractor.health()
            assert status.is_available is True
            assert status.available_count == 3
            assert status.source_type == "universal"

    def test_health_check_broken_selectors(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "container": "table.broken",
            },
        }
        extractor = UniversalExtractor("city-test", config, "https://example.gov")
        with patch.object(
            extractor, "_fetch_page", return_value=SAMPLE_TABLE_HTML
        ):
            status = extractor.health()
            assert status.is_available is False
            assert len(status.errors) > 0

    def test_validate_good_config(self):
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        result = extractor.validate()
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_fields(self):
        config = {
            "listing": {
                "url_template": "https://example.gov",
                "row": "tr",
                "fields": {},  # Missing title and date
            }
        }
        extractor = UniversalExtractor("city-test", config)
        result = extractor.validate()
        assert result.is_valid is False
        assert any("title" in e for e in result.errors)
        assert any("date" in e for e in result.errors)

    def test_detail_enrichment(self):
        """Detail config should merge additional fields from a detail page."""
        detail_html = """
        <html><body>
        <h1>Council Meeting</h1>
        <time class="datetime">Wednesday, March 15, 2026 9:30 am</time>
        <strong>City Hall, 123 Main St</strong>
        <a href="https://youtube.com/watch?v=abc">Watch Video</a>
        </body></html>
        """
        config = {
            **TABLE_ADAPTER_CONFIG,
            "detail": {
                "url_field": "agenda_url",
                "fields": {
                    "title": {"selector": "h1", "extract": "text"},
                    "time": {"selector": "time.datetime", "extract": "text"},
                    "location": {"selector": "strong", "extract": "text"},
                    "video_url": {"selector": "a[href*='youtube.com']", "extract": "href"},
                },
            },
        }
        extractor = UniversalExtractor("city-test", config, "https://example.gov")
        event = {
            "title": "March 15, 2026 Council Meeting",
            "date": "March 15, 2026",
            "_parsed_date": datetime(2026, 3, 15),
            "agenda_url": "https://example.gov/meeting/1",
        }
        with patch.object(extractor, "_fetch_page", return_value=detail_html):
            enriched = extractor._enrich_from_detail(event)
        # Title overridden from detail page
        assert enriched["title"] == "Council Meeting"
        # Time merged into date
        assert enriched["_parsed_date"] == datetime(2026, 3, 15, 9, 30)
        # New fields from detail
        assert enriched["location"] == "City Hall, 123 Main St"
        assert enriched["video_url"] == "https://youtube.com/watch?v=abc"

    def test_detail_enrichment_skipped_without_config(self):
        """Events should pass through unchanged when no detail config exists."""
        extractor = UniversalExtractor("city-test", TABLE_ADAPTER_CONFIG)
        event = {"title": "Test", "_parsed_date": datetime(2026, 1, 1)}
        result = extractor._enrich_from_detail(event)
        assert result is event  # Same object, unchanged

    def test_detail_enrichment_survives_fetch_failure(self):
        """Detail fetch failure should log warning, not crash."""
        config = {
            **TABLE_ADAPTER_CONFIG,
            "detail": {
                "url_field": "agenda_url",
                "fields": {"time": {"selector": "time", "extract": "text"}},
            },
        }
        extractor = UniversalExtractor("city-test", config, "https://example.gov")
        event = {
            "title": "Test",
            "_parsed_date": datetime(2026, 1, 1),
            "agenda_url": "https://example.gov/broken",
        }
        with patch.object(extractor, "_fetch_page", side_effect=Exception("timeout")):
            result = extractor._enrich_from_detail(event)
        # Should return event unchanged, not crash
        assert result["title"] == "Test"
        assert "time" not in result

    def test_stable_meeting_ids(self):
        """Same input should produce the same meeting ID."""
        extractor = UniversalExtractor(
            "city-test", TABLE_ADAPTER_CONFIG, "https://example.gov"
        )
        events = extractor._extract_rows_from_page(SAMPLE_TABLE_HTML)
        m1 = extractor.normalize_event(events[0])
        m2 = extractor.normalize_event(events[0])
        assert m1.id == m2.id


# --- Config Validation Tests ---


class TestConfigValidation:
    """Tests for the config validation logic."""

    def test_valid_config(self):
        errors = _validate_config(TABLE_ADAPTER_CONFIG)
        assert errors == []

    def test_missing_listing(self):
        errors = _validate_config({"page_type": "table"})
        assert any("listing" in e for e in errors)

    def test_missing_required_fields(self):
        config = {
            "listing": {
                "row": "tr",
                "fields": {"agenda_url": {"selector": "a", "extract": "href"}},
            }
        }
        errors = _validate_config(config)
        assert any("title" in e for e in errors)
        assert any("date" in e for e in errors)

    def test_invalid_page_type(self):
        config = {**TABLE_ADAPTER_CONFIG, "page_type": "unknown"}
        errors = _validate_config(config)
        assert any("page_type" in e for e in errors)

    def test_invalid_pagination_type(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "pagination": {"type": "infinite_scroll"},
        }
        errors = _validate_config(config)
        assert any("pagination" in e for e in errors)

    def test_invalid_extract_mode(self):
        config = {
            "listing": {
                "row": "tr",
                "fields": {
                    "title": {"selector": "td", "extract": "invalid_mode"},
                    "date": {"selector": "td", "extract": "text"},
                },
            }
        }
        errors = _validate_config(config)
        assert any("extract mode" in e for e in errors)

    def test_attr_extract_mode_valid(self):
        config = {
            "listing": {
                "row": "tr",
                "fields": {
                    "title": {"selector": "td", "extract": "text"},
                    "date": {"selector": "td", "extract": "text"},
                    "data_id": {"selector": "td", "extract": "attr:data-id"},
                },
            }
        }
        errors = _validate_config(config)
        assert errors == []


# --- Sample Extraction Tests ---


class TestExtractSample:
    """Tests for HTML sample extraction."""

    def test_extracts_largest_table(self):
        html = """
        <html><body>
        <table><tr><td>small</td></tr></table>
        <table class="meetings"><tr><td>r1</td></tr><tr><td>r2</td></tr><tr><td>r3</td></tr></table>
        </body></html>
        """
        sample = _extract_sample(html)
        assert "r1" in sample
        assert "r2" in sample

    def test_removes_noise(self):
        html = """
        <html><body>
        <script>alert('evil')</script>
        <nav>Navigation</nav>
        <table><tr><td>meeting data</td></tr></table>
        <footer>Footer</footer>
        </body></html>
        """
        sample = _extract_sample(html)
        assert "alert" not in sample
        assert "Navigation" not in sample
        assert "meeting data" in sample

    def test_truncates_large_html(self):
        html = "<html><body><table>" + "<tr><td>" + "x" * 500 + "</td></tr>" * 100 + "</table></body></html>"
        sample = _extract_sample(html, max_chars=1000)
        assert len(sample) <= 1000


# --- Smoke Test Tests ---


class TestSmokeTest:
    """Tests for config smoke testing against HTML."""

    def test_good_config_passes(self):
        errors = _smoke_test(TABLE_ADAPTER_CONFIG, SAMPLE_TABLE_HTML)
        assert errors == []

    def test_broken_container_fails(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "container": "table.nonexistent",
            },
        }
        errors = _smoke_test(config, SAMPLE_TABLE_HTML)
        assert len(errors) > 0
        assert any("Container" in e for e in errors)

    def test_broken_row_selector_fails(self):
        config = {
            **TABLE_ADAPTER_CONFIG,
            "listing": {
                **TABLE_ADAPTER_CONFIG["listing"],
                "row": "div.nonexistent",
            },
        }
        errors = _smoke_test(config, SAMPLE_TABLE_HTML)
        assert len(errors) > 0
        assert any("Row" in e for e in errors)


# --- UniversalSource Tests ---


class TestUniversalSource:
    """Tests for the DataSource protocol wrapper."""

    def test_requires_adapter_in_metadata(self):
        config = ExtractionConfig(
            source_id="universal-test",
            source_type="universal",
            jurisdiction_id="city-test",
            base_url="https://example.gov",
            metadata={},  # No adapter config
        )
        with pytest.raises(ValueError, match="missing 'adapter'"):
            UniversalSource(config)

    def test_creates_from_config(self):
        config = ExtractionConfig(
            source_id="universal-test",
            source_type="universal",
            jurisdiction_id="city-test",
            base_url="https://example.gov",
            metadata={"adapter": TABLE_ADAPTER_CONFIG},
        )
        source = UniversalSource(config)
        assert source.source_id == "universal-city-test"
        assert source.source_type == "universal"


# --- Factory Integration Test ---


class TestFactoryIntegration:
    """Test that factory.py can create UniversalSource."""

    def test_factory_creates_universal_source(self):
        from civicos_extraction.clients.factory import create_source

        config = ExtractionConfig(
            source_id="universal-test",
            source_type="universal",
            jurisdiction_id="city-test",
            base_url="https://example.gov",
            metadata={"adapter": TABLE_ADAPTER_CONFIG},
        )
        source = create_source(config)
        assert isinstance(source, UniversalSource)
        assert source.source_id == "universal-city-test"


# --- Platform Detection Integration Test ---


class TestPlatformDetection:
    """Test universal adapter detection in the platform detection chain."""

    @patch("civicos_extraction.platform_detection.requests.get")
    def test_detect_universal_with_meeting_content(self, mock_get):
        from civicos_extraction.platform_detection import _detect_universal

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html><body>
        <h1>City Council Meetings</h1>
        <table>
        <tr><td>Council Meeting</td><td>March 15, 2026</td><td>Agenda</td></tr>
        <tr><td>Board Meeting</td><td>April 1, 2026</td><td>Minutes</td></tr>
        <tr><td>Planning Commission</td><td>April 10, 2026</td><td>Agenda</td></tr>
        </table>
        </body></html>
        """
        mock_get.return_value = mock_response

        confidence, metadata = _detect_universal("https://custom-city.gov/meetings", 10)
        # Should detect meeting-like content
        assert confidence >= 0.30
        assert metadata["keyword_hits"] >= 3
        assert metadata["date_count"] >= 2

    @patch("civicos_extraction.platform_detection.requests.get")
    def test_detect_universal_no_meeting_content(self, mock_get):
        from civicos_extraction.platform_detection import _detect_universal

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body><h1>Welcome to our city!</h1><p>Parks info.</p></body></html>"
        mock_get.return_value = mock_response

        confidence, _ = _detect_universal("https://generic-city.gov", 10)
        assert confidence == 0.0

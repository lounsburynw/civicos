"""
Tests for CivicPlus Archive client.

All tests use mocked HTTP responses — no live network calls.
Tests focus on the parsing, normalization, and orchestration logic.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_extraction.clients.base import ExtractionConfig, Meeting
from civicos_extraction.clients.civicplus import (
    CivicPlusClient,
    CivicPlusSource,
    _parse_entry_text,
    _parse_date,
    _ADID_RE,
)


# ============================================================================
# Sample HTML
# ============================================================================

SAMPLE_ARCHIVE_HTML = """
<html><body>
<a href="Archive.aspx?ADID=1001"><span>March 30, 2026, City Council Agenda</span></a>
<a href="Archive.aspx?ADID=1002"><span>March 16, 2026, City Council Agenda</span></a>
<a href="Archive.aspx?ADID=1003"><span>February 4, 2026, Planning Commission Staff Report</span></a>
</body></html>
"""

SAMPLE_ARCHIVE_NUMERIC_DATES = """
<html><body>
<a href="Archive.aspx?ADID=2001"><span>3/30/2026 City Council Agenda</span></a>
<a href="Archive.aspx?ADID=2002"><span>1/5/2026 Special Meeting Minutes</span></a>
</body></html>
"""

SAMPLE_ARCHIVE_COMPACT_DATES = """
<html><body>
<a href="Archive.aspx?ADID=3001"><span>02172026 Approved Corte Madera Regular Town Council Minutes</span></a>
</body></html>
"""

SAMPLE_ARCHIVE_MIXED = """
<html><body>
<a href="Archive.aspx?ADID=4001"><span>March 30, 2026, City Council Agenda</span></a>
<a href="Archive.aspx?ADID=4002"><span>not a parseable entry</span></a>
<a href="Archive.aspx?ADID=4003"><span>January 15, 2026, Planning Commission Report</span></a>
</body></html>
"""

SAMPLE_ARCHIVE_EMPTY = """
<html><body><p>No documents found.</p></body></html>
"""

SAMPLE_MINUTES_HTML = """
<html><body>
<a href="Archive.aspx?ADID=5001"><span>March 30, 2026, City Council Minutes</span></a>
<a href="Archive.aspx?ADID=5002"><span>February 10, 2026, City Council Minutes</span></a>
</body></html>
"""

SAMPLE_ARCHIVE_HTML_TAGS_IN_LINK = """
<html><body>
<a href="Archive.aspx?ADID=6001"><span><strong>April 5, 2026</strong>, Council Agenda</span></a>
</body></html>
"""


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """CivicPlusClient with throttling disabled for tests."""
    c = CivicPlusClient(
        base_url="https://www.ci.larkspur.ca.us",
        jurisdiction_id="city-larkspur",
        archives={"city_council": "49"},
    )
    c.last_request_time = 999999999.0  # Skip throttle
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def client_with_minutes():
    """CivicPlusClient with both agenda and minutes archives."""
    c = CivicPlusClient(
        base_url="https://www.ci.larkspur.ca.us",
        jurisdiction_id="city-larkspur",
        archives={"city_council": "49"},
        minutes_archives={"city_council": "50"},
    )
    c.last_request_time = 999999999.0
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def config():
    """ExtractionConfig for CivicPlus."""
    return ExtractionConfig(
        source_id="civicplus-city-larkspur",
        source_type="civicplus",
        jurisdiction_id="city-larkspur",
        base_url="https://www.ci.larkspur.ca.us",
        archives={"city_council": "49"},
        metadata={"minutes_archives": {"city_council": "50"}},
    )


def _mock_response(html, status_code=200):
    """Create a mock requests.Response with given HTML."""
    resp = MagicMock(spec=requests.Response)
    resp.text = html
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ============================================================================
# _parse_entry_text — pure function tests
# ============================================================================


class TestParseEntryText:
    """Tests for date+description parsing from CivicPlus link text."""

    def test_long_date_with_comma_separator(self):
        result = _parse_entry_text("March 30, 2026, City Council Agenda")
        assert result["date_str"] == "March 30, 2026"
        assert result["description"] == "City Council Agenda"

    def test_long_date_without_trailing_comma(self):
        result = _parse_entry_text("March 30 2026 City Council Agenda")
        assert result["date_str"] == "March 30 2026"
        assert result["description"] == "City Council Agenda"

    def test_numeric_date_format(self):
        result = _parse_entry_text("3/30/2026 City Council Agenda")
        assert result["date_str"] == "3/30/2026"
        assert result["description"] == "City Council Agenda"

    def test_compact_date_format(self):
        result = _parse_entry_text("02172026 Approved Corte Madera Regular Town Council Minutes")
        assert result["date_str"] == "02172026"
        assert result["description"] == "Approved Corte Madera Regular Town Council Minutes"

    def test_whitespace_normalization(self):
        result = _parse_entry_text("  March  30, 2026,  City  Council  Agenda  ")
        assert result["date_str"] == "March 30, 2026"
        assert result["description"] == "City Council Agenda"

    def test_unparseable_text_returns_none(self):
        assert _parse_entry_text("Not a date at all") is None

    def test_empty_string_returns_none(self):
        assert _parse_entry_text("") is None

    def test_only_whitespace_returns_none(self):
        assert _parse_entry_text("   ") is None

    def test_case_insensitive_month(self):
        result = _parse_entry_text("JANUARY 5, 2026, Special Meeting")
        assert result["date_str"] == "JANUARY 5, 2026"
        assert result["description"] == "Special Meeting"

    def test_single_digit_day(self):
        result = _parse_entry_text("February 4, 2026, Planning Commission Staff Report")
        assert result["date_str"] == "February 4, 2026"
        assert result["description"] == "Planning Commission Staff Report"

    def test_description_empty_when_only_date(self):
        result = _parse_entry_text("March 30, 2026,")
        assert result["date_str"] == "March 30, 2026"
        assert result["description"] == ""

    def test_numeric_single_digit_month_and_day(self):
        result = _parse_entry_text("1/5/2026 Special Meeting Minutes")
        assert result["date_str"] == "1/5/2026"
        assert result["description"] == "Special Meeting Minutes"


# ============================================================================
# _parse_date — pure function tests
# ============================================================================


class TestParseDate:
    """Tests for date string parsing into datetime objects."""

    def test_long_format_with_comma(self):
        assert _parse_date("March 30, 2026") == datetime(2026, 3, 30)

    def test_long_format_without_comma(self):
        assert _parse_date("March 30 2026") == datetime(2026, 3, 30)

    def test_numeric_format(self):
        assert _parse_date("3/30/2026") == datetime(2026, 3, 30)

    def test_compact_format(self):
        assert _parse_date("02172026") == datetime(2026, 2, 17)

    def test_january_first(self):
        assert _parse_date("January 1, 2026") == datetime(2026, 1, 1)

    def test_december_31(self):
        assert _parse_date("December 31, 2025") == datetime(2025, 12, 31)

    def test_unrecognized_format_returns_none(self):
        assert _parse_date("2026-03-30") is None

    def test_garbage_returns_none(self):
        assert _parse_date("not a date") is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_numeric_leading_zeros(self):
        assert _parse_date("01/05/2026") == datetime(2026, 1, 5)


# ============================================================================
# ADID regex
# ============================================================================


class TestAdidRegex:
    """Tests for the ADID link extraction regex."""

    def test_extracts_adid_and_text_with_span(self):
        html = '<a href="Archive.aspx?ADID=1234"><span>March 30, 2026, Agenda</span></a>'
        matches = list(_ADID_RE.finditer(html))
        assert len(matches) == 1
        assert matches[0].group(1) == "1234"
        assert "March 30, 2026" in matches[0].group(2)

    def test_extracts_adid_without_span(self):
        html = '<a href="Archive.aspx?ADID=5678">Some text</a>'
        matches = list(_ADID_RE.finditer(html))
        assert len(matches) == 1
        assert matches[0].group(1) == "5678"

    def test_case_insensitive_href(self):
        html = '<a HREF="Archive.aspx?ADID=9999"><span>Jan 1, 2026, Test</span></a>'
        matches = list(_ADID_RE.finditer(html))
        assert len(matches) == 1
        assert matches[0].group(1) == "9999"

    def test_no_match_on_amid_link(self):
        html = '<a href="Archive.aspx?AMID=49">Archive</a>'
        matches = list(_ADID_RE.finditer(html))
        assert len(matches) == 0

    def test_multiple_matches(self):
        html = (
            '<a href="Archive.aspx?ADID=100"><span>Jan 1, 2026, A</span></a>'
            '<a href="Archive.aspx?ADID=200"><span>Feb 2, 2026, B</span></a>'
        )
        matches = list(_ADID_RE.finditer(html))
        assert len(matches) == 2
        assert matches[0].group(1) == "100"
        assert matches[1].group(1) == "200"


# ============================================================================
# CivicPlusClient — properties
# ============================================================================


class TestCivicPlusClientProperties:
    """Tests for CivicPlusClient identity and config properties."""

    def test_platform_name(self, client):
        assert client.platform_name == "civicplus"

    def test_source_id_format(self, client):
        assert client.source_id == "civicplus-city-larkspur"

    def test_source_type(self, client):
        assert client.source_type == "civicplus"

    def test_base_url_trailing_slash_stripped(self):
        c = CivicPlusClient(
            base_url="https://example.com/",
            jurisdiction_id="city-test",
        )
        assert c.base_url == "https://example.com"

    def test_default_archives_empty(self):
        c = CivicPlusClient(
            base_url="https://example.com",
            jurisdiction_id="city-test",
        )
        assert c.archives == {}
        assert c.minutes_archives == {}


# ============================================================================
# CivicPlusClient._fetch_archive — mock HTTP
# ============================================================================


class TestFetchArchive:
    """Tests for _fetch_archive HTML parsing."""

    def test_parses_standard_entries(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        assert len(entries) == 3
        assert entries[0]["adid"] == "1001"
        assert entries[0]["date"] == datetime(2026, 3, 30)
        assert entries[0]["description"] == "City Council Agenda"
        assert entries[0]["doc_url"] == "https://www.ci.larkspur.ca.us/ArchiveCenter/ViewFile/Item/1001"

    def test_parses_numeric_date_entries(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_NUMERIC_DATES)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        assert len(entries) == 2
        assert entries[0]["date"] == datetime(2026, 3, 30)
        assert entries[1]["date"] == datetime(2026, 1, 5)

    def test_parses_compact_date_entries(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_COMPACT_DATES)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        assert len(entries) == 1
        assert entries[0]["date"] == datetime(2026, 2, 17)
        assert entries[0]["description"] == "Approved Corte Madera Regular Town Council Minutes"

    def test_skips_unparseable_entries(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_MIXED)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        # "not a parseable entry" is skipped
        assert len(entries) == 2
        assert entries[0]["adid"] == "4001"
        assert entries[1]["adid"] == "4003"

    def test_empty_page_returns_no_entries(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_EMPTY)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        assert entries == []

    def test_strips_html_tags_from_entry_text(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML_TAGS_IN_LINK)
        with patch.object(client.session, "get", return_value=mock_resp):
            entries = client._fetch_archive("49")

        assert len(entries) == 1
        assert entries[0]["date"] == datetime(2026, 4, 5)
        assert entries[0]["description"] == "Council Agenda"

    def test_http_error_propagates(self, client):
        mock_resp = _mock_response("", status_code=500)
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError, match="500"):
                client._fetch_archive("49")

    def test_constructs_correct_url(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_EMPTY)
        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client._fetch_archive("49")
            mock_get.assert_called_once_with(
                "https://www.ci.larkspur.ca.us/Archive.aspx?AMID=49",
                timeout=15,
                allow_redirects=True,
            )


# ============================================================================
# CivicPlusClient.get_events — orchestration
# ============================================================================


class TestGetEvents:
    """Tests for event grouping and date filtering in get_events."""

    def test_groups_agendas_by_body_and_date(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            events = client.get_events(days_ahead=9000, days_past=9000)

        assert len(events) == 3
        # Sorted descending by date
        dates = [e["date"] for e in events]
        assert dates == sorted(dates, reverse=True)

    def test_filters_events_outside_date_range(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            # Very narrow window: only 1 day past, 0 future
            events = client.get_events(days_ahead=0, days_past=1)

        # All sample dates are in 2026, so with 1-day window from "now", none should match
        # (unless test runs exactly on those dates, which is extremely unlikely)
        assert len(events) == 0

    def test_body_name_derived_from_slug(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            events = client.get_events(days_ahead=9000, days_past=9000)

        for event in events:
            assert event["body_name"] == "City Council"
            assert event["body_slug"] == "city_council"

    def test_minutes_correlated_by_date(self, client_with_minutes):
        mock_agenda_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        mock_minutes_resp = _mock_response(SAMPLE_MINUTES_HTML)

        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            if "AMID=49" in url:
                return mock_agenda_resp
            elif "AMID=50" in url:
                return mock_minutes_resp
            return _mock_response(SAMPLE_ARCHIVE_EMPTY)

        with patch.object(client_with_minutes.session, "get", side_effect=side_effect):
            events = client_with_minutes.get_events(days_ahead=9000, days_past=9000)

        # March 30 appears in both agenda and minutes
        march_30 = [e for e in events if e["date"] == datetime(2026, 3, 30)]
        assert len(march_30) == 1
        assert march_30[0]["agenda_url"] == "https://www.ci.larkspur.ca.us/ArchiveCenter/ViewFile/Item/1001"
        assert march_30[0]["minutes_url"] == "https://www.ci.larkspur.ca.us/ArchiveCenter/ViewFile/Item/5001"

    def test_event_without_matching_minutes(self, client_with_minutes):
        mock_agenda_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        mock_minutes_resp = _mock_response(SAMPLE_ARCHIVE_EMPTY)

        def side_effect(url, **kwargs):
            if "AMID=49" in url:
                return mock_agenda_resp
            return mock_minutes_resp

        with patch.object(client_with_minutes.session, "get", side_effect=side_effect):
            events = client_with_minutes.get_events(days_ahead=9000, days_past=9000)

        for event in events:
            assert event["minutes_url"] is None

    def test_no_archives_returns_empty(self):
        c = CivicPlusClient(
            base_url="https://example.com",
            jurisdiction_id="city-test",
            archives={},
        )
        events = c.get_events()
        assert events == []

    def test_duplicate_agendas_same_date_keeps_first(self, client):
        # HTML with two entries for the same date
        html = """
        <html><body>
        <a href="Archive.aspx?ADID=100"><span>March 30, 2026, First Agenda</span></a>
        <a href="Archive.aspx?ADID=101"><span>March 30, 2026, Second Agenda</span></a>
        </body></html>
        """
        mock_resp = _mock_response(html)
        with patch.object(client.session, "get", return_value=mock_resp):
            events = client.get_events(days_ahead=9000, days_past=9000)

        # Only one event for March 30 — first one wins
        march_30_events = [e for e in events if e["date"] == datetime(2026, 3, 30)]
        assert len(march_30_events) == 1
        assert march_30_events[0]["adid"] == "100"
        assert march_30_events[0]["description"] == "First Agenda"


# ============================================================================
# CivicPlusClient.normalize_event
# ============================================================================


class TestNormalizeEvent:
    """Tests for raw event -> Meeting normalization."""

    def _make_event(self, **overrides):
        base = {
            "body_slug": "city_council",
            "body_name": "City Council",
            "date": datetime(2026, 3, 30),
            "description": "Regular Meeting Agenda",
            "agenda_url": "https://www.ci.larkspur.ca.us/ArchiveCenter/ViewFile/Item/1001",
            "minutes_url": None,
            "adid": "1001",
        }
        base.update(overrides)
        return base

    def test_meeting_id_format(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.id == "civicplus-city-larkspur-city_council-20260330"

    def test_title_includes_body_name(self, client):
        event = self._make_event(description="Regular Meeting Agenda")
        meeting = client.normalize_event(event)
        assert meeting.title == "City Council — Regular Meeting Agenda"

    def test_title_no_duplicate_body_name(self, client):
        event = self._make_event(description="City Council Special Meeting")
        meeting = client.normalize_event(event)
        # Body name already in description, so no " — " suffix
        assert meeting.title == "City Council"

    def test_title_empty_description(self, client):
        event = self._make_event(description="")
        meeting = client.normalize_event(event)
        assert meeting.title == "City Council"

    def test_meeting_type_from_body_slug(self, client):
        event = self._make_event(body_slug="planning_commission")
        meeting = client.normalize_event(event)
        assert meeting.meeting_type == "planning_commission"

    def test_meeting_type_fallback_when_no_slug(self, client):
        event = self._make_event(body_slug="")
        meeting = client.normalize_event(event)
        assert meeting.meeting_type == "city_council"  # Fallback from body_name

    def test_status_cancelled_from_description(self, client):
        event = self._make_event(description="CANCELLED - City Council Meeting")
        meeting = client.normalize_event(event)
        assert meeting.status == "cancelled"

    def test_status_completed_for_past_date(self, client):
        past_date = datetime(2020, 1, 1)
        event = self._make_event(date=past_date, description="Regular Meeting")
        meeting = client.normalize_event(event)
        assert meeting.status == "completed"

    def test_status_scheduled_for_future_date(self, client):
        future_date = datetime(2099, 12, 31)
        event = self._make_event(date=future_date, description="Regular Meeting")
        meeting = client.normalize_event(event)
        assert meeting.status == "scheduled"

    def test_agenda_and_minutes_urls_propagated(self, client):
        event = self._make_event(
            agenda_url="https://example.com/agenda.pdf",
            minutes_url="https://example.com/minutes.pdf",
        )
        meeting = client.normalize_event(event)
        assert meeting.agenda_url == "https://example.com/agenda.pdf"
        assert meeting.minutes_url == "https://example.com/minutes.pdf"

    def test_source_platform_is_civicplus(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.source_platform == "civicplus"

    def test_source_url_includes_amid(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.source_url == "https://www.ci.larkspur.ca.us/Archive.aspx?AMID=49"

    def test_jurisdiction_id_from_client(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.jurisdiction_id == "city-larkspur"

    def test_datetime_has_utc_timezone(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.meeting_datetime.tzinfo == timezone.utc

    def test_raw_data_preserved(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert meeting.raw_data == event

    def test_returns_meeting_instance(self, client):
        event = self._make_event()
        meeting = client.normalize_event(event)
        assert isinstance(meeting, Meeting)
        assert meeting.id == "civicplus-city-larkspur-city_council-20260330"


# ============================================================================
# CivicPlusClient.health
# ============================================================================


class TestHealth:
    """Tests for health check behavior."""

    def test_healthy_when_events_available(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            health = client.health()

        assert health.is_available is True
        assert health.source_id == "civicplus-city-larkspur"
        assert health.source_type == "civicplus"
        assert health.jurisdiction_id == "city-larkspur"
        assert health.errors == []
        assert health.check_duration_ms > 0
        assert health.metadata["event_count_60day"] == health.available_count

    def test_unhealthy_on_http_error(self, client):
        mock_resp = _mock_response("", status_code=500)
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Error")
        with patch.object(client.session, "get", return_value=mock_resp):
            health = client.health()

        assert health.is_available is False
        assert health.available_count == 0
        assert len(health.errors) == 1
        assert "500" in health.errors[0]

    def test_unhealthy_on_connection_error(self, client):
        with patch.object(client.session, "get", side_effect=ConnectionError("DNS failure")):
            health = client.health()

        assert health.is_available is False
        assert len(health.errors) == 1
        assert "DNS failure" in health.errors[0]

    def test_last_successful_set_on_success(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_EMPTY)
        with patch.object(client.session, "get", return_value=mock_resp):
            health = client.health()

        assert health.is_available is True
        assert health.last_successful is not None

    def test_last_successful_none_on_failure(self, client):
        with patch.object(client.session, "get", side_effect=Exception("fail")):
            health = client.health()

        assert health.last_successful is None


# ============================================================================
# CivicPlusClient.validate
# ============================================================================


class TestValidate:
    """Tests for preflight validation."""

    def test_valid_when_reachable(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.validate()

        assert result.is_valid is True
        assert result.config_valid is True
        assert result.api_reachable is True
        assert result.errors == []
        assert result.check_duration_ms > 0

    def test_invalid_when_empty_base_url(self):
        c = CivicPlusClient(
            base_url="",
            jurisdiction_id="city-test",
            archives={"council": "1"},
        )
        result = c.validate()
        assert result.is_valid is False
        assert "base_url is required" in result.errors

    def test_invalid_when_no_archives(self):
        c = CivicPlusClient(
            base_url="https://example.com",
            jurisdiction_id="city-test",
            archives={},
        )
        result = c.validate()
        assert result.is_valid is False
        assert "At least one archive AMID is required" in result.errors

    def test_invalid_when_http_error(self, client):
        mock_resp = _mock_response("", status_code=404)
        mock_resp.status_code = 404
        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.validate()

        assert result.is_valid is False
        assert result.api_reachable is False
        assert any("HTTP 404" in e for e in result.errors)

    def test_invalid_when_connection_fails(self, client):
        with patch.object(client.session, "get", side_effect=ConnectionError("refused")):
            result = client.validate()

        assert result.is_valid is False
        assert result.api_reachable is False
        assert len(result.errors) == 1
        assert "refused" in result.errors[0]

    def test_probes_first_archive_amid(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.validate()
            mock_get.assert_called_once_with(
                "https://www.ci.larkspur.ca.us/Archive.aspx?AMID=49",
                timeout=10,
                allow_redirects=True,
            )

    def test_skips_probe_when_config_errors(self):
        c = CivicPlusClient(
            base_url="",
            jurisdiction_id="city-test",
            archives={},
        )
        with patch.object(c.session, "get") as mock_get:
            result = c.validate()
            mock_get.assert_not_called()

        assert result.is_valid is False
        assert len(result.errors) == 2


# ============================================================================
# CivicPlusClient.get_meetings — integration of get_events + normalize
# ============================================================================


class TestGetMeetings:
    """Tests for the get_meetings convenience method from BaseExtractor."""

    def test_returns_normalized_meetings(self, client):
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(client.session, "get", return_value=mock_resp):
            meetings = client.get_meetings(days_ahead=9000, days_past=9000)

        assert len(meetings) == 3
        for m in meetings:
            assert isinstance(m, Meeting)
            assert m.source_platform == "civicplus"
            assert m.jurisdiction_id == "city-larkspur"


# ============================================================================
# CivicPlusSource — config-driven wrapper
# ============================================================================


class TestCivicPlusSource:
    """Tests for CivicPlusSource config wrapper."""

    def test_from_config(self, config):
        source = CivicPlusSource(config)
        assert source.source_id == "civicplus-city-larkspur"
        assert source.source_type == "civicplus"

    def test_minutes_archives_from_metadata(self, config):
        source = CivicPlusSource(config)
        assert source._client.minutes_archives == {"city_council": "50"}

    def test_delegates_health_to_client(self, config):
        source = CivicPlusSource(config)
        source._client.last_request_time = 999999999.0
        source._client.min_request_interval = 0.0

        mock_resp = _mock_response(SAMPLE_ARCHIVE_EMPTY)
        with patch.object(source._client.session, "get", return_value=mock_resp):
            health = source.health()

        assert health.is_available is True
        assert health.source_id == "civicplus-city-larkspur"

    def test_delegates_validate_to_client(self, config):
        source = CivicPlusSource(config)
        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(source._client.session, "get", return_value=mock_resp):
            result = source.validate()

        assert result.is_valid is True

    def test_get_events_delegates(self, config):
        source = CivicPlusSource(config)
        source._client.last_request_time = 999999999.0
        source._client.min_request_interval = 0.0

        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(source._client.session, "get", return_value=mock_resp):
            events = source.get_events(days_ahead=9000, days_past=9000)

        assert len(events) == 3

    def test_get_meetings_delegates(self, config):
        source = CivicPlusSource(config)
        source._client.last_request_time = 999999999.0
        source._client.min_request_interval = 0.0

        mock_resp = _mock_response(SAMPLE_ARCHIVE_HTML)
        with patch.object(source._client.session, "get", return_value=mock_resp):
            meetings = source.get_meetings(days_ahead=9000, days_past=9000)

        assert len(meetings) == 3
        assert all(isinstance(m, Meeting) for m in meetings)

    def test_config_without_minutes_archives(self):
        config = ExtractionConfig(
            source_id="civicplus-city-test",
            source_type="civicplus",
            jurisdiction_id="city-test",
            base_url="https://example.com",
            archives={"council": "1"},
            metadata={},
        )
        source = CivicPlusSource(config)
        assert source._client.minutes_archives == {}


# ============================================================================
# Throttle behavior
# ============================================================================


class TestThrottle:
    """Tests for rate limiting behavior."""

    def test_throttle_sleeps_when_too_fast(self):
        c = CivicPlusClient(
            base_url="https://example.com",
            jurisdiction_id="city-test",
        )
        c.min_request_interval = 1.0
        c.last_request_time = 999999999.0  # Far future, so elapsed is negative

        with patch("civicos_extraction.clients.civicplus.time.sleep") as mock_sleep:
            with patch("civicos_extraction.clients.civicplus.time.time", return_value=999999999.1):
                c._throttle()
                # 999999999.1 - 999999999.0 = 0.1, which is < 1.0, so sleep(0.9)
                mock_sleep.assert_called_once()
                sleep_duration = mock_sleep.call_args[0][0]
                assert 0.8 < sleep_duration < 1.0

    def test_throttle_no_sleep_when_enough_time_passed(self):
        c = CivicPlusClient(
            base_url="https://example.com",
            jurisdiction_id="city-test",
        )
        c.min_request_interval = 0.5
        c.last_request_time = 0.0  # Long ago

        with patch("civicos_extraction.clients.civicplus.time.sleep") as mock_sleep:
            with patch("civicos_extraction.clients.civicplus.time.time", return_value=999999999.0):
                c._throttle()
                mock_sleep.assert_not_called()

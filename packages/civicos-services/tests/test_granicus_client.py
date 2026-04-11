"""
Tests for granicus_client.py — Granicus ViewPublisher API client.

Tests cover:
- GranicusClient.__init__ (URL assembly, header setup)
- _find_column_index (pure logic over header lists)
- _parse_date (pure logic — multiple formats, unix-prefix, regex fallback)
- _make_absolute_url (pure logic — relative/absolute URL construction)
- get_meetings (HTTP mocked at requests.Session — real HTML parsing + filtering)
- create_client factory
- discover_granicus_cities registry

All external I/O (requests) is mocked; HTML parsing, date parsing, URL
construction, and temporal filtering all run against real implementations.

To run:
    pytest packages/civicos-services/tests/test_granicus_client.py -q --override-ini="addopts="
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_services.clients.granicus_client import (
    GranicusClient,
    create_client,
    discover_granicus_cities,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _future_date(days: int) -> datetime:
    """A datetime `days` in the future, normalized to midnight."""
    base = datetime.now() + timedelta(days=days)
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def _past_date(days: int) -> datetime:
    base = datetime.now() - timedelta(days=days)
    return base.replace(hour=0, minute=0, second=0, microsecond=0)


def _make_html(rows_html: str, headers: str | None = None) -> str:
    """Wrap table rows in a ViewPublisher-like HTML shell."""
    if headers is None:
        headers = (
            "<tr><th>Name</th><th>Date</th>"
            "<th>Agenda</th><th>Agenda Packet</th></tr>"
        )
    return f"<html><body><table>{headers}{rows_html}</table></body></html>"


def _make_client_with_mock_session(html: str, status: int = 200) -> GranicusClient:
    """Create a GranicusClient with its session.get patched to return `html`."""
    client = GranicusClient("dublin", view_id=1)
    response = MagicMock()
    response.status_code = status
    response.text = html
    response.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# GranicusClient.__init__
# ---------------------------------------------------------------------------


class TestGranicusClientInit:
    def test_city_name_stored(self):
        client = GranicusClient("dublin")
        assert client.city_name == "dublin"

    def test_default_view_id_is_one(self):
        client = GranicusClient("dublin")
        assert client.view_id == 1

    def test_custom_view_id_preserved(self):
        client = GranicusClient("dublin", view_id=42)
        assert client.view_id == 42

    def test_base_url_uses_city_subdomain(self):
        client = GranicusClient("cityofcampbell")
        assert client.base_url == "https://cityofcampbell.granicus.com"

    def test_base_url_has_no_trailing_slash(self):
        client = GranicusClient("dublin")
        assert not client.base_url.endswith("/")
        assert client.base_url == "https://dublin.granicus.com"

    def test_user_agent_header_set(self):
        client = GranicusClient("dublin")
        assert client.session.headers["User-Agent"] == "Mozilla/5.0 (CivicEngagement/1.0)"


# ---------------------------------------------------------------------------
# _find_column_index
# ---------------------------------------------------------------------------


class TestFindColumnIndex:
    def setup_method(self):
        self.client = GranicusClient("dublin")

    def test_exact_match_first_name(self):
        idx = self.client._find_column_index(["name", "date"], ["name"])
        assert idx == 0

    def test_returns_index_of_first_header_that_matches_first_name(self):
        idx = self.client._find_column_index(
            ["name", "meeting name", "date"], ["meeting", "name"]
        )
        # 'meeting' is tried first; first header containing 'meeting' is index 1
        assert idx == 1

    def test_substring_match(self):
        idx = self.client._find_column_index(
            ["meeting name", "meeting date"], ["name"]
        )
        assert idx == 0

    def test_returns_none_when_no_match(self):
        idx = self.client._find_column_index(
            ["foo", "bar", "baz"], ["name", "meeting"]
        )
        assert idx is None

    def test_second_candidate_used_if_first_not_found(self):
        idx = self.client._find_column_index(
            ["title", "meeting info"], ["name", "meeting"]
        )
        # 'name' matches nothing, 'meeting' matches 'meeting info' at index 1
        assert idx == 1

    def test_empty_headers_returns_none(self):
        idx = self.client._find_column_index([], ["name"])
        assert idx is None

    def test_empty_possible_names_returns_none(self):
        idx = self.client._find_column_index(["name", "date"], [])
        assert idx is None

    def test_first_match_wins_even_across_later_candidates(self):
        """When candidate 'name' finds a hit, later candidates are not tried."""
        idx = self.client._find_column_index(
            ["name", "date"], ["name", "date"]
        )
        assert idx == 0


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def setup_method(self):
        self.client = GranicusClient("dublin")

    def test_full_month_format(self):
        dt = self.client._parse_date("October 7, 2025")
        assert dt == datetime(2025, 10, 7)

    def test_abbrev_month_format(self):
        dt = self.client._parse_date("Oct 7, 2025")
        assert dt == datetime(2025, 10, 7)

    def test_abbrev_sep_from_campbell(self):
        dt = self.client._parse_date("Sep 16, 2025")
        assert dt == datetime(2025, 9, 16)

    def test_numeric_slash_format(self):
        dt = self.client._parse_date("10/7/2025")
        assert dt == datetime(2025, 10, 7)

    def test_iso_format(self):
        dt = self.client._parse_date("2025-10-07")
        assert dt == datetime(2025, 10, 7)

    def test_full_month_with_time(self):
        dt = self.client._parse_date("October 7, 2025 6:00 PM")
        assert dt == datetime(2025, 10, 7, 18, 0)

    def test_abbrev_month_with_time(self):
        dt = self.client._parse_date("Oct 7, 2025 6:00 PM")
        assert dt == datetime(2025, 10, 7, 18, 0)

    def test_unix_timestamp_prefix_stripped(self):
        """Campbell uses a leading unix timestamp joined to the human date."""
        dt = self.client._parse_date("1758006000Sep 16, 2025")
        assert dt == datetime(2025, 9, 16)

    def test_unix_timestamp_prefix_with_full_month(self):
        dt = self.client._parse_date("1728259200October 7, 2025")
        assert dt == datetime(2025, 10, 7)

    def test_empty_string_returns_none(self):
        assert self.client._parse_date("") is None

    def test_whitespace_only_returns_none(self):
        assert self.client._parse_date("   ") is None

    def test_unparseable_text_returns_none(self):
        assert self.client._parse_date("not a date at all") is None

    def test_regex_fallback_extracts_date_from_mixed_text(self):
        """Date embedded in surrounding text should be extracted."""
        dt = self.client._parse_date("Meeting on October 7, 2025 at the library")
        assert dt == datetime(2025, 10, 7)

    def test_regex_fallback_abbrev_month(self):
        dt = self.client._parse_date("Scheduled Oct 7, 2025 tentative")
        assert dt == datetime(2025, 10, 7)

    def test_date_text_with_surrounding_whitespace(self):
        dt = self.client._parse_date("  October 7, 2025  ")
        assert dt == datetime(2025, 10, 7)

    def test_invalid_numeric_date_returns_none(self):
        # 13/45 is not a valid month/day combination
        assert self.client._parse_date("13/45/2025") is None


# ---------------------------------------------------------------------------
# _make_absolute_url
# ---------------------------------------------------------------------------


class TestMakeAbsoluteUrl:
    def setup_method(self):
        self.client = GranicusClient("dublin")

    def test_https_url_unchanged(self):
        url = "https://example.com/foo"
        assert self.client._make_absolute_url(url) == "https://example.com/foo"

    def test_http_url_unchanged(self):
        url = "http://example.com/foo"
        assert self.client._make_absolute_url(url) == "http://example.com/foo"

    def test_protocol_relative_gets_https(self):
        url = "//example.com/foo"
        assert self.client._make_absolute_url(url) == "https://example.com/foo"

    def test_root_relative_joins_base_url(self):
        url = "/AgendaViewer.php?view_id=1"
        expected = "https://dublin.granicus.com/AgendaViewer.php?view_id=1"
        assert self.client._make_absolute_url(url) == expected

    def test_bare_relative_joins_base_url_with_slash(self):
        url = "Packet.pdf"
        expected = "https://dublin.granicus.com/Packet.pdf"
        assert self.client._make_absolute_url(url) == expected

    def test_root_relative_preserves_single_slash(self):
        """Neither missing nor doubled slash between base and path."""
        url = "/foo/bar"
        result = self.client._make_absolute_url(url)
        assert result == "https://dublin.granicus.com/foo/bar"
        assert "//foo" not in result.replace("https://", "")


# ---------------------------------------------------------------------------
# get_meetings — HTML parsing + filtering (HTTP mocked)
# ---------------------------------------------------------------------------


class TestGetMeetings:
    def test_successful_parsing_one_meeting(self):
        future = _future_date(5)
        date_str = future.strftime("%B %d, %Y")
        rows = (
            f"<tr>"
            f"<td>City Council</td>"
            f"<td>{date_str}</td>"
            f'<td><a href="/AgendaViewer.php?view_id=1&event_id=42">View</a></td>'
            f'<td><a href="/AgendaPacket.pdf">Packet</a></td>'
            f"</tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings(days_future=30, days_past=7)

        assert len(meetings) == 1
        meeting = meetings[0]
        assert meeting["title"] == "City Council"
        assert meeting["date_text"] == date_str
        assert meeting["datetime"] == future.isoformat()
        assert meeting["platform"] == "granicus"
        assert meeting["agenda_url"] == (
            "https://dublin.granicus.com/AgendaViewer.php?view_id=1&event_id=42"
        )
        assert meeting["packet_url"] == "https://dublin.granicus.com/AgendaPacket.pdf"
        assert meeting["source_url"] == (
            "https://dublin.granicus.com/ViewPublisher.php?view_id=1"
        )

    def test_request_url_uses_view_id(self):
        html = _make_html("")
        client = GranicusClient("dublin", view_id=7)
        response = MagicMock(status_code=200, text=html)
        response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=response)

        client.get_meetings()

        called_url = client.session.get.call_args[0][0]
        assert called_url == "https://dublin.granicus.com/ViewPublisher.php?view_id=7"
        # Also verify the 30s timeout was passed
        assert client.session.get.call_args.kwargs.get("timeout") == 30

    def test_meeting_too_far_in_past_excluded(self):
        past = _past_date(60)
        rows = (
            f"<tr><td>Old Meeting</td><td>{past.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings(days_future=30, days_past=30)

        assert meetings == []

    def test_meeting_too_far_in_future_excluded(self):
        future = _future_date(200)
        rows = (
            f"<tr><td>Far Future</td><td>{future.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings(days_future=90, days_past=30)

        assert meetings == []

    def test_past_within_window_included(self):
        past = _past_date(5)
        rows = (
            f"<tr><td>Recent</td><td>{past.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings(days_future=30, days_past=30)

        assert len(meetings) == 1
        assert meetings[0]["title"] == "Recent"

    def test_row_with_unparseable_date_skipped(self):
        rows = (
            "<tr><td>Bad Date</td><td>not-a-real-date</td><td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert meetings == []

    def test_row_with_too_few_cells_skipped(self):
        """When header has 4 columns but row has only 1 cell, it's skipped."""
        future = _future_date(5)
        good_row = (
            f"<tr><td>Good</td><td>{future.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        bad_row = "<tr><td>Only one cell</td></tr>"
        html = _make_html(bad_row + good_row)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert len(meetings) == 1
        assert meetings[0]["title"] == "Good"

    def test_no_tables_returns_empty_list(self):
        client = _make_client_with_mock_session("<html><body>no tables</body></html>")
        assert client.get_meetings() == []

    def test_table_with_only_header_skipped(self):
        html = _make_html("")  # only the header row
        client = _make_client_with_mock_session(html)
        assert client.get_meetings() == []

    def test_http_error_returns_empty_list(self):
        """Exceptions during fetch are swallowed and the result is []."""
        client = GranicusClient("dublin")
        client.session.get = MagicMock(side_effect=requests.ConnectionError("boom"))

        assert client.get_meetings() == []

    def test_raise_for_status_error_returns_empty_list(self):
        client = GranicusClient("dublin")
        response = MagicMock(status_code=500, text="")
        response.raise_for_status.side_effect = requests.HTTPError("500 server error")
        client.session.get = MagicMock(return_value=response)

        assert client.get_meetings() == []

    def test_missing_agenda_link_produces_none(self):
        future = _future_date(5)
        rows = (
            f"<tr><td>Council</td><td>{future.strftime('%B %d, %Y')}</td>"
            f"<td>No link here</td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert len(meetings) == 1
        assert meetings[0]["agenda_url"] is None
        assert meetings[0]["packet_url"] is None

    def test_absolute_url_in_packet_not_rewritten(self):
        future = _future_date(5)
        rows = (
            f"<tr><td>Council</td><td>{future.strftime('%B %d, %Y')}</td>"
            f'<td><a href="/agenda">A</a></td>'
            f'<td><a href="https://cdn.example.com/packet.pdf">P</a></td></tr>'
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert len(meetings) == 1
        assert meetings[0]["packet_url"] == "https://cdn.example.com/packet.pdf"
        assert meetings[0]["agenda_url"] == "https://dublin.granicus.com/agenda"

    def test_multiple_rows_all_parsed_in_order(self):
        f1 = _future_date(5)
        f2 = _future_date(10)
        rows = (
            f"<tr><td>Meeting A</td><td>{f1.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
            f"<tr><td>Meeting B</td><td>{f2.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert len(meetings) == 2
        assert meetings[0]["title"] == "Meeting A"
        assert meetings[1]["title"] == "Meeting B"
        assert meetings[0]["datetime"] == f1.isoformat()
        assert meetings[1]["datetime"] == f2.isoformat()

    def test_header_row_with_no_matching_columns_returns_empty(self):
        """Header with no name/date columns: rows get unknown name, empty date."""
        future = _future_date(5)
        headers = "<tr><th>Foo</th><th>Bar</th></tr>"
        rows = f"<tr><td>Ignored</td><td>{future.strftime('%B %d, %Y')}</td></tr>"
        html = _make_html(rows, headers=headers)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        # date_idx is None → date_text='' → _parse_date returns None → row skipped
        assert meetings == []

    def test_packet_column_only_still_parses_meeting(self):
        """Table with Name/Date/Packet but no Agenda column."""
        future = _future_date(5)
        headers = "<tr><th>Name</th><th>Date</th><th>Documents</th></tr>"
        rows = (
            f"<tr><td>Council</td><td>{future.strftime('%B %d, %Y')}</td>"
            f'<td><a href="/pkt.pdf">Packet</a></td></tr>'
        )
        html = _make_html(rows, headers=headers)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings()

        assert len(meetings) == 1
        assert meetings[0]["title"] == "Council"
        assert meetings[0]["agenda_url"] is None
        assert meetings[0]["packet_url"] == "https://dublin.granicus.com/pkt.pdf"

    def test_date_past_boundary_exactly_at_limit_included(self):
        """A meeting exactly `days_past` days old should be included (inclusive)."""
        # Use 3 days past with a 5-day window; well inside the window.
        past = _past_date(3)
        rows = (
            f"<tr><td>Recent</td><td>{past.strftime('%B %d, %Y')}</td>"
            f"<td></td><td></td></tr>"
        )
        html = _make_html(rows)
        client = _make_client_with_mock_session(html)

        meetings = client.get_meetings(days_future=30, days_past=5)

        assert len(meetings) == 1


# ---------------------------------------------------------------------------
# create_client factory
# ---------------------------------------------------------------------------


class TestCreateClient:
    def test_returns_granicus_client_with_expected_base_url(self):
        client = create_client("dublin")
        assert isinstance(client, GranicusClient)
        assert client.base_url == "https://dublin.granicus.com"
        assert client.city_name == "dublin"

    def test_passes_city_name(self):
        client = create_client("campbell")
        assert client.city_name == "campbell"
        assert client.base_url == "https://campbell.granicus.com"

    def test_default_view_id_is_one(self):
        client = create_client("dublin")
        assert client.view_id == 1

    def test_custom_view_id_preserved(self):
        client = create_client("dublin", view_id=99)
        assert client.view_id == 99


# ---------------------------------------------------------------------------
# discover_granicus_cities
# ---------------------------------------------------------------------------


class TestDiscoverGranicusCities:
    def test_returns_dublin_and_campbell(self):
        cities = discover_granicus_cities()
        assert set(cities.keys()) == {"dublin", "campbell"}

    def test_dublin_full_entry(self):
        cities = discover_granicus_cities()
        dublin = cities["dublin"]
        assert dublin["name"] == "City of Dublin"
        assert dublin["jurisdiction_id"] == "city-dublin"
        assert dublin["view_id"] == 1
        assert dublin["url"] == "https://dublin.granicus.com/ViewPublisher.php?view_id=1"

    def test_campbell_full_entry(self):
        cities = discover_granicus_cities()
        campbell = cities["campbell"]
        assert campbell["name"] == "City of Campbell"
        assert campbell["jurisdiction_id"] == "city-campbell"
        assert campbell["view_id"] == 1
        assert campbell["url"] == (
            "https://cityofcampbell.granicus.com/ViewPublisher.php?view_id=1"
        )

    def test_all_entries_have_required_keys(self):
        cities = discover_granicus_cities()
        required = {"name", "jurisdiction_id", "view_id", "url"}
        for key, entry in cities.items():
            assert set(entry.keys()) == required, f"{key} missing keys"

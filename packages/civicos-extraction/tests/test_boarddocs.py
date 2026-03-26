"""
Tests for BoardDocsClient — school board meeting extraction.

Unit tests mock the HTTP API. Integration tests hit live BoardDocs endpoints (no auth needed).
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import date, datetime

from civicos_extraction.clients.boarddocs import (
    BoardDocsClient,
    BoardDocsMeeting,
    AgendaItem,
    boarddocs_meeting_to_storage,
    _parse_meeting,
    _parse_agenda_html,
    _infer_meeting_type,
)


# ==================== Fixtures ====================


SAMPLE_MEETINGS_JSON = [
    {
        "unique": "DMYPDZ643003",
        "name": "RVSD BOARD OF TRUSTEES REGULAR MEETING",
        "current": "",
        "numberdate": "20251112",
        "unid": "BF1BDD46B5A4726985258D3400643003",
    },
    {
        "unique": "ABCDEF123456",
        "name": "SPECIAL BOARD MEETING",
        "current": "1",
        "numberdate": "20251015",
        "unid": "AA1BDD46B5A4726985258D3400123456",
    },
    {},  # Sentinel at end of array
]

SAMPLE_AGENDA_HTML = """
<div id="print-top-meeting-info">
  <div class="print-meeting-date">Wednesday, November 12, 2025</div>
  <div class="print-meeting-name">RVSD BOARD OF TRUSTEES REGULAR MEETING</div>
</div>

<div style="font-weight: bold; font-size: 16px; border-bottom: 2px solid #000;">
  A. CALL TO ORDER
</div>

<div class="container item agendaorder">
  <dl><dt>Subject</dt><dd>1. Meeting Called to Order</dd></dl>
  <dl><dt>Type</dt><dd>Procedural</dd></dl>
</div>

<div style="font-weight: bold; font-size: 16px; border-bottom: 2px solid #000;">
  B. PUBLIC COMMENT
</div>

<div class="container item agendaorder">
  <dl><dt>Subject</dt><dd>2. Public Comment on Non-Agenda Items</dd></dl>
  <dl><dt>Type</dt><dd>Information</dd></dl>
  <div class="itembody"><p>Members of the public may address the Board.</p></div>
</div>

<div style="font-weight: bold; font-size: 16px; border-bottom: 2px solid #000;">
  C. ACTION ITEMS
</div>

<div class="container item agendaorder">
  <dl><dt>Subject</dt><dd>3. Approve Budget Amendment</dd></dl>
  <dl><dt>Type</dt><dd>Action</dd></dl>
  <div class="itembody"><p>Staff recommends approval of the budget amendment.</p></div>
  <div class="print-files">
    <div class="public-file print-file" unique="DNCUY37E4547">
      <a href="/ca/rova/Board.nsf/files/DNCUY37E4547/$file/Budget%20Amendment.pdf">
        Budget Amendment.pdf (109 KB)
      </a>
    </div>
    <div class="public-file print-file" unique="XYZABC789012">
      <a href="/ca/rova/Board.nsf/files/XYZABC789012/$file/Supporting%20Docs.pdf">
        Supporting Docs.pdf (245 KB)
      </a>
    </div>
  </div>
</div>
"""

SAMPLE_COMMITTEE_HTML = """
<html>
<body>
<div class="dropdown-menu">
  <a class="dropdown-item committee-trigger" committeeid="AB9A2R259AF0">Main Governing Board</a>
  <a class="dropdown-item committee-trigger" committeeid="CD3E4F567890">Budget Committee</a>
</div>
</body>
</html>
"""


# ==================== Unit Tests: Parsing ====================


class TestParseMeeting:
    """Tests for _parse_meeting()."""

    def test_parse_valid_meeting(self):
        raw = SAMPLE_MEETINGS_JSON[0]
        meeting = _parse_meeting(raw)
        assert meeting is not None
        assert meeting.unique == "DMYPDZ643003"
        assert meeting.title == "RVSD BOARD OF TRUSTEES REGULAR MEETING"
        assert meeting.meeting_date == date(2025, 11, 12)
        assert meeting.unid == "BF1BDD46B5A4726985258D3400643003"
        assert meeting.is_current is False

    def test_parse_current_meeting(self):
        raw = SAMPLE_MEETINGS_JSON[1]
        meeting = _parse_meeting(raw)
        assert meeting is not None
        assert meeting.is_current is True
        assert meeting.title == "SPECIAL BOARD MEETING"
        assert meeting.meeting_date == date(2025, 10, 15)

    def test_parse_sentinel_returns_none(self):
        meeting = _parse_meeting({})
        assert meeting is None

    def test_parse_missing_unique_returns_none(self):
        meeting = _parse_meeting({"name": "Test", "numberdate": "20251112"})
        assert meeting is None

    def test_parse_missing_date_returns_none(self):
        meeting = _parse_meeting({"unique": "ABC", "name": "Test"})
        assert meeting is None

    def test_parse_invalid_date_returns_none(self):
        meeting = _parse_meeting({"unique": "ABC", "name": "Test", "numberdate": "not-a-date"})
        assert meeting is None

    def test_title_whitespace_stripped(self):
        raw = {"unique": "X", "name": "  Board Meeting  ", "numberdate": "20250101", "unid": "U", "current": ""}
        meeting = _parse_meeting(raw)
        assert meeting is not None
        assert meeting.title == "Board Meeting"


class TestInferMeetingType:
    """Tests for _infer_meeting_type()."""

    def test_regular(self):
        assert _infer_meeting_type("RVSD BOARD OF TRUSTEES REGULAR MEETING") == "regular"

    def test_special(self):
        assert _infer_meeting_type("SPECIAL BOARD MEETING") == "special"

    def test_study_session(self):
        assert _infer_meeting_type("Board Study Session") == "study_session"

    def test_workshop(self):
        assert _infer_meeting_type("Budget Workshop") == "study_session"

    def test_closed_session(self):
        assert _infer_meeting_type("Closed Session - Personnel") == "closed_session"

    def test_committee(self):
        assert _infer_meeting_type("Finance Committee Meeting") == "committee"

    def test_retreat(self):
        assert _infer_meeting_type("Annual Board Retreat") == "retreat"


class TestParseAgendaHtml:
    """Tests for _parse_agenda_html()."""

    def test_parse_agenda_items(self):
        items = _parse_agenda_html(SAMPLE_AGENDA_HTML, "https://go.boarddocs.com/ca/rova/Board.nsf")
        assert len(items) == 3

    def test_first_item_subject(self):
        items = _parse_agenda_html(SAMPLE_AGENDA_HTML, "https://go.boarddocs.com/ca/rova/Board.nsf")
        assert items[0].subject == "1. Meeting Called to Order"
        assert items[0].item_type == "Procedural"
        assert items[0].category == "A. CALL TO ORDER"

    def test_item_with_body(self):
        items = _parse_agenda_html(SAMPLE_AGENDA_HTML, "https://go.boarddocs.com/ca/rova/Board.nsf")
        assert items[1].body_text is not None
        assert "Members of the public" in items[1].body_text
        assert items[1].category == "B. PUBLIC COMMENT"

    def test_item_with_attachments(self):
        items = _parse_agenda_html(SAMPLE_AGENDA_HTML, "https://go.boarddocs.com/ca/rova/Board.nsf")
        action_item = items[2]
        assert action_item.subject == "3. Approve Budget Amendment"
        assert action_item.item_type == "Action"
        assert action_item.attachments is not None
        assert len(action_item.attachments) == 2
        assert action_item.attachments[0]["name"] == "Budget Amendment.pdf"
        assert action_item.attachments[0]["size"] == "109 KB"
        assert "go.boarddocs.com" in action_item.attachments[0]["url"]

    def test_empty_html(self):
        items = _parse_agenda_html("", "https://example.com")
        assert items == []

    def test_categories_tracked(self):
        items = _parse_agenda_html(SAMPLE_AGENDA_HTML, "https://go.boarddocs.com/ca/rova/Board.nsf")
        categories = [i.category for i in items]
        assert categories == ["A. CALL TO ORDER", "B. PUBLIC COMMENT", "C. ACTION ITEMS"]


class TestBoardDocsMeetingToStorage:
    """Tests for boarddocs_meeting_to_storage()."""

    def test_basic_mapping(self):
        meeting = BoardDocsMeeting(
            unique="DMYPDZ643003",
            title="Regular Board Meeting",
            meeting_date=date(2025, 11, 12),
            unid="BF1BDD46B5A4726985258D3400643003",
        )
        result = boarddocs_meeting_to_storage(meeting, "school-ross-valley", "ca/rova")

        assert result["id"] == "boarddocs-DMYPDZ643003"
        assert result["title"] == "Regular Board Meeting"
        assert result["jurisdiction_id"] == "school-ross-valley"
        assert result["meeting_type"] == "regular"
        assert result["status"] == "confirmed"
        assert result["source_platform"] == "boarddocs"
        assert "ca/rova" in result["source_url"]
        assert result["raw_data"]["boarddocs_unique"] == "DMYPDZ643003"
        assert result["raw_data"]["boarddocs_unid"] == "BF1BDD46B5A4726985258D3400643003"

    def test_datetime_is_isoformat(self):
        meeting = BoardDocsMeeting(
            unique="X", title="Test", meeting_date=date(2025, 3, 15), unid="U",
        )
        result = boarddocs_meeting_to_storage(meeting, "test-jid", "ca/test")
        assert result["meeting_datetime"] == "2025-03-15T00:00:00"


class TestBoardDocsMeetingToMeeting:
    """Tests for BoardDocsMeeting.to_meeting()."""

    def test_conversion(self):
        bm = BoardDocsMeeting(
            unique="ABC123",
            title="Special Board Meeting",
            meeting_date=date(2025, 6, 1),
            unid="UNID123",
        )
        meeting = bm.to_meeting("school-test", "ca/test")
        assert meeting.id == "boarddocs-ABC123"
        assert meeting.meeting_type == "special"
        assert meeting.source_platform == "boarddocs"
        assert meeting.jurisdiction_id == "school-test"
        assert "ca/test" in meeting.source_url


# ==================== Unit Tests: Client (mocked HTTP) ====================


class TestBoardDocsClientMocked:
    """Tests for BoardDocsClient with mocked HTTP calls."""

    def _make_client(self, committee_id="TEST_COMMITTEE"):
        return BoardDocsClient(
            app_path="ca/test",
            jurisdiction_id="school-test",
            committee_id=committee_id,
            request_delay=0,
        )

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_meetings_raw(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            raw = client.get_meetings_raw()

        assert len(raw) == 2  # Sentinel filtered out
        assert raw[0]["unique"] == "DMYPDZ643003"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_meetings_parsed(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            meetings = client.get_meetings()

        assert len(meetings) == 2
        assert isinstance(meetings[0], BoardDocsMeeting)
        assert meetings[0].title == "RVSD BOARD OF TRUSTEES REGULAR MEETING"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_meetings_with_since_filter(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            meetings = client.get_meetings(since=date(2025, 11, 1))

        assert len(meetings) == 1
        assert meetings[0].meeting_date == date(2025, 11, 12)

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_agenda(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_AGENDA_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            items = client.get_agenda("DMYPDZ643003")

        assert items is not None
        assert len(items) == 3

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_discover_committee_ids(self, mock_sleep):
        client = self._make_client(committee_id="")
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_COMMITTEE_HTML
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "get", return_value=mock_resp):
            committees = client.discover_committee_ids()

        assert len(committees) == 2
        assert committees["Main Governing Board"] == "AB9A2R259AF0"
        assert committees["Budget Committee"] == "CD3E4F567890"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_auto_discover_committee_on_get_meetings(self, mock_sleep):
        client = self._make_client(committee_id="")

        # First call: GET for committee discovery
        mock_get_resp = MagicMock()
        mock_get_resp.text = SAMPLE_COMMITTEE_HTML
        mock_get_resp.raise_for_status = MagicMock()

        # Second call: POST for meetings
        mock_post_resp = MagicMock()
        mock_post_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_post_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "get", return_value=mock_get_resp), \
             patch.object(client._session, "post", return_value=mock_post_resp):
            raw = client.get_meetings_raw()

        assert len(raw) == 2
        assert client.committee_id == "AB9A2R259AF0"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_meetings_raw_http_error(self, mock_sleep):
        client = self._make_client()

        import requests
        with patch.object(
            client._session, "post",
            side_effect=requests.RequestException("Connection error"),
        ):
            raw = client.get_meetings_raw()

        assert raw == []

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_get_meetings_raw_invalid_json(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = ValueError("No JSON")

        with patch.object(client._session, "post", return_value=mock_resp):
            raw = client.get_meetings_raw()

        assert raw == []

    def test_source_id(self):
        client = self._make_client()
        assert client.source_id == "boarddocs-ca-test"

    def test_platform_name(self):
        client = self._make_client()
        assert client.platform_name == "boarddocs"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_normalize_event(self, mock_sleep):
        client = self._make_client()
        event = {
            "unique": "ABC",
            "title": "Special Board Meeting",
            "meeting_date": "2025-06-01",
            "unid": "UNID",
            "is_current": False,
        }
        meeting = client.normalize_event(event)
        assert meeting.id == "boarddocs-ABC"
        assert meeting.meeting_type == "special"
        assert meeting.source_platform == "boarddocs"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_health_success(self, mock_sleep):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            status = client.health()

        assert status.is_available is True
        assert status.available_count == 2
        assert status.source_type == "boarddocs"

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_health_failure(self, mock_sleep):
        client = self._make_client()
        import requests
        with patch.object(
            client._session, "post",
            side_effect=requests.RequestException("Timeout"),
        ):
            status = client.health()

        assert status.is_available is False
        assert status.available_count == 0


# ==================== Unit Tests: Storage extraction ====================


class TestExtractBoardDocsMeetingsToStorage:
    """Tests for extract_boarddocs_meetings_to_storage()."""

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_extract_and_store(self, mock_sleep):
        from civicos_extraction.clients.boarddocs import extract_boarddocs_meetings_to_storage

        client = BoardDocsClient("ca/test", "school-test", committee_id="C", request_delay=0)
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_MEETINGS_JSON
        mock_resp.raise_for_status = MagicMock()

        mock_storage = MagicMock()
        mock_storage.store_meetings.return_value = 2

        with patch.object(client._session, "post", return_value=mock_resp):
            count = extract_boarddocs_meetings_to_storage(client, mock_storage, "school-test")

        assert count == 2
        mock_storage.store_meetings.assert_called_once()
        args = mock_storage.store_meetings.call_args
        assert args[0][0] == "school-test"
        assert len(args[0][1]) == 2

    @patch("civicos_extraction.clients.boarddocs.time.sleep")
    def test_extract_empty(self, mock_sleep):
        from civicos_extraction.clients.boarddocs import extract_boarddocs_meetings_to_storage

        client = BoardDocsClient("ca/test", "school-test", committee_id="C", request_delay=0)
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{}]  # Only sentinel
        mock_resp.raise_for_status = MagicMock()

        mock_storage = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            count = extract_boarddocs_meetings_to_storage(client, mock_storage, "school-test")

        assert count == 0
        mock_storage.store_meetings.assert_not_called()


# ==================== Integration Tests (live API) ====================


@pytest.mark.integration
class TestBoardDocsIntegration:
    """
    Live API tests against BoardDocs.

    These hit real endpoints (no auth needed). Skip with: pytest -m "not integration"
    """

    def test_ross_valley_meetings(self):
        """Fetch meetings from Ross Valley SD — should have ~300+ meetings."""
        client = BoardDocsClient(
            app_path="ca/rova",
            jurisdiction_id="school-ross-valley",
            committee_id="AB9A2R259AF0",
        )
        meetings = client.get_meetings()
        assert len(meetings) > 50, f"Expected 50+ meetings, got {len(meetings)}"

        # Check first meeting has required fields
        m = meetings[0]
        assert m.unique
        assert m.title
        assert m.meeting_date
        assert m.unid

    def test_ross_valley_agenda(self):
        """Fetch agenda for most recent Ross Valley SD meeting."""
        client = BoardDocsClient(
            app_path="ca/rova",
            jurisdiction_id="school-ross-valley",
            committee_id="AB9A2R259AF0",
        )
        meetings = client.get_meetings()
        assert len(meetings) > 0

        # Get agenda for the most recent meeting
        items = client.get_agenda(meetings[0].unique)
        assert items is not None
        assert len(items) > 0, "Expected at least one agenda item"
        assert items[0].subject, "First item should have a subject"

    def test_mcoe_meetings(self):
        """Fetch meetings from Marin County Office of Education."""
        client = BoardDocsClient(
            app_path="ca/marinschools",
            jurisdiction_id="school-marin-county-oe",
            committee_id="A4EP6J588C05",
        )
        meetings = client.get_meetings()
        assert len(meetings) > 10, f"Expected 10+ meetings, got {len(meetings)}"

    def test_health_check(self):
        """Health check against live Ross Valley SD endpoint."""
        client = BoardDocsClient(
            app_path="ca/rova",
            jurisdiction_id="school-ross-valley",
            committee_id="AB9A2R259AF0",
        )
        status = client.health()
        assert status.is_available is True
        assert status.available_count > 50

    def test_validate(self):
        """Validate config against live Ross Valley SD endpoint."""
        client = BoardDocsClient(
            app_path="ca/rova",
            jurisdiction_id="school-ross-valley",
            committee_id="AB9A2R259AF0",
        )
        result = client.validate()
        assert result.is_valid is True
        assert result.api_reachable is True

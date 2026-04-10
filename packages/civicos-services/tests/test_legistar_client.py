"""
Tests for legistar_client.py — Legistar API client for civic meeting data.

Tests pure-logic methods (text cleaning, event normalization, relevance filtering,
matter normalization, testimony normalization) and request-handling logic (retry,
throttle, exponential backoff). HTTP calls are mocked; all data transformation
and control flow runs for real.

To run:
    pytest packages/civicos-services/tests/test_legistar_client.py -q --override-ini="addopts="
"""

import time as _time
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.clients.legistar_client import (
    LegistarClient,
    KNOWN_LEGISTAR_CLIENTS,
    create_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(client_name: str = "oakland") -> LegistarClient:
    """Create a client with rate-limiting interval zeroed for test speed."""
    client = LegistarClient(client_name)
    client.min_request_interval = 0
    return client


def _raw_event(**overrides) -> dict:
    """Minimal raw Legistar API event with controllable fields."""
    defaults = {
        "EventId": 5001,
        "EventGuid": "abc-123-def",
        "EventBodyName": "City Council Regular Meeting",
        "EventDate": "2025-10-02T00:00:00",
        "EventTime": "7:00 PM",
        "EventAgendaStatusName": "Final",
        "EventTypeName": "Regular",
        "EventLocation": "City Hall, Council Chambers",
        "EventVideoUrl": "https://example.com/video/5001",
        "EventAgendaFile": "https://example.com/agenda/5001.pdf",
        "EventMinutesFile": "https://example.com/minutes/5001.pdf",
    }
    defaults.update(overrides)
    return defaults


def _raw_matter(**overrides) -> dict:
    """Minimal raw Legistar API matter with controllable fields."""
    defaults = {
        "MatterId": 9001,
        "MatterGuid": "mat-guid-001",
        "MatterTitle": "Resolution to Approve Housing Element Update",
        "MatterSummary": "Annual update to the housing element per state requirements.",
        "MatterTypeName": "Resolution",
        "MatterStatusName": "Approved",
        "MatterFile": "RES-2025-042",
    }
    defaults.update(overrides)
    return defaults


def _raw_person(**overrides) -> dict:
    """Minimal raw Legistar API event item person."""
    defaults = {
        "EventItemPersonId": 7001,
        "EventItemPersonName": "Jane Smith",
        "EventItemPersonPosition": 1,
        "EventItemAgendaSequence": 3,
    }
    defaults.update(overrides)
    return defaults


def _mock_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestLegistarClientInit:
    def test_base_url_includes_client_name(self):
        client = LegistarClient("oakland")
        assert client.base_url == "https://webapi.legistar.com/v1/oakland"

    def test_base_url_with_hyphenated_name(self):
        client = LegistarClient("santa-rosa")
        assert client.base_url == "https://webapi.legistar.com/v1/santa-rosa"

    def test_capabilities_start_empty(self):
        client = LegistarClient("oakland")
        assert client.capabilities == {}

    def test_throttle_defaults(self):
        client = LegistarClient("oakland")
        assert client.last_request_time == 0
        assert client.min_request_interval == 1.0


# ---------------------------------------------------------------------------
# _throttle_request
# ---------------------------------------------------------------------------


class TestThrottleRequest:
    def test_first_call_does_not_sleep(self):
        client = _make_client()
        client.last_request_time = 0
        client.min_request_interval = 0.5
        with patch("civicos_services.clients.legistar_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_not_called()
        assert client.last_request_time > 0

    def test_rapid_call_triggers_sleep(self):
        client = _make_client()
        client.min_request_interval = 0.5
        client.last_request_time = _time.time()  # Just now
        with patch("civicos_services.clients.legistar_client.time.sleep") as mock_sleep:
            client._throttle_request()
            mock_sleep.assert_called_once_with(0.5)
        assert client.last_request_time > 0


# ---------------------------------------------------------------------------
# _make_request
# ---------------------------------------------------------------------------


class TestMakeRequest:
    def test_success_returns_json(self):
        client = _make_client()
        mock_resp = _mock_response(200, json_data=[{"EventId": 1}])
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request("events", {"$top": 1})
        assert result == [{"EventId": 1}]
        call_args = client.session.get.call_args
        assert call_args[0][0] == "https://webapi.legistar.com/v1/oakland/events"

    def test_non_retryable_error_returns_none(self):
        client = _make_client()
        mock_resp = _mock_response(404, text="Not Found")
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request("events/99999")
        assert result is None
        assert client.session.get.call_count == 1

    def test_retryable_500_retries_then_succeeds(self):
        client = _make_client()
        fail_resp = _mock_response(500, text="Internal Server Error")
        ok_resp = _mock_response(200, json_data=[{"ok": True}])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result == [{"ok": True}]
        assert client.session.get.call_count == 2

    def test_retryable_429_retries(self):
        client = _make_client()
        rate_resp = _mock_response(429, text="Rate Limited")
        ok_resp = _mock_response(200, json_data={"data": "ok"})
        client.session.get = MagicMock(side_effect=[rate_resp, ok_resp])

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result == {"data": "ok"}
        assert client.session.get.call_count == 2

    def test_retryable_502_retries(self):
        client = _make_client()
        fail_resp = _mock_response(502, text="Bad Gateway")
        ok_resp = _mock_response(200, json_data=[])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result == []
        assert client.session.get.call_count == 2

    def test_retryable_503_retries(self):
        client = _make_client()
        fail_resp = _mock_response(503, text="Service Unavailable")
        ok_resp = _mock_response(200, json_data=[{"id": 1}])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result == [{"id": 1}]

    def test_all_retries_exhausted_returns_none(self):
        client = _make_client()
        fail_resp = _mock_response(500, text="Error")
        client.session.get = MagicMock(return_value=fail_resp)

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result is None
        assert client.session.get.call_count == 3

    def test_exception_retries_then_returns_none(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=ConnectionError("timeout"))

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=2)

        assert result is None
        assert client.session.get.call_count == 2

    def test_exception_on_first_then_success(self):
        client = _make_client()
        ok_resp = _mock_response(200, json_data={"events": []})
        client.session.get = MagicMock(
            side_effect=[ConnectionError("fail"), ok_resp]
        )

        with patch("civicos_services.clients.legistar_client.time.sleep"):
            result = client._make_request("events", retries=3)

        assert result == {"events": []}
        assert client.session.get.call_count == 2

    def test_non_retryable_status_does_not_retry(self):
        """Status codes not in [429, 500, 502, 503] should return None immediately."""
        client = _make_client()
        mock_resp = _mock_response(403, text="Forbidden")
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request("events", retries=3)
        assert result is None
        assert client.session.get.call_count == 1


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_empty_string_returns_empty(self):
        client = _make_client()
        assert client._clean_text("") == ""

    def test_none_returns_empty(self):
        client = _make_client()
        assert client._clean_text(None) == ""

    def test_strips_whitespace(self):
        client = _make_client()
        assert client._clean_text("  hello  ") == "hello"

    def test_replaces_en_dash(self):
        client = _make_client()
        assert client._clean_text("Jan\u2013Feb") == "Jan-Feb"

    def test_replaces_em_dash(self):
        client = _make_client()
        assert client._clean_text("A\u2014B") == "A--B"

    def test_strips_html_tags(self):
        client = _make_client()
        assert client._clean_text("<b>Bold</b> text") == "Bold text"

    def test_strips_anchor_tags(self):
        client = _make_client()
        assert client._clean_text("<a href='url'>link</a>") == "link"

    def test_combined_cleaning(self):
        client = _make_client()
        result = client._clean_text("  <p>A\u2013B</p>  ")
        assert result == "A-B"

    def test_non_string_converted(self):
        client = _make_client()
        assert client._clean_text(12345) == "12345"


# ---------------------------------------------------------------------------
# _is_relevant_meeting
# ---------------------------------------------------------------------------


class TestIsRelevantMeeting:
    def test_city_council_is_relevant(self):
        client = _make_client()
        event = {"title": "City Council Regular Meeting", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_planning_commission_is_relevant(self):
        client = _make_client()
        event = {"title": "Planning Commission Meeting", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_public_hearing_is_relevant(self):
        client = _make_client()
        event = {"title": "Public Hearing on Zoning", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_board_meeting_is_relevant(self):
        client = _make_client()
        event = {"title": "Board of Supervisors", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_committee_is_relevant(self):
        client = _make_client()
        event = {"title": "Finance Committee", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_commission_is_relevant(self):
        client = _make_client()
        event = {"title": "Parks and Recreation Commission", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_cancelled_status_is_not_relevant(self):
        client = _make_client()
        event = {"title": "City Council Meeting", "status": "Cancelled"}
        assert client._is_relevant_meeting(event) is False

    def test_hidden_status_is_not_relevant(self):
        client = _make_client()
        event = {"title": "City Council Meeting", "status": "Hidden"}
        assert client._is_relevant_meeting(event) is False

    def test_irrelevant_title_excluded(self):
        client = _make_client()
        event = {"title": "Staff Retreat", "status": "Final"}
        assert client._is_relevant_meeting(event) is False

    def test_empty_title_excluded(self):
        client = _make_client()
        event = {"title": "", "status": "Final"}
        assert client._is_relevant_meeting(event) is False

    def test_missing_title_excluded(self):
        client = _make_client()
        event = {"status": "Final"}
        assert client._is_relevant_meeting(event) is False

    def test_keyword_case_insensitive(self):
        client = _make_client()
        event = {"title": "PUBLIC HEARING ON ZONING", "status": "Final"}
        assert client._is_relevant_meeting(event) is True

    def test_cancel_substring_in_status_triggers_filter(self):
        """'cancel' as substring in status triggers filter (e.g. 'Canceled')."""
        client = _make_client()
        event = {"title": "City Council Meeting", "status": "Canceled"}
        assert client._is_relevant_meeting(event) is False

    def test_missing_status_defaults_empty(self):
        client = _make_client()
        event = {"title": "City Council Meeting"}
        assert client._is_relevant_meeting(event) is True


# ---------------------------------------------------------------------------
# _normalize_events
# ---------------------------------------------------------------------------


class TestNormalizeEvents:
    def test_basic_event_normalization(self):
        client = _make_client()
        raw = _raw_event()
        result = client._normalize_events([raw])

        assert len(result) == 1
        event = result[0]
        assert event["event_id"] == 5001
        assert event["event_guid"] == "abc-123-def"
        assert event["title"] == "City Council Regular Meeting"
        assert event["date"] == "2025-10-02T00:00:00"
        assert event["status"] == "Final"
        assert event["body_name"] == "City Council Regular Meeting"
        assert event["meeting_type"] == "Regular"
        assert event["location"] == "City Hall, Council Chambers"
        assert event["video_url"] == "https://example.com/video/5001"
        assert event["agenda_url"] == "https://example.com/agenda/5001.pdf"
        assert event["minutes_url"] == "https://example.com/minutes/5001.pdf"

    def test_meeting_datetime_combines_date_and_time(self):
        """EventDate + EventTime should combine into proper ISO datetime."""
        client = _make_client()
        raw = _raw_event(EventDate="2025-10-02T00:00:00", EventTime="7:00 PM")
        result = client._normalize_events([raw])

        assert len(result) == 1
        assert result[0]["meeting_datetime"] == "2025-10-02T19:00:00"

    def test_morning_time_parsed_correctly(self):
        client = _make_client()
        raw = _raw_event(EventTime="10:30 AM")
        result = client._normalize_events([raw])
        assert result[0]["meeting_datetime"] == "2025-10-02T10:30:00"

    def test_noon_time_parsed_correctly(self):
        client = _make_client()
        raw = _raw_event(EventTime="12:00 PM")
        result = client._normalize_events([raw])
        assert result[0]["meeting_datetime"] == "2025-10-02T12:00:00"

    def test_missing_event_time_falls_back_to_date(self):
        client = _make_client()
        raw = _raw_event(EventTime="")
        result = client._normalize_events([raw])
        assert result[0]["meeting_datetime"] == "2025-10-02T00:00:00"

    def test_missing_event_date_uses_empty(self):
        client = _make_client()
        raw = _raw_event(EventDate="", EventTime="7:00 PM")
        result = client._normalize_events([raw])
        assert result[0]["meeting_datetime"] == ""

    def test_unparseable_time_falls_back_to_date(self):
        client = _make_client()
        raw = _raw_event(EventTime="not-a-time")
        result = client._normalize_events([raw])
        # Should fall back to EventDate
        assert result[0]["meeting_datetime"] == "2025-10-02T00:00:00"

    def test_cancelled_events_filtered_out(self):
        client = _make_client()
        events = [
            _raw_event(EventId=1, EventAgendaStatusName="Cancelled"),
            _raw_event(EventId=2, EventAgendaStatusName="Final"),
        ]
        result = client._normalize_events(events)
        assert len(result) == 1
        assert result[0]["event_id"] == 2

    def test_irrelevant_title_filtered_out(self):
        client = _make_client()
        events = [
            _raw_event(EventId=1, EventBodyName="Staff Retreat"),
            _raw_event(EventId=2, EventBodyName="City Council Meeting"),
        ]
        result = client._normalize_events(events)
        assert len(result) == 1
        assert result[0]["event_id"] == 2

    def test_encoding_cleaned_in_title(self):
        client = _make_client()
        raw = _raw_event(EventBodyName="Budget \u2013 City Council")
        result = client._normalize_events([raw])
        assert result[0]["title"] == "Budget - City Council"

    def test_html_stripped_from_location(self):
        client = _make_client()
        raw = _raw_event(EventLocation="<b>City Hall</b>, Room 101")
        result = client._normalize_events([raw])
        assert result[0]["location"] == "City Hall, Room 101"

    def test_default_body_name_when_missing(self):
        client = _make_client()
        raw = _raw_event(EventBodyName=None)
        result = client._normalize_events([raw])
        # "Unknown Meeting" doesn't match any relevant keyword -> filtered out
        assert len(result) == 0

    def test_missing_meeting_type_key_defaults_to_regular(self):
        client = _make_client()
        raw = _raw_event()
        del raw["EventTypeName"]
        result = client._normalize_events([raw])
        assert result[0]["meeting_type"] == "Regular"

    def test_none_meeting_type_preserved_as_none(self):
        """When EventTypeName is explicitly None, .get() returns None (key exists)."""
        client = _make_client()
        raw = _raw_event(EventTypeName=None)
        result = client._normalize_events([raw])
        assert result[0]["meeting_type"] is None

    def test_event_time_preserved_in_output(self):
        client = _make_client()
        raw = _raw_event(EventTime="3:30 PM")
        result = client._normalize_events([raw])
        assert result[0]["event_time"] == "3:30 PM"

    def test_empty_list_returns_empty(self):
        client = _make_client()
        assert client._normalize_events([]) == []


# ---------------------------------------------------------------------------
# _normalize_matters
# ---------------------------------------------------------------------------


class TestNormalizeMatters:
    def test_basic_matter_normalization(self):
        client = _make_client()
        raw = _raw_matter()
        result = client._normalize_matters([raw])

        assert len(result) == 1
        matter = result[0]
        assert matter["matter_id"] == 9001
        assert matter["matter_guid"] == "mat-guid-001"
        assert matter["title"] == "Resolution to Approve Housing Element Update"
        assert matter["summary"] == "Annual update to the housing element per state requirements."
        assert matter["type"] == "Resolution"
        assert matter["status"] == "Approved"
        assert matter["file_number"] == "RES-2025-042"
        assert matter["attachments"] == []

    def test_short_title_filtered_out(self):
        """Matters with titles <= 10 chars are excluded."""
        client = _make_client()
        result = client._normalize_matters([_raw_matter(MatterTitle="Short")])
        assert len(result) == 0

    def test_exactly_10_chars_filtered_out(self):
        client = _make_client()
        result = client._normalize_matters([_raw_matter(MatterTitle="1234567890")])
        assert len(result) == 0

    def test_11_chars_included(self):
        client = _make_client()
        result = client._normalize_matters([_raw_matter(MatterTitle="12345678901")])
        assert len(result) == 1
        assert result[0]["title"] == "12345678901"

    def test_empty_title_filtered_out(self):
        client = _make_client()
        result = client._normalize_matters([_raw_matter(MatterTitle="")])
        assert len(result) == 0

    def test_none_title_filtered_out(self):
        client = _make_client()
        result = client._normalize_matters([_raw_matter(MatterTitle=None)])
        assert len(result) == 0

    def test_encoding_cleaned_in_title(self):
        client = _make_client()
        result = client._normalize_matters([
            _raw_matter(MatterTitle="Budget Resolution \u2013 Housing Element")
        ])
        assert result[0]["title"] == "Budget Resolution - Housing Element"

    def test_missing_fields_use_defaults(self):
        client = _make_client()
        raw = {"MatterTitle": "A reasonably long matter title"}
        result = client._normalize_matters([raw])
        assert len(result) == 1
        assert result[0]["matter_id"] is None
        assert result[0]["matter_guid"] is None
        assert result[0]["summary"] == ""
        assert result[0]["type"] == ""
        assert result[0]["status"] == ""
        assert result[0]["file_number"] == ""

    def test_empty_list_returns_empty(self):
        client = _make_client()
        assert client._normalize_matters([]) == []

    def test_multiple_matters_filtered_correctly(self):
        client = _make_client()
        matters = [
            _raw_matter(MatterId=1, MatterTitle="Budget Plan for FY 2025-2026"),
            _raw_matter(MatterId=2, MatterTitle="Short"),
            _raw_matter(MatterId=3, MatterTitle="Resolution to Rezone Parcel X"),
        ]
        result = client._normalize_matters(matters)
        assert len(result) == 2
        assert result[0]["matter_id"] == 1
        assert result[1]["matter_id"] == 3


# ---------------------------------------------------------------------------
# _normalize_testimony
# ---------------------------------------------------------------------------


class TestNormalizeTestimony:
    def test_basic_testimony_normalization(self):
        client = _make_client()
        raw = _raw_person()
        result = client._normalize_testimony([raw])

        assert len(result) == 1
        person = result[0]
        assert person["event_item_person_id"] == 7001
        assert person["speaker_name"] == "Jane Smith"
        assert person["speaking_order"] == 1
        assert person["agenda_sequence"] == 3
        assert person["position"] is None
        assert person["organization"] is None
        assert person["testimony_text"] is None

    def test_empty_name_filtered_out(self):
        client = _make_client()
        result = client._normalize_testimony([_raw_person(EventItemPersonName="")])
        assert len(result) == 0

    def test_single_char_name_filtered_out(self):
        """Names < 2 chars are excluded."""
        client = _make_client()
        result = client._normalize_testimony([_raw_person(EventItemPersonName="A")])
        assert len(result) == 0

    def test_two_char_name_included(self):
        client = _make_client()
        result = client._normalize_testimony([_raw_person(EventItemPersonName="Li")])
        assert len(result) == 1
        assert result[0]["speaker_name"] == "Li"

    def test_none_name_filtered_out(self):
        client = _make_client()
        result = client._normalize_testimony([_raw_person(EventItemPersonName=None)])
        assert len(result) == 0

    def test_sorted_by_speaking_order(self):
        client = _make_client()
        persons = [
            _raw_person(EventItemPersonId=1, EventItemPersonName="Third Speaker", EventItemPersonPosition=3),
            _raw_person(EventItemPersonId=2, EventItemPersonName="First Speaker", EventItemPersonPosition=1),
            _raw_person(EventItemPersonId=3, EventItemPersonName="Second Speaker", EventItemPersonPosition=2),
        ]
        result = client._normalize_testimony(persons)
        assert len(result) == 3
        assert result[0]["speaker_name"] == "First Speaker"
        assert result[1]["speaker_name"] == "Second Speaker"
        assert result[2]["speaker_name"] == "Third Speaker"

    def test_encoding_cleaned_in_name(self):
        client = _make_client()
        result = client._normalize_testimony([
            _raw_person(EventItemPersonName="Jos\u00e9 Garc\u00eda")
        ])
        assert result[0]["speaker_name"] == "Jos\u00e9 Garc\u00eda"

    def test_html_stripped_from_name(self):
        client = _make_client()
        result = client._normalize_testimony([
            _raw_person(EventItemPersonName="<b>John Doe</b>")
        ])
        assert result[0]["speaker_name"] == "John Doe"

    def test_default_speaking_order_is_zero(self):
        client = _make_client()
        raw = {"EventItemPersonName": "Test Person"}
        result = client._normalize_testimony([raw])
        assert result[0]["speaking_order"] == 0
        assert result[0]["agenda_sequence"] == 0

    def test_empty_list_returns_empty(self):
        client = _make_client()
        assert client._normalize_testimony([]) == []


# ---------------------------------------------------------------------------
# probe_capabilities
# ---------------------------------------------------------------------------


class TestProbeCapabilities:
    def test_all_endpoints_available(self):
        client = _make_client()
        client._make_request = MagicMock(side_effect=[
            [{"BodyId": 1}],    # bodies
            [{"EventId": 1, "EventDate": "2025-10-01", "other": None}],  # events
            [{"MatterId": 1}],  # matters
        ])

        caps = client.probe_capabilities()

        assert caps["client_name"] == "oakland"
        assert caps["api_accessible"] is True
        assert caps["bodies_available"] is True
        assert caps["events_available"] is True
        assert caps["matters_available"] is True
        assert caps["timezone_detected"] == "America/Los_Angeles"

    def test_only_bodies_available(self):
        client = _make_client()
        client._make_request = MagicMock(side_effect=[
            [{"BodyId": 1}],  # bodies
            None,              # events failed
            None,              # matters failed
        ])

        caps = client.probe_capabilities()

        assert caps["api_accessible"] is True
        assert caps["bodies_available"] is True
        assert caps["events_available"] is False
        assert caps["matters_available"] is False

    def test_all_endpoints_fail(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=None)

        caps = client.probe_capabilities()

        assert caps["api_accessible"] is False
        assert caps["bodies_available"] is False
        assert caps["events_available"] is False
        assert caps["matters_available"] is False

    def test_null_patterns_detected_from_events(self):
        client = _make_client()
        event_with_nulls = {
            "EventId": 1,
            "EventDate": "2025-10-01",
            "EventVideoUrl": None,
            "EventMinutesFile": None,
            "EventAgendaFile": None,
        }
        client._make_request = MagicMock(side_effect=[
            None,                  # bodies fail
            [event_with_nulls],    # events
            None,                  # matters fail
        ])

        caps = client.probe_capabilities()

        assert caps["events_available"] is True
        # null_patterns should contain up to 5 null field names
        assert "EventVideoUrl" in caps["null_patterns"]
        assert "EventMinutesFile" in caps["null_patterns"]
        assert "EventAgendaFile" in caps["null_patterns"]

    def test_capabilities_stored_on_client(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=None)

        caps = client.probe_capabilities()

        assert client.capabilities is caps
        assert client.capabilities["client_name"] == "oakland"

    def test_empty_list_response_treated_as_available(self):
        """An empty list is still a valid API response."""
        client = _make_client()
        client._make_request = MagicMock(side_effect=[
            [],     # bodies - empty but valid
            [],     # events - empty but valid
            [],     # matters - empty but valid
        ])

        caps = client.probe_capabilities()

        # Empty lists are falsy in Python, so they won't pass `if bodies and isinstance(bodies, list)`
        assert caps["api_accessible"] is False
        assert caps["bodies_available"] is False
        assert caps["events_available"] is False
        assert caps["matters_available"] is False


# ---------------------------------------------------------------------------
# get_recent_events
# ---------------------------------------------------------------------------


class TestGetRecentEvents:
    def test_returns_normalized_events(self):
        client = _make_client()
        raw_events = [_raw_event(EventId=1), _raw_event(EventId=2)]
        client._make_request = MagicMock(return_value=raw_events)

        result = client.get_recent_events(days_back=30, days_forward=14)

        assert len(result) == 2
        assert result[0]["event_id"] == 1
        assert result[1]["event_id"] == 2
        # Verify normalized structure
        assert "meeting_datetime" in result[0]
        assert "title" in result[0]

    def test_api_failure_returns_empty_list(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=None)

        result = client.get_recent_events()
        assert result == []

    def test_non_list_response_returns_empty(self):
        client = _make_client()
        client._make_request = MagicMock(return_value={"error": "bad"})

        result = client.get_recent_events()
        assert result == []

    def test_request_params_include_date_filter(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=[])

        client.get_recent_events(days_back=7, days_forward=3)

        call_args = client._make_request.call_args
        assert call_args[0][0] == "events"
        params = call_args[0][1]
        assert "$filter" in params
        assert "EventDate ge datetime'" in params["$filter"]
        assert "EventDate le datetime'" in params["$filter"]
        assert params["$orderby"] == "EventDate desc"
        assert params["$top"] == 50

    def test_does_not_require_probe_first(self):
        """get_recent_events should work even without calling probe_capabilities."""
        client = _make_client()
        assert client.capabilities == {}
        client._make_request = MagicMock(return_value=[_raw_event()])

        result = client.get_recent_events()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_event_matters
# ---------------------------------------------------------------------------


class TestGetEventMatters:
    def test_returns_normalized_matters(self):
        client = _make_client()
        client.capabilities = {"matters_available": True}
        client._make_request = MagicMock(return_value=[_raw_matter()])

        result = client.get_event_matters(event_id=5001)

        assert len(result) == 1
        assert result[0]["matter_id"] == 9001
        assert result[0]["title"] == "Resolution to Approve Housing Element Update"

    def test_matters_not_available_returns_empty(self):
        client = _make_client()
        client.capabilities = {"matters_available": False}

        result = client.get_event_matters(event_id=5001)
        assert result == []

    def test_empty_capabilities_returns_empty(self):
        """When capabilities haven't been probed, matters_available is missing."""
        client = _make_client()
        assert client.capabilities == {}

        result = client.get_event_matters(event_id=5001)
        assert result == []

    def test_api_failure_returns_empty(self):
        client = _make_client()
        client.capabilities = {"matters_available": True}
        client._make_request = MagicMock(return_value=None)

        result = client.get_event_matters(event_id=5001)
        assert result == []

    def test_request_uses_event_id_filter(self):
        client = _make_client()
        client.capabilities = {"matters_available": True}
        client._make_request = MagicMock(return_value=[])

        client.get_event_matters(event_id=42)

        call_args = client._make_request.call_args
        assert call_args[0][0] == "matters"
        assert call_args[0][1] == {"$filter": "EventId eq 42"}


# ---------------------------------------------------------------------------
# get_event_item_persons
# ---------------------------------------------------------------------------


class TestGetEventItemPersons:
    def test_returns_normalized_testimony(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=[
            _raw_person(EventItemPersonId=1, EventItemPersonName="Alice"),
            _raw_person(EventItemPersonId=2, EventItemPersonName="Bob"),
        ])

        result = client.get_event_item_persons(event_item_id=100)

        assert len(result) == 2
        assert result[0]["speaker_name"] == "Alice"
        assert result[1]["speaker_name"] == "Bob"

    def test_api_failure_returns_empty(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=None)

        result = client.get_event_item_persons(event_item_id=100)
        assert result == []

    def test_request_uses_correct_endpoint(self):
        client = _make_client()
        client._make_request = MagicMock(return_value=[])

        client.get_event_item_persons(event_item_id=456)

        call_args = client._make_request.call_args
        assert call_args[0][0] == "EventItems/456/EventItemPersons"


# ---------------------------------------------------------------------------
# KNOWN_LEGISTAR_CLIENTS registry
# ---------------------------------------------------------------------------


class TestKnownLegistarClients:
    def test_oakland_config(self):
        cfg = KNOWN_LEGISTAR_CLIENTS["oakland"]
        assert cfg["client_name"] == "oakland"
        assert cfg["status"] == "confirmed_working"
        assert cfg["timezone"] == "America/Los_Angeles"
        assert "Oakland City Council" in cfg["expected_bodies"]

    def test_santa_rosa_config(self):
        cfg = KNOWN_LEGISTAR_CLIENTS["santa-rosa"]
        assert cfg["client_name"] == "santa-rosa"
        assert cfg["status"] == "discovered_api"

    def test_san_francisco_requires_insite(self):
        cfg = KNOWN_LEGISTAR_CLIENTS["san_francisco"]
        assert cfg["client_name"] == "sanfrancisco"
        assert cfg["status"] == "requires_insite_config"

    def test_bart_config(self):
        cfg = KNOWN_LEGISTAR_CLIENTS["bart"]
        assert cfg["client_name"] == "bart"
        assert "BART Board of Directors" in cfg["expected_bodies"]

    def test_registry_has_seven_entries(self):
        assert len(KNOWN_LEGISTAR_CLIENTS) == 7

    def test_all_entries_have_required_keys(self):
        required_keys = {"client_name", "status", "expected_bodies", "timezone"}
        for name, cfg in KNOWN_LEGISTAR_CLIENTS.items():
            assert required_keys.issubset(cfg.keys()), f"{name} missing keys"


# ---------------------------------------------------------------------------
# create_client (factory function)
# ---------------------------------------------------------------------------


class TestCreateClient:
    def test_known_city_returns_client(self):
        client = create_client("oakland")
        assert client is not None
        assert client.client_name == "oakland"
        assert client.base_url == "https://webapi.legistar.com/v1/oakland"

    def test_case_insensitive_lookup(self):
        client = create_client("Oakland")
        assert client is not None
        assert client.client_name == "oakland"

    def test_unknown_city_returns_none(self):
        result = create_client("atlantis")
        assert result is None

    def test_san_francisco_uses_config_client_name(self):
        """SF config has client_name='sanfrancisco' (no underscore)."""
        client = create_client("san_francisco")
        assert client is not None
        assert client.client_name == "sanfrancisco"
        assert client.base_url == "https://webapi.legistar.com/v1/sanfrancisco"

    def test_hayward_returns_client(self):
        client = create_client("hayward")
        assert client is not None
        assert client.client_name == "hayward"

    def test_napa_returns_client(self):
        client = create_client("napa")
        assert client is not None
        assert client.client_name == "napa"

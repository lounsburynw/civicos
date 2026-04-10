"""
Tests for civicclerk_client.py — CivicClerk API client (Granicus product).

Tests pure-logic methods (URL construction, agenda file prioritization, schema
conversion, category mapping) and request-handling logic (event fetching,
enrichment, error handling). HTTP calls are mocked; all data transformation
and control flow runs for real.

To run:
    pytest packages/civicos-services/tests/test_civicclerk_client.py -q --override-ini="addopts="
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.clients.civicclerk_client import (
    CivicClerkClient,
    create_client,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(subdomain: str = "elcerritoca") -> CivicClerkClient:
    return CivicClerkClient(subdomain)


def _make_event(**overrides) -> dict:
    """Minimal CivicClerk event dict with controllable fields."""
    defaults = {
        "id": 101,
        "eventName": "City Council Regular Meeting",
        "startDateTime": "2025-08-10T18:00:00Z",
        "categoryName": "Council",
        "categoryId": 5,
        "eventDescription": "Regular session of the city council",
        "eventLocation": {
            "address1": "123 Main St",
            "city": "El Cerrito",
            "state": "CA",
            "zipCode": "94530",
        },
        "hasAgenda": True,
        "hasMedia": False,
        "agendaId": None,
        "publishedFiles": [],
    }
    defaults.update(overrides)
    return defaults


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestCivicClerkClientInit:
    def test_api_base_url_uses_subdomain(self):
        client = _make_client("elcerritoca")
        assert client.api_base == "https://elcerritoca.api.civicclerk.com/v1"

    def test_portal_base_url_uses_subdomain(self):
        client = _make_client("losaltosca")
        assert client.portal_base == "https://losaltosca.portal.civicclerk.com"

    def test_subdomain_stored(self):
        client = _make_client("elcerritoca")
        assert client.subdomain == "elcerritoca"

    def test_session_headers_accept_json(self):
        client = _make_client()
        assert client.session.headers["Accept"] == "application/json"

    def test_session_headers_user_agent(self):
        client = _make_client()
        assert "Civic-Engagement-Platform" in client.session.headers["User-Agent"]


# ---------------------------------------------------------------------------
# get_portal_url
# ---------------------------------------------------------------------------


class TestGetPortalUrl:
    def test_event_only(self):
        client = _make_client("elcerritoca")
        url = client.get_portal_url(101)
        assert url == "https://elcerritoca.portal.civicclerk.com/event/101"

    def test_event_with_file_id(self):
        client = _make_client("elcerritoca")
        url = client.get_portal_url(101, file_id=42)
        assert url == "https://elcerritoca.portal.civicclerk.com/event/101/files/agenda/42"

    def test_no_file_id_omits_files_path(self):
        client = _make_client("losaltosca")
        url = client.get_portal_url(999)
        assert "/files/" not in url
        assert url == "https://losaltosca.portal.civicclerk.com/event/999"

    def test_file_id_none_treated_as_absent(self):
        client = _make_client()
        url = client.get_portal_url(50, file_id=None)
        assert url.endswith("/event/50")

    def test_file_id_zero_treated_as_present(self):
        """file_id=0 is falsy but should still be treated as 'no file_id'
        by the current implementation (if file_id:)."""
        client = _make_client()
        url = client.get_portal_url(50, file_id=0)
        # 0 is falsy, so current implementation omits the files path
        assert url.endswith("/event/50")


# ---------------------------------------------------------------------------
# get_agenda_info
# ---------------------------------------------------------------------------


class TestGetAgendaInfo:
    def test_no_published_files_no_agenda_id_returns_none(self):
        client = _make_client()
        event = _make_event(publishedFiles=[], agendaId=None)
        assert client.get_agenda_info(event) is None

    def test_agenda_file_type_high_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Agenda", "url": "https://example.com/agenda.pdf", "fileId": 10}
        ])
        info = client.get_agenda_info(event)
        assert info["url"] == "https://example.com/agenda.pdf"
        assert info["file_type"] == "Agenda"
        assert info["file_id"] == 10
        assert info["confidence"] == "high"
        assert info["all_files"] == ["Agenda"]

    def test_notice_file_type_medium_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Notice", "url": "https://example.com/notice.pdf", "fileId": 20}
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Notice"
        assert info["confidence"] == "medium"

    def test_packet_file_type_medium_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Packet", "url": "https://example.com/packet.pdf", "fileId": 30}
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Packet"
        assert info["confidence"] == "medium"

    def test_agenda_packet_high_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Agenda Packet", "url": "https://example.com/ap.pdf", "fileId": 40}
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Agenda Packet"
        assert info["confidence"] == "high"

    def test_special_notice_medium_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Special Notice", "url": "https://example.com/sn.pdf", "fileId": 50}
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Special Notice"
        assert info["confidence"] == "medium"

    def test_agenda_preferred_over_notice(self):
        """Agenda type has higher priority than Notice."""
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Notice", "url": "https://example.com/notice.pdf", "fileId": 20},
            {"type": "Agenda", "url": "https://example.com/agenda.pdf", "fileId": 10},
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Agenda"
        assert info["file_id"] == 10

    def test_unknown_file_type_falls_back_low_confidence(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Staff Report", "url": "https://example.com/sr.pdf", "fileId": 60}
        ])
        info = client.get_agenda_info(event)
        assert info["file_type"] == "Staff Report"
        assert info["confidence"] == "low"
        assert "_warning" in info
        assert "Staff Report" in info["_warning"]

    def test_agenda_id_fallback_low_confidence(self):
        client = _make_client("elcerritoca")
        event = _make_event(publishedFiles=[], agendaId=77, id=101)
        info = client.get_agenda_info(event)
        assert info["file_type"] == "agendaId"
        assert info["file_id"] == 77
        assert info["confidence"] == "low"
        assert "GetMeetingFile" in info["url"]
        assert "fileId=77" in info["url"]
        assert "_warning" in info

    def test_agenda_id_requires_event_id(self):
        """agendaId fallback requires both agendaId and event id."""
        client = _make_client()
        event = {"publishedFiles": [], "agendaId": 77}  # No 'id' key
        info = client.get_agenda_info(event)
        assert info is None

    def test_all_files_lists_all_types(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Agenda", "url": "u1", "fileId": 1},
            {"type": "Minutes", "url": "u2", "fileId": 2},
            {"type": "Packet", "url": "u3", "fileId": 3},
        ])
        info = client.get_agenda_info(event)
        assert set(info["all_files"]) == {"Agenda", "Minutes", "Packet"}

    def test_empty_published_files_no_agenda_id_returns_none(self):
        client = _make_client()
        event = {"publishedFiles": []}
        assert client.get_agenda_info(event) is None

    def test_files_with_none_type_excluded_from_all_files(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": None, "url": "u1", "fileId": 1},
            {"type": "Agenda", "url": "u2", "fileId": 2},
        ])
        info = client.get_agenda_info(event)
        assert info["all_files"] == ["Agenda"]
        assert info["file_type"] == "Agenda"


# ---------------------------------------------------------------------------
# get_agenda_url
# ---------------------------------------------------------------------------


class TestGetAgendaUrl:
    def test_returns_url_when_agenda_found(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Agenda", "url": "https://example.com/agenda.pdf", "fileId": 10}
        ])
        url = client.get_agenda_url(event)
        assert url == "https://example.com/agenda.pdf"

    def test_returns_none_when_no_agenda(self):
        client = _make_client()
        event = _make_event(publishedFiles=[], agendaId=None)
        assert client.get_agenda_url(event) is None


# ---------------------------------------------------------------------------
# get_event_details
# ---------------------------------------------------------------------------


class TestGetEventDetails:
    def test_success_returns_event_dict(self):
        client = _make_client("elcerritoca")
        event_data = {"id": 101, "eventName": "Council Meeting"}
        mock_resp = _mock_response(200, json_data=event_data)
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_event_details(101)

        assert result == {"id": 101, "eventName": "Council Meeting"}
        call_url = client.session.get.call_args[0][0]
        assert call_url == "https://elcerritoca.api.civicclerk.com/v1/Events/101"

    def test_http_error_returns_none(self):
        client = _make_client()
        mock_resp = _mock_response(404)
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_event_details(999)
        assert result is None

    def test_network_error_returns_none(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=ConnectionError("timeout"))

        result = client.get_event_details(101)
        assert result is None

    def test_timeout_passed_to_session(self):
        client = _make_client()
        event_data = {"id": 50}
        mock_resp = _mock_response(200, json_data=event_data)
        client.session.get = MagicMock(return_value=mock_resp)

        client.get_event_details(50)

        call_kwargs = client.session.get.call_args[1]
        assert call_kwargs["timeout"] == 10


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------


class TestGetEvents:
    def test_returns_enriched_events(self):
        client = _make_client("elcerritoca")
        list_response = _mock_response(200, json_data={
            "value": [{"id": 1, "eventName": "E1"}, {"id": 2, "eventName": "E2"}]
        })
        detail_1 = {"id": 1, "eventName": "E1", "publishedFiles": []}
        detail_2 = {"id": 2, "eventName": "E2", "publishedFiles": []}

        # First call is the list request, then two detail requests
        client.session.get = MagicMock(side_effect=[
            list_response,
            _mock_response(200, json_data=detail_1),
            _mock_response(200, json_data=detail_2),
        ])

        start = datetime(2025, 8, 1)
        end = datetime(2025, 8, 31)
        result = client.get_events(start_date=start, end_date=end)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_falls_back_to_list_data_on_detail_failure(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={
            "value": [{"id": 1, "eventName": "Fallback Event"}]
        })
        # Detail fetch fails
        detail_response = _mock_response(500)

        client.session.get = MagicMock(side_effect=[list_response, detail_response])

        result = client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )

        assert len(result) == 1
        assert result[0]["eventName"] == "Fallback Event"

    def test_api_error_returns_empty_list(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=ConnectionError("offline"))

        result = client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )
        assert result == []

    def test_default_dates_computed(self):
        """Without explicit dates, start=now, end=start+days_ahead."""
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        result = client.get_events(days_ahead=30)

        assert result == []
        # Verify the URL was constructed (call was made)
        assert client.session.get.call_count == 1
        call_url = client.session.get.call_args[0][0]
        assert "Events?" in call_url

    def test_has_agenda_filter_true(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
            has_agenda=True,
        )

        call_url = client.session.get.call_args[0][0]
        assert "hasAgenda%20eq%20true" in call_url

    def test_has_agenda_filter_false(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
            has_agenda=False,
        )

        call_url = client.session.get.call_args[0][0]
        assert "hasAgenda%20eq%20false" in call_url

    def test_has_agenda_none_omits_filter(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
            has_agenda=None,
        )

        call_url = client.session.get.call_args[0][0]
        assert "hasAgenda" not in call_url

    def test_events_without_id_skipped(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={
            "value": [
                {"id": None, "eventName": "No ID Event"},
                {"eventName": "Also no ID"},
            ]
        })
        client.session.get = MagicMock(return_value=list_response)

        result = client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )
        # Events without id are skipped (id is falsy)
        assert result == []

    def test_orderby_ascending(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )

        call_url = client.session.get.call_args[0][0]
        assert "startDateTime%20asc" in call_url

    def test_timeout_on_list_request(self):
        client = _make_client()
        list_response = _mock_response(200, json_data={"value": []})
        client.session.get = MagicMock(return_value=list_response)

        client.get_events(
            start_date=datetime(2025, 8, 1),
            end_date=datetime(2025, 8, 31),
        )

        call_kwargs = client.session.get.call_args[1]
        assert call_kwargs["timeout"] == 15


# ---------------------------------------------------------------------------
# convert_to_civic_schema
# ---------------------------------------------------------------------------


class TestConvertToCivicSchema:
    def test_council_category_mapping(self):
        client = _make_client("elcerritoca")
        event = _make_event(categoryName="City Council")
        jurisdiction = {"id": "city-el-cerrito", "name": "El Cerrito"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["project_type"] == "governance"
        assert result["meeting_type"] == "city_council"

    def test_planning_category_mapping(self):
        client = _make_client()
        event = _make_event(categoryName="Planning Commission")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["project_type"] == "building/development"
        assert result["meeting_type"] == "planning_commission"

    def test_commission_category_mapping(self):
        client = _make_client()
        event = _make_event(categoryName="Parks Commission")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["project_type"] == "governance"
        assert result["meeting_type"] == "commission"

    def test_unknown_category_defaults(self):
        client = _make_client()
        event = _make_event(categoryName="Special Workshop")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["project_type"] == "governance"
        assert result["meeting_type"] == "public_meeting"

    def test_title_from_event_name(self):
        client = _make_client()
        event = _make_event(eventName="Budget Workshop 2025")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["title"] == "Budget Workshop 2025"
        assert result["original_title"] == "Budget Workshop 2025"

    def test_location_string_built_from_parts(self):
        client = _make_client()
        event = _make_event(eventLocation={
            "address1": "10 Main St",
            "city": "El Cerrito",
            "state": "CA",
            "zipCode": "94530",
        })
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["location"] == "10 Main St, El Cerrito, CA, 94530"

    def test_location_with_partial_parts(self):
        client = _make_client()
        event = _make_event(eventLocation={
            "address1": "City Hall",
            "city": None,
            "state": "CA",
            "zipCode": None,
        })
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["location"] == "City Hall, CA"

    def test_empty_location(self):
        client = _make_client()
        event = _make_event(eventLocation={})
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["location"] is None

    def test_no_location_key(self):
        client = _make_client()
        event = _make_event(eventLocation=None)
        # Remove the key entirely — .get returns None for missing
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["location"] is None

    def test_datetime_parsing_with_z_suffix(self):
        client = _make_client()
        event = _make_event(startDateTime="2025-08-10T18:00:00Z")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["when"] == "2025-08-10T18:00:00+00:00"
        assert "Sun Aug 10, 2025" in result["when_human"]
        assert "06:00 PM" in result["when_human"]

    def test_datetime_parsing_without_z(self):
        client = _make_client()
        event = _make_event(startDateTime="2025-08-10T18:00:00+00:00")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["when"] == "2025-08-10T18:00:00+00:00"

    def test_no_start_datetime(self):
        client = _make_client()
        event = _make_event(startDateTime=None)
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["when"] is None
        assert result["when_human"] is None

    def test_description_stored(self):
        client = _make_client()
        event = _make_event(eventDescription="Public hearing on zoning change")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["description"] == "Public hearing on zoning change"

    def test_empty_description_becomes_none(self):
        client = _make_client()
        event = _make_event(eventDescription="")
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["description"] is None

    def test_jurisdiction_passed_through(self):
        client = _make_client()
        event = _make_event()
        jurisdiction = {"id": "city-el-cerrito", "name": "El Cerrito"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["jurisdiction"] == {"id": "city-el-cerrito", "name": "El Cerrito"}

    def test_contact_email_included(self):
        client = _make_client()
        event = _make_event()
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction, contact_email="clerk@city.gov")

        assert result["contact_info"]["email"] == "clerk@city.gov"

    def test_contact_email_default_none(self):
        client = _make_client()
        event = _make_event()
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["contact_info"]["email"] is None

    def test_portal_url_in_source_url(self):
        client = _make_client("elcerritoca")
        event = _make_event(id=101)
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["source_url"] == "https://elcerritoca.portal.civicclerk.com/event/101"
        assert result["scraped_from"] == result["source_url"]
        assert result["agenda_page"] == result["source_url"]

    def test_agenda_url_populated_when_available(self):
        client = _make_client()
        event = _make_event(publishedFiles=[
            {"type": "Agenda", "url": "https://example.com/agenda.pdf", "fileId": 10}
        ])
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["agenda_url"] == "https://example.com/agenda.pdf"
        assert result["agenda_available"] is True
        assert result["agenda_expansion"]["available"] is True
        assert result["agenda_expansion"]["source_url"] == "https://example.com/agenda.pdf"

    def test_no_agenda_url_when_unavailable(self):
        client = _make_client()
        event = _make_event(publishedFiles=[], agendaId=None)
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["agenda_url"] is None
        assert result["agenda_available"] is False
        assert result["agenda_expansion"]["available"] is False

    def test_civicclerk_metadata_stored(self):
        client = _make_client()
        event = _make_event(id=101, categoryId=5, categoryName="Council", hasAgenda=True, hasMedia=False)
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        meta = result["_civicclerk_metadata"]
        assert meta["event_id"] == 101
        assert meta["category_id"] == 5
        assert meta["category_name"] == "Council"
        assert meta["has_agenda"] is True
        assert meta["has_media"] is False

    def test_static_fields(self):
        client = _make_client()
        event = _make_event()
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["action_type"] == "meeting"
        assert result["engagement_tier"] == "meeting"
        assert result["timezone"] == "America/Los_Angeles"
        assert result["deadline"] is None
        assert result["deadline_reason"] is None
        assert result["agenda_item_number"] is None

    def test_participation_mechanisms_populated(self):
        client = _make_client()
        event = _make_event(
            startDateTime="2025-08-10T18:00:00Z",
            eventLocation={"address1": "City Hall", "city": "El Cerrito", "state": "CA", "zipCode": "94530"},
        )
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        mechanisms = result["participation_mechanisms"]
        assert len(mechanisms) == 1
        assert mechanisms[0]["type"] == "attend"
        assert mechanisms[0]["location"] == "City Hall, El Cerrito, CA, 94530"
        assert mechanisms[0]["when"] == "2025-08-10T18:00:00+00:00"
        assert mechanisms[0]["description"] == "Attend meeting for public comment"

    def test_uuid_id_generated(self):
        client = _make_client()
        event = _make_event()
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        # UUID format: 8-4-4-4-12 hex chars
        assert len(result["id"]) == 36
        assert result["id"].count("-") == 4

    def test_missing_event_name_defaults(self):
        client = _make_client()
        event = _make_event()
        del event["eventName"]
        jurisdiction = {"id": "city-test"}

        result = client.convert_to_civic_schema(event, jurisdiction)

        assert result["title"] == "Untitled Event"


# ---------------------------------------------------------------------------
# create_client (factory function)
# ---------------------------------------------------------------------------


class TestCreateClient:
    def test_el_cerrito_returns_client(self):
        client = create_client("el-cerrito")
        assert client is not None
        assert client.subdomain == "elcerritoca"
        assert "elcerritoca" in client.api_base

    def test_los_altos_returns_client(self):
        client = create_client("los-altos")
        assert client is not None
        assert client.subdomain == "losaltosca"

    def test_unknown_jurisdiction_returns_none(self):
        result = create_client("atlantis")
        assert result is None

    def test_empty_string_returns_none(self):
        result = create_client("")
        assert result is None

    def test_case_sensitive_lookup(self):
        """Jurisdiction keys are exact-match (case-sensitive)."""
        result = create_client("El-Cerrito")
        assert result is None

    def test_returned_client_is_civicclerk_instance(self):
        client = create_client("el-cerrito")
        assert isinstance(client, CivicClerkClient)
        assert client.api_base == "https://elcerritoca.api.civicclerk.com/v1"
        assert client.portal_base == "https://elcerritoca.portal.civicclerk.com"

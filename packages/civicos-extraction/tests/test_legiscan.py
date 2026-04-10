"""Tests for LegiScan API client — bill search, parsing, hearing date extraction, deduplication."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_extraction.clients.legiscan import (
    LegiScanClient,
    TOPIC_KEYWORDS,
    parse_hearing_date,
    parse_hearing_events_from_legislation,
    _MONTH_MAP,
)


# ==================== Fixtures ====================


@pytest.fixture
def client():
    """LegiScanClient with API key set."""
    return LegiScanClient(api_key="test-key-123")


@pytest.fixture
def bill_search_result():
    """Single bill item as returned inside a searchresult dict."""
    return {
        "bill_id": 1234567,
        "bill_number": "AB-1234",
        "title": "Housing Density Reform Act",
        "description": "Increases allowable density in residential zones",
        "state": "CA",
        "session": {"session_id": 2000, "session_name": "2025-2026"},
        "status": 2,
        "status_date": "2026-03-15",
        "url": "https://legiscan.com/CA/bill/AB1234/2025",
        "last_action": "Set for hearing April 2",
        "last_action_date": "2026-03-20",
    }


@pytest.fixture
def bill_detail_response():
    """Full bill detail response from getBill."""
    return {
        "bill": {
            "bill_id": 1234567,
            "bill_number": "AB-1234",
            "title": "Housing Density Reform Act",
            "history": [
                {
                    "date": "2026-01-15",
                    "action": "Introduced",
                    "chamber": "Assembly",
                    "chamber_id": 1,
                    "importance": 1,
                },
                {
                    "date": "2026-02-10",
                    "action": "Referred to Com. on HOUSING",
                    "chamber": "Assembly",
                    "chamber_id": 1,
                    "importance": 2,
                },
                {
                    "date": "2026-03-20",
                    "action": "Set for hearing April 2",
                    "chamber": "Assembly",
                    "chamber_id": 1,
                    "importance": 3,
                },
            ],
        }
    }


@pytest.fixture
def calendar_response():
    """Calendar response from getSessionCalendar."""
    return {
        "calendar": {
            "0": {
                "date": "2026-04-02",
                "description": "Assembly Housing Committee",
                "location": "Room 4202",
                "type": "hearing",
                "type_id": 1,
                "bills": [
                    {"bill_id": 1234567, "number": "AB-1234", "title": "Housing Density Reform Act"},
                    {"bill_id": 1234568, "number": "AB-5678", "title": "Zoning Update"},
                ],
            },
            "1": {
                "date": "2026-04-05",
                "description": "Senate Budget Committee",
                "location": "Room 112",
                "type": "hearing",
                "type_id": 2,
                "bills": [],
            },
        }
    }


# ==================== __init__ ====================


class TestClientInit:
    def test_api_key_from_argument(self):
        client = LegiScanClient(api_key="my-key")
        assert client.api_key == "my-key"

    def test_api_key_strips_quotes(self):
        client = LegiScanClient(api_key="'quoted-key'")
        assert client.api_key == "quoted-key"

    def test_api_key_strips_double_quotes(self):
        client = LegiScanClient(api_key='"double-quoted"')
        assert client.api_key == "double-quoted"

    @patch.dict("os.environ", {"LEGISCAN_API_KEY": "env-key-456"})
    def test_api_key_from_env(self):
        client = LegiScanClient()
        assert client.api_key == "env-key-456"

    @patch.dict("os.environ", {}, clear=True)
    def test_no_api_key_sets_none(self):
        # Remove LEGISCAN_API_KEY if present
        client = LegiScanClient(api_key=None)
        assert client.api_key is None

    def test_query_count_starts_at_zero(self):
        client = LegiScanClient(api_key="k")
        assert client.query_count == 0

    def test_base_url(self):
        assert LegiScanClient.BASE_URL == "https://api.legiscan.com/"


# ==================== STATE_CODES ====================


class TestStateCodes:
    def test_california_lowercase_maps_to_ca(self):
        assert LegiScanClient.STATE_CODES["california"] == "CA"

    def test_ca_maps_to_ca(self):
        assert LegiScanClient.STATE_CODES["CA"] == "CA"

    def test_federal_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["federal"] == "US"

    def test_congress_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["congress"] == "US"

    def test_us_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["US"] == "US"


# ==================== _request ====================


class TestRequest:
    def test_raises_without_api_key(self):
        client = LegiScanClient(api_key=None)
        client.api_key = None  # Ensure it's None
        with pytest.raises(ValueError, match="LegiScan API key required"):
            client._request("getSearch")

    def test_successful_request_returns_json(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK", "searchresult": {}}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        result = client._request("getSearch", {"state": "CA"})

        assert result == {"status": "OK", "searchresult": {}}
        assert client.query_count == 1

    def test_increments_query_count(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client._request("op1")
        client._request("op2")

        assert client.query_count == 2

    def test_passes_api_key_and_operation(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client._request("getBill", {"id": 42})

        call_kwargs = client.session.get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        assert params["key"] == "test-key-123"
        assert params["op"] == "getBill"
        assert params["id"] == 42

    def test_error_status_returns_empty_dict(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "ERROR",
            "alert": {"message": "Rate limit exceeded"},
        }
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        result = client._request("getSearch")

        assert result == {}

    def test_request_exception_returns_empty_dict(self, client):
        client.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("timeout")
        )

        result = client._request("getSearch")

        assert result == {}

    def test_http_error_returns_empty_dict(self, client):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        client.session.get = MagicMock(return_value=mock_response)

        result = client._request("getSearch")

        assert result == {}

    def test_no_extra_params_when_none(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client._request("getSessions")

        call_kwargs = client.session.get.call_args
        params = call_kwargs[1].get("params", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
        assert params == {"key": "test-key-123", "op": "getSessions"}


# ==================== search_bills ====================


class TestSearchBills:
    def test_returns_parsed_bills(self, client, bill_search_result):
        api_response = {
            "status": "OK",
            "searchresult": {
                "summary": {"count": 1, "page": 1, "page_total": 1},
                "0": bill_search_result,
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="housing density")

        assert len(bills) == 1
        assert bills[0]["bill_id"] == 1234567
        assert bills[0]["bill_number"] == "AB-1234"
        assert bills[0]["title"] == "Housing Density Reform Act"
        assert bills[0]["description"] == "Increases allowable density in residential zones"
        assert bills[0]["state"] == "CA"
        assert bills[0]["status"] == 2
        assert bills[0]["status_date"] == "2026-03-15"
        assert bills[0]["url"] == "https://legiscan.com/CA/bill/AB1234/2025"
        assert bills[0]["last_action"] == "Set for hearing April 2"
        assert bills[0]["last_action_date"] == "2026-03-20"

    def test_skips_summary_key(self, client, bill_search_result):
        api_response = {
            "status": "OK",
            "searchresult": {
                "summary": {"count": 1},
                "0": bill_search_result,
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="housing")

        assert len(bills) == 1
        # Summary should not appear as a bill
        assert all(b["bill_number"] != "summary" for b in bills)

    def test_respects_limit(self, client):
        search_results = {
            "summary": {"count": 5},
        }
        for i in range(5):
            search_results[str(i)] = {
                "bill_id": 100 + i,
                "bill_number": f"AB-{100 + i}",
                "title": f"Bill {i}",
            }
        api_response = {"status": "OK", "searchresult": search_results}
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="test", limit=3)

        assert len(bills) == 3

    def test_empty_results_returns_empty_list(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="nonexistent")

        assert bills == []

    def test_api_failure_returns_empty_list(self, client):
        client.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("fail")
        )

        bills = client.search_bills(state="CA", query="housing")

        assert bills == []

    def test_state_code_mapping_applied(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK", "searchresult": {}}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client.search_bills(state="california", query="test")

        params = client.session.get.call_args[1]["params"]
        assert params["state"] == "CA"

    def test_unknown_state_passed_through(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK", "searchresult": {}}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client.search_bills(state="NY", query="test")

        params = client.session.get.call_args[1]["params"]
        assert params["state"] == "NY"

    def test_skips_non_dict_entries(self, client):
        api_response = {
            "status": "OK",
            "searchresult": {
                "summary": {"count": 1},
                "0": {"bill_id": 100, "bill_number": "AB-100", "title": "Real"},
                "1": "not a dict",
                "2": 42,
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="test")

        assert len(bills) == 1
        assert bills[0]["bill_id"] == 100

    def test_skips_dict_without_bill_id(self, client):
        api_response = {
            "status": "OK",
            "searchresult": {
                "summary": {"count": 1},
                "0": {"bill_id": 100, "bill_number": "AB-100"},
                "1": {"title": "Missing bill_id field"},
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.search_bills(state="CA", query="test")

        assert len(bills) == 1
        assert bills[0]["bill_id"] == 100


# ==================== get_bill_details ====================


class TestGetBillDetails:
    def test_returns_bill_dict(self, client, bill_detail_response):
        mock_response = MagicMock()
        mock_response.json.return_value = bill_detail_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        result = client.get_bill_details(1234567)

        assert result["bill_id"] == 1234567
        assert result["bill_number"] == "AB-1234"
        assert result["title"] == "Housing Density Reform Act"
        assert len(result["history"]) == 3

    def test_returns_none_on_missing_bill(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        result = client.get_bill_details(9999999)

        assert result is None

    def test_returns_none_on_api_failure(self, client):
        client.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("fail")
        )

        result = client.get_bill_details(1234567)

        assert result is None


# ==================== get_master_list ====================


class TestGetMasterList:
    def test_returns_bill_list(self, client):
        api_response = {
            "status": "OK",
            "masterlist": {
                "session": {"session_id": 2000},
                "0": {"bill_id": 100, "bill_number": "AB-100"},
                "1": {"bill_id": 101, "bill_number": "SB-50"},
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.get_master_list(state="CA")

        assert len(bills) == 2
        bill_ids = {b["bill_id"] for b in bills}
        assert bill_ids == {100, 101}

    def test_skips_session_metadata(self, client):
        api_response = {
            "status": "OK",
            "masterlist": {
                "session": {"session_id": 2000, "session_name": "2025-2026"},
                "0": {"bill_id": 100, "bill_number": "AB-100"},
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.get_master_list(state="CA")

        # session metadata should be excluded (no bill_id key)
        assert len(bills) == 1
        assert bills[0]["bill_id"] == 100

    def test_empty_masterlist_returns_empty(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        bills = client.get_master_list(state="CA")

        assert bills == []

    def test_state_code_mapping_applied(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK", "masterlist": {}}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client.get_master_list(state="federal")

        params = client.session.get.call_args[1]["params"]
        assert params["state"] == "US"

    def test_session_id_passed_when_provided(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK", "masterlist": {}}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        client.get_master_list(state="CA", session_id=2000)

        params = client.session.get.call_args[1]["params"]
        assert params["id"] == 2000


# ==================== get_recent_bills ====================


class TestGetRecentBills:
    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_deduplicates_by_bill_id(self, mock_sleep, client):
        """Bills appearing for multiple keywords should be deduplicated."""
        bill_a = {"bill_id": 100, "bill_number": "AB-100", "last_action_date": "2026-04-01"}
        bill_b = {"bill_id": 101, "bill_number": "SB-50", "last_action_date": "2026-04-01"}

        # Both keywords return bill_a; second also returns bill_b
        def mock_search(state, query, limit):
            if query == "housing":
                return [bill_a]
            elif query == "density":
                return [bill_a, bill_b]
            return []

        client.search_bills = MagicMock(side_effect=mock_search)

        result = client.get_recent_bills(
            state="CA", topic_keywords=["housing", "density"], days_back=30
        )

        assert len(result) == 2
        result_ids = [b["bill_id"] for b in result]
        assert result_ids == [100, 101]

    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_filters_old_bills(self, mock_sleep, client):
        """Bills with last_action_date older than days_back are excluded."""
        recent_bill = {"bill_id": 100, "last_action_date": "2026-04-05"}
        old_bill = {"bill_id": 101, "last_action_date": "2025-01-01"}

        client.search_bills = MagicMock(return_value=[recent_bill, old_bill])

        result = client.get_recent_bills(
            state="CA", topic_keywords=["housing"], days_back=30
        )

        assert len(result) == 1
        assert result[0]["bill_id"] == 100

    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_empty_keywords_returns_empty(self, mock_sleep, client):
        result = client.get_recent_bills(state="CA", topic_keywords=[], days_back=30)

        assert result == []

    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_none_keywords_returns_empty(self, mock_sleep, client):
        result = client.get_recent_bills(state="CA", topic_keywords=None, days_back=30)

        assert result == []

    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_bills_without_bill_id_excluded_from_dedup(self, mock_sleep, client):
        bill_with_id = {"bill_id": 100, "last_action_date": "2026-04-05"}
        bill_no_id = {"last_action_date": "2026-04-05"}

        client.search_bills = MagicMock(return_value=[bill_with_id, bill_no_id])

        result = client.get_recent_bills(
            state="CA", topic_keywords=["housing"], days_back=30
        )

        assert len(result) == 1
        assert result[0]["bill_id"] == 100

    @patch("civicos_extraction.clients.legiscan.time.sleep")
    def test_missing_last_action_date_excluded(self, mock_sleep, client):
        """Bills without last_action_date get empty string, which is < any cutoff."""
        bill_no_date = {"bill_id": 200}

        client.search_bills = MagicMock(return_value=[bill_no_date])

        result = client.get_recent_bills(
            state="CA", topic_keywords=["housing"], days_back=30
        )

        assert result == []


# ==================== get_session_calendar ====================


class TestGetSessionCalendar:
    def test_returns_parsed_events(self, client, calendar_response):
        mock_response = MagicMock()
        mock_response.json.return_value = calendar_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        events = client.get_session_calendar(session_id=2000)

        assert len(events) == 2
        assert events[0]["date"] == "2026-04-02"
        assert events[0]["description"] == "Assembly Housing Committee"
        assert events[0]["location"] == "Room 4202"
        assert events[0]["type"] == "hearing"
        assert events[0]["type_id"] == 1
        assert len(events[0]["bills"]) == 2
        assert events[0]["bills"][0]["bill_id"] == 1234567
        assert events[0]["bills"][0]["bill_number"] == "AB-1234"
        assert events[0]["bills"][0]["title"] == "Housing Density Reform Act"

    def test_event_without_bills_has_empty_list(self, client, calendar_response):
        mock_response = MagicMock()
        mock_response.json.return_value = calendar_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        events = client.get_session_calendar(session_id=2000)

        assert events[1]["bills"] == []

    def test_no_calendar_returns_empty(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        events = client.get_session_calendar(session_id=9999)

        assert events == []

    def test_non_dict_items_skipped(self, client):
        api_response = {
            "calendar": {
                "0": {
                    "date": "2026-04-02",
                    "description": "Real event",
                    "bills": [],
                },
                "1": "not a dict",
                "2": 42,
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        events = client.get_session_calendar(session_id=2000)

        assert len(events) == 1
        assert events[0]["date"] == "2026-04-02"

    def test_bills_field_not_list_treated_as_empty(self, client):
        api_response = {
            "calendar": {
                "0": {
                    "date": "2026-04-02",
                    "description": "Event with bad bills field",
                    "bills": "not a list",
                },
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        events = client.get_session_calendar(session_id=2000)

        assert len(events) == 1
        assert events[0]["bills"] == []


# ==================== get_bill_history ====================


class TestGetBillHistory:
    def test_returns_formatted_history(self, client, bill_detail_response):
        mock_response = MagicMock()
        mock_response.json.return_value = bill_detail_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        history = client.get_bill_history(1234567)

        assert len(history) == 3
        assert history[0]["date"] == "2026-01-15"
        assert history[0]["action"] == "Introduced"
        assert history[0]["chamber"] == "Assembly"
        assert history[0]["chamber_id"] == 1
        assert history[0]["importance"] == 1

        assert history[2]["date"] == "2026-03-20"
        assert history[2]["action"] == "Set for hearing April 2"
        assert history[2]["importance"] == 3

    def test_returns_empty_when_bill_not_found(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "OK"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        history = client.get_bill_history(9999999)

        assert history == []

    def test_filters_non_dict_history_entries(self, client):
        detail_response = {
            "bill": {
                "bill_id": 100,
                "history": [
                    {"date": "2026-01-15", "action": "Introduced"},
                    "not a dict",
                    42,
                    {"date": "2026-02-10", "action": "Referred"},
                ],
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = detail_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        history = client.get_bill_history(100)

        assert len(history) == 2
        assert history[0]["action"] == "Introduced"
        assert history[1]["action"] == "Referred"

    def test_defaults_for_missing_fields(self, client):
        detail_response = {
            "bill": {
                "bill_id": 100,
                "history": [{"date": "2026-01-15"}],
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = detail_response
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        history = client.get_bill_history(100)

        assert len(history) == 1
        assert history[0]["action"] == ""
        assert history[0]["chamber"] == ""
        assert history[0]["chamber_id"] is None
        assert history[0]["importance"] == 0


# ==================== get_query_stats ====================


class TestGetQueryStats:
    def test_initial_stats(self, client):
        stats = client.get_query_stats()

        assert stats["queries_this_session"] == 0
        assert stats["monthly_limit"] == 30000
        assert stats["estimated_remaining"] == 30000

    def test_stats_after_queries(self, client):
        client.query_count = 150

        stats = client.get_query_stats()

        assert stats["queries_this_session"] == 150
        assert stats["monthly_limit"] == 30000
        assert stats["estimated_remaining"] == 29850


# ==================== TOPIC_KEYWORDS ====================


class TestTopicKeywords:
    def test_housing_includes_core_terms(self):
        assert "housing" in TOPIC_KEYWORDS["housing"]
        assert "affordable housing" in TOPIC_KEYWORDS["housing"]
        assert "ADU" in TOPIC_KEYWORDS["housing"]
        assert "RHNA" in TOPIC_KEYWORDS["housing"]

    def test_all_topics_have_keywords(self):
        expected_topics = {"housing", "transportation", "environment", "budget", "education"}
        assert set(TOPIC_KEYWORDS.keys()) == expected_topics

    def test_all_keyword_lists_non_empty(self):
        for topic, keywords in TOPIC_KEYWORDS.items():
            assert len(keywords) >= 3, f"Topic '{topic}' has fewer than 3 keywords"


# ==================== _MONTH_MAP ====================


class TestMonthMap:
    def test_full_month_names(self):
        assert _MONTH_MAP["january"] == 1
        assert _MONTH_MAP["june"] == 6
        assert _MONTH_MAP["december"] == 12

    def test_abbreviated_month_names(self):
        assert _MONTH_MAP["jan"] == 1
        assert _MONTH_MAP["feb"] == 2
        assert _MONTH_MAP["sep"] == 9
        assert _MONTH_MAP["sept"] == 9

    def test_may_is_both_full_and_short(self):
        assert _MONTH_MAP["may"] == 5


# ==================== parse_hearing_date ====================


class TestParseHearingDate:
    def test_heard_in_committee_pattern(self):
        result = parse_hearing_date("May be heard in committee March 8", reference_year=2026)

        assert result["hearing_date"] == "2026-03-08"

    def test_set_for_hearing_pattern(self):
        result = parse_hearing_date("Set for hearing April 2", reference_year=2026)

        assert result["hearing_date"] == "2026-04-02"

    def test_hearing_scheduled_with_year(self):
        result = parse_hearing_date("Hearing scheduled for March 8, 2027")

        assert result["hearing_date"] == "2027-03-08"

    def test_hearing_set_for_pattern(self):
        result = parse_hearing_date("Hearing set for June 15", reference_year=2026)

        assert result["hearing_date"] == "2026-06-15"

    def test_committee_hearing_pattern(self):
        result = parse_hearing_date("Committee hearing October 20", reference_year=2026)

        assert result["hearing_date"] == "2026-10-20"

    def test_committee_extraction_referred(self):
        result = parse_hearing_date("Referred to Com. on HOUSING", reference_year=2026)

        assert result["committee"] == "Housing"

    def test_committee_extraction_re_referred(self):
        result = parse_hearing_date("Re-referred to Committee on JUDICIARY", reference_year=2026)

        assert result["committee"] == "Judiciary"

    def test_committee_extraction_in_committee(self):
        result = parse_hearing_date(
            "Discussed in committee on Public Safety",
            reference_year=2026,
        )

        assert result["committee"] == "Public Safety"

    def test_both_date_and_committee(self):
        result = parse_hearing_date(
            "Referred to Com. on HOUSING. Set for hearing April 2",
            reference_year=2026,
        )

        assert result["hearing_date"] == "2026-04-02"
        assert result["committee"] == "Housing"

    def test_none_input_returns_none(self):
        result = parse_hearing_date(None)

        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_hearing_date("")

        assert result is None

    def test_no_hearing_info_returns_none(self):
        result = parse_hearing_date("Introduced in Assembly")

        assert result is None

    def test_invalid_day_skipped(self):
        # Day 32 is invalid — should not produce a result from that pattern
        result = parse_hearing_date("Set for hearing February 32", reference_year=2026)

        assert result is None

    def test_invalid_month_returns_none(self):
        result = parse_hearing_date("Set for hearing Smarch 15", reference_year=2026)

        assert result is None

    def test_case_insensitive_month(self):
        result = parse_hearing_date("Set for hearing APRIL 2", reference_year=2026)

        assert result["hearing_date"] == "2026-04-02"

    def test_abbreviated_month(self):
        result = parse_hearing_date("Committee hearing Sep 14", reference_year=2026)

        assert result["hearing_date"] == "2026-09-14"

    def test_committee_name_title_cased(self):
        result = parse_hearing_date("Referred to Com. on ENVIRONMENTAL QUALITY")

        assert result["committee"] == "Environmental Quality"

    def test_february_29_in_non_leap_year_skipped(self):
        result = parse_hearing_date("Set for hearing February 29", reference_year=2025)

        assert result is None

    def test_february_29_in_leap_year_accepted(self):
        result = parse_hearing_date("Set for hearing February 29", reference_year=2028)

        assert result["hearing_date"] == "2028-02-29"


# ==================== parse_hearing_events_from_legislation ====================


class TestParseHearingEventsFromLegislation:
    def test_extracts_events_from_bills(self):
        bills = [
            {
                "bill_id": 100,
                "bill_number": "AB-100",
                "last_action": "Set for hearing April 2",
            },
            {
                "bill_id": 101,
                "bill_number": "SB-50",
                "last_action": "Referred to Com. on HOUSING. Hearing scheduled for March 15",
            },
        ]

        events = parse_hearing_events_from_legislation(bills, state="CA", reference_year=2026)

        assert len(events) == 2
        assert events[0]["bill_id"] == 100
        assert events[0]["state"] == "CA"
        assert events[0]["event_type"] == "hearing"
        assert events[0]["event_date"] == "2026-04-02"
        assert events[0]["source"] == "last_action_parse"

        assert events[1]["bill_id"] == 101
        assert events[1]["event_date"] == "2026-03-15"
        assert events[1]["committee"] == "Housing"

    def test_skips_bills_without_hearing_dates(self):
        bills = [
            {"bill_id": 100, "last_action": "Introduced in Assembly"},
            {"bill_id": 101, "last_action": "Set for hearing April 2"},
        ]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert len(events) == 1
        assert events[0]["bill_id"] == 101

    def test_empty_bills_returns_empty(self):
        events = parse_hearing_events_from_legislation([], reference_year=2026)

        assert events == []

    def test_bill_without_last_action_skipped(self):
        bills = [
            {"bill_id": 100},
            {"bill_id": 101, "last_action": None},
            {"bill_id": 102, "last_action": ""},
        ]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert events == []

    def test_uses_bill_number_as_fallback_id(self):
        bills = [
            {
                "bill_number": "AB-999",
                "last_action": "Set for hearing April 2",
            },
        ]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert len(events) == 1
        assert events[0]["bill_id"] == "AB-999"

    def test_description_truncated_to_500_chars(self):
        long_action = "Set for hearing April 2. " + "x" * 500

        bills = [{"bill_id": 100, "last_action": long_action}]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert len(events) == 1
        assert len(events[0]["description"]) == 500

    def test_default_state_is_ca(self):
        bills = [{"bill_id": 100, "last_action": "Set for hearing April 2"}]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert events[0]["state"] == "CA"

    def test_custom_state(self):
        bills = [{"bill_id": 100, "last_action": "Set for hearing April 2"}]

        events = parse_hearing_events_from_legislation(
            bills, state="NY", reference_year=2026
        )

        assert events[0]["state"] == "NY"

    def test_committee_none_when_not_in_action(self):
        bills = [{"bill_id": 100, "last_action": "Set for hearing April 2"}]

        events = parse_hearing_events_from_legislation(bills, reference_year=2026)

        assert events[0]["committee"] is None

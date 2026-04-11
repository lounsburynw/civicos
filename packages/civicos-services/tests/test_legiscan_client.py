"""
Tests for legiscan_client.py — LegiScan API client for state/federal legislation.

Tests the client's real transformation logic (state code mapping, search result
parsing, dedup, date filtering) by mocking the HTTP layer (requests.Session.get).
The subject under test — LegiScanClient — is never mocked.

To run:
    pytest packages/civicos-services/tests/test_legiscan_client.py -q --override-ini="addopts="
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_services.clients.legiscan_client import (
    LegiScanClient,
    TOPIC_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(api_key: str = "test_key_abc") -> LegiScanClient:
    """Create a client with a stubbed key and no real network session."""
    return LegiScanClient(api_key=api_key)


def _mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


def _raw_search_item(**overrides) -> dict:
    defaults = {
        "bill_id": 1234567,
        "bill_number": "AB-123",
        "title": "Housing Density Bonus Act",
        "description": "Expands density bonus for affordable housing",
        "state": "CA",
        "session": "2025-2026 Regular Session",
        "status": "1",
        "status_date": "2025-03-15",
        "url": "https://legiscan.com/CA/bill/AB123/2025",
        "last_action": "Introduced",
        "last_action_date": "2025-03-15",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_uses_explicit_key(self):
        client = LegiScanClient(api_key="explicit_key")
        assert client.api_key == "explicit_key"

    def test_strips_double_quotes(self):
        client = LegiScanClient(api_key='"quoted_key"')
        assert client.api_key == "quoted_key"

    def test_strips_single_quotes(self):
        client = LegiScanClient(api_key="'single_quoted'")
        assert client.api_key == "single_quoted"

    def test_strips_mixed_quotes(self):
        client = LegiScanClient(api_key="'\"weird\"'")
        assert client.api_key == "weird"

    def test_falls_back_to_env_var(self, monkeypatch):
        monkeypatch.setenv("LEGISCAN_API_KEY", "from_env")
        client = LegiScanClient()
        assert client.api_key == "from_env"

    def test_strips_env_var_quotes(self, monkeypatch):
        monkeypatch.setenv("LEGISCAN_API_KEY", "'env_quoted'")
        client = LegiScanClient()
        assert client.api_key == "env_quoted"

    def test_explicit_key_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv("LEGISCAN_API_KEY", "env_key")
        client = LegiScanClient(api_key="explicit")
        assert client.api_key == "explicit"

    def test_missing_key_leaves_none(self, monkeypatch):
        monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
        client = LegiScanClient()
        assert client.api_key is None

    def test_query_count_starts_at_zero(self):
        client = _make_client()
        assert client.query_count == 0

    def test_session_is_reused_across_calls(self):
        """Session must be shared so connection pooling and cookies persist."""
        client = _make_client()
        session_before = client.session
        # Make a fake call that would increment state
        client.session.get = MagicMock(
            return_value=_mock_response(200, {"status": "OK"})
        )
        client._request("getSearch")
        # Same session object is still used
        assert client.session is session_before


# ---------------------------------------------------------------------------
# _request
# ---------------------------------------------------------------------------


class TestRequest:
    def test_no_api_key_raises_value_error(self, monkeypatch):
        monkeypatch.delenv("LEGISCAN_API_KEY", raising=False)
        client = LegiScanClient()
        with pytest.raises(ValueError, match="LegiScan API key required"):
            client._request("getSearch", {"state": "CA"})

    def test_success_returns_json(self):
        client = _make_client()
        expected = {"status": "OK", "searchresult": {}}
        client.session.get = MagicMock(return_value=_mock_response(200, expected))

        result = client._request("getSearch", {"state": "CA"})
        assert result == expected

    def test_increments_query_count(self):
        client = _make_client()
        client.session.get = MagicMock(return_value=_mock_response(200, {"status": "OK"}))

        client._request("getSearch")
        client._request("getBill")
        assert client.query_count == 2

    def test_passes_operation_and_key_as_params(self):
        client = _make_client(api_key="my_key")
        payload = {"status": "OK", "bill": {"bill_id": 42}}
        client.session.get = MagicMock(return_value=_mock_response(200, payload))

        result = client._request("getBill", {"id": 42})

        assert result == payload
        params = client.session.get.call_args.kwargs["params"]
        assert params["key"] == "my_key"
        assert params["op"] == "getBill"
        assert params["id"] == 42

    def test_custom_params_merged_with_defaults(self):
        client = _make_client()
        payload = {"status": "OK", "searchresult": {"0": {"bill_id": 1}}}
        client.session.get = MagicMock(return_value=_mock_response(200, payload))

        result = client._request("getSearch", {"state": "CA", "query": "housing"})

        assert result == payload
        params = client.session.get.call_args.kwargs["params"]
        assert params["state"] == "CA"
        assert params["query"] == "housing"
        assert params["op"] == "getSearch"

    def test_uses_thirty_second_timeout(self):
        client = _make_client()
        payload = {"status": "OK", "data": "x"}
        client.session.get = MagicMock(return_value=_mock_response(200, payload))

        result = client._request("getSearch")

        assert result == payload
        assert client.session.get.call_args.kwargs["timeout"] == 30

    def test_hits_base_url(self):
        client = _make_client()
        payload = {"status": "OK", "data": "x"}
        client.session.get = MagicMock(return_value=_mock_response(200, payload))

        result = client._request("getSearch")

        assert result == payload
        assert client.session.get.call_args.args[0] == "https://api.legiscan.com/"

    def test_api_error_status_returns_empty_dict(self):
        client = _make_client()
        error_payload = {"status": "ERROR", "alert": {"message": "invalid key"}}
        client.session.get = MagicMock(return_value=_mock_response(200, error_payload))

        result = client._request("getSearch")
        assert result == {}

    def test_api_error_still_increments_query_count(self):
        client = _make_client()
        error_payload = {"status": "ERROR", "alert": {"message": "invalid key"}}
        client.session.get = MagicMock(return_value=_mock_response(200, error_payload))

        client._request("getSearch")
        assert client.query_count == 1

    def test_request_exception_returns_empty_dict(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=requests.exceptions.Timeout("timeout"))

        result = client._request("getSearch")
        assert result == {}

    def test_connection_error_returns_empty_dict(self):
        client = _make_client()
        client.session.get = MagicMock(
            side_effect=requests.exceptions.ConnectionError("network down")
        )

        result = client._request("getSearch")
        assert result == {}

    def test_http_error_via_raise_for_status_returns_empty_dict(self):
        client = _make_client()
        bad = _mock_response(500, {})
        bad.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        client.session.get = MagicMock(return_value=bad)

        result = client._request("getSearch")
        assert result == {}

    def test_exception_does_not_increment_query_count(self):
        client = _make_client()
        client.session.get = MagicMock(side_effect=requests.exceptions.Timeout("t"))

        client._request("getSearch")
        assert client.query_count == 0

    def test_none_params_still_sends_key_and_op(self):
        client = _make_client(api_key="k")
        client.session.get = MagicMock(return_value=_mock_response(200, {"status": "OK"}))

        client._request("getSearch", None)

        params = client.session.get.call_args.kwargs["params"]
        assert params == {"key": "k", "op": "getSearch"}


# ---------------------------------------------------------------------------
# search_bills
# ---------------------------------------------------------------------------


class TestSearchBills:
    def test_maps_california_to_ca(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1)}}
        )

        bills = client.search_bills(state="california", query="housing")

        assert len(bills) == 1
        assert bills[0]["bill_id"] == 1
        assert client._request.call_args.args[1]["state"] == "CA"

    def test_maps_federal_to_us(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1, state="US")}}
        )

        bills = client.search_bills(state="federal", query="defense")

        assert bills[0]["state"] == "US"
        assert client._request.call_args.args[1]["state"] == "US"

    def test_maps_congress_to_us(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=2, state="US")}}
        )

        bills = client.search_bills(state="congress", query="defense")

        assert bills[0]["state"] == "US"
        assert client._request.call_args.args[1]["state"] == "US"

    def test_unknown_state_passed_through(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=3, state="NY")}}
        )

        bills = client.search_bills(state="NY", query="x")

        assert bills[0]["state"] == "NY"
        assert client._request.call_args.args[1]["state"] == "NY"

    def test_defaults_to_current_year(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1)}}
        )

        bills = client.search_bills(state="CA", query="x")

        assert len(bills) == 1
        assert client._request.call_args.args[1]["year"] == datetime.now().year

    def test_explicit_year_overrides_default(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1)}}
        )

        bills = client.search_bills(state="CA", query="x", year=2023)

        assert len(bills) == 1
        assert client._request.call_args.args[1]["year"] == 2023

    def test_none_query_becomes_empty_string(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1)}}
        )

        bills = client.search_bills(state="CA", query=None)

        assert len(bills) == 1
        assert client._request.call_args.args[1]["query"] == ""

    def test_uses_get_search_operation(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"searchresult": {"0": _raw_search_item(bill_id=1)}}
        )

        bills = client.search_bills(state="CA", query="x")

        assert len(bills) == 1
        assert client._request.call_args.args[0] == "getSearch"

    def test_empty_response_returns_empty_list(self):
        client = _make_client()
        client._request = MagicMock(return_value={})

        result = client.search_bills(state="CA", query="housing")
        assert result == []

    def test_missing_searchresult_returns_empty_list(self):
        client = _make_client()
        client._request = MagicMock(return_value={"status": "OK"})

        result = client.search_bills(state="CA", query="housing")
        assert result == []

    def test_parses_single_bill(self):
        client = _make_client()
        raw = _raw_search_item(
            bill_id=9999,
            bill_number="AB-42",
            title="Transit Equity Act",
        )
        client._request = MagicMock(
            return_value={"searchresult": {"0": raw, "summary": {"query": "transit"}}}
        )

        bills = client.search_bills(state="CA", query="transit")
        assert len(bills) == 1
        assert bills[0]["bill_id"] == 9999
        assert bills[0]["bill_number"] == "AB-42"
        assert bills[0]["title"] == "Transit Equity Act"

    def test_skips_summary_metadata_key(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={
                "searchresult": {
                    "summary": {"page": 1, "count": 1},
                    "0": _raw_search_item(bill_id=1),
                }
            }
        )

        bills = client.search_bills(state="CA", query="x")
        assert len(bills) == 1
        assert bills[0]["bill_id"] == 1

    def test_skips_items_without_bill_id(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={
                "searchresult": {
                    "0": _raw_search_item(bill_id=10),
                    "1": {"no_bill_id": "junk"},
                    "2": _raw_search_item(bill_id=20),
                }
            }
        )

        bills = client.search_bills(state="CA", query="x")
        assert [b["bill_id"] for b in bills] == [10, 20]

    def test_skips_non_dict_items(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={
                "searchresult": {
                    "0": _raw_search_item(bill_id=1),
                    "1": "a_string_not_a_dict",
                    "2": 42,
                    "3": _raw_search_item(bill_id=2),
                }
            }
        )

        bills = client.search_bills(state="CA", query="x")
        assert [b["bill_id"] for b in bills] == [1, 2]

    def test_limit_caps_result_count(self):
        client = _make_client()
        items = {str(i): _raw_search_item(bill_id=i) for i in range(10)}
        client._request = MagicMock(return_value={"searchresult": items})

        bills = client.search_bills(state="CA", query="x", limit=3)
        assert len(bills) == 3

    def test_limit_larger_than_results_returns_all(self):
        client = _make_client()
        items = {str(i): _raw_search_item(bill_id=i) for i in range(4)}
        client._request = MagicMock(return_value={"searchresult": items})

        bills = client.search_bills(state="CA", query="x", limit=100)
        assert len(bills) == 4

    def test_parsed_bill_contains_all_expected_fields(self):
        client = _make_client()
        raw = _raw_search_item(
            bill_id=555,
            bill_number="SB-10",
            title="Title X",
            description="Desc X",
            state="CA",
            session="2025",
            status="2",
            status_date="2025-04-01",
            url="https://example.com/sb10",
            last_action="Passed committee",
            last_action_date="2025-04-02",
        )
        client._request = MagicMock(return_value={"searchresult": {"0": raw}})

        bill = client.search_bills(state="CA", query="x")[0]
        assert bill == {
            "bill_id": 555,
            "bill_number": "SB-10",
            "title": "Title X",
            "description": "Desc X",
            "state": "CA",
            "session": "2025",
            "status": "2",
            "status_date": "2025-04-01",
            "url": "https://example.com/sb10",
            "last_action": "Passed committee",
            "last_action_date": "2025-04-02",
        }

    def test_missing_optional_fields_preserved_as_none(self):
        client = _make_client()
        # Only bill_id present; other fields absent
        client._request = MagicMock(
            return_value={"searchresult": {"0": {"bill_id": 777}}}
        )

        bill = client.search_bills(state="CA", query="x")[0]
        assert bill["bill_id"] == 777
        assert bill["title"] is None
        assert bill["bill_number"] is None
        assert bill["status"] is None


# ---------------------------------------------------------------------------
# get_bill_details
# ---------------------------------------------------------------------------


class TestGetBillDetails:
    def test_returns_bill_dict_on_success(self):
        client = _make_client()
        bill_payload = {
            "bill_id": 42,
            "title": "Housing Act",
            "sponsors": [{"name": "Jane Doe"}],
        }
        client._request = MagicMock(return_value={"bill": bill_payload})

        result = client.get_bill_details(42)
        assert result == bill_payload

    def test_uses_get_bill_operation(self):
        client = _make_client()
        client._request = MagicMock(return_value={"bill": {"bill_id": 99}})

        result = client.get_bill_details(99)

        assert result == {"bill_id": 99}
        assert client._request.call_args.args[0] == "getBill"

    def test_passes_bill_id_as_id_param(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"bill": {"bill_id": 12345, "title": "Test Bill"}}
        )

        result = client.get_bill_details(12345)

        assert result["bill_id"] == 12345
        assert client._request.call_args.args[1] == {"id": 12345}

    def test_empty_response_returns_none(self):
        client = _make_client()
        client._request = MagicMock(return_value={})

        assert client.get_bill_details(42) is None

    def test_response_without_bill_key_returns_none(self):
        client = _make_client()
        client._request = MagicMock(return_value={"status": "OK"})

        assert client.get_bill_details(42) is None


# ---------------------------------------------------------------------------
# get_master_list
# ---------------------------------------------------------------------------


class TestGetMasterList:
    def test_uses_get_master_list_operation(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"masterlist": {"0": {"bill_id": 1}}}
        )

        bills = client.get_master_list(state="CA")

        assert [b["bill_id"] for b in bills] == [1]
        assert client._request.call_args.args[0] == "getMasterList"

    def test_maps_state_code(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"masterlist": {"0": {"bill_id": 5}}}
        )

        bills = client.get_master_list(state="california")

        assert len(bills) == 1
        assert client._request.call_args.args[1]["state"] == "CA"

    def test_session_id_passed_as_id(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"masterlist": {"0": {"bill_id": 7}}}
        )

        bills = client.get_master_list(state="CA", session_id=2007)

        assert len(bills) == 1
        params = client._request.call_args.args[1]
        assert params["id"] == 2007
        assert params["state"] == "CA"

    def test_no_session_id_omits_id_param(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={"masterlist": {"0": {"bill_id": 8}}}
        )

        bills = client.get_master_list(state="CA")

        assert len(bills) == 1
        params = client._request.call_args.args[1]
        assert "id" not in params

    def test_empty_response_returns_empty_list(self):
        client = _make_client()
        client._request = MagicMock(return_value={})

        assert client.get_master_list(state="CA") == []

    def test_missing_masterlist_returns_empty_list(self):
        client = _make_client()
        client._request = MagicMock(return_value={"status": "OK"})

        assert client.get_master_list(state="CA") == []

    def test_filters_dict_items_with_bill_id(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={
                "masterlist": {
                    "session": {"session_id": 1, "year_start": 2025},  # no bill_id
                    "0": {"bill_id": 111, "title": "A"},
                    "1": {"bill_id": 222, "title": "B"},
                    "2": "not_a_dict",
                }
            }
        )

        bills = client.get_master_list(state="CA")
        ids = sorted(b["bill_id"] for b in bills)
        assert ids == [111, 222]

    def test_returns_full_bill_dicts(self):
        client = _make_client()
        client._request = MagicMock(
            return_value={
                "masterlist": {
                    "0": {"bill_id": 500, "title": "Example", "status": "1"},
                }
            }
        )

        bills = client.get_master_list(state="CA")
        assert bills[0]["title"] == "Example"
        assert bills[0]["status"] == "1"


# ---------------------------------------------------------------------------
# get_recent_bills
# ---------------------------------------------------------------------------


class TestGetRecentBills:
    def test_empty_keywords_returns_empty_list(self):
        client = _make_client()
        client.search_bills = MagicMock()

        with patch(
            "civicos_services.clients.legiscan_client.time.sleep"
        ) as mock_sleep:
            result = client.get_recent_bills(state="CA", topic_keywords=[])

        assert result == []
        client.search_bills.assert_not_called()
        mock_sleep.assert_not_called()

    def test_none_keywords_returns_empty_list(self):
        client = _make_client()
        client.search_bills = MagicMock()

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            result = client.get_recent_bills(state="CA", topic_keywords=None)

        assert result == []

    def test_calls_search_once_per_keyword(self):
        client = _make_client()
        today = datetime.now().strftime("%Y-%m-%d")
        client.search_bills = MagicMock(
            side_effect=[
                [_raw_search_item(bill_id=1, last_action_date=today)],
                [_raw_search_item(bill_id=2, last_action_date=today)],
                [_raw_search_item(bill_id=3, last_action_date=today)],
            ]
        )

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["housing", "transit", "climate"]
            )

        assert sorted(b["bill_id"] for b in bills) == [1, 2, 3]
        assert client.search_bills.call_count == 3
        queries = [c.kwargs["query"] for c in client.search_bills.call_args_list]
        assert queries == ["housing", "transit", "climate"]

    def test_search_bills_called_with_limit_20(self):
        client = _make_client()
        today = datetime.now().strftime("%Y-%m-%d")
        client.search_bills = MagicMock(
            return_value=[_raw_search_item(bill_id=42, last_action_date=today)]
        )

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(state="CA", topic_keywords=["x"])

        assert [b["bill_id"] for b in bills] == [42]
        assert client.search_bills.call_args.kwargs["limit"] == 20

    def test_deduplicates_by_bill_id(self):
        client = _make_client()
        today = datetime.now().strftime("%Y-%m-%d")
        bill_a = _raw_search_item(bill_id=100, last_action_date=today)
        bill_a_dup = _raw_search_item(
            bill_id=100, last_action_date=today, title="dup title"
        )
        bill_b = _raw_search_item(bill_id=200, last_action_date=today)

        client.search_bills = MagicMock(
            side_effect=[[bill_a, bill_b], [bill_a_dup]]
        )

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["housing", "zoning"]
            )

        ids = sorted(b["bill_id"] for b in bills)
        assert ids == [100, 200]
        # The first-seen bill wins, not the dup
        bill_100 = [b for b in bills if b["bill_id"] == 100][0]
        assert bill_100["title"] != "dup title"

    def test_filters_bills_older_than_cutoff(self):
        client = _make_client()
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        recent = _raw_search_item(bill_id=1, last_action_date=recent_date)
        old = _raw_search_item(bill_id=2, last_action_date=old_date)

        client.search_bills = MagicMock(return_value=[recent, old])

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["housing"], days_back=30
            )

        assert [b["bill_id"] for b in bills] == [1]

    def test_missing_last_action_date_excluded(self):
        client = _make_client()
        # Missing last_action_date -> .get returns '' -> '' >= cutoff is False
        client.search_bills = MagicMock(
            return_value=[{"bill_id": 99, "title": "x"}]
        )

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["x"], days_back=30
            )

        assert bills == []

    def test_days_back_controls_cutoff(self):
        client = _make_client()
        ten_days_ago = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        bill = _raw_search_item(bill_id=1, last_action_date=ten_days_ago)
        client.search_bills = MagicMock(return_value=[bill])

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills_wide = client.get_recent_bills(
                state="CA", topic_keywords=["x"], days_back=30
            )
            bills_narrow = client.get_recent_bills(
                state="CA", topic_keywords=["x"], days_back=5
            )

        assert len(bills_wide) == 1
        assert bills_narrow == []

    def test_sleeps_between_keyword_searches(self):
        client = _make_client()
        client.search_bills = MagicMock(return_value=[])

        with patch(
            "civicos_services.clients.legiscan_client.time.sleep"
        ) as mock_sleep:
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["a", "b", "c"]
            )

        assert bills == []
        # One sleep per keyword iteration
        assert mock_sleep.call_count == 3
        # Verify the delay value used
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 0.5

    def test_bills_without_bill_id_dropped_during_dedup(self):
        client = _make_client()
        today = datetime.now().strftime("%Y-%m-%d")
        bill = _raw_search_item(bill_id=1, last_action_date=today)
        orphan = {"bill_id": None, "last_action_date": today, "title": "orphan"}
        client.search_bills = MagicMock(return_value=[bill, orphan])

        with patch("civicos_services.clients.legiscan_client.time.sleep"):
            bills = client.get_recent_bills(
                state="CA", topic_keywords=["x"]
            )

        assert len(bills) == 1
        assert bills[0]["bill_id"] == 1


# ---------------------------------------------------------------------------
# get_query_stats
# ---------------------------------------------------------------------------


class TestQueryStats:
    def test_reports_zero_on_fresh_client(self):
        client = _make_client()
        stats = client.get_query_stats()
        assert stats["queries_this_session"] == 0
        assert stats["monthly_limit"] == 30000
        assert stats["estimated_remaining"] == 30000

    def test_reports_count_after_requests(self):
        client = _make_client()
        client.query_count = 7

        stats = client.get_query_stats()
        assert stats["queries_this_session"] == 7
        assert stats["estimated_remaining"] == 29993

    def test_reports_remaining_after_many_queries(self):
        client = _make_client()
        client.query_count = 29999

        stats = client.get_query_stats()
        assert stats["estimated_remaining"] == 1

    def test_stats_keys_exact(self):
        client = _make_client()
        stats = client.get_query_stats()
        assert set(stats.keys()) == {
            "queries_this_session",
            "monthly_limit",
            "estimated_remaining",
        }


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


class TestStateCodes:
    def test_california_maps_to_ca(self):
        assert LegiScanClient.STATE_CODES["california"] == "CA"

    def test_ca_maps_to_ca(self):
        assert LegiScanClient.STATE_CODES["CA"] == "CA"

    def test_federal_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["federal"] == "US"

    def test_congress_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["congress"] == "US"

    def test_us_maps_to_us(self):
        assert LegiScanClient.STATE_CODES["US"] == "US"


class TestTopicKeywords:
    def test_housing_topic_includes_core_terms(self):
        assert "housing" in TOPIC_KEYWORDS["housing"]
        assert "zoning" in TOPIC_KEYWORDS["housing"]
        assert "ADU" in TOPIC_KEYWORDS["housing"]
        assert "RHNA" in TOPIC_KEYWORDS["housing"]

    def test_transportation_topic_includes_transit(self):
        assert "transit" in TOPIC_KEYWORDS["transportation"]
        assert "bicycle" in TOPIC_KEYWORDS["transportation"]

    def test_environment_topic_includes_climate(self):
        assert "climate" in TOPIC_KEYWORDS["environment"]
        assert "emissions" in TOPIC_KEYWORDS["environment"]

    def test_budget_topic_includes_tax(self):
        assert "tax" in TOPIC_KEYWORDS["budget"]
        assert "appropriation" in TOPIC_KEYWORDS["budget"]

    def test_education_topic_includes_school(self):
        assert "school" in TOPIC_KEYWORDS["education"]
        assert "teacher" in TOPIC_KEYWORDS["education"]

    def test_five_topic_categories(self):
        assert set(TOPIC_KEYWORDS.keys()) == {
            "housing",
            "transportation",
            "environment",
            "budget",
            "education",
        }

    def test_base_url_constant(self):
        assert LegiScanClient.BASE_URL == "https://api.legiscan.com/"

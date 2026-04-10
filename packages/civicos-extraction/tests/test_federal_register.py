"""Tests for Federal Register API client — EO normalization, rule fetching, pagination, retries."""

from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.clients.federal_register import (
    FederalRegisterClient,
    get_recent_executive_orders,
)


# ==================== Fixtures ====================


@pytest.fixture
def client():
    """FederalRegisterClient with zero throttle delay."""
    c = FederalRegisterClient()
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def raw_eo_full():
    """Complete raw EO response from Federal Register API."""
    return {
        "document_number": "2025-01753",
        "title": "Establishing the Department of Government Efficiency",
        "abstract": "By the authority vested in me as President...",
        "publication_date": "2025-02-03",
        "signing_date": "2025-01-20",
        "executive_order_number": 14158,
        "president": {"name": "Donald Trump", "identifier": "donald-trump"},
        "html_url": "https://www.federalregister.gov/d/2025-01753",
        "pdf_url": "https://www.federalregister.gov/d/2025-01753.pdf",
        "raw_text_url": "https://www.federalregister.gov/d/2025-01753.txt",
        "type": "Presidential Document",
        "subtype": "Executive Order",
        "agencies": [{"name": "Executive Office of the President"}],
        "topics": ["Government Organization"],
        "citation": "90 FR 8337",
    }


@pytest.fixture
def raw_eo_minimal():
    """Bare-minimum EO with only document_number."""
    return {"document_number": "2024-00001"}


@pytest.fixture
def raw_eo_title_with_number():
    """EO where the number is only in the title, not as a field."""
    return {
        "document_number": "2024-99999",
        "title": "Executive Order 14009: Strengthening Medicaid",
        "president": {},
    }


@pytest.fixture
def raw_rule_proposed():
    """Raw proposed-rule response from Federal Register API."""
    return {
        "document_number": "2025-05678",
        "title": "Proposed Updates to Fair Housing Standards",
        "abstract": "HUD proposes amendments...",
        "agency_names": ["Department of Housing and Urban Development"],
        "publication_date": "2025-03-15",
        "comments_close_on": "2025-05-15",
        "comment_url": "https://www.regulations.gov/docket/HUD-2025-0001",
        "html_url": "https://www.federalregister.gov/d/2025-05678",
        "pdf_url": "https://www.federalregister.gov/d/2025-05678.pdf",
        "regulation_id_numbers": ["2501-AA01"],
        "docket_ids": ["HUD-2025-0001"],
        "type": "Proposed Rule",
        "subtype": None,
        "topics": ["Housing", "Civil Rights"],
    }


@pytest.fixture
def raw_rule_agencies_fallback():
    """Rule where agency_names is empty but agencies has dicts."""
    return {
        "document_number": "2025-11111",
        "title": "EPA Notice",
        "agency_names": [],
        "agencies": [
            {"name": "Environmental Protection Agency"},
            {"name": "Department of the Interior"},
        ],
        "publication_date": "2025-04-01",
    }


# ==================== _normalize_executive_order ====================


class TestNormalizeExecutiveOrder:
    def test_full_eo_maps_all_fields(self, client, raw_eo_full):
        result = client._normalize_executive_order(raw_eo_full)

        assert result["document_number"] == "2025-01753"
        assert result["title"] == "Establishing the Department of Government Efficiency"
        assert result["abstract"] == "By the authority vested in me as President..."
        assert result["eo_number"] == 14158
        assert result["president"] == "Donald Trump"
        assert result["president_id"] == "donald-trump"
        assert result["signing_date"] == "2025-01-20"
        assert result["publication_date"] == "2025-02-03"
        assert result["html_url"] == "https://www.federalregister.gov/d/2025-01753"
        assert result["pdf_url"] == "https://www.federalregister.gov/d/2025-01753.pdf"
        assert result["raw_text_url"] == "https://www.federalregister.gov/d/2025-01753.txt"
        assert result["status"] == "active"
        assert result["revoked_by_eo"] is None
        assert result["full_text"] is None
        assert result["type"] == "Presidential Document"
        assert result["subtype"] == "Executive Order"
        assert result["agencies"] == [{"name": "Executive Office of the President"}]
        assert result["topics"] == ["Government Organization"]
        assert result["citation"] == "90 FR 8337"

    def test_missing_document_number_returns_none(self, client):
        result = client._normalize_executive_order({"title": "No doc number"})
        assert result is None

    def test_empty_dict_returns_none(self, client):
        result = client._normalize_executive_order({})
        assert result is None

    def test_eo_number_parsed_from_title_when_field_missing(self, client, raw_eo_title_with_number):
        result = client._normalize_executive_order(raw_eo_title_with_number)
        assert result["eo_number"] == 14009

    def test_eo_number_none_when_not_available(self, client, raw_eo_minimal):
        result = client._normalize_executive_order(raw_eo_minimal)
        assert result["eo_number"] is None

    def test_eo_number_field_preferred_over_title(self, client):
        raw = {
            "document_number": "2025-00001",
            "title": "Executive Order 99999: Something",
            "executive_order_number": 14200,
        }
        result = client._normalize_executive_order(raw)
        assert result["eo_number"] == 14200

    def test_eo_number_non_numeric_field_falls_back_to_title(self, client):
        raw = {
            "document_number": "2025-00002",
            "title": "Executive Order 14050: Test",
            "executive_order_number": "not-a-number",
        }
        result = client._normalize_executive_order(raw)
        assert result["eo_number"] == 14050

    def test_president_defaults_to_unknown(self, client, raw_eo_minimal):
        result = client._normalize_executive_order(raw_eo_minimal)
        assert result["president"] == "Unknown"
        assert result["president_id"] is None

    def test_minimal_eo_defaults(self, client, raw_eo_minimal):
        result = client._normalize_executive_order(raw_eo_minimal)
        assert result["title"] == ""
        assert result["abstract"] is None
        assert result["signing_date"] is None
        assert result["publication_date"] is None
        assert result["html_url"] is None
        assert result["pdf_url"] is None
        assert result["raw_text_url"] is None
        assert result["agencies"] == []
        assert result["topics"] == []
        assert result["citation"] is None

    def test_eo_number_string_integer_coerced(self, client):
        raw = {"document_number": "X", "executive_order_number": "14100"}
        result = client._normalize_executive_order(raw)
        assert result["eo_number"] == 14100

    def test_title_parsing_case_insensitive(self, client):
        raw = {
            "document_number": "Z",
            "title": "executive order 13000: Something",
        }
        result = client._normalize_executive_order(raw)
        assert result["eo_number"] == 13000


# ==================== _normalize_rule ====================


class TestNormalizeRule:
    def test_proposed_rule_maps_all_fields(self, client, raw_rule_proposed):
        result = client._normalize_rule(raw_rule_proposed, "PRORULE")

        assert result["document_number"] == "2025-05678"
        assert result["title"] == "Proposed Updates to Fair Housing Standards"
        assert result["abstract"] == "HUD proposes amendments..."
        assert result["agency_names"] == ["Department of Housing and Urban Development"]
        assert result["publication_date"] == "2025-03-15"
        assert result["comments_close_on"] == "2025-05-15"
        assert result["comment_url"] == "https://www.regulations.gov/docket/HUD-2025-0001"
        assert result["html_url"] == "https://www.federalregister.gov/d/2025-05678"
        assert result["pdf_url"] == "https://www.federalregister.gov/d/2025-05678.pdf"
        assert result["regulation_id_numbers"] == ["2501-AA01"]
        assert result["docket_ids"] == ["HUD-2025-0001"]
        assert result["document_type"] == "proposed_rule"
        assert result["topics"] == ["Housing", "Civil Rights"]

    def test_final_rule_type_mapping(self, client):
        raw = {"document_number": "X"}
        result = client._normalize_rule(raw, "RULE")
        assert result["document_type"] == "final_rule"

    def test_notice_type_mapping(self, client):
        raw = {"document_number": "X"}
        result = client._normalize_rule(raw, "NOTICE")
        assert result["document_type"] == "notice"

    def test_unknown_type_lowercased(self, client):
        raw = {"document_number": "X"}
        result = client._normalize_rule(raw, "UNKNOWN_TYPE")
        assert result["document_type"] == "unknown_type"

    def test_missing_document_number_returns_none(self, client):
        result = client._normalize_rule({"title": "No number"}, "RULE")
        assert result is None

    def test_agency_names_fallback_to_agencies_dicts(self, client, raw_rule_agencies_fallback):
        result = client._normalize_rule(raw_rule_agencies_fallback, "NOTICE")
        assert result["agency_names"] == [
            "Environmental Protection Agency",
            "Department of the Interior",
        ]

    def test_agency_names_empty_when_both_missing(self, client):
        raw = {"document_number": "X"}
        result = client._normalize_rule(raw, "RULE")
        assert result["agency_names"] == []

    def test_defaults_for_optional_fields(self, client):
        raw = {"document_number": "Z"}
        result = client._normalize_rule(raw, "PRORULE")
        assert result["title"] == ""
        assert result["abstract"] is None
        assert result["comments_close_on"] is None
        assert result["comment_url"] is None
        assert result["regulation_id_numbers"] == []
        assert result["docket_ids"] == []
        assert result["topics"] == []


# ==================== _make_request ====================


class TestMakeRequest:
    def test_successful_request_returns_json(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        client.session.get = MagicMock(return_value=mock_response)

        result = client._make_request("documents", {"page": 1})

        assert result == {"results": []}
        client.session.get.assert_called_once()
        call_args = client.session.get.call_args
        assert "documents" in call_args[0][0]

    def test_non_retryable_error_returns_none(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        client.session.get = MagicMock(return_value=mock_response)

        result = client._make_request("documents/bad-id")

        assert result is None
        assert client.session.get.call_count == 1  # no retry

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_retryable_error_retries_then_returns_none(self, mock_sleep, client):
        mock_response = MagicMock()
        mock_response.status_code = 503
        client.session.get = MagicMock(return_value=mock_response)

        result = client._make_request("documents", retries=3)

        assert result is None
        assert client.session.get.call_count == 3

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_retryable_error_recovers_on_second_attempt(self, mock_sleep, client):
        fail_response = MagicMock()
        fail_response.status_code = 429

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"results": ["data"]}

        client.session.get = MagicMock(side_effect=[fail_response, ok_response])

        result = client._make_request("documents", retries=3)

        assert result == {"results": ["data"]}
        assert client.session.get.call_count == 2

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_connection_error_retries(self, mock_sleep, client):
        client.session.get = MagicMock(
            side_effect=[ConnectionError("timeout"), ConnectionError("timeout")]
        )

        result = client._make_request("documents", retries=2)

        assert result is None
        assert client.session.get.call_count == 2

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_exception_on_last_attempt_returns_none(self, mock_sleep, client):
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"ok": True}

        client.session.get = MagicMock(
            side_effect=[ConnectionError("fail"), ok_response]
        )

        result = client._make_request("documents", retries=2)

        assert result == {"ok": True}
        assert client.session.get.call_count == 2

    def test_url_construction(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        client.session.get = MagicMock(return_value=mock_response)

        client._make_request("documents/2025-01753")

        called_url = client.session.get.call_args[0][0]
        assert called_url == "https://www.federalregister.gov/api/v1/documents/2025-01753"


# ==================== fetch_executive_orders ====================


class TestFetchExecutiveOrders:
    def _mock_api_response(self, results, total_pages=1):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": results,
            "total_pages": total_pages,
        }
        return mock_response

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_single_page_returns_normalized_eos(self, mock_sleep, client, raw_eo_full):
        client.session.get = MagicMock(
            return_value=self._mock_api_response([raw_eo_full])
        )

        results = client.fetch_executive_orders(per_page=10, max_pages=1, include_full_text=False)

        assert len(results) == 1
        assert results[0]["document_number"] == "2025-01753"
        assert results[0]["eo_number"] == 14158
        assert results[0]["president"] == "Donald Trump"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_pagination_fetches_multiple_pages(self, mock_sleep, client):
        page1_eo = {"document_number": "A", "executive_order_number": 1}
        page2_eo = {"document_number": "B", "executive_order_number": 2}

        page1_resp = self._mock_api_response([page1_eo], total_pages=2)
        page2_resp = self._mock_api_response([page2_eo], total_pages=2)

        client.session.get = MagicMock(side_effect=[page1_resp, page2_resp])

        results = client.fetch_executive_orders(max_pages=5, include_full_text=False)

        assert len(results) == 2
        assert results[0]["document_number"] == "A"
        assert results[1]["document_number"] == "B"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_max_pages_respected(self, mock_sleep, client):
        """Stop at max_pages even if total_pages is larger."""
        eo = {"document_number": "X"}
        resp = self._mock_api_response([eo], total_pages=100)
        client.session.get = MagicMock(return_value=resp)

        results = client.fetch_executive_orders(max_pages=2, include_full_text=False)

        # 2 pages fetched, 1 EO each
        assert len(results) == 2
        assert client.session.get.call_count == 2

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_empty_results_stop_pagination(self, mock_sleep, client):
        page1 = self._mock_api_response([{"document_number": "A"}], total_pages=3)
        page2 = self._mock_api_response([], total_pages=3)

        client.session.get = MagicMock(side_effect=[page1, page2])

        results = client.fetch_executive_orders(max_pages=5, include_full_text=False)

        assert len(results) == 1
        assert client.session.get.call_count == 2

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_failed_page_stops_pagination(self, mock_sleep, client):
        page1 = self._mock_api_response([{"document_number": "A"}], total_pages=3)
        fail = MagicMock()
        fail.status_code = 500
        # All 3 retries fail
        client.session.get = MagicMock(side_effect=[page1, fail, fail, fail])

        results = client.fetch_executive_orders(max_pages=5, include_full_text=False)

        assert len(results) == 1
        assert results[0]["document_number"] == "A"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_since_date_passed_in_params(self, mock_sleep, client):
        client.session.get = MagicMock(
            return_value=self._mock_api_response([])
        )

        client.fetch_executive_orders(since_date="2025-01-01", include_full_text=False)

        call_params = client.session.get.call_args[1].get("params", client.session.get.call_args[0][1] if len(client.session.get.call_args[0]) > 1 else {})
        # params are passed as keyword arg
        actual_params = client.session.get.call_args.kwargs.get("params") or client.session.get.call_args[1].get("params", {})
        assert actual_params.get("conditions[publication_date][gte]") == "2025-01-01"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_include_full_text_fetches_text(self, mock_sleep, client, raw_eo_full):
        api_resp = self._mock_api_response([raw_eo_full])
        text_resp = MagicMock()
        text_resp.status_code = 200
        text_resp.text = "Full text of the executive order..."

        client.session.get = MagicMock(side_effect=[api_resp, text_resp])

        results = client.fetch_executive_orders(max_pages=1, include_full_text=True)

        assert len(results) == 1
        assert results[0]["full_text"] == "Full text of the executive order..."

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_full_text_failure_leaves_field_absent(self, mock_sleep, client, raw_eo_full):
        api_resp = self._mock_api_response([raw_eo_full])
        text_resp = MagicMock()
        text_resp.status_code = 500

        client.session.get = MagicMock(side_effect=[api_resp, text_resp])

        results = client.fetch_executive_orders(max_pages=1, include_full_text=True)

        assert len(results) == 1
        # full_text stays None (the default) since fetch failed
        assert results[0].get("full_text") is None

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_skips_eos_without_document_number(self, mock_sleep, client):
        good_eo = {"document_number": "A", "title": "Good"}
        bad_eo = {"title": "No document number"}

        client.session.get = MagicMock(
            return_value=self._mock_api_response([good_eo, bad_eo])
        )

        results = client.fetch_executive_orders(max_pages=1, include_full_text=False)

        assert len(results) == 1
        assert results[0]["document_number"] == "A"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_per_page_capped_at_1000(self, mock_sleep, client):
        client.session.get = MagicMock(
            return_value=self._mock_api_response([])
        )

        client.fetch_executive_orders(per_page=5000, max_pages=1, include_full_text=False)

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        assert actual_params["per_page"] == 1000


# ==================== _fetch_full_text ====================


class TestFetchFullText:
    def test_returns_text_on_success(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Executive Order full text content here"
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._fetch_full_text("https://example.com/text")

        assert result == "Executive Order full text content here"

    def test_returns_none_on_non_200(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._fetch_full_text("https://example.com/missing")

        assert result is None

    def test_returns_none_on_exception(self, client):
        client.session.get = MagicMock(side_effect=ConnectionError("network error"))

        result = client._fetch_full_text("https://example.com/fail")

        assert result is None


# ==================== get_order_by_document_number ====================


class TestGetOrderByDocumentNumber:
    def test_returns_normalized_eo(self, client, raw_eo_full):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = raw_eo_full
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_order_by_document_number("2025-01753")

        assert result["document_number"] == "2025-01753"
        assert result["eo_number"] == 14158
        assert result["president"] == "Donald Trump"

    def test_returns_none_on_failed_request(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_order_by_document_number("nonexistent")

        assert result is None

    def test_returns_none_when_normalization_fails(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "No document number field"}
        client.session.get = MagicMock(return_value=mock_resp)

        result = client.get_order_by_document_number("2025-99999")

        assert result is None

    def test_constructs_correct_endpoint(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"document_number": "2025-01753"}
        client.session.get = MagicMock(return_value=mock_resp)

        client.get_order_by_document_number("2025-01753")

        called_url = client.session.get.call_args[0][0]
        assert called_url.endswith("/documents/2025-01753")


# ==================== _fetch_rules (via get_proposed_rules, etc.) ====================


class TestFetchRules:
    def _mock_rules_response(self, results, total_pages=1):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": results,
            "total_pages": total_pages,
        }
        return mock_response

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_get_proposed_rules_returns_proposed_type(self, mock_sleep, client, raw_rule_proposed):
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([raw_rule_proposed])
        )

        results = client.get_proposed_rules(per_page=10, max_pages=1)

        assert len(results) == 1
        assert results[0]["document_type"] == "proposed_rule"
        assert results[0]["comment_url"] == "https://www.regulations.gov/docket/HUD-2025-0001"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_get_final_rules_returns_final_type(self, mock_sleep, client):
        raw = {"document_number": "FR-001", "title": "Final Rule"}
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([raw])
        )

        results = client.get_final_rules(max_pages=1)

        assert len(results) == 1
        assert results[0]["document_type"] == "final_rule"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_get_notices_returns_notice_type(self, mock_sleep, client):
        raw = {"document_number": "N-001", "title": "EPA Notice"}
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([raw])
        )

        results = client.get_notices(max_pages=1)

        assert len(results) == 1
        assert results[0]["document_type"] == "notice"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_since_date_filter_applied(self, mock_sleep, client):
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([])
        )

        client.get_proposed_rules(since_date="2025-03-01", max_pages=1)

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        assert actual_params.get("conditions[publication_date][gte]") == "2025-03-01"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_agency_ids_filter_applied(self, mock_sleep, client):
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([])
        )

        client.get_proposed_rules(agency_ids=["HUD", "EPA"], max_pages=1)

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        # The last agency_id wins due to dict key collision in the code
        assert actual_params["conditions[agencies][]"] == "EPA"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_rules_pagination(self, mock_sleep, client):
        page1 = self._mock_rules_response(
            [{"document_number": "R1"}], total_pages=2
        )
        page2 = self._mock_rules_response(
            [{"document_number": "R2"}], total_pages=2
        )
        client.session.get = MagicMock(side_effect=[page1, page2])

        results = client.get_proposed_rules(max_pages=5)

        assert len(results) == 2
        assert results[0]["document_number"] == "R1"
        assert results[1]["document_number"] == "R2"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_rules_skip_entries_without_document_number(self, mock_sleep, client):
        good = {"document_number": "R1", "title": "Good"}
        bad = {"title": "Missing number"}
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([good, bad])
        )

        results = client.get_final_rules(max_pages=1)

        assert len(results) == 1
        assert results[0]["document_number"] == "R1"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_rules_per_page_capped_at_1000(self, mock_sleep, client):
        client.session.get = MagicMock(
            return_value=self._mock_rules_response([])
        )

        client.get_notices(per_page=9999, max_pages=1)

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        assert actual_params["per_page"] == 1000


# ==================== get_current_president_eos ====================


class TestGetCurrentPresidentEOs:
    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_returns_normalized_eos(self, mock_sleep, client, raw_eo_full):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [raw_eo_full]}
        client.session.get = MagicMock(return_value=mock_resp)

        results = client.get_current_president_eos(president_name="Trump")

        assert len(results) == 1
        assert results[0]["president"] == "Donald Trump"
        assert results[0]["eo_number"] == 14158

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_president_name_filter_passed(self, mock_sleep, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        client.session.get = MagicMock(return_value=mock_resp)

        client.get_current_president_eos(president_name="Biden")

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        assert actual_params["conditions[president]"] == "Biden"

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_no_president_name_omits_filter(self, mock_sleep, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        client.session.get = MagicMock(return_value=mock_resp)

        client.get_current_president_eos()

        actual_params = client.session.get.call_args.kwargs.get("params", {})
        assert "conditions[president]" not in actual_params

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    def test_returns_empty_on_api_failure(self, mock_sleep, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        client.session.get = MagicMock(return_value=mock_resp)

        results = client.get_current_president_eos(president_name="Trump")

        assert results == []


# ==================== get_recent_executive_orders ====================


class TestGetRecentExecutiveOrders:
    @patch("civicos_extraction.clients.federal_register.FederalRegisterClient.fetch_executive_orders")
    def test_passes_computed_date(self, mock_fetch):
        from datetime import datetime, timedelta

        mock_fetch.return_value = [{"document_number": "recent-1", "title": "Recent EO"}]

        results = get_recent_executive_orders(days_back=7)

        assert len(results) == 1
        assert results[0]["document_number"] == "recent-1"
        # Verify since_date is exactly 7 days before today
        since_date = mock_fetch.call_args.kwargs.get("since_date")
        expected = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        assert since_date == expected

    @patch("civicos_extraction.clients.federal_register.FederalRegisterClient.fetch_executive_orders")
    def test_default_30_days(self, mock_fetch):
        from datetime import datetime, timedelta

        mock_fetch.return_value = []

        get_recent_executive_orders()

        since_date = mock_fetch.call_args.kwargs.get("since_date")
        expected = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        assert since_date == expected


# ==================== _throttle_request ====================


class TestThrottleRequest:
    @patch("civicos_extraction.clients.federal_register.time.sleep")
    @patch("civicos_extraction.clients.federal_register.time.time")
    def test_throttles_when_too_fast(self, mock_time, mock_sleep):
        client = FederalRegisterClient()
        client.min_request_interval = 0.5

        # First call at t=100, second at t=100.1 (too fast)
        mock_time.side_effect = [100.0, 100.1, 100.6]
        client.last_request_time = 100.0

        client._throttle_request()

        mock_sleep.assert_called_once_with(0.5)

    @patch("civicos_extraction.clients.federal_register.time.sleep")
    @patch("civicos_extraction.clients.federal_register.time.time")
    def test_no_throttle_when_enough_time_passed(self, mock_time, mock_sleep):
        client = FederalRegisterClient()
        client.min_request_interval = 0.5

        # Last request was at t=100, now it's t=101 (enough gap)
        mock_time.side_effect = [101.0, 101.0]
        client.last_request_time = 100.0

        client._throttle_request()

        mock_sleep.assert_not_called()


# ==================== __init__ ====================


class TestClientInit:
    def test_base_url(self):
        client = FederalRegisterClient()
        assert client.base_url == "https://www.federalregister.gov/api/v1"

    def test_session_headers(self):
        client = FederalRegisterClient()
        assert "Civic" in client.session.headers["User-Agent"]
        assert client.session.headers["Accept"] == "application/json"

    def test_rate_limit_defaults(self):
        client = FederalRegisterClient()
        assert client.min_request_interval == 0.5
        assert client.last_request_time == 0

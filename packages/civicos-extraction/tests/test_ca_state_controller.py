"""Tests for CA State Controller client — revenue parsing, classification, and normalization."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_extraction.clients.ca_state_controller import (
    CAStateControllerClient,
    create_san_rafael_sco_client,
)


# ==================== Fixtures ====================


@pytest.fixture
def client():
    """CAStateControllerClient with zero throttle delay."""
    c = CAStateControllerClient(
        jurisdiction_id="san-rafael",
        entity_name="San Rafael",
        county="Marin",
    )
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def client_no_entity():
    """Client without entity_name configured."""
    c = CAStateControllerClient(jurisdiction_id="san-rafael")
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def federal_revenue_row():
    """Revenue row with a federal form_table code."""
    return {
        "form_table": "FUNC_COMM_DEV_BLOCK_GRANT",
        "value": "523000.50",
        "category": "Intergovernmental \u2013 Federal",
        "subcategory_1": "Federal Grants",
        "subcategory_2": "",
        "line_description": "Community Development Block Grant",
        "entity_name": "San Rafael",
        "county": "Marin",
        "fiscal_year": "2024",
        "row_number": "12345",
    }


@pytest.fixture
def state_revenue_row():
    """Revenue row with a state form_table code."""
    return {
        "form_table": "FUNC_GAS_TAX",
        "value": "1200000",
        "category": "Intergovernmental \u2013 State",
        "subcategory_1": "State Apportionments",
        "subcategory_2": "",
        "line_description": "Gas Tax Revenue",
        "entity_name": "San Rafael",
        "county": "Marin",
        "fiscal_year": "2024",
        "row_number": "12346",
    }


@pytest.fixture
def county_revenue_row():
    """Revenue row with a county form_table code."""
    return {
        "form_table": "FUNC_OTHER_CO_GRANT",
        "value": "75000",
        "category": "Intergovernmental - County",
        "subcategory_1": "County Grants",
        "subcategory_2": "",
        "line_description": "County Grant Program",
        "entity_name": "San Rafael",
        "county": "Marin",
        "fiscal_year": "2024",
        "row_number": "12347",
    }


@pytest.fixture
def non_intergovernmental_row():
    """Revenue row that is NOT intergovernmental."""
    return {
        "form_table": "PROP_TAX",
        "value": "5000000",
        "category": "Property Taxes",
        "subcategory_1": "Current Secured",
        "subcategory_2": "",
        "line_description": "Current Secured Property Tax",
        "entity_name": "San Rafael",
        "county": "Marin",
        "fiscal_year": "2024",
        "row_number": "99999",
    }


def _mock_response(status_code=200, json_data=None, text=""):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = text
    return resp


# ==================== Client properties ====================


class TestClientProperties:
    """Tests for CAStateControllerClient identity properties."""

    def test_platform_name(self, client):
        assert client.platform_name == "ca_state_controller"

    def test_source_id_includes_jurisdiction(self, client):
        assert client.source_id == "ca_state_controller-san-rafael"

    def test_source_type(self, client):
        assert client.source_type == "ca_state_controller"

    def test_entity_name_stored(self, client):
        assert client.entity_name == "San Rafael"

    def test_county_stored(self, client):
        assert client.county == "Marin"

    def test_default_county_is_none(self):
        c = CAStateControllerClient(jurisdiction_id="x", entity_name="X")
        assert c.county is None

    def test_default_entity_name_is_none(self):
        c = CAStateControllerClient(jurisdiction_id="x")
        assert c.entity_name is None


# ==================== _make_request ====================


class TestMakeRequest:
    """Tests for HTTP request handling, retries, and format parsing."""

    def test_successful_json_request(self, client):
        mock_resp = _mock_response(200, json_data=[{"fiscal_year": "2024"}])
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request(params={"$limit": 1})

        assert result == [{"fiscal_year": "2024"}]
        # Verify URL includes .json format
        call_args = client.session.get.call_args
        assert call_args[0][0].endswith(".json")

    def test_csv_format_returns_raw_text(self, client):
        mock_resp = _mock_response(200, text="col1,col2\nval1,val2")
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request(params={}, format="csv")

        assert len(result) == 1
        assert result[0]["raw_csv"] == "col1,col2\nval1,val2"

    def test_non_retryable_error_returns_none(self, client):
        mock_resp = _mock_response(404)
        client.session.get = MagicMock(return_value=mock_resp)

        result = client._make_request(params={}, retries=3)

        assert result is None
        # Should NOT retry on 404 — only 1 call
        assert client.session.get.call_count == 1

    def test_retryable_error_retries_then_returns_none(self, client):
        mock_resp = _mock_response(503)
        client.session.get = MagicMock(return_value=mock_resp)

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=3)

        assert result is None
        assert client.session.get.call_count == 3

    def test_retryable_error_succeeds_on_second_attempt(self, client):
        fail_resp = _mock_response(500)
        ok_resp = _mock_response(200, json_data=[{"id": 1}])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=3)

        assert result == [{"id": 1}]
        assert client.session.get.call_count == 2

    def test_connection_error_retries_then_returns_none(self, client):
        client.session.get = MagicMock(
            side_effect=requests.ConnectionError("refused")
        )

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=2)

        assert result is None
        assert client.session.get.call_count == 2

    def test_timeout_error_retries(self, client):
        client.session.get = MagicMock(
            side_effect=requests.Timeout("timed out")
        )

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=2)

        assert result is None
        assert client.session.get.call_count == 2

    def test_429_triggers_retry(self, client):
        fail_resp = _mock_response(429)
        ok_resp = _mock_response(200, json_data=[{"x": 1}])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=3)

        assert result == [{"x": 1}]

    def test_502_triggers_retry(self, client):
        fail_resp = _mock_response(502)
        ok_resp = _mock_response(200, json_data=[{"y": 2}])
        client.session.get = MagicMock(side_effect=[fail_resp, ok_resp])

        with patch("civicos_extraction.clients.ca_state_controller.time.sleep"):
            result = client._make_request(params={}, retries=3)

        assert result == [{"y": 2}]

    def test_no_params_sends_none(self, client):
        mock_resp = _mock_response(200, json_data=[])
        client.session.get = MagicMock(return_value=mock_resp)

        client._make_request(params=None)

        call_kwargs = client.session.get.call_args[1]
        assert call_kwargs["params"] is None


# ==================== get_intergovernmental_revenues ====================


class TestGetIntergovernmentalRevenues:
    """Tests for intergovernmental revenue fetching and filtering."""

    def test_filters_to_intergovernmental_categories(
        self, client, federal_revenue_row, non_intergovernmental_row
    ):
        api_response = [federal_revenue_row, non_intergovernmental_row]
        with patch.object(client, "_make_request", return_value=api_response):
            result = client.get_intergovernmental_revenues(fiscal_year=2024)

        assert len(result) == 1
        assert result[0]["form_table"] == "FUNC_COMM_DEV_BLOCK_GRANT"

    def test_includes_all_intergovernmental_prefixes(self, client):
        rows = [
            {"category": "Intergovernmental \u2013 Federal", "form_table": "A"},
            {"category": "Intergovernmental \u2013 State", "form_table": "B"},
            {"category": "Intergovernmental - County", "form_table": "C"},
            {"category": "Intergovernmental \u2013 Other", "form_table": "D"},
            {
                "category": "Intergovernmental \u2013 Federal, County, and Other Taxes In-Lieu",
                "form_table": "E",
            },
            {"category": "Property Taxes", "form_table": "F"},
        ]
        with patch.object(client, "_make_request", return_value=rows):
            result = client.get_intergovernmental_revenues()

        assert len(result) == 5
        form_tables = [r["form_table"] for r in result]
        assert form_tables == ["A", "B", "C", "D", "E"]

    def test_returns_empty_list_on_api_failure(self, client):
        with patch.object(client, "_make_request", return_value=None):
            result = client.get_intergovernmental_revenues(fiscal_year=2024)

        assert result == []

    def test_fiscal_year_param_sent_as_string(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_intergovernmental_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert params["fiscal_year"] == "2024"
        assert "$where" not in params

    def test_no_fiscal_year_uses_where_clause(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_intergovernmental_revenues(min_year=2010)

        params = mock_req.call_args[1]["params"]
        assert params["$where"] == "fiscal_year >= 2010"
        assert "fiscal_year" not in params

    def test_county_filter_applied(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_intergovernmental_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert params["county"] == "Marin"

    def test_no_county_omits_county_param(self):
        c = CAStateControllerClient(jurisdiction_id="x", entity_name="X")
        c.min_request_interval = 0.0
        with patch.object(c, "_make_request", return_value=[]) as mock_req:
            c.get_intergovernmental_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert "county" not in params

    def test_entity_name_in_params(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_intergovernmental_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert params["entity_name"] == "San Rafael"

    def test_custom_limit(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_intergovernmental_revenues(fiscal_year=2024, limit=100)

        params = mock_req.call_args[1]["params"]
        assert params["$limit"] == 100


# ==================== get_all_revenues ====================


class TestGetAllRevenues:
    """Tests for fetching all revenue types."""

    def test_returns_all_rows_unfiltered(self, client):
        rows = [{"category": "Property Taxes"}, {"category": "Sales Tax"}]
        with patch.object(client, "_make_request", return_value=rows):
            result = client.get_all_revenues(fiscal_year=2024)

        assert len(result) == 2
        assert result[0]["category"] == "Property Taxes"
        assert result[1]["category"] == "Sales Tax"

    def test_includes_revenue_type_filter(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_all_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert params["type"] == "Revenues"

    def test_returns_empty_on_api_failure(self, client):
        with patch.object(client, "_make_request", return_value=None):
            result = client.get_all_revenues(fiscal_year=2024)

        assert result == []

    def test_county_filter_applied(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_all_revenues(fiscal_year=2024)

        params = mock_req.call_args[1]["params"]
        assert params["county"] == "Marin"

    def test_fiscal_year_as_string_in_params(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_all_revenues(fiscal_year=2023)

        params = mock_req.call_args[1]["params"]
        assert params["fiscal_year"] == "2023"

    def test_no_fiscal_year_uses_where(self, client):
        with patch.object(client, "_make_request", return_value=[]) as mock_req:
            client.get_all_revenues(min_year=2015)

        params = mock_req.call_args[1]["params"]
        assert params["$where"] == "fiscal_year >= 2015"


# ==================== get_revenue_summary — classification ====================


class TestRevenueSummaryClassification:
    """Tests for revenue source classification in get_revenue_summary."""

    def _make_summary(self, client, revenues):
        with patch.object(client, "get_intergovernmental_revenues", return_value=revenues):
            return client.get_revenue_summary(fiscal_year=2024)

    def test_federal_code_classified_as_federal(self, client):
        row = {
            "form_table": "FUNC_COMM_DEV_BLOCK_GRANT",
            "value": "100.00",
            "category": "Intergovernmental \u2013 Federal",
            "subcategory_1": "",
            "line_description": "CDBG",
        }
        summary = self._make_summary(client, [row])

        assert summary["federal_total_cents"] == 10000
        assert summary["state_total_cents"] == 0
        assert summary["county_total_cents"] == 0
        assert summary["details"][0]["source"] == "federal"

    def test_state_code_classified_as_state(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "250.00",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "",
            "line_description": "Gas Tax",
        }
        summary = self._make_summary(client, [row])

        assert summary["state_total_cents"] == 25000
        assert summary["federal_total_cents"] == 0
        assert summary["details"][0]["source"] == "state"

    def test_county_code_classified_as_county(self, client):
        row = {
            "form_table": "FUNC_OTHER_CO_GRANT",
            "value": "50.00",
            "category": "Intergovernmental - County",
            "subcategory_1": "",
            "line_description": "County Grant",
        }
        summary = self._make_summary(client, [row])

        assert summary["county_total_cents"] == 5000
        assert summary["details"][0]["source"] == "county"

    def test_county_code_overrides_federal_category(self, client):
        """County form_table codes should classify as county even under a Federal category."""
        row = {
            "form_table": "INTERGOV_COUNTY",
            "value": "30.00",
            "category": "Intergovernmental \u2013 Federal, County, and Other Taxes In-Lieu",
            "subcategory_1": "Federal County Other",
            "line_description": "County Intergov",
        }
        summary = self._make_summary(client, [row])

        assert summary["county_total_cents"] == 3000
        assert summary["federal_total_cents"] == 0
        assert summary["details"][0]["source"] == "county"

    def test_subcategory_county_fallback(self, client):
        """Unknown form_table with 'County' in subcategory_1 → county."""
        row = {
            "form_table": "UNKNOWN_CODE",
            "value": "10.00",
            "category": "Intergovernmental \u2013 Other",
            "subcategory_1": "County Reimbursement",
            "line_description": "Some county thing",
        }
        summary = self._make_summary(client, [row])

        assert summary["county_total_cents"] == 1000
        assert summary["details"][0]["source"] == "county"

    def test_subcategory_federal_fallback(self, client):
        """Unknown form_table with 'Federal' in subcategory_1 → federal."""
        row = {
            "form_table": "UNKNOWN_CODE",
            "value": "20.00",
            "category": "Intergovernmental \u2013 Other",
            "subcategory_1": "Federal Emergency Aid",
            "line_description": "FEMA",
        }
        summary = self._make_summary(client, [row])

        assert summary["federal_total_cents"] == 2000
        assert summary["details"][0]["source"] == "federal"

    def test_subcategory_state_fallback(self, client):
        """Unknown form_table with 'State' in subcategory_1 → state."""
        row = {
            "form_table": "UNKNOWN_CODE",
            "value": "15.00",
            "category": "Intergovernmental \u2013 Other",
            "subcategory_1": "State Mandate Reimbursement",
            "line_description": "Mandated costs",
        }
        summary = self._make_summary(client, [row])

        assert summary["state_total_cents"] == 1500
        assert summary["details"][0]["source"] == "state"

    def test_category_state_fallback(self, client):
        """Unknown form_table with 'State' in category (but not subcategory) → state."""
        row = {
            "form_table": "UNKNOWN_CODE",
            "value": "77.00",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "Miscellaneous",
            "line_description": "Misc state rev",
        }
        summary = self._make_summary(client, [row])

        assert summary["state_total_cents"] == 7700
        assert summary["details"][0]["source"] == "state"

    def test_undetermined_when_no_match(self, client):
        """Row with unknown code and no matching keywords → undetermined."""
        row = {
            "form_table": "UNKNOWN_CODE",
            "value": "42.00",
            "category": "Intergovernmental \u2013 Other",
            "subcategory_1": "Miscellaneous",
            "line_description": "Miscellaneous revenue",
        }
        summary = self._make_summary(client, [row])

        assert summary["undetermined_total_cents"] == 4200
        assert summary["federal_total_cents"] == 0
        assert summary["state_total_cents"] == 0
        assert summary["county_total_cents"] == 0
        assert summary["details"][0]["source"] == "undetermined"


# ==================== get_revenue_summary — amounts and edge cases ====================


class TestRevenueSummaryAmounts:
    """Tests for amount parsing, zero handling, and totals."""

    def _make_summary(self, client, revenues):
        with patch.object(client, "get_intergovernmental_revenues", return_value=revenues):
            return client.get_revenue_summary(fiscal_year=2024)

    def test_empty_revenues_returns_zero_totals(self, client):
        summary = self._make_summary(client, [])

        assert summary["fiscal_year"] == 2024
        assert summary["entity_name"] == "San Rafael"
        assert summary["federal_total_cents"] == 0
        assert summary["state_total_cents"] == 0
        assert summary["county_total_cents"] == 0
        assert summary["undetermined_total_cents"] == 0
        assert summary["total_intergovernmental_cents"] == 0
        assert summary["details"] == []

    def test_zero_value_rows_excluded_from_details(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "0",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "",
            "line_description": "Zero gas tax",
        }
        summary = self._make_summary(client, [row])

        assert summary["details"] == []
        assert summary["total_intergovernmental_cents"] == 0

    def test_none_value_treated_as_zero(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": None,
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "",
            "line_description": "No value",
        }
        summary = self._make_summary(client, [row])

        assert summary["details"] == []

    def test_invalid_value_treated_as_zero(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "not-a-number",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "",
            "line_description": "Bad value",
        }
        summary = self._make_summary(client, [row])

        assert summary["details"] == []

    def test_float_value_converted_to_cents(self, client):
        row = {
            "form_table": "FUNC_COMM_DEV_BLOCK_GRANT",
            "value": "523000.50",
            "category": "Intergovernmental \u2013 Federal",
            "subcategory_1": "",
            "line_description": "CDBG",
        }
        summary = self._make_summary(client, [row])

        assert summary["federal_total_cents"] == 52300050

    def test_total_is_sum_of_all_sources(self, client):
        rows = [
            {
                "form_table": "FUNC_COMM_DEV_BLOCK_GRANT",
                "value": "100.00",
                "category": "Intergovernmental \u2013 Federal",
                "subcategory_1": "",
                "line_description": "Fed",
            },
            {
                "form_table": "FUNC_GAS_TAX",
                "value": "200.00",
                "category": "Intergovernmental \u2013 State",
                "subcategory_1": "",
                "line_description": "State",
            },
            {
                "form_table": "FUNC_OTHER_CO_GRANT",
                "value": "50.00",
                "category": "Intergovernmental - County",
                "subcategory_1": "",
                "line_description": "County",
            },
        ]
        summary = self._make_summary(client, rows)

        assert summary["federal_total_cents"] == 10000
        assert summary["state_total_cents"] == 20000
        assert summary["county_total_cents"] == 5000
        assert summary["total_intergovernmental_cents"] == 35000

    def test_details_sorted_by_amount_descending(self, client):
        rows = [
            {
                "form_table": "FUNC_OTHER_CO_GRANT",
                "value": "10.00",
                "category": "Intergovernmental - County",
                "subcategory_1": "",
                "line_description": "Small",
            },
            {
                "form_table": "FUNC_COMM_DEV_BLOCK_GRANT",
                "value": "1000.00",
                "category": "Intergovernmental \u2013 Federal",
                "subcategory_1": "",
                "line_description": "Large",
            },
            {
                "form_table": "FUNC_GAS_TAX",
                "value": "500.00",
                "category": "Intergovernmental \u2013 State",
                "subcategory_1": "",
                "line_description": "Medium",
            },
        ]
        summary = self._make_summary(client, rows)

        amounts = [d["amount_cents"] for d in summary["details"]]
        assert amounts == [100000, 50000, 1000]

    def test_missing_value_key_treated_as_zero(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "",
            "line_description": "No value key",
        }
        summary = self._make_summary(client, [row])

        assert summary["details"] == []


# ==================== get_multi_year_summary ====================


class TestMultiYearSummary:
    """Tests for multi-year revenue aggregation."""

    def test_returns_summaries_for_years_with_revenue(self, client):
        def mock_summary(fiscal_year):
            if fiscal_year == 2024:
                return {"fiscal_year": 2024, "total_intergovernmental_cents": 50000}
            elif fiscal_year == 2023:
                return {"fiscal_year": 2023, "total_intergovernmental_cents": 0}
            else:
                return {"fiscal_year": fiscal_year, "total_intergovernmental_cents": 30000}

        with patch.object(client, "get_revenue_summary", side_effect=mock_summary):
            result = client.get_multi_year_summary(min_year=2022, max_year=2024)

        assert len(result) == 2
        assert result[0]["fiscal_year"] == 2024
        assert result[1]["fiscal_year"] == 2022

    def test_empty_when_all_years_zero(self, client):
        with patch.object(
            client,
            "get_revenue_summary",
            return_value={"fiscal_year": 2024, "total_intergovernmental_cents": 0},
        ):
            result = client.get_multi_year_summary(min_year=2023, max_year=2024)

        assert result == []

    def test_iterates_from_max_to_min_year(self, client):
        calls = []

        def track_calls(fiscal_year):
            calls.append(fiscal_year)
            return {"fiscal_year": fiscal_year, "total_intergovernmental_cents": 100}

        with patch.object(client, "get_revenue_summary", side_effect=track_calls):
            client.get_multi_year_summary(min_year=2020, max_year=2022)

        assert calls == [2022, 2021, 2020]

    def test_single_year_range(self, client):
        with patch.object(
            client,
            "get_revenue_summary",
            return_value={"fiscal_year": 2024, "total_intergovernmental_cents": 500},
        ):
            result = client.get_multi_year_summary(min_year=2024, max_year=2024)

        assert len(result) == 1
        assert result[0]["fiscal_year"] == 2024


# ==================== _normalize_revenue ====================


class TestNormalizeRevenue:
    """Tests for revenue normalization to civic storage format."""

    def test_federal_code_normalized(self, client, federal_revenue_row):
        result = client._normalize_revenue(federal_revenue_row)

        assert result["source"] == "federal"
        assert result["amount_cents"] == 52300050
        assert result["fiscal_year"] == 2024
        assert result["entity_name"] == "San Rafael"
        assert result["county"] == "Marin"
        assert result["form_table"] == "FUNC_COMM_DEV_BLOCK_GRANT"
        assert result["data_source"] == "ca_state_controller"
        assert "rrtv-rsj9" in result["source_url"]
        assert result["row_number"] == "12345"

    def test_state_code_normalized(self, client, state_revenue_row):
        result = client._normalize_revenue(state_revenue_row)

        assert result["source"] == "state"
        assert result["amount_cents"] == 120000000

    def test_county_code_normalized(self, client, county_revenue_row):
        result = client._normalize_revenue(county_revenue_row)

        assert result["source"] == "county"
        assert result["amount_cents"] == 7500000

    def test_subcategory_county_fallback_in_normalize(self, client):
        row = {
            "form_table": "UNKNOWN",
            "value": "10.00",
            "category": "Intergovernmental",
            "subcategory_1": "County Aid",
            "subcategory_2": "",
            "line_description": "Aid",
            "entity_name": "X",
            "county": "Y",
            "fiscal_year": "2024",
            "row_number": "1",
        }
        result = client._normalize_revenue(row)

        assert result["source"] == "county"

    def test_subcategory_federal_fallback_in_normalize(self, client):
        row = {
            "form_table": "UNKNOWN",
            "value": "10.00",
            "category": "Intergovernmental",
            "subcategory_1": "Federal Emergency",
            "subcategory_2": "",
            "line_description": "FEMA",
            "entity_name": "X",
            "county": "Y",
            "fiscal_year": "2024",
            "row_number": "1",
        }
        result = client._normalize_revenue(row)

        assert result["source"] == "federal"

    def test_category_state_fallback_in_normalize(self, client):
        row = {
            "form_table": "UNKNOWN",
            "value": "10.00",
            "category": "Intergovernmental \u2013 State",
            "subcategory_1": "Misc",
            "subcategory_2": "",
            "line_description": "Misc",
            "entity_name": "X",
            "county": "Y",
            "fiscal_year": "2024",
            "row_number": "1",
        }
        result = client._normalize_revenue(row)

        assert result["source"] == "state"

    def test_undetermined_source_in_normalize(self, client):
        row = {
            "form_table": "UNKNOWN",
            "value": "10.00",
            "category": "Intergovernmental",
            "subcategory_1": "Misc",
            "subcategory_2": "",
            "line_description": "Misc",
            "entity_name": "X",
            "county": "Y",
            "fiscal_year": "2024",
            "row_number": "1",
        }
        result = client._normalize_revenue(row)

        assert result["source"] == "undetermined"

    def test_zero_value_returns_none(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "0",
            "category": "",
            "subcategory_1": "",
        }
        result = client._normalize_revenue(row)

        assert result is None

    def test_none_value_returns_none(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": None,
            "category": "",
            "subcategory_1": "",
        }
        result = client._normalize_revenue(row)

        assert result is None

    def test_invalid_value_returns_none(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "abc",
            "category": "",
            "subcategory_1": "",
        }
        result = client._normalize_revenue(row)

        assert result is None

    def test_missing_optional_fields_default_to_none(self, client):
        row = {
            "form_table": "FUNC_GAS_TAX",
            "value": "5.00",
        }
        result = client._normalize_revenue(row)

        assert result["category"] is None
        assert result["subcategory_1"] is None
        assert result["subcategory_2"] is None
        assert result["line_description"] is None
        assert result["entity_name"] is None
        assert result["county"] is None
        assert result["fiscal_year"] == 0

    def test_all_federal_codes_recognized(self, client):
        for code in CAStateControllerClient.FEDERAL_CODES:
            row = {"form_table": code, "value": "1.00", "category": "", "subcategory_1": ""}
            result = client._normalize_revenue(row)
            assert result["source"] == "federal", f"{code} not classified as federal"

    def test_all_state_codes_recognized(self, client):
        for code in CAStateControllerClient.STATE_CODES:
            row = {"form_table": code, "value": "1.00", "category": "", "subcategory_1": ""}
            result = client._normalize_revenue(row)
            assert result["source"] == "state", f"{code} not classified as state"

    def test_all_county_codes_recognized(self, client):
        for code in CAStateControllerClient.COUNTY_CODES:
            row = {"form_table": code, "value": "1.00", "category": "", "subcategory_1": ""}
            result = client._normalize_revenue(row)
            assert result["source"] == "county", f"{code} not classified as county"


# ==================== health ====================


class TestHealth:
    """Tests for health check behavior."""

    def test_healthy_when_api_returns_data(self, client):
        with patch.object(client, "_make_request", return_value=[{"id": 1}]):
            status = client.health()

        assert status.is_available is True
        assert status.available_count == 1
        assert status.source_id == "ca_state_controller-san-rafael"
        assert status.source_type == "ca_state_controller"
        assert status.jurisdiction_id == "san-rafael"
        assert status.errors == []
        assert status.last_successful is not None
        assert status.metadata["api_base"] == CAStateControllerClient.BASE_URL

    def test_unhealthy_when_no_entity_name(self, client_no_entity):
        status = client_no_entity.health()

        assert status.is_available is False
        assert status.available_count == 0
        assert "No entity_name configured" in status.errors
        assert status.check_duration_ms == 0.0

    def test_unhealthy_when_api_returns_none(self, client):
        with patch.object(client, "_make_request", return_value=None):
            status = client.health()

        assert status.is_available is False
        assert status.last_successful is None

    def test_unhealthy_on_exception(self, client):
        with patch.object(
            client, "_make_request", side_effect=RuntimeError("boom")
        ):
            status = client.health()

        assert status.is_available is False
        assert any("boom" in e for e in status.errors)

    def test_check_duration_measured(self, client):
        with patch.object(client, "_make_request", return_value=[{"id": 1}]):
            status = client.health()

        assert status.check_duration_ms >= 0.0


# ==================== validate ====================


class TestValidate:
    """Tests for configuration validation."""

    def test_valid_config_and_reachable_api(self, client):
        with patch.object(
            client,
            "_make_request",
            side_effect=[
                [{"id": 1}],        # API connectivity check
                [{"entity": "ok"}],  # Entity verification
            ],
        ):
            result = client.validate()

        assert result.is_valid is True
        assert result.config_valid is True
        assert result.api_reachable is True
        assert result.errors == []
        assert result.metadata["entity_found"] is True

    def test_invalid_without_entity_name(self, client_no_entity):
        result = client_no_entity.validate()

        assert result.is_valid is False
        assert result.config_valid is False
        assert "entity_name" in result.errors[0]

    def test_api_unreachable(self, client):
        with patch.object(client, "_make_request", return_value=None):
            result = client.validate()

        assert result.is_valid is False
        assert result.api_reachable is False
        assert any("Cannot reach" in e for e in result.errors)

    def test_api_exception_during_connectivity(self, client):
        with patch.object(
            client, "_make_request", side_effect=ConnectionError("refused")
        ):
            result = client.validate()

        assert result.is_valid is False
        assert result.api_reachable is False
        assert any("refused" in e for e in result.errors)

    def test_entity_not_found_is_warning(self, client):
        with patch.object(
            client,
            "_make_request",
            side_effect=[
                [{"id": 1}],  # API reachable
                [],            # Entity not found (empty list)
            ],
        ):
            result = client.validate()

        assert result.is_valid is True  # still valid, just a warning
        assert any("not found" in w for w in result.warnings)

    def test_entity_check_exception_is_warning(self, client):
        with patch.object(
            client,
            "_make_request",
            side_effect=[
                [{"id": 1}],                    # API reachable
                RuntimeError("entity error"),    # Entity check fails
            ],
        ):
            result = client.validate()

        assert result.is_valid is True
        assert any("Could not verify" in w for w in result.warnings)

    def test_check_duration_measured(self, client):
        with patch.object(
            client,
            "_make_request",
            side_effect=[[{"id": 1}], [{"e": 1}]],
        ):
            result = client.validate()

        assert result.check_duration_ms >= 0.0


# ==================== create_san_rafael_sco_client ====================


class TestFactoryFunction:
    """Tests for the San Rafael client factory."""

    def test_creates_client_with_correct_config(self):
        c = create_san_rafael_sco_client()

        assert c.jurisdiction_id == "san-rafael"
        assert c.entity_name == "San Rafael"
        assert c.county == "Marin"
        assert c.platform_name == "ca_state_controller"
        assert c.source_id == "ca_state_controller-san-rafael"


# ==================== Intergovernmental category constants ====================


class TestIntergovernmentalCategories:
    """Tests for the INTERGOVERNMENTAL_CATEGORIES constant coverage."""

    def test_all_categories_filter_correctly(self, client):
        """Each INTERGOVERNMENTAL_CATEGORIES entry should match rows with that category."""
        for cat in CAStateControllerClient.INTERGOVERNMENTAL_CATEGORIES:
            rows = [
                {"category": cat, "form_table": "X"},
                {"category": "Property Taxes", "form_table": "Y"},
            ]
            with patch.object(client, "_make_request", return_value=rows):
                result = client.get_intergovernmental_revenues(fiscal_year=2024)
            assert len(result) == 1, f"Category '{cat}' did not match"
            assert result[0]["form_table"] == "X"

    def test_partial_category_match(self, client):
        """Category containing an intergovernmental prefix as substring should match."""
        rows = [{"category": "Intergovernmental \u2013 Federal Grants Subtotal", "form_table": "Z"}]
        with patch.object(client, "_make_request", return_value=rows):
            result = client.get_intergovernmental_revenues(fiscal_year=2024)

        assert len(result) == 1

    def test_non_matching_category_excluded(self, client):
        rows = [{"category": "Taxes and Assessments", "form_table": "A"}]
        with patch.object(client, "_make_request", return_value=rows):
            result = client.get_intergovernmental_revenues(fiscal_year=2024)

        assert result == []

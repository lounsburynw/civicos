"""Tests for Federal Audit Clearinghouse client — audit search, expenditure normalization, and API handling."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_extraction.clients.fac import (
    FederalAuditClearinghouseClient,
    create_san_rafael_fac_client,
)


# ==================== Fixtures ====================


@pytest.fixture
def client():
    """FAC client with zero throttle delay and a test API key."""
    c = FederalAuditClearinghouseClient(
        jurisdiction_id="san-rafael",
        api_key="test-key-123",
        auditee_name="City of San Rafael",
        auditee_city="San Rafael",
        auditee_state="CA",
    )
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def client_no_key():
    """FAC client without an API key."""
    with patch.dict("os.environ", {}, clear=True):
        c = FederalAuditClearinghouseClient(
            jurisdiction_id="san-rafael",
            auditee_name="City of San Rafael",
        )
    c.min_request_interval = 0.0
    return c


@pytest.fixture
def sample_audit():
    """A realistic audit record from the FAC general endpoint."""
    return {
        "report_id": "2023-06-GSAFAC-0001234567",
        "audit_year": 2023,
        "auditee_name": "City of San Rafael",
        "auditee_uei": "ABC123DEF456",
        "auditee_ein": "941234567",
        "fy_start_date": "2022-07-01",
        "fy_end_date": "2023-06-30",
    }


@pytest.fixture
def sample_award():
    """A realistic federal award record from the FAC federal_awards endpoint."""
    return {
        "award_reference": "AWARD-001",
        "federal_agency_prefix": "20",
        "federal_award_extension": "205",
        "amount_expended": "523000",
        "federal_program_total": "1500000",
        "cluster_total": "3000000",
        "federal_program_name": "Highway Planning and Construction",
        "cluster_name": "Highway Planning and Construction Cluster",
        "is_major": "Y",
        "is_passthrough_award": "N",
    }


# ==================== Initialization ====================


def test_init_uses_explicit_api_key():
    c = FederalAuditClearinghouseClient(
        jurisdiction_id="test",
        api_key="explicit-key",
    )
    assert c.api_key == "explicit-key"


def test_init_reads_fac_gov_api_key_from_env():
    with patch.dict("os.environ", {"FAC_GOV_API_KEY": "env-key-gov"}):
        c = FederalAuditClearinghouseClient(jurisdiction_id="test")
    assert c.api_key == "env-key-gov"


def test_init_reads_fac_api_key_from_env():
    with patch.dict("os.environ", {"FAC_API_KEY": "env-key"}, clear=True):
        c = FederalAuditClearinghouseClient(jurisdiction_id="test")
    assert c.api_key == "env-key"


def test_init_explicit_key_takes_precedence_over_env():
    with patch.dict("os.environ", {"FAC_GOV_API_KEY": "env-key"}):
        c = FederalAuditClearinghouseClient(
            jurisdiction_id="test",
            api_key="explicit",
        )
    assert c.api_key == "explicit"


def test_init_production_url_by_default():
    c = FederalAuditClearinghouseClient(jurisdiction_id="test", api_key="k")
    assert c.base_url == "https://api.fac.gov"


def test_init_staging_url_when_requested():
    c = FederalAuditClearinghouseClient(
        jurisdiction_id="test", api_key="k", use_staging=True
    )
    assert c.base_url == "https://api-staging.fac.gov"


# ==================== Properties ====================


def test_platform_name_is_fac(client):
    assert client.platform_name == "fac"


def test_source_id_includes_jurisdiction(client):
    assert client.source_id == "fac-san-rafael"


def test_source_type_is_fac(client):
    assert client.source_type == "fac"


# ==================== Health Check ====================


def test_health_returns_unavailable_without_api_key(client_no_key):
    result = client_no_key.health()
    assert result.is_available is False
    assert result.available_count == 0
    assert len(result.errors) == 1
    assert "FAC API key" in result.errors[0]
    assert result.source_id == "fac-san-rafael"
    assert result.jurisdiction_id == "san-rafael"


def test_health_returns_available_on_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"report_id": "test"}]

    with patch.object(client.session, "get", return_value=mock_response):
        result = client.health()

    assert result.is_available is True
    assert result.available_count == 1
    assert result.errors == []
    assert result.metadata["api_base"] == "https://api.fac.gov"
    assert result.last_successful is not None
    assert result.check_duration_ms >= 0


def test_health_returns_unavailable_on_api_failure(client):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with patch.object(client.session, "get", return_value=mock_response):
        result = client.health()

    assert result.is_available is False
    assert result.available_count == 0


def test_health_returns_unavailable_when_request_returns_none(client):
    """When _make_request returns None (e.g. connection errors absorbed by retries),
    health() should report unavailable with no errors (exception was handled internally)."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    with patch.object(client.session, "get", return_value=mock_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client.health()

    assert result.is_available is False
    assert result.available_count == 0
    assert result.last_successful is None


# ==================== Validate ====================


def test_validate_fails_without_api_key(client_no_key):
    result = client_no_key.validate()
    assert result.is_valid is False
    assert result.config_valid is False
    assert result.api_reachable is False
    assert any("FAC API key" in e for e in result.errors)


def test_validate_warns_without_search_criteria():
    with patch.dict("os.environ", {}, clear=True):
        c = FederalAuditClearinghouseClient(
            jurisdiction_id="test",
            api_key="k",
        )
    c.min_request_interval = 0.0
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{}]

    with patch.object(c.session, "get", return_value=mock_response):
        result = c.validate()

    assert result.config_valid is True
    assert len(result.warnings) == 1
    assert "auditee_name" in result.warnings[0]


def test_validate_succeeds_with_key_and_reachable_api(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{}]

    with patch.object(client.session, "get", return_value=mock_response):
        result = client.validate()

    assert result.is_valid is True
    assert result.config_valid is True
    assert result.api_reachable is True
    assert result.errors == []
    assert result.check_duration_ms >= 0


def test_validate_detects_unreachable_api(client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.json.return_value = None

    with patch.object(client.session, "get", return_value=mock_response):
        result = client.validate()

    assert result.is_valid is False
    assert result.api_reachable is False
    assert any("Cannot reach" in e for e in result.errors)


def test_validate_reports_unreachable_when_make_request_returns_none(client):
    """When _make_request returns None (connection errors absorbed by retries),
    validate() reports Cannot reach and is_valid=False."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    with patch.object(client.session, "get", return_value=mock_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client.validate()

    assert result.is_valid is False
    assert result.api_reachable is False
    assert any("Cannot reach" in e for e in result.errors)


# ==================== _make_request ====================


def test_make_request_returns_none_without_api_key(client_no_key):
    result = client_no_key._make_request("general", params={"limit": 1})
    assert result is None


def test_make_request_returns_json_on_200(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"report_id": "r1"}, {"report_id": "r2"}]

    with patch.object(client.session, "get", return_value=mock_response):
        result = client._make_request("general", params={"limit": 2})

    assert result == [{"report_id": "r1"}, {"report_id": "r2"}]


def test_make_request_sends_correct_headers(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        client._make_request("federal_awards")

    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["headers"]["X-Api-Key"] == "test-key-123"
    assert call_kwargs.kwargs["headers"]["Accept"] == "application/json"


def test_make_request_builds_correct_url(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        client._make_request("federal_awards")

    assert mock_get.call_args.args[0] == "https://api.fac.gov/federal_awards"


def test_make_request_returns_none_on_non_retryable_error(client):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch.object(client.session, "get", return_value=mock_response):
        result = client._make_request("general", retries=1)

    assert result is None


def test_make_request_retries_on_429(client):
    fail_response = MagicMock()
    fail_response.status_code = 429

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = [{"ok": True}]

    with patch.object(
        client.session, "get", side_effect=[fail_response, success_response]
    ):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=2)

    assert result == [{"ok": True}]


def test_make_request_retries_on_503(client):
    fail_response = MagicMock()
    fail_response.status_code = 503

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = [{"recovered": True}]

    with patch.object(
        client.session, "get", side_effect=[fail_response, success_response]
    ):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=2)

    assert result == [{"recovered": True}]


def test_make_request_returns_none_after_exhausting_retries(client):
    fail_response = MagicMock()
    fail_response.status_code = 500

    with patch.object(client.session, "get", return_value=fail_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=2)

    assert result is None


def test_make_request_handles_timeout_with_retry(client):
    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = [{"data": 1}]

    with patch.object(
        client.session,
        "get",
        side_effect=[requests.Timeout("timed out"), success_response],
    ):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=2)

    assert result == [{"data": 1}]


def test_make_request_returns_none_after_exhausting_timeout_retries(client):
    with patch.object(
        client.session, "get", side_effect=requests.Timeout("timed out")
    ):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=2)

    assert result is None


def test_make_request_handles_connection_error(client):
    with patch.object(
        client.session, "get", side_effect=requests.ConnectionError("refused")
    ):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client._make_request("general", retries=1)

    assert result is None


# ==================== get_audits ====================


def test_get_audits_returns_results(client, sample_audit):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_audit]

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        result = client.get_audits()

    assert len(result) == 1
    assert result[0]["report_id"] == "2023-06-GSAFAC-0001234567"
    assert result[0]["audit_year"] == 2023

    # Verify PostgREST query parameters
    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["auditee_state"] == "eq.CA"
    assert call_params["auditee_name"] == "ilike.*City of San Rafael*"
    assert call_params["auditee_city"] == "ilike.*San Rafael*"
    assert call_params["order"] == "audit_year.desc"
    assert call_params["audit_year"] == "gte.2016"


def test_get_audits_filters_by_specific_year(client, sample_audit):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_audit]

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        client.get_audits(audit_year=2023)

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["audit_year"] == "eq.2023"


def test_get_audits_uses_custom_min_year(client, sample_audit):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_audit]

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        client.get_audits(min_year=2020)

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["audit_year"] == "gte.2020"


def test_get_audits_returns_empty_on_api_failure(client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    with patch.object(client.session, "get", return_value=mock_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client.get_audits()

    assert result == []


def test_get_audits_omits_name_filter_when_not_set():
    c = FederalAuditClearinghouseClient(
        jurisdiction_id="test",
        api_key="k",
        auditee_state="CA",
    )
    c.min_request_interval = 0.0

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch.object(c.session, "get", return_value=mock_response) as mock_get:
        c.get_audits()

    call_params = mock_get.call_args.kwargs["params"]
    assert "auditee_name" not in call_params
    assert "auditee_city" not in call_params


# ==================== get_federal_awards ====================


def test_get_federal_awards_returns_results(client, sample_award):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_award]

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        result = client.get_federal_awards("report-123")

    assert len(result) == 1
    assert result[0]["federal_program_name"] == "Highway Planning and Construction"

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["report_id"] == "eq.report-123"
    assert call_params["order"] == "amount_expended.desc"


def test_get_federal_awards_returns_empty_on_failure(client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    with patch.object(client.session, "get", return_value=mock_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client.get_federal_awards("report-123")

    assert result == []


# ==================== get_passthrough ====================


def test_get_passthrough_returns_results(client):
    passthrough_record = {"passthrough_name": "CA Dept of Transportation", "amount": 50000}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [passthrough_record]

    with patch.object(client.session, "get", return_value=mock_response) as mock_get:
        result = client.get_passthrough("report-456")

    assert len(result) == 1
    assert result[0]["passthrough_name"] == "CA Dept of Transportation"

    call_params = mock_get.call_args.kwargs["params"]
    assert call_params["report_id"] == "eq.report-456"


def test_get_passthrough_returns_empty_on_failure(client):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Error"

    with patch.object(client.session, "get", return_value=mock_response):
        with patch("civicos_extraction.clients.fac.time.sleep"):
            result = client.get_passthrough("report-456")

    assert result == []


# ==================== _normalize_expenditure ====================


def test_normalize_builds_complete_record(client, sample_award, sample_audit):
    result = client._normalize_expenditure(sample_award, sample_audit)

    assert result["report_id"] == "2023-06-GSAFAC-0001234567"
    assert result["award_reference"] == "AWARD-001"
    assert result["aln_number"] == "20.205"
    assert result["cfda_number"] == "20.205"
    assert result["auditee_name"] == "City of San Rafael"
    assert result["auditee_uei"] == "ABC123DEF456"
    assert result["auditee_ein"] == "941234567"
    assert result["audit_year"] == 2023
    assert result["fy_start_date"] == "2022-07-01"
    assert result["fy_end_date"] == "2023-06-30"
    assert result["amount_expended_cents"] == 52300000
    assert result["federal_program_total_cents"] == 150000000
    assert result["cluster_total_cents"] == 300000000
    assert result["federal_program_name"] == "Highway Planning and Construction"
    assert result["cluster_name"] == "Highway Planning and Construction Cluster"
    assert result["is_major"] is True
    assert result["is_passthrough_award"] is False
    assert result["federal_agency_prefix"] == "20"
    assert result["source"] == "fac"
    assert result["source_url"] == "https://app.fac.gov/dissemination/report/pdf/2023-06-GSAFAC-0001234567"


def test_normalize_returns_none_when_prefix_missing(client, sample_audit):
    award = {"federal_agency_prefix": None, "amount_expended": "100"}
    result = client._normalize_expenditure(award, sample_audit)
    assert result is None


def test_normalize_returns_none_when_prefix_empty_string(client, sample_audit):
    award = {"federal_agency_prefix": "", "amount_expended": "100"}
    result = client._normalize_expenditure(award, sample_audit)
    assert result is None


def test_normalize_returns_none_when_amount_missing(client, sample_audit):
    award = {"federal_agency_prefix": "20", "federal_award_extension": "205"}
    result = client._normalize_expenditure(award, sample_audit)
    assert result is None


def test_normalize_returns_none_on_invalid_amount(client, sample_audit):
    award = {
        "federal_agency_prefix": "20",
        "federal_award_extension": "205",
        "amount_expended": "not-a-number",
    }
    result = client._normalize_expenditure(award, sample_audit)
    assert result is None


def test_normalize_handles_float_amount(client, sample_audit):
    award = {
        "federal_agency_prefix": "14",
        "federal_award_extension": "228",
        "amount_expended": "100000.75",
    }
    result = client._normalize_expenditure(award, sample_audit)
    assert result["amount_expended_cents"] == 10000075
    assert result["aln_number"] == "14.228"


def test_normalize_aln_without_extension(client, sample_audit):
    award = {
        "federal_agency_prefix": "93",
        "federal_award_extension": None,
        "amount_expended": "50000",
    }
    result = client._normalize_expenditure(award, sample_audit)
    assert result["aln_number"] == "93"
    assert result["cfda_number"] == "93"


def test_normalize_is_major_field_parsing(client, sample_audit):
    # "Y" → True
    award_major = {
        "federal_agency_prefix": "10",
        "federal_award_extension": "551",
        "amount_expended": "100",
        "is_major": "Y",
        "is_passthrough_award": "N",
    }
    result = client._normalize_expenditure(award_major, sample_audit)
    assert result["is_major"] is True
    assert result["is_passthrough_award"] is False

    # "N" → False
    award_not_major = {
        "federal_agency_prefix": "10",
        "federal_award_extension": "551",
        "amount_expended": "100",
        "is_major": "N",
        "is_passthrough_award": "Y",
    }
    result2 = client._normalize_expenditure(award_not_major, sample_audit)
    assert result2["is_major"] is False
    assert result2["is_passthrough_award"] is True


def test_normalize_source_url_none_when_no_report_id(client):
    audit_no_id = {"report_id": None}
    award = {
        "federal_agency_prefix": "10",
        "federal_award_extension": "551",
        "amount_expended": "100",
    }
    result = client._normalize_expenditure(award, audit_no_id)
    assert result["source_url"] is None


def test_normalize_handles_missing_optional_financial_fields(client, sample_audit):
    """federal_program_total and cluster_total may be absent."""
    award = {
        "federal_agency_prefix": "10",
        "federal_award_extension": "551",
        "amount_expended": "200",
    }
    result = client._normalize_expenditure(award, sample_audit)
    assert result["federal_program_total_cents"] is None
    assert result["cluster_total_cents"] is None
    assert result["federal_program_name"] is None
    assert result["cluster_name"] is None


# ==================== get_all_expenditures ====================


def test_get_all_expenditures_combines_audits_and_awards(client, sample_audit, sample_award):
    audits_response = MagicMock()
    audits_response.status_code = 200
    audits_response.json.return_value = [sample_audit]

    awards_response = MagicMock()
    awards_response.status_code = 200
    awards_response.json.return_value = [sample_award]

    with patch.object(
        client.session, "get", side_effect=[audits_response, awards_response]
    ):
        result = client.get_all_expenditures(audit_year=2023)

    assert len(result) == 1
    assert result[0]["aln_number"] == "20.205"
    assert result[0]["amount_expended_cents"] == 52300000
    assert result[0]["report_id"] == "2023-06-GSAFAC-0001234567"


def test_get_all_expenditures_skips_audits_without_report_id(client):
    audit_no_id = {"audit_year": 2023}  # no report_id key

    audits_response = MagicMock()
    audits_response.status_code = 200
    audits_response.json.return_value = [audit_no_id]

    with patch.object(client.session, "get", return_value=audits_response):
        result = client.get_all_expenditures()

    assert result == []


def test_get_all_expenditures_returns_empty_when_no_audits(client):
    audits_response = MagicMock()
    audits_response.status_code = 200
    audits_response.json.return_value = []

    with patch.object(client.session, "get", return_value=audits_response):
        result = client.get_all_expenditures()

    assert result == []


def test_get_all_expenditures_handles_multiple_audits(client):
    audit1 = {"report_id": "r1", "audit_year": 2023, "auditee_name": "City A"}
    audit2 = {"report_id": "r2", "audit_year": 2022, "auditee_name": "City A"}

    award1 = {
        "federal_agency_prefix": "20",
        "federal_award_extension": "205",
        "amount_expended": "100000",
    }
    award2 = {
        "federal_agency_prefix": "14",
        "federal_award_extension": "228",
        "amount_expended": "200000",
    }

    audits_response = MagicMock()
    audits_response.status_code = 200
    audits_response.json.return_value = [audit1, audit2]

    awards_response_1 = MagicMock()
    awards_response_1.status_code = 200
    awards_response_1.json.return_value = [award1]

    awards_response_2 = MagicMock()
    awards_response_2.status_code = 200
    awards_response_2.json.return_value = [award2]

    with patch.object(
        client.session,
        "get",
        side_effect=[audits_response, awards_response_1, awards_response_2],
    ):
        result = client.get_all_expenditures()

    assert len(result) == 2
    alns = {r["aln_number"] for r in result}
    assert alns == {"20.205", "14.228"}


# ==================== create_san_rafael_fac_client ====================


def test_create_san_rafael_client_default_configuration():
    with patch.dict("os.environ", {"FAC_API_KEY": "sr-key"}, clear=True):
        c = create_san_rafael_fac_client()

    assert c.jurisdiction_id == "san-rafael"
    assert c.auditee_name == "City of San Rafael"
    assert c.auditee_city == "San Rafael"
    assert c.auditee_state == "CA"
    assert c.api_key == "sr-key"


def test_create_san_rafael_client_with_explicit_key():
    c = create_san_rafael_fac_client(api_key="my-key")
    assert c.api_key == "my-key"
    assert c.jurisdiction_id == "san-rafael"


# ==================== Throttle ====================


def test_throttle_enforces_minimum_interval(client):
    """Verify _throttle_request updates last_request_time."""
    client.min_request_interval = 0.0
    client.last_request_time = 0.0
    client._throttle_request()
    assert client.last_request_time > 0

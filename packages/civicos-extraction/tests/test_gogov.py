"""
Tests for GoGov CRM API client.

All tests mock the external `gogov` package — no live network calls.
Tests focus on credential resolution, normalization logic, and edge cases.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.clients.gogov import GoGovClient


# ============================================================================
# Sample raw issue data (as returned by gogov.Client.search())
# ============================================================================

def _make_raw_issue(**overrides):
    """Build a realistic GOGov raw issue dict."""
    base = {
        "caseId": "12345",
        "displayId": "CASE-12345",
        "description": "Pothole on Main Street near intersection with Oak Ave",
        "status": "Open",
        "locationPoint": {"lat": 37.9735, "lon": -122.5311},
        "location": "100 Main St, San Rafael, CA",
        "dateEntered": "2026-03-15T10:30:00",
        "dateLastUpdated": "2026-03-16T14:00:00",
        "dateClosed": None,
        "classificationId": 42,
        "priority": "Normal",
        "caseType": "pothole",
        "howEntered": "web",
        "departmentId": "DPW-001",
    }
    base.update(overrides)
    return base


# ============================================================================
# GoGovClient.__init__ — credential resolution
# ============================================================================


class TestGoGovClientInit:
    """Tests for credential resolution from params vs environment."""

    def test_params_take_precedence_over_env(self):
        with patch.dict(os.environ, {
            "GOGOV_EMAIL": "env@example.com",
            "GOGOV_PASSWORD": "envpass",
            "GOGOV_SITE": "envsite",
            "GOGOV_CITY_ID": "envcity",
        }):
            client = GoGovClient(
                email="param@example.com",
                password="parampass",
                site="paramsite",
                city_id="paramcity",
            )
        assert client.email == "param@example.com"
        assert client.password == "parampass"
        assert client.site == "paramsite"
        assert client.city_id == "paramcity"

    def test_falls_back_to_env_vars(self):
        with patch.dict(os.environ, {
            "GOGOV_EMAIL": "env@example.com",
            "GOGOV_PASSWORD": "envpass",
            "GOGOV_SITE": "envsite",
            "GOGOV_CITY_ID": "envcity",
        }):
            client = GoGovClient()
        assert client.email == "env@example.com"
        assert client.password == "envpass"
        assert client.site == "envsite"
        assert client.city_id == "envcity"

    def test_empty_string_when_no_env_and_no_params(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove GOGOV_* keys specifically
            env = {k: v for k, v in os.environ.items() if not k.startswith("GOGOV_")}
            with patch.dict(os.environ, env, clear=True):
                client = GoGovClient()
        assert client.email == ""
        assert client.password == ""
        assert client.site == ""
        assert client.city_id == ""

    def test_jurisdiction_id_stored(self):
        client = GoGovClient(jurisdiction_id="county-marin")
        assert client.jurisdiction_id == "county-marin"

    def test_jurisdiction_id_defaults_to_empty_string(self):
        client = GoGovClient()
        assert client.jurisdiction_id == ""

    def test_client_not_initialized_on_construction(self):
        client = GoGovClient(email="a", password="b", site="c")
        assert client._client is None


# ============================================================================
# GoGovClient._get_client — lazy initialization
# ============================================================================


class TestGetClient:
    """Tests for lazy client initialization and error handling."""

    def test_raises_runtime_error_when_email_missing(self):
        client = GoGovClient(password="pass", site="site")
        with pytest.raises(RuntimeError, match="GOGOV_EMAIL"):
            client._get_client()

    def test_raises_runtime_error_when_password_missing(self):
        client = GoGovClient(email="email@test.com", site="site")
        with pytest.raises(RuntimeError, match="GOGOV_PASSWORD"):
            client._get_client()

    def test_raises_runtime_error_when_site_missing(self):
        client = GoGovClient(email="email@test.com", password="pass")
        with pytest.raises(RuntimeError, match="GOGOV_SITE"):
            client._get_client()

    def test_raises_import_error_when_gogov_not_installed(self):
        client = GoGovClient(email="a@b.com", password="pass", site="testsite")
        with patch.dict("sys.modules", {"gogov": None}):
            with pytest.raises(ImportError, match="gogov package required"):
                client._get_client()

    def test_creates_client_with_correct_params(self):
        mock_client_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.Client = mock_client_cls

        client = GoGovClient(
            email="staff@example.com",
            password="secret",
            site="marincountyca",
            city_id="123",
        )

        with patch.dict("sys.modules", {"gogov": mock_module}):
            result = client._get_client()

        mock_client_cls.assert_called_once_with(
            email="staff@example.com",
            password="secret",
            site="marincountyca",
            city_id="123",
            wait=5,
        )
        assert result == mock_client_cls.return_value

    def test_returns_cached_client_on_second_call(self):
        mock_client_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.Client = mock_client_cls

        client = GoGovClient(email="a@b.com", password="p", site="s")

        with patch.dict("sys.modules", {"gogov": mock_module}):
            first = client._get_client()
            second = client._get_client()

        assert first is second
        assert mock_client_cls.call_count == 1


# ============================================================================
# GoGovClient.get_topics
# ============================================================================


class TestGetTopics:
    """Tests for topic/category fetching."""

    def test_returns_data_array_from_response(self):
        mock_gogov = MagicMock()
        mock_gogov.get_topics.return_value = {
            "data": [
                {"id": 1, "name": "Potholes"},
                {"id": 2, "name": "Graffiti"},
            ]
        }
        client = GoGovClient(email="a", password="b", site="c")
        client._client = mock_gogov

        topics = client.get_topics()

        assert len(topics) == 2
        assert topics[0]["name"] == "Potholes"
        assert topics[1]["id"] == 2

    def test_returns_empty_list_when_no_data_key(self):
        mock_gogov = MagicMock()
        mock_gogov.get_topics.return_value = {"status": "ok"}
        client = GoGovClient(email="a", password="b", site="c")
        client._client = mock_gogov

        topics = client.get_topics()

        assert topics == []

    def test_returns_empty_list_when_data_is_empty(self):
        mock_gogov = MagicMock()
        mock_gogov.get_topics.return_value = {"data": []}
        client = GoGovClient(email="a", password="b", site="c")
        client._client = mock_gogov

        topics = client.get_topics()

        assert topics == []


# ============================================================================
# GoGovClient.get_issues — orchestration
# ============================================================================


class TestGetIssues:
    """Tests for issue fetching and normalization pipeline."""

    def _make_client_with_mock(self, raw_results):
        mock_gogov = MagicMock()
        mock_gogov.search.return_value = raw_results
        client = GoGovClient(
            email="a", password="b", site="c",
            jurisdiction_id="county-marin",
        )
        client._client = mock_gogov
        return client, mock_gogov

    def test_normalizes_and_returns_issues(self):
        raw = [_make_raw_issue(caseId="100"), _make_raw_issue(caseId="200")]
        client, _ = self._make_client_with_mock(raw)

        issues = client.get_issues(max_results=50)

        assert len(issues) == 2
        assert issues[0]["external_id"] == "100"
        assert issues[1]["external_id"] == "200"

    def test_sets_search_limit(self):
        client, mock_gogov = self._make_client_with_mock([])

        client.get_issues(max_results=250)

        assert mock_gogov.search_limit == 250

    def test_default_max_results_is_500(self):
        client, mock_gogov = self._make_client_with_mock([])

        client.get_issues()

        assert mock_gogov.search_limit == 500

    def test_skips_limit_when_max_results_is_none(self):
        raw = [_make_raw_issue(caseId="999")]
        client, mock_gogov = self._make_client_with_mock(raw)

        issues = client.get_issues(max_results=None)

        # search still runs and returns results even without setting limit
        assert len(issues) == 1
        assert issues[0]["external_id"] == "999"

    def test_filters_out_issues_without_case_id(self):
        raw = [
            _make_raw_issue(caseId="100"),
            _make_raw_issue(caseId=None, displayId=None),  # Should be skipped
            _make_raw_issue(caseId="300"),
        ]
        client, _ = self._make_client_with_mock(raw)

        issues = client.get_issues()

        assert len(issues) == 2
        assert issues[0]["external_id"] == "100"
        assert issues[1]["external_id"] == "300"

    def test_empty_search_results(self):
        client, _ = self._make_client_with_mock([])

        issues = client.get_issues()

        assert issues == []


# ============================================================================
# GoGovClient._normalize_issue — core normalization logic
# ============================================================================


class TestNormalizeIssue:
    """Tests for raw GOGov issue -> CivicOS schema normalization."""

    @pytest.fixture
    def client(self):
        return GoGovClient(
            email="a", password="b", site="c",
            jurisdiction_id="county-marin",
        )

    # --- ID generation ---

    def test_id_format(self, client):
        raw = _make_raw_issue(caseId="12345")
        result = client._normalize_issue(raw)
        assert result["id"] == "gogov-county-marin-12345"

    def test_uses_display_id_when_case_id_missing(self, client):
        raw = _make_raw_issue(caseId=None, displayId="DISP-999")
        result = client._normalize_issue(raw)
        assert result["id"] == "gogov-county-marin-DISP-999"
        assert result["external_id"] == "DISP-999"

    def test_prefers_case_id_over_display_id(self, client):
        raw = _make_raw_issue(caseId="111", displayId="DISP-222")
        result = client._normalize_issue(raw)
        assert result["external_id"] == "111"

    def test_returns_none_when_no_case_id_or_display_id(self, client):
        raw = _make_raw_issue(caseId=None, displayId=None)
        result = client._normalize_issue(raw)
        assert result is None

    def test_returns_none_when_case_id_empty_string(self, client):
        raw = _make_raw_issue(caseId="", displayId="")
        result = client._normalize_issue(raw)
        assert result is None

    # --- Provider ---

    def test_provider_is_gogov(self, client):
        raw = _make_raw_issue()
        result = client._normalize_issue(raw)
        assert result["provider"] == "gogov"

    def test_jurisdiction_id_from_client(self, client):
        raw = _make_raw_issue()
        result = client._normalize_issue(raw)
        assert result["jurisdiction_id"] == "county-marin"

    # --- Title and description ---

    def test_title_from_description(self, client):
        raw = _make_raw_issue(description="Broken streetlight on Elm St")
        result = client._normalize_issue(raw)
        assert result["title"] == "Broken streetlight on Elm St"

    def test_title_truncated_to_200_chars(self, client):
        long_desc = "A" * 300
        raw = _make_raw_issue(description=long_desc)
        result = client._normalize_issue(raw)
        assert len(result["title"]) == 200
        assert result["title"] == "A" * 200

    def test_description_preserved_in_full(self, client):
        long_desc = "B" * 300
        raw = _make_raw_issue(description=long_desc)
        result = client._normalize_issue(raw)
        assert result["description"] == long_desc
        assert len(result["description"]) == 300

    def test_title_fallback_when_description_empty(self, client):
        raw = _make_raw_issue(description="", caseId="42")
        result = client._normalize_issue(raw)
        assert result["title"] == "Case 42"

    def test_title_fallback_when_description_missing(self, client):
        raw = _make_raw_issue(caseId="77")
        del raw["description"]
        result = client._normalize_issue(raw)
        assert result["title"] == "Case 77"

    # --- Location ---

    def test_location_with_both_coordinates(self, client):
        raw = _make_raw_issue(locationPoint={"lat": 37.97, "lon": -122.53})
        result = client._normalize_issue(raw)
        assert result["latitude"] == 37.97
        assert result["longitude"] == -122.53

    def test_location_nullified_when_lat_missing(self, client):
        raw = _make_raw_issue(locationPoint={"lat": None, "lon": -122.53})
        result = client._normalize_issue(raw)
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_location_nullified_when_lon_missing(self, client):
        raw = _make_raw_issue(locationPoint={"lat": 37.97, "lon": None})
        result = client._normalize_issue(raw)
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_location_nullified_when_both_missing(self, client):
        raw = _make_raw_issue(locationPoint={"lat": None, "lon": None})
        result = client._normalize_issue(raw)
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_location_nullified_when_location_point_empty(self, client):
        raw = _make_raw_issue(locationPoint={})
        result = client._normalize_issue(raw)
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_location_nullified_when_location_point_missing(self, client):
        raw = _make_raw_issue()
        del raw["locationPoint"]
        result = client._normalize_issue(raw)
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_location_string_preserved(self, client):
        raw = _make_raw_issue(location="100 Main St, San Rafael, CA")
        result = client._normalize_issue(raw)
        assert result["location"] == "100 Main St, San Rafael, CA"

    # --- Date normalization ---

    def test_iso_date_normalized(self, client):
        raw = _make_raw_issue(dateEntered="2026-03-15T10:30:00")
        result = client._normalize_issue(raw)
        assert result["created_at"] == "2026-03-15T10:30:00"

    def test_updated_at_from_date_last_updated(self, client):
        raw = _make_raw_issue(
            dateEntered="2026-03-15T10:30:00",
            dateLastUpdated="2026-03-16T14:00:00",
        )
        result = client._normalize_issue(raw)
        assert result["updated_at"] == "2026-03-16T14:00:00"

    def test_updated_at_falls_back_to_created_at(self, client):
        raw = _make_raw_issue(
            dateEntered="2026-03-15T10:30:00",
            dateLastUpdated=None,
        )
        result = client._normalize_issue(raw)
        assert result["updated_at"] == "2026-03-15T10:30:00"

    def test_closed_at_normalized(self, client):
        raw = _make_raw_issue(dateClosed="2026-03-20T09:00:00")
        result = client._normalize_issue(raw)
        assert result["closed_at"] == "2026-03-20T09:00:00"

    def test_closed_at_none_when_not_closed(self, client):
        raw = _make_raw_issue(dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["closed_at"] is None

    def test_null_dates_return_none(self, client):
        raw = _make_raw_issue(dateEntered=None, dateLastUpdated=None, dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["created_at"] is None
        assert result["updated_at"] is None
        assert result["closed_at"] is None

    def test_unparseable_date_preserved_as_raw(self, client):
        raw = _make_raw_issue(dateEntered="March 15, 2026 at noon")
        result = client._normalize_issue(raw)
        # Unparseable by fromisoformat, so returned raw
        assert result["created_at"] == "March 15, 2026 at noon"

    # --- Status mapping ---

    def test_status_open(self, client):
        raw = _make_raw_issue(status="Open", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "open"

    def test_status_closed_from_status_field(self, client):
        raw = _make_raw_issue(status="Closed", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "closed"

    def test_status_closed_when_date_closed_present(self, client):
        raw = _make_raw_issue(status="Open", dateClosed="2026-03-20T09:00:00")
        result = client._normalize_issue(raw)
        assert result["status"] == "closed"

    def test_status_acknowledged(self, client):
        raw = _make_raw_issue(status="Acknowledged", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "acknowledged"

    def test_status_case_insensitive(self, client):
        raw = _make_raw_issue(status="CLOSED", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "closed"

    def test_status_contains_close_substring(self, client):
        raw = _make_raw_issue(status="Case Closed - Resolved", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "closed"

    def test_status_contains_acknowledge_substring(self, client):
        raw = _make_raw_issue(status="Auto-Acknowledged", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "acknowledged"

    def test_status_defaults_to_open_for_unknown(self, client):
        raw = _make_raw_issue(status="In Progress", dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "open"

    def test_status_none_treated_as_open(self, client):
        raw = _make_raw_issue(status=None, dateClosed=None)
        result = client._normalize_issue(raw)
        assert result["status"] == "open"

    # --- Category and metadata ---

    def test_category_from_classification_id(self, client):
        raw = _make_raw_issue(classificationId=42)
        result = client._normalize_issue(raw)
        assert result["category"] == "42"

    def test_category_empty_when_no_classification(self, client):
        raw = _make_raw_issue(classificationId=None)
        # Quirk: str(None) would give "None", but raw.get defaults to ""
        del raw["classificationId"]
        result = client._normalize_issue(raw)
        assert result["category"] == ""

    def test_priority_preserved(self, client):
        raw = _make_raw_issue(priority="High")
        result = client._normalize_issue(raw)
        assert result["priority"] == "High"

    def test_provider_metadata_populated(self, client):
        raw = _make_raw_issue(
            caseType="pothole",
            howEntered="mobile",
            departmentId="DPW-001",
        )
        result = client._normalize_issue(raw)
        meta = result["provider_metadata"]
        assert meta["case_type"] == "pothole"
        assert meta["how_entered"] == "mobile"
        assert meta["department_id"] == "DPW-001"

    def test_provider_metadata_with_missing_fields(self, client):
        raw = _make_raw_issue()
        del raw["caseType"]
        del raw["howEntered"]
        del raw["departmentId"]
        result = client._normalize_issue(raw)
        meta = result["provider_metadata"]
        assert meta["case_type"] is None
        assert meta["how_entered"] is None
        assert meta["department_id"] is None

    # --- Full output shape ---

    def test_all_expected_keys_present(self, client):
        raw = _make_raw_issue()
        result = client._normalize_issue(raw)
        expected_keys = {
            "id", "jurisdiction_id", "provider", "external_id",
            "title", "description", "status", "latitude", "longitude",
            "location", "created_at", "updated_at", "closed_at",
            "category", "priority", "provider_metadata",
        }
        assert set(result.keys()) == expected_keys


# ============================================================================
# GoGovClient.close — cleanup
# ============================================================================


class TestClose:
    """Tests for logout and cleanup."""

    def test_calls_logout_on_active_client(self):
        mock_gogov = MagicMock()
        client = GoGovClient(email="a", password="b", site="c")
        client._client = mock_gogov

        client.close()

        mock_gogov.logout.assert_called_once()
        assert client._client is None

    def test_noop_when_no_client(self):
        client = GoGovClient(email="a", password="b", site="c")
        assert client._client is None
        client.close()  # Should not raise
        assert client._client is None

    def test_swallows_logout_exception(self):
        mock_gogov = MagicMock()
        mock_gogov.logout.side_effect = ConnectionError("server gone")
        client = GoGovClient(email="a", password="b", site="c")
        client._client = mock_gogov

        client.close()  # Should not raise

        assert client._client is None

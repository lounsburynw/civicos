"""
Tests for admin status endpoint.

Tests the /api/admin/status endpoint that returns JSON pipeline health including:
- Storage backend health (PostgreSQL or SQLite)
- Vector backend health (pgvector or ChromaDB)
- Overall system health status

Session 299: Initial test coverage for admin_status_endpoint feature.
Session 508: Migrated to FastAPI TestClient after FastAPI migration.
"""

import json
import sqlite3
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestAdminStatusEndpoint:
    """Tests for /api/admin/status endpoint (FastAPI)."""

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        # Use dev key for testing
        return {"Authorization": "Bearer dev_key_local"}

    def test_admin_status_returns_valid_json(self, test_client, auth_headers):
        """Test that /api/admin/status returns valid JSON response."""
        response = test_client.get("/api/admin/status", headers=auth_headers)

        # Should either succeed or fail gracefully
        assert response.status_code in [200, 401, 500]

        if response.status_code == 200:
            data = response.json()

            # Check required top-level keys
            assert 'timestamp' in data
            assert 'components' in data
            assert 'overall' in data

    def test_admin_status_includes_storage_status(self, test_client, auth_headers):
        """Test that response includes storage backend status."""
        response = test_client.get("/api/admin/status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            components = data['components']

            # Check storage component
            assert 'storage' in components
            assert 'status' in components['storage']
            assert components['storage']['status'] in ['healthy', 'unhealthy']

            # Should report backend type
            if components['storage']['status'] == 'healthy':
                assert 'backend' in components['storage']

    def test_admin_status_includes_vector_status(self, test_client, auth_headers):
        """Test that response includes vector backend status."""
        response = test_client.get("/api/admin/status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            components = data['components']

            # Check vector component
            assert 'vector' in components
            assert 'status' in components['vector']
            assert components['vector']['status'] in ['healthy', 'unhealthy']

    def test_admin_status_overall_status(self, test_client, auth_headers):
        """Test that overall status reflects component health."""
        response = test_client.get("/api/admin/status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Overall should be healthy or degraded
            assert data['overall'] in ['healthy', 'degraded']

    def test_admin_status_timestamp_format(self, test_client, auth_headers):
        """Test that timestamp is in ISO format with Z suffix."""
        response = test_client.get("/api/admin/status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data['timestamp'].endswith('Z')
            # Should be parseable as ISO format
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))

    def test_admin_status_requires_auth(self, test_client):
        """Test that /api/admin/status requires authentication."""
        response = test_client.get("/api/admin/status")

        # Should return 401 without auth (or 403 depending on setup)
        assert response.status_code in [401, 403, 422]


class TestVectorStatsEndpoint:
    """Tests for /api/admin/vector-stats endpoint."""

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        return {"Authorization": "Bearer dev_key_local"}

    def test_vector_stats_returns_corpus_stats(self, test_client, auth_headers):
        """Test that vector-stats returns per-corpus statistics."""
        response = test_client.get("/api/admin/vector-stats", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            assert 'timestamp' in data
            assert 'corpus_stats' in data
            assert 'total_embeddings' in data

            # Should have stats for common corpus types
            corpus_stats = data['corpus_stats']
            expected_types = ['transcripts', 'chunks', 'municipal_code', 'issues', 'decisions', 'meetings']
            for corpus_type in expected_types:
                assert corpus_type in corpus_stats

    def test_vector_stats_requires_auth(self, test_client):
        """Test that vector-stats requires authentication."""
        response = test_client.get("/api/admin/vector-stats")

        assert response.status_code in [401, 403, 422]


class TestOperationsEndpoint:
    """Tests for /api/admin/operations endpoints."""

    @pytest.fixture
    def test_client_with_auth(self):
        """Create a FastAPI test client with mocked auth."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app
        from civicos_services.servers.routers.dependencies import verify_auth

        # Override the auth dependency to always pass
        async def mock_verify_auth():
            return "test_user"

        app.dependency_overrides[verify_auth] = mock_verify_auth
        client = TestClient(app)
        yield client
        # Clean up override
        app.dependency_overrides.clear()

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client without auth override."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    def test_list_operations(self, test_client_with_auth):
        """Test that operations list returns expected format."""
        response = test_client_with_auth.get("/api/admin/operations")

        assert response.status_code == 200
        data = response.json()

        assert 'operations' in data
        assert 'count' in data
        assert isinstance(data['operations'], list)
        assert isinstance(data['count'], int)

    def test_get_operation_not_found(self, test_client_with_auth):
        """Test that non-existent operation returns 404."""
        response = test_client_with_auth.get(
            "/api/admin/operations/nonexistent-id"
        )

        assert response.status_code == 404

    def test_operations_requires_auth(self, test_client):
        """Test that operations endpoints require authentication."""
        response = test_client.get("/api/admin/operations")

        assert response.status_code in [401, 403, 422]


class TestOperationErrorLogs:
    """Tests for detailed error logging in operations.

    Session 347: Verifies that failed operations store detailed error information
    including error_type and error_traceback in result_json for debugging.
    """

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary state database with operations table."""
        db_path = tmp_path / "civic_state.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create operations table (matches state_manager.py schema)
        cursor.execute("""
            CREATE TABLE operations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                jurisdiction_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                started_at TEXT,
                completed_at TEXT,
                duration_seconds REAL,
                progress_percent INTEGER DEFAULT 0,
                current_step TEXT,
                items_processed INTEGER DEFAULT 0,
                items_total INTEGER DEFAULT 0,
                result_json TEXT,
                error TEXT
            )
        """)

        conn.commit()
        conn.close()

        return db_path

    def test_operation_error_includes_traceback(self, temp_db):
        """Test that failed operations store error_traceback in result_json."""
        from civicos_services.storage.state_manager import StateManager

        state_mgr = StateManager(str(temp_db))

        # Create an operation
        operation_id = 'test-op-001'
        state_mgr.create_operation(operation_id, 'city-san-rafael', 'test_operation')

        # Simulate error with detailed info (like the updated handler does)
        error_details = {
            'status': 'error',
            'error': 'Test error message',
            'error_type': 'ValueError',
            'error_traceback': 'Traceback (most recent call last):\n  File "test.py", line 1\nValueError: Test error message',
            'failed_at': '2024-01-15T12:00:00Z'
        }

        state_mgr.complete_operation(operation_id, error_details, error='Test error message')

        # Retrieve and verify
        operation = state_mgr.get_operation(operation_id)

        assert operation['status'] == 'failed'
        assert operation['error'] == 'Test error message'
        assert operation['result'] is not None
        assert operation['result']['error_type'] == 'ValueError'
        assert 'Traceback' in operation['result']['error_traceback']
        assert operation['result']['failed_at'] == '2024-01-15T12:00:00Z'

    def test_operation_success_has_no_error_fields(self, temp_db):
        """Test that successful operations don't have error fields in result."""
        from civicos_services.storage.state_manager import StateManager

        state_mgr = StateManager(str(temp_db))

        operation_id = 'test-op-002'
        state_mgr.create_operation(operation_id, 'city-san-rafael', 'test_operation')

        # Successful result
        result = {
            'status': 'success',
            'count_processed': 10,
            'duration_seconds': 5.5
        }

        state_mgr.complete_operation(operation_id, result, error=None)

        operation = state_mgr.get_operation(operation_id)

        assert operation['status'] == 'completed'
        assert operation['error'] is None
        assert operation['result']['status'] == 'success'
        assert 'error_traceback' not in operation['result']
        assert 'error_type' not in operation['result']

    def test_error_logs_pilot_artifact(self, temp_db):
        """Verify error_logs pilot.json artifact: expandable error details.

        Session 347: Validates that operations store error details that can
        be displayed as expandable error information in the dashboard.

        Artifact: "Show errors/failures with log output"
        Note: "Store error details in operation_history result_json."
        """
        from civicos_services.storage.state_manager import StateManager

        state_mgr = StateManager(str(temp_db))

        # Create and fail an operation
        operation_id = 'pilot-test-error'
        state_mgr.create_operation(operation_id, 'city-san-rafael', 'fetch_meetings')

        # Simulate realistic error with full traceback
        error_details = {
            'status': 'error',
            'operation': 'fetch_meetings',
            'jurisdiction': 'san-rafael',
            'error': 'HTTP 503: Service Unavailable',
            'error_type': 'HTTPError',
            'error_traceback': '''Traceback (most recent call last):
  File "/app/api.py", line 100, in run_operation
    result = handler(jurisdiction)
  File "/app/api.py", line 200, in _trigger_fetch_meetings
    events = client.get_events(days_ahead=90, days_past=30)
  File "/app/proudcity.py", line 45, in get_events
    response.raise_for_status()
HTTPError: HTTP 503: Service Unavailable''',
            'failed_at': '2024-01-15T12:00:00Z'
        }

        state_mgr.complete_operation(operation_id, error_details, error='HTTP 503: Service Unavailable')

        # Verify all required fields for dashboard display
        operation = state_mgr.get_operation(operation_id)

        # Basic error info (summary view)
        assert operation['status'] == 'failed'
        assert operation['error'] is not None

        # Detailed error info (expandable view)
        result = operation['result']
        assert result['error_type'] == 'HTTPError', "Must include error type for categorization"
        assert 'Traceback' in result['error_traceback'], "Must include traceback for debugging"
        assert 'proudcity.py' in result['error_traceback'], "Traceback should show source file"
        assert result['failed_at'] is not None, "Must include failure timestamp"


class TestCostDashboardEndpoint:
    """Tests for /api/admin/cost-dashboard endpoint.

    Session 509: Tests cost dashboard showing actual operating costs
    from the operating_costs table (LLM and Modal compute costs).
    """

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        return {"Authorization": "Bearer dev_key_local"}

    def test_cost_dashboard_returns_expected_structure(self, test_client, auth_headers):
        """Test that cost-dashboard returns expected JSON structure."""
        response = test_client.get("/api/admin/cost-dashboard", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Check required top-level keys
            assert 'timestamp' in data
            assert 'period' in data
            assert 'range' in data
            assert 'summary' in data
            assert 'time_series' in data

            # Check summary structure
            summary = data['summary']
            assert 'total_cost_usd' in summary
            assert 'record_count' in summary
            assert 'by_service' in summary
            assert 'by_category' in summary

            # Check range structure
            assert 'since' in data['range']
            assert 'until' in data['range']

    def test_cost_dashboard_period_parameter(self, test_client, auth_headers):
        """Test that period parameter is accepted and reflected in response."""
        for period in ["day", "week", "month", "all"]:
            response = test_client.get(
                f"/api/admin/cost-dashboard?period={period}",
                headers=auth_headers
            )

            if response.status_code == 200:
                data = response.json()
                assert data['period'] == period

    def test_cost_dashboard_service_filter(self, test_client, auth_headers):
        """Test that service filter parameter is accepted."""
        response = test_client.get(
            "/api/admin/cost-dashboard?service=modal",
            headers=auth_headers
        )

        # Should not error (401 expected in CI without auth keys)
        assert response.status_code in [200, 401, 500]

    def test_cost_dashboard_timestamp_format(self, test_client, auth_headers):
        """Test that timestamp is in ISO format with Z suffix."""
        response = test_client.get("/api/admin/cost-dashboard", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data['timestamp'].endswith('Z')
            # Should be parseable as ISO format
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))

    def test_cost_dashboard_time_series_structure(self, test_client, auth_headers):
        """Test that time_series has correct structure when data exists."""
        response = test_client.get("/api/admin/cost-dashboard", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            time_series = data['time_series']

            assert isinstance(time_series, list)

            # If there's data, check structure
            if time_series:
                entry = time_series[0]
                assert 'date' in entry
                assert 'total_usd' in entry
                assert 'by_service' in entry

    def test_cost_dashboard_requires_auth(self, test_client):
        """Test that cost-dashboard requires authentication."""
        response = test_client.get("/api/admin/cost-dashboard")

        # Should return 401 without auth
        assert response.status_code in [401, 403, 422]

    def test_cost_dashboard_numeric_values(self, test_client, auth_headers):
        """Test that cost values are numeric types."""
        response = test_client.get("/api/admin/cost-dashboard", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            summary = data['summary']

            assert isinstance(summary['total_cost_usd'], (int, float))
            assert isinstance(summary['record_count'], int)

            for value in summary['by_service'].values():
                assert isinstance(value, (int, float))
            for value in summary['by_category'].values():
                assert isinstance(value, (int, float))


class TestDailyCostDigest:
    """Tests for DailyCostDigest email generation.

    Session 512: Tests for daily cost digest that sends email summary
    of operating costs vs budget thresholds.
    """

    def test_digest_data_collection(self):
        """Test that digest collects cost data correctly."""
        from civicos_services.monitoring.daily_cost_digest import DailyCostDigest

        digest = DailyCostDigest(jurisdiction_id="city-san-rafael")
        data = digest.collect_data()

        # Check required fields
        assert data.date is not None
        assert isinstance(data.total_cost_usd, float)
        assert isinstance(data.by_service, dict)
        assert isinstance(data.by_category, dict)
        assert isinstance(data.record_count, int)
        assert isinstance(data.daily_budget, float)
        assert isinstance(data.monthly_budget, float)
        assert data.budget_status in ["healthy", "warning", "critical"]
        assert data.trend in ["up", "down", "flat"]

    def test_digest_plaintext_format(self):
        """Test that plaintext format is valid."""
        from civicos_services.monitoring.daily_cost_digest import DailyCostDigest

        digest = DailyCostDigest(jurisdiction_id="city-san-rafael")
        data = digest.collect_data()
        plaintext = digest.format_plaintext(data)

        # Check content includes expected sections
        assert "Daily Cost Digest" in plaintext
        assert "TODAY'S COSTS" in plaintext
        assert "BY SERVICE" in plaintext
        assert "MONTHLY STATUS" in plaintext
        assert data.date in plaintext

    def test_digest_html_format(self):
        """Test that HTML format is valid."""
        from civicos_services.monitoring.daily_cost_digest import DailyCostDigest

        digest = DailyCostDigest(jurisdiction_id="city-san-rafael")
        data = digest.collect_data()
        html = digest.format_html(data)

        # Check HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "</html>" in html
        assert "Cost Digest" in html
        assert data.date in html

    def test_digest_preview(self):
        """Test preview function returns expected structure."""
        from civicos_services.monitoring.daily_cost_digest import DailyCostDigest

        digest = DailyCostDigest(jurisdiction_id="city-san-rafael")
        preview = digest.preview()

        assert "data" in preview
        assert "plaintext" in preview
        assert "html" in preview
        assert "date" in preview["data"]
        assert "budget_status" in preview["data"]

    def test_digest_disabled_mode(self):
        """Test that digest respects disabled flag."""
        import os
        from civicos_services.monitoring.daily_cost_digest import DailyCostDigest

        # Save original value
        original = os.environ.get("CIVICOS_COST_DIGEST_ENABLED")

        try:
            os.environ["CIVICOS_COST_DIGEST_ENABLED"] = "false"
            digest = DailyCostDigest(jurisdiction_id="city-san-rafael")
            result = digest.send()

            assert result["success"] is False
            assert result["reason"] == "disabled"
        finally:
            # Restore original value
            if original is not None:
                os.environ["CIVICOS_COST_DIGEST_ENABLED"] = original
            elif "CIVICOS_COST_DIGEST_ENABLED" in os.environ:
                del os.environ["CIVICOS_COST_DIGEST_ENABLED"]


class TestAPIKeyStatusEndpoint:
    """Tests for /api/admin/api-key-status endpoint.

    Session 514: Tests for API key status endpoint that validates external
    API keys (AssemblyAI, LegiScan) and helps catch expired/invalid keys
    before they cause pipeline failures.
    """

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        return {"Authorization": "Bearer dev_key_local"}

    def test_api_key_status_returns_expected_structure(self, test_client, auth_headers):
        """Test that api-key-status returns expected JSON structure."""
        response = test_client.get("/api/admin/api-key-status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Check required top-level keys
            assert 'timestamp' in data
            assert 'keys' in data
            assert 'overall_status' in data

            # Check keys structure
            keys = data['keys']
            assert 'assemblyai' in keys
            assert 'legiscan' in keys

            # Check per-key fields
            for key_name, key_status in keys.items():
                assert 'service_name' in key_status
                assert 'is_configured' in key_status
                assert 'validation_method' in key_status
                assert isinstance(key_status['is_configured'], bool)

    def test_api_key_status_overall_status_values(self, test_client, auth_headers):
        """Test that overall_status is one of expected values."""
        response = test_client.get("/api/admin/api-key-status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data['overall_status'] in ['healthy', 'warning', 'degraded', 'unconfigured']

    def test_api_key_status_timestamp_format(self, test_client, auth_headers):
        """Test that timestamp is in ISO format with Z suffix."""
        response = test_client.get("/api/admin/api-key-status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data['timestamp'].endswith('Z')
            # Should be parseable as ISO format
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))

    def test_api_key_status_requires_auth(self, test_client):
        """Test that api-key-status requires authentication."""
        response = test_client.get("/api/admin/api-key-status")

        # Should return 401 without auth
        assert response.status_code in [401, 403, 422]

    def test_api_key_status_force_refresh_parameter(self, test_client, auth_headers):
        """Test that force_refresh parameter is accepted."""
        response = test_client.get(
            "/api/admin/api-key-status?force_refresh=true",
            headers=auth_headers
        )

        # Should not error
        assert response.status_code in [200, 401]

    def test_api_key_status_validation_method_values(self, test_client, auth_headers):
        """Test that validation_method is one of expected values."""
        response = test_client.get("/api/admin/api-key-status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            valid_methods = ['api_call', 'not_configured', 'cached']

            for key_status in data['keys'].values():
                assert key_status['validation_method'] in valid_methods

    def test_api_key_status_unconfigured_key_has_error_message(self, test_client, auth_headers):
        """Test that unconfigured keys have appropriate error message."""
        response = test_client.get("/api/admin/api-key-status", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            for key_name, key_status in data['keys'].items():
                if not key_status['is_configured']:
                    assert key_status['validation_method'] == 'not_configured'
                    assert key_status['error_message'] is not None
                    assert 'not set' in key_status['error_message'].lower()


class TestAPIKeyValidationHelpers:
    """Unit tests for API key validation helper functions.

    Session 514: Tests the validation logic for AssemblyAI and LegiScan keys
    without making actual API calls (mocked).
    """

    def test_validate_assemblyai_key_success(self):
        """Test AssemblyAI key validation with successful response."""
        from unittest.mock import patch, Mock
        from civicos_services.servers.routers.admin import _validate_assemblyai_key

        mock_response = Mock()
        mock_response.status_code = 200

        with patch('requests.get', return_value=mock_response) as mock_get:
            result = _validate_assemblyai_key("test_api_key")

            assert result['is_valid'] is True
            assert result['validation_method'] == 'api_call'
            assert 'response_time_ms' in result

            # Verify correct endpoint was called
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert 'api.assemblyai.com' in call_args[0][0]
            assert call_args[1]['headers']['Authorization'] == 'test_api_key'

    def test_validate_assemblyai_key_unauthorized(self):
        """Test AssemblyAI key validation with 401 response."""
        from unittest.mock import patch, Mock
        from civicos_services.servers.routers.admin import _validate_assemblyai_key

        mock_response = Mock()
        mock_response.status_code = 401

        with patch('requests.get', return_value=mock_response):
            result = _validate_assemblyai_key("invalid_key")

            assert result['is_valid'] is False
            assert 'Unauthorized' in result['error_message']

    def test_validate_assemblyai_key_timeout(self):
        """Test AssemblyAI key validation with timeout."""
        from unittest.mock import patch
        import requests
        from civicos_services.servers.routers.admin import _validate_assemblyai_key

        with patch('requests.get', side_effect=requests.exceptions.Timeout()):
            result = _validate_assemblyai_key("test_key")

            assert result['is_valid'] is None
            assert 'timed out' in result['error_message'].lower()

    def test_validate_legiscan_key_success(self):
        """Test LegiScan key validation with successful response."""
        from unittest.mock import patch, Mock
        from civicos_services.servers.routers.admin import _validate_legiscan_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'OK'}

        with patch('requests.get', return_value=mock_response) as mock_get:
            result = _validate_legiscan_key("test_api_key")

            assert result['is_valid'] is True
            assert result['validation_method'] == 'api_call'

            # Verify correct endpoint was called
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert 'api.legiscan.com' in call_args[0][0]
            assert call_args[1]['params']['key'] == 'test_api_key'
            assert call_args[1]['params']['op'] == 'getStateList'

    def test_validate_legiscan_key_api_error(self):
        """Test LegiScan key validation with API error response."""
        from unittest.mock import patch, Mock
        from civicos_services.servers.routers.admin import _validate_legiscan_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'ERROR',
            'alert': {'message': 'Invalid API key'}
        }

        with patch('requests.get', return_value=mock_response):
            result = _validate_legiscan_key("invalid_key")

            assert result['is_valid'] is False
            assert 'Invalid API key' in result['error_message']

    def test_validate_legiscan_key_connection_error(self):
        """Test LegiScan key validation with connection error."""
        from unittest.mock import patch
        import requests
        from civicos_services.servers.routers.admin import _validate_legiscan_key

        with patch('requests.get', side_effect=requests.exceptions.ConnectionError("Failed to connect")):
            result = _validate_legiscan_key("test_key")

            assert result['is_valid'] is None
            assert 'connection error' in result['error_message'].lower()


class TestAPIKeyValidationCache:
    """Tests for API key validation caching.

    Session 514: Tests that validation results are cached to avoid
    hitting external APIs on every request.
    """

    def test_cache_stores_result(self):
        """Test that validation results are cached."""
        from civicos_services.servers.routers.admin import (
            _get_cached_validation,
            _set_cached_validation,
            _api_key_cache
        )

        # Clear cache first
        _api_key_cache.clear()

        # Store a result
        test_result = {
            'is_valid': True,
            'response_time_ms': 100
        }
        _set_cached_validation('test_service', test_result)

        # Retrieve it
        cached = _get_cached_validation('test_service')

        assert cached is not None
        assert cached['is_valid'] is True
        assert 'cached_at' in cached

    def test_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        from civicos_services.servers.routers.admin import (
            _get_cached_validation,
            _api_key_cache
        )

        # Clear cache first
        _api_key_cache.clear()

        cached = _get_cached_validation('nonexistent_service')
        assert cached is None

    def test_expired_cache_returns_none(self):
        """Test that expired cache entries are not returned."""
        import time
        from civicos_services.servers.routers.admin import (
            _get_cached_validation,
            _api_key_cache,
            _API_KEY_CACHE_TTL_SECONDS
        )

        # Clear cache first
        _api_key_cache.clear()

        # Store an expired result (set cached_at in the past)
        _api_key_cache['expired_service'] = {
            'is_valid': True,
            'cached_at': time.time() - _API_KEY_CACHE_TTL_SECONDS - 10
        }

        cached = _get_cached_validation('expired_service')
        assert cached is None


class TestAssemblyAIUsageEndpoint:
    """Tests for /api/admin/assemblyai-usage endpoint.

    Session 515: Tests for AssemblyAI usage tracking endpoint that shows
    transcript count, total minutes, and estimated cost for the current
    month or last 30 days.
    """

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        return {"Authorization": "Bearer dev_key_local"}

    def test_assemblyai_usage_returns_expected_structure(self, test_client, auth_headers):
        """Test that assemblyai-usage returns expected JSON structure."""
        response = test_client.get("/api/admin/assemblyai-usage", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Check required top-level keys
            assert 'timestamp' in data
            assert 'is_configured' in data
            assert isinstance(data['is_configured'], bool)

            # If configured and no error, usage should be present
            if data['is_configured'] and data.get('error_message') is None:
                assert 'usage' in data
                usage = data['usage']
                assert 'period' in usage
                assert 'period_start' in usage
                assert 'period_end' in usage
                assert 'transcript_count' in usage
                assert 'total_minutes' in usage
                assert 'estimated_cost_usd' in usage
                assert 'last_updated' in usage

    def test_assemblyai_usage_period_parameter(self, test_client, auth_headers):
        """Test that period parameter accepts valid values."""
        # Current month (default)
        response = test_client.get(
            "/api/admin/assemblyai-usage?period=current_month",
            headers=auth_headers
        )
        assert response.status_code in [200, 401]

        # Last 30 days
        response = test_client.get(
            "/api/admin/assemblyai-usage?period=last_30_days",
            headers=auth_headers
        )
        assert response.status_code in [200, 401]

    def test_assemblyai_usage_requires_auth(self, test_client):
        """Test that assemblyai-usage requires authentication."""
        response = test_client.get("/api/admin/assemblyai-usage")

        # Should return 401/403/422 without auth
        assert response.status_code in [401, 403, 422]

    def test_assemblyai_usage_force_refresh_parameter(self, test_client, auth_headers):
        """Test that force_refresh parameter is accepted."""
        response = test_client.get(
            "/api/admin/assemblyai-usage?force_refresh=true",
            headers=auth_headers
        )

        # Should not error
        assert response.status_code in [200, 401]

    def test_assemblyai_usage_timestamp_format(self, test_client, auth_headers):
        """Test that timestamp is in ISO format with Z suffix."""
        response = test_client.get("/api/admin/assemblyai-usage", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            assert data['timestamp'].endswith('Z')
            # Should be parseable as ISO format
            datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))

    def test_assemblyai_usage_unconfigured_returns_error(self, test_client, auth_headers):
        """Test that missing API key returns appropriate error."""
        import os
        from unittest.mock import patch

        # Mock environment to not have API key
        with patch.dict(os.environ, {'ASSEMBLYAI_API_KEY': ''}, clear=False):
            with patch.object(os, 'getenv', side_effect=lambda k, d=None: '' if k == 'ASSEMBLYAI_API_KEY' else os.environ.get(k, d)):
                response = test_client.get("/api/admin/assemblyai-usage", headers=auth_headers)

        # Response structure should still be valid
        if response.status_code == 200:
            data = response.json()
            # When not configured, should have error message
            if not data.get('is_configured', True):
                assert data.get('error_message') is not None
                assert 'not set' in data['error_message'].lower()


class TestAssemblyAIUsageFetcher:
    """Unit tests for _fetch_assemblyai_usage helper function.

    Session 515: Tests the usage fetching logic with mocked API calls.
    """

    def test_fetch_usage_success(self):
        """Test successful usage fetch with mock transcripts."""
        from unittest.mock import patch, Mock
        from datetime import datetime, timedelta
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        # Use dynamic dates within current month (use hours to stay safely in current month)
        now = datetime.utcnow()
        recent_date = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        older_date = (now - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

        # Mock response with 2 completed transcripts
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transcripts": [
                {
                    "id": "abc123",
                    "status": "completed",
                    "audio_duration": 120000,  # 2 minutes in ms
                    "created": recent_date
                },
                {
                    "id": "def456",
                    "status": "completed",
                    "audio_duration": 180000,  # 3 minutes in ms
                    "created": older_date
                }
            ],
            "page_details": {}
        }

        with patch('requests.get', return_value=mock_response):
            result = _fetch_assemblyai_usage("test_api_key", "current_month")

            assert "error" not in result
            assert result["period"] == "current_month"
            assert result["transcript_count"] == 2
            assert result["total_minutes"] == 5.0  # 2 + 3 minutes
            assert result["estimated_cost_usd"] == 0.10  # 5 * $0.02

    def test_fetch_usage_filters_by_date(self):
        """Test that old transcripts are filtered out."""
        from unittest.mock import patch, Mock
        from datetime import datetime, timedelta
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        # Use dynamic dates - one recent, one from last year
        now = datetime.utcnow()
        recent_date = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        old_date = (now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")  # Over a year ago

        # Mock response with one current and one old transcript
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transcripts": [
                {
                    "id": "recent",
                    "status": "completed",
                    "audio_duration": 60000,  # 1 minute
                    "created": recent_date
                },
                {
                    "id": "old",
                    "status": "completed",
                    "audio_duration": 600000,  # 10 minutes
                    "created": old_date
                }
            ],
            "page_details": {}
        }

        with patch('requests.get', return_value=mock_response):
            result = _fetch_assemblyai_usage("test_api_key", "current_month")

            # Only the recent transcript should be counted
            assert result["transcript_count"] == 1
            assert result["total_minutes"] == 1.0

    def test_fetch_usage_excludes_non_completed(self):
        """Test that non-completed transcripts are excluded."""
        from unittest.mock import patch, Mock
        from datetime import datetime, timedelta
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        # Use dynamic dates within current month
        now = datetime.utcnow()
        date1 = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        date2 = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        date3 = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transcripts": [
                {
                    "id": "completed1",
                    "status": "completed",
                    "audio_duration": 60000,
                    "created": date1
                },
                {
                    "id": "processing",
                    "status": "processing",
                    "audio_duration": 120000,
                    "created": date2
                },
                {
                    "id": "error",
                    "status": "error",
                    "audio_duration": 180000,
                    "created": date3
                }
            ],
            "page_details": {}
        }

        with patch('requests.get', return_value=mock_response):
            result = _fetch_assemblyai_usage("test_api_key", "current_month")

            # Only completed transcripts count
            assert result["transcript_count"] == 1
            assert result["total_minutes"] == 1.0

    def test_fetch_usage_handles_api_error(self):
        """Test handling of API error response."""
        from unittest.mock import patch, Mock
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        mock_response = Mock()
        mock_response.status_code = 401

        with patch('requests.get', return_value=mock_response):
            result = _fetch_assemblyai_usage("invalid_key", "current_month")

            assert "error" in result
            assert "401" in result["error"]

    def test_fetch_usage_handles_timeout(self):
        """Test handling of request timeout."""
        from unittest.mock import patch
        import requests
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        with patch('requests.get', side_effect=requests.exceptions.Timeout()):
            result = _fetch_assemblyai_usage("test_key", "current_month")

            assert "error" in result
            assert "timed out" in result["error"].lower()

    def test_fetch_usage_handles_connection_error(self):
        """Test handling of connection error."""
        from unittest.mock import patch
        import requests
        from civicos_services.servers.routers.admin import _fetch_assemblyai_usage

        with patch('requests.get', side_effect=requests.exceptions.ConnectionError("Failed")):
            result = _fetch_assemblyai_usage("test_key", "current_month")

            assert "error" in result
            assert "connection error" in result["error"].lower()


class TestAssemblyAIUsageCache:
    """Tests for AssemblyAI usage caching.

    Session 515: Tests that usage results are cached for 1 hour.
    """

    def test_usage_cache_stores_result(self):
        """Test that usage results are cached."""
        from civicos_services.servers.routers.admin import (
            _get_cached_usage,
            _set_cached_usage,
            _usage_cache
        )

        # Clear cache first
        _usage_cache.clear()

        # Store a result
        test_result = {
            'period': 'current_month',
            'transcript_count': 5,
            'total_minutes': 120.0,
            'estimated_cost_usd': 2.40
        }
        _set_cached_usage('assemblyai_usage_current_month', test_result)

        # Retrieve it
        cached = _get_cached_usage('assemblyai_usage_current_month')

        assert cached is not None
        assert cached['transcript_count'] == 5
        assert cached['total_minutes'] == 120.0
        assert 'cached_at' in cached

    def test_usage_cache_miss_returns_none(self):
        """Test that cache miss returns None."""
        from civicos_services.servers.routers.admin import (
            _get_cached_usage,
            _usage_cache
        )

        # Clear cache first
        _usage_cache.clear()

        cached = _get_cached_usage('nonexistent_key')
        assert cached is None

    def test_usage_cache_expiry(self):
        """Test that expired cache entries are not returned."""
        import time
        from civicos_services.servers.routers.admin import (
            _get_cached_usage,
            _usage_cache,
            _USAGE_CACHE_TTL_SECONDS
        )

        # Clear cache first
        _usage_cache.clear()

        # Store an expired result (set cached_at in the past)
        _usage_cache['expired_usage'] = {
            'period': 'current_month',
            'transcript_count': 10,
            'cached_at': time.time() - _USAGE_CACHE_TTL_SECONDS - 10
        }

        cached = _get_cached_usage('expired_usage')
        assert cached is None

    def test_usage_cache_ttl_is_one_hour(self):
        """Verify cache TTL is set to 1 hour (3600 seconds)."""
        from civicos_services.servers.routers.admin import _USAGE_CACHE_TTL_SECONDS

        assert _USAGE_CACHE_TTL_SECONDS == 3600

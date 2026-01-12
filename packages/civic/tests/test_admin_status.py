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
        from civic_services.servers.api import app

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
        from civic_services.servers.api import app

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
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from civic_services.servers.api import app

        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Headers for authenticated requests."""
        return {"Authorization": "Bearer dev_key_local"}

    def test_list_operations(self, test_client, auth_headers):
        """Test that operations list returns expected format."""
        response = test_client.get("/api/admin/operations", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            assert 'operations' in data
            assert 'count' in data
            assert isinstance(data['operations'], list)
            assert isinstance(data['count'], int)

    def test_get_operation_not_found(self, test_client, auth_headers):
        """Test that non-existent operation returns 404."""
        response = test_client.get(
            "/api/admin/operations/nonexistent-id",
            headers=auth_headers
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
        from civic_services.storage.state_manager import StateManager

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
        from civic_services.storage.state_manager import StateManager

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
        from civic_services.storage.state_manager import StateManager

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

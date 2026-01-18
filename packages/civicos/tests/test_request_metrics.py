"""
Tests for request metrics tracking system.

Tests request volume monitoring, response time tracking, and health endpoint integration.

Session 296: Initial test coverage for request_count feature.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


class TestRequestMetricsCollector:
    """Tests for RequestMetricsCollector class."""

    def test_calculate_metrics_no_log_file(self, tmp_path):
        """Test metrics calculation when log file doesn't exist."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        collector = RequestMetricsCollector(log_file=str(tmp_path / "nonexistent.log"))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 0
        assert metrics.requests_per_minute == 0.0
        assert metrics.success_count == 0
        assert metrics.server_error_count == 0

    def test_calculate_metrics_with_requests(self, tmp_path):
        """Test metrics calculation with mixed responses."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        # Create log file with test data
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            # 8 successful requests
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/events", "method": "GET", "duration_ms": 50.0}} for _ in range(8)],
            # 1 client error
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 404, "path": "/api/missing", "method": "GET", "duration_ms": 10.0}},
            # 1 server error
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/failing", "method": "POST", "duration_ms": 100.0}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = RequestMetricsCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 10
        assert metrics.success_count == 8
        assert metrics.client_error_count == 1
        assert metrics.server_error_count == 1
        assert metrics.requests_per_minute == 2.0  # 10 requests / 5 minutes

    def test_calculate_metrics_response_times(self, tmp_path):
        """Test response time percentile calculations."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        # Create 100 requests with predictable response times
        log_entries = [
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test", "method": "GET", "duration_ms": float(i)}}
            for i in range(1, 101)  # 1ms to 100ms
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = RequestMetricsCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 100
        # Percentile values depend on exact algorithm; check reasonable ranges
        assert 49 <= metrics.response_time_p50 <= 52  # ~50th percentile
        assert 94 <= metrics.response_time_p95 <= 97  # ~95th percentile
        assert metrics.response_time_avg == 50.5  # Average of 1-100

    def test_calculate_metrics_top_endpoints(self, tmp_path):
        """Test top endpoint aggregation."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/events", "method": "GET"}} for _ in range(50)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/issues", "method": "GET"}} for _ in range(30)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/users", "method": "GET"}} for _ in range(20)],
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = RequestMetricsCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # Verify top endpoints are sorted by count
        assert len(metrics.top_endpoints) == 3
        assert metrics.top_endpoints[0]["path"] == "/api/events"
        assert metrics.top_endpoints[0]["count"] == 50
        assert metrics.top_endpoints[1]["path"] == "/api/issues"
        assert metrics.top_endpoints[1]["count"] == 30
        assert metrics.top_endpoints[2]["path"] == "/api/users"
        assert metrics.top_endpoints[2]["count"] == 20

    def test_calculate_metrics_by_method(self, tmp_path):
        """Test request counting by HTTP method."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test", "method": "GET"}} for _ in range(10)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 201, "path": "/api/test", "method": "POST"}} for _ in range(5)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test", "method": "PUT"}} for _ in range(3)],
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = RequestMetricsCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.requests_by_method["GET"] == 10
        assert metrics.requests_by_method["POST"] == 5
        assert metrics.requests_by_method["PUT"] == 3

    def test_normalize_path_removes_query_strings(self, tmp_path):
        """Test path normalization removes query strings."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        collector = RequestMetricsCollector(log_file=str(tmp_path / "test.log"))

        # Query strings should be stripped
        assert collector._normalize_path("/api/events?limit=10&offset=0") == "/api/events"
        assert collector._normalize_path("/api/search?q=housing") == "/api/search"

    def test_normalize_path_replaces_ids(self, tmp_path):
        """Test path normalization replaces ID-like segments."""
        from civicos_services.monitoring.request_metrics import RequestMetricsCollector

        collector = RequestMetricsCollector(log_file=str(tmp_path / "test.log"))

        # Numeric IDs
        assert collector._normalize_path("/api/issues/12345") == "/api/issues/{id}"

        # UUID-like segments
        assert collector._normalize_path("/api/users/abc-def-123/profile") == "/api/users/{id}/profile"


class TestRequestMetricsManager:
    """Tests for RequestMetricsManager class."""

    def test_get_request_metrics_returns_dict(self, tmp_path):
        """Test that get_request_metrics returns a serializable dict."""
        from civicos_services.monitoring.request_metrics import RequestMetricsManager

        manager = RequestMetricsManager(
            log_file=str(tmp_path / "test.log"),
            window_minutes=5
        )

        metrics = manager.get_request_metrics()

        assert isinstance(metrics, dict)
        assert "total_requests" in metrics
        assert "requests_per_minute" in metrics
        assert "window_minutes" in metrics
        assert metrics["window_minutes"] == 5

    def test_get_request_count(self, tmp_path):
        """Test get_request_count convenience method."""
        from civicos_services.monitoring.request_metrics import RequestMetricsManager

        # Create log file with test data
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test", "method": "GET"}}
            for _ in range(15)
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = RequestMetricsManager(log_file=str(log_file))
        count = manager.get_request_count()

        assert count == 15

    def test_window_override(self, tmp_path):
        """Test that window can be overridden in method calls."""
        from civicos_services.monitoring.request_metrics import RequestMetricsManager

        manager = RequestMetricsManager(
            log_file=str(tmp_path / "test.log"),
            window_minutes=5
        )

        # Override to 10 minute window
        metrics = manager.get_request_metrics(window_minutes=10)

        assert metrics["window_minutes"] == 10


class TestModuleSingleton:
    """Tests for module-level singleton pattern."""

    def test_get_request_metrics_manager_returns_same_instance(self):
        """Test that get_request_metrics_manager returns a singleton."""
        from civicos_services.monitoring import request_metrics

        # Reset the singleton
        request_metrics._request_metrics_manager = None
        request_metrics._request_metrics_manager = None

        manager1 = request_metrics.get_request_metrics_manager()
        manager2 = request_metrics.get_request_metrics_manager()

        assert manager1 is manager2


class TestHealthEndpointIntegration:
    """Tests for request metrics integration with /health endpoint."""

    def test_check_request_metrics_returns_expected_structure(self, tmp_path):
        """Test _check_request_metrics returns proper health check structure."""
        # This tests the integration pattern without running the full server
        from civicos_services.monitoring.request_metrics import RequestMetricsManager

        manager = RequestMetricsManager(log_file=str(tmp_path / "test.log"))
        metrics = manager.get_request_metrics()

        # Verify all expected fields are present
        assert "total_requests" in metrics
        assert "requests_per_minute" in metrics
        assert "success_count" in metrics
        assert "client_error_count" in metrics
        assert "server_error_count" in metrics
        assert "response_time_p50" in metrics
        assert "response_time_p95" in metrics
        assert "top_endpoints" in metrics
        assert "requests_by_method" in metrics

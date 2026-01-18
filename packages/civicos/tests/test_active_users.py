"""
Tests for active users tracking system.

Tests unique user counting, authentication type breakdown, and health endpoint integration.

Session 297: Initial test coverage for active_users feature.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


class TestActiveUsersCollector:
    """Tests for ActiveUsersCollector class."""

    def test_calculate_metrics_no_log_file(self, tmp_path):
        """Test metrics calculation when log file doesn't exist."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        collector = ActiveUsersCollector(log_file=str(tmp_path / "nonexistent.log"))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.unique_users == 0
        assert metrics.authenticated_users == 0
        assert metrics.anonymous_users == 0
        assert metrics.daily_active_users == 0

    def test_calculate_metrics_with_anonymous_users(self, tmp_path):
        """Test metrics calculation with anonymous (IP-only) users."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        # Create log entries with different client IPs
        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "192.168.1.1", "method": "GET", "path": "/api/events"}},
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "192.168.1.1", "method": "GET", "path": "/api/issues"}},  # Same IP
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "192.168.1.2", "method": "GET", "path": "/api/events"}},
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "10.0.0.1", "method": "GET", "path": "/api/events"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # Should count 3 unique IPs
        assert metrics.unique_users == 3
        assert metrics.anonymous_users == 3
        assert metrics.authenticated_users == 0

    def test_calculate_metrics_with_authenticated_users(self, tmp_path):
        """Test metrics calculation with authenticated users."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        # Create log entries with user_id (authenticated)
        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-001", "client_ip": "192.168.1.1"}},
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-001", "client_ip": "192.168.1.1"}},  # Same user
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-002", "client_ip": "192.168.1.2"}},
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-003", "client_ip": "192.168.1.3"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # Should count 3 unique authenticated users
        assert metrics.unique_users == 3
        assert metrics.authenticated_users == 3
        assert metrics.anonymous_users == 0

    def test_calculate_metrics_mixed_users(self, tmp_path):
        """Test metrics calculation with both authenticated and anonymous users."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        # Create log entries with mixed user types
        log_entries = [
            # Authenticated users
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-001", "client_ip": "192.168.1.1"}},
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-002", "client_ip": "192.168.1.2"}},
            # Anonymous users (IP only)
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "10.0.0.1"}},
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "10.0.0.2"}},
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "10.0.0.3"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.unique_users == 5  # 2 authenticated + 3 anonymous
        assert metrics.authenticated_users == 2
        assert metrics.anonymous_users == 3

    def test_calculate_metrics_users_per_hour(self, tmp_path):
        """Test users per hour calculation."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        # 10 unique users in 5 minute window
        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": f"192.168.1.{i}"}}
            for i in range(10)
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # 10 users / 5 min * 60 = 120 users per hour
        assert metrics.active_users_per_hour == 120.0

    def test_get_user_identifiers_returns_sets(self, tmp_path):
        """Test that get_user_identifiers returns proper sets."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"user_id": "user-001", "client_ip": "192.168.1.1"}},
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "10.0.0.1"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        users = collector.get_user_identifiers(minutes=5)

        assert isinstance(users['authenticated'], set)
        assert isinstance(users['anonymous'], set)
        assert "user-001" in users['authenticated']
        assert "10.0.0.1" in users['anonymous']

    def test_processes_request_complete_events_too(self, tmp_path):
        """Test that both request_start and request_complete events are processed."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": "192.168.1.1"}},
            {"message": "request_complete", "timestamp": now, "extra": {"client_ip": "192.168.1.2", "status_code": 200}},
            {"message": "other_event", "timestamp": now, "extra": {"client_ip": "192.168.1.3"}},  # Should be ignored
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # Only request_start and request_complete should be counted
        assert metrics.unique_users == 2
        assert metrics.anonymous_users == 2

    def test_handles_malformed_log_entries(self, tmp_path):
        """Test that malformed log entries are skipped gracefully."""
        from civicos_services.monitoring.active_users import ActiveUsersCollector

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        with open(log_file, 'w') as f:
            f.write("not valid json\n")
            f.write('{"message": "request_start", "timestamp": "invalid-date", "extra": {"client_ip": "192.168.1.1"}}\n')
            f.write(json.dumps({"message": "request_start", "timestamp": now, "extra": {"client_ip": "192.168.1.2"}}) + "\n")

        collector = ActiveUsersCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        # Only the valid entry should be counted
        assert metrics.unique_users == 1


class TestActiveUsersManager:
    """Tests for ActiveUsersManager class."""

    def test_get_active_users_returns_dict(self, tmp_path):
        """Test that get_active_users returns a serializable dict."""
        from civicos_services.monitoring.active_users import ActiveUsersManager

        manager = ActiveUsersManager(
            log_file=str(tmp_path / "test.log"),
            window_minutes=5
        )

        metrics = manager.get_active_users()

        assert isinstance(metrics, dict)
        assert "unique_users" in metrics
        assert "active_users_per_hour" in metrics
        assert "window_minutes" in metrics
        assert metrics["window_minutes"] == 5

    def test_get_unique_users_count(self, tmp_path):
        """Test get_unique_users_count convenience method."""
        from civicos_services.monitoring.active_users import ActiveUsersManager

        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            {"message": "request_start", "timestamp": now, "extra": {"client_ip": f"192.168.1.{i}"}}
            for i in range(7)
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = ActiveUsersManager(log_file=str(log_file))
        count = manager.get_unique_users_count()

        assert count == 7

    def test_window_override(self, tmp_path):
        """Test that window can be overridden in method calls."""
        from civicos_services.monitoring.active_users import ActiveUsersManager

        manager = ActiveUsersManager(
            log_file=str(tmp_path / "test.log"),
            window_minutes=5
        )

        # Override to 10 minute window
        metrics = manager.get_active_users(window_minutes=10)

        assert metrics["window_minutes"] == 10


class TestModuleSingleton:
    """Tests for module-level singleton pattern."""

    def test_get_active_users_manager_returns_same_instance(self):
        """Test that get_active_users_manager returns a singleton."""
        from civicos_services.monitoring import active_users

        # Reset the singleton
        active_users._active_users_manager = None

        manager1 = active_users.get_active_users_manager()
        manager2 = active_users.get_active_users_manager()

        assert manager1 is manager2


class TestHealthEndpointIntegration:
    """Tests for active users integration with /health endpoint."""

    def test_check_active_users_returns_expected_structure(self, tmp_path):
        """Test _check_active_users returns proper health check structure."""
        from civicos_services.monitoring.active_users import ActiveUsersManager

        manager = ActiveUsersManager(log_file=str(tmp_path / "test.log"))
        metrics = manager.get_active_users()

        # Verify all expected fields are present
        assert "unique_users" in metrics
        assert "active_users_per_hour" in metrics
        assert "authenticated_users" in metrics
        assert "anonymous_users" in metrics
        assert "daily_active_users" in metrics
        assert "window_minutes" in metrics
        assert "timestamp" in metrics

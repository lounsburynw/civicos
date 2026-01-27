"""
Tests for error alerting system.

Tests email and push notification channels for error rate alerts.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestErrorMetricsCollector:
    """Tests for ErrorMetricsCollector class."""

    def test_calculate_metrics_no_log_file(self, tmp_path):
        """Test metrics calculation when log file doesn't exist."""
        from civicos_services.monitoring.error_alerting import ErrorMetricsCollector

        collector = ErrorMetricsCollector(log_file=str(tmp_path / "nonexistent.log"))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 0
        assert metrics.error_count == 0
        assert metrics.error_rate_percent == 0.0
        assert metrics.status == "normal"

    def test_calculate_metrics_with_errors(self, tmp_path):
        """Test metrics calculation with mixed responses."""
        from civicos_services.monitoring.error_alerting import ErrorMetricsCollector

        # Create log file with test data
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            # 8 successful requests
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test"}} for _ in range(8)],
            # 2 server errors (20% error rate)
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/failing"}},
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 503, "path": "/api/failing"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        collector = ErrorMetricsCollector(log_file=str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 10
        assert metrics.error_count == 2
        assert metrics.error_rate_percent == 20.0
        assert metrics.status == "critical"  # >= 10%
        assert len(metrics.top_error_endpoints) == 1
        assert metrics.top_error_endpoints[0]["path"] == "/api/failing"


class TestErrorAlertManager:
    """Tests for ErrorAlertManager class."""

    def test_init_reads_environment_variables(self, tmp_path, monkeypatch):
        """Test that manager reads configuration from environment."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        monkeypatch.setenv("CIVICOS_ALERT_EMAILS", "test@example.com, admin@example.com")
        monkeypatch.setenv("CIVICOS_SMTP_SERVER", "smtp.test.com")
        monkeypatch.setenv("CIVICOS_SMTP_PORT", "465")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        assert manager.alert_emails == ["test@example.com", "admin@example.com"]
        assert manager.smtp_server == "smtp.test.com"
        assert manager.smtp_port == 465

    def test_check_and_alert_insufficient_requests(self, tmp_path, monkeypatch):
        """Test that alerts are not triggered with insufficient requests."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Clean environment
        monkeypatch.delenv("CIVICOS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)

        # Create log with only 5 requests (below min_requests=10)
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/test"}}
            for _ in range(5)
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = ErrorAlertManager(
            log_file=str(log_file),
            alert_log_file=str(tmp_path / "alerts.json"),
            min_requests=10
        )

        result = manager.check_and_alert()
        assert result is None  # No alert due to insufficient data

    def test_check_and_alert_below_threshold(self, tmp_path, monkeypatch):
        """Test that no alert is triggered when error rate is below threshold."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        monkeypatch.delenv("CIVICOS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)

        # Create log with 1% error rate (below 5% threshold)
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test"}} for _ in range(99)],
            {"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/test"}},
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = ErrorAlertManager(
            log_file=str(log_file),
            alert_log_file=str(tmp_path / "alerts.json"),
            min_requests=10
        )

        result = manager.check_and_alert()
        assert result is None  # No alert, error rate too low


class TestPushAlertChannel:
    """Tests for push notification alert channel (ntfy or legacy Slack)."""

    def test_send_push_alert_not_configured(self, tmp_path, monkeypatch):
        """Test push alert returns False when no backend is configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)
        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type="error_rate_critical",
            error_rate=15.0,
            threshold=10.0,
            total_requests=100,
            error_count=15,
            top_endpoints=["/api/test"],
            notification_sent=False,
            notification_method="log_only"
        )

        metrics = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=15,
            client_error_count=5,
            error_rate_percent=15.0,
            status="critical",
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[{"path": "/api/test", "count": 10}]
        )

        result = manager._send_push_alert(alert, metrics)
        assert result is False

    def test_send_push_alert_via_ntfy(self, tmp_path, monkeypatch):
        """Test successful push notification delivery via ntfy."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.setenv("CIVICOS_NTFY_TOPIC", "civicos-test-abc123")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type="error_rate_critical",
            error_rate=15.0,
            threshold=10.0,
            total_requests=100,
            error_count=15,
            top_endpoints=["/api/test"],
            notification_sent=False,
            notification_method="log_only"
        )

        metrics = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=15,
            client_error_count=5,
            error_rate_percent=15.0,
            status="critical",
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[{"path": "/api/test", "count": 10}]
        )

        with patch("civicos_services.monitoring.notify.send_notification", return_value=True) as mock_notify:
            result = manager._send_push_alert(alert, metrics)

        assert result is True
        mock_notify.assert_called_once()

        # Verify title includes severity
        call_kwargs = mock_notify.call_args
        assert "CRITICAL" in call_kwargs.kwargs.get("title", "") or "CRITICAL" in call_kwargs[1].get("title", "")

    def test_send_push_alert_via_slack_legacy(self, tmp_path, monkeypatch):
        """Test push notification delivery falls back to Slack webhook."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type="error_rate_elevated",
            error_rate=7.0,
            threshold=5.0,
            total_requests=100,
            error_count=7,
            top_endpoints=["/api/test"],
            notification_sent=False,
            notification_method="log_only"
        )

        metrics = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=7,
            client_error_count=3,
            error_rate_percent=7.0,
            status="elevated",
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[{"path": "/api/test", "count": 5}]
        )

        with patch("civicos_services.monitoring.notify.send_notification", return_value=True) as mock_notify:
            result = manager._send_push_alert(alert, metrics)

        assert result is True
        mock_notify.assert_called_once()

        # Verify WARNING level for elevated alerts
        call_kwargs = mock_notify.call_args
        assert "WARNING" in call_kwargs.kwargs.get("title", "") or "WARNING" in call_kwargs[1].get("title", "")

    def test_push_alert_includes_endpoint_info(self, tmp_path, monkeypatch):
        """Test that push alert body includes top error endpoints."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.setenv("CIVICOS_NTFY_TOPIC", "civicos-test")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type="error_rate_critical",
            error_rate=15.0,
            threshold=10.0,
            total_requests=100,
            error_count=15,
            top_endpoints=["/api/failing"],
            notification_sent=False,
            notification_method="log_only"
        )

        metrics = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=15,
            client_error_count=5,
            error_rate_percent=15.0,
            status="critical",
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[{"path": "/api/failing", "count": 10}]
        )

        with patch("civicos_services.monitoring.notify.send_notification", return_value=True) as mock_notify:
            manager._send_push_alert(alert, metrics)

        call_kwargs = mock_notify.call_args
        body = call_kwargs.kwargs.get("body", "") or call_kwargs[1].get("body", "")
        assert "/api/failing" in body


class TestMultiChannelAlerting:
    """Tests for multi-channel alert delivery."""

    def test_both_channels_configured(self, tmp_path, monkeypatch):
        """Test that alerts are sent to both email and push when configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Configure email
        monkeypatch.setenv("CIVICOS_ALERT_EMAILS", "test@example.com")
        monkeypatch.setenv("CIVICOS_SMTP_USERNAME", "user@test.com")
        monkeypatch.setenv("CIVICOS_SMTP_PASSWORD", "password")
        # Configure push (ntfy)
        monkeypatch.setenv("CIVICOS_NTFY_TOPIC", "civicos-test")

        # Create log with critical error rate
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test"}} for _ in range(85)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/failing"}} for _ in range(15)],
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = ErrorAlertManager(
            log_file=str(log_file),
            alert_log_file=str(tmp_path / "alerts.json"),
            min_requests=10
        )

        with patch("civicos_services.monitoring.notify.send_notification", return_value=True), \
             patch("smtplib.SMTP") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            alert = manager.check_and_alert()

        assert alert is not None
        assert alert.notification_sent is True
        assert alert.notification_method == "email+push"

    def test_push_only_when_email_not_configured(self, tmp_path, monkeypatch):
        """Test that only push is used when email is not configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Only configure push
        monkeypatch.delenv("CIVICOS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("CIVICOS_SMTP_USERNAME", raising=False)
        monkeypatch.setenv("CIVICOS_NTFY_TOPIC", "civicos-test")

        # Create log with critical error rate
        log_file = tmp_path / "test.json.log"
        now = datetime.now(timezone.utc).isoformat()

        log_entries = [
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 200, "path": "/api/test"}} for _ in range(85)],
            *[{"message": "request_complete", "timestamp": now, "extra": {"status_code": 500, "path": "/api/failing"}} for _ in range(15)],
        ]

        with open(log_file, 'w') as f:
            for entry in log_entries:
                f.write(json.dumps(entry) + "\n")

        manager = ErrorAlertManager(
            log_file=str(log_file),
            alert_log_file=str(tmp_path / "alerts.json"),
            min_requests=10
        )

        with patch("civicos_services.monitoring.notify.send_notification", return_value=True):
            alert = manager.check_and_alert()

        assert alert is not None
        assert alert.notification_sent is True
        assert alert.notification_method == "push"


class TestNotifyModule:
    """Tests for the notify.py abstraction module."""

    def test_send_notification_ntfy_preferred(self, monkeypatch):
        """Test that ntfy is used when both ntfy and Slack are configured."""
        from civicos_services.monitoring.notify import send_notification

        monkeypatch.setenv("CIVICOS_NTFY_TOPIC", "civicos-test")
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("civicos_services.monitoring.notify._send_ntfy", return_value=True) as mock_ntfy, \
             patch("civicos_services.monitoring.notify._send_slack") as mock_slack:
            result = send_notification(title="Test", body="Test body")

        assert result is True
        mock_ntfy.assert_called_once()
        mock_slack.assert_not_called()

    def test_send_notification_falls_back_to_slack(self, monkeypatch):
        """Test fallback to Slack when ntfy is not configured."""
        from civicos_services.monitoring.notify import send_notification

        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        with patch("civicos_services.monitoring.notify._send_slack", return_value=True) as mock_slack:
            result = send_notification(title="Test", body="Test body")

        assert result is True
        mock_slack.assert_called_once()

    def test_send_notification_no_backend(self, monkeypatch):
        """Test that False is returned when no backend is configured."""
        from civicos_services.monitoring.notify import send_notification

        monkeypatch.delenv("CIVICOS_NTFY_TOPIC", raising=False)
        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)

        result = send_notification(title="Test", body="Test body")
        assert result is False

    def test_ntfy_sends_correct_headers(self, monkeypatch):
        """Test that ntfy request includes correct HTTP headers."""
        from civicos_services.monitoring.notify import _send_ntfy, Priority

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("civicos_services.monitoring.notify.urlopen", return_value=mock_response) as mock_urlopen:
            result = _send_ntfy(
                server="https://ntfy.sh",
                topic="test-topic",
                title="Test Title",
                body="Test body",
                priority=Priority.HIGH,
                tags=["warning", "test"],
                click_url="https://example.com",
            )

        assert result is True
        call_args = mock_urlopen.call_args[0][0]

        # Verify URL includes topic
        assert call_args.full_url == "https://ntfy.sh/test-topic"

        # Verify headers
        assert call_args.get_header("Title") == "Test Title"
        assert call_args.get_header("Priority") == "4"
        assert call_args.get_header("Tags") == "warning,test"
        assert call_args.get_header("Click") == "https://example.com"

        # Verify body
        assert call_args.data == b"Test body"

    def test_slack_sends_block_kit(self, monkeypatch):
        """Test that Slack backend sends Block Kit formatted payload."""
        from civicos_services.monitoring.notify import _send_slack, Priority

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("civicos_services.monitoring.notify.urlopen", return_value=mock_response) as mock_urlopen:
            result = _send_slack(
                webhook_url="https://hooks.slack.com/test",
                title="Test Title",
                body="Test body",
                priority=Priority.HIGH,
            )

        assert result is True
        call_args = mock_urlopen.call_args[0][0]
        payload = json.loads(call_args.data.decode('utf-8'))

        assert "blocks" in payload
        assert "text" in payload
        assert payload["blocks"][0]["type"] == "header"

    def test_priority_enum_values(self):
        """Test Priority enum maps to ntfy integer values."""
        from civicos_services.monitoring.notify import Priority

        assert int(Priority.MIN) == 1
        assert int(Priority.LOW) == 2
        assert int(Priority.DEFAULT) == 3
        assert int(Priority.HIGH) == 4
        assert int(Priority.URGENT) == 5

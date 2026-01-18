"""
Tests for error alerting system.

Tests both email and Slack notification channels for error rate alerts.

Session 295: Initial test coverage for alert_channel feature.
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
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        assert manager.alert_emails == ["test@example.com", "admin@example.com"]
        assert manager.smtp_server == "smtp.test.com"
        assert manager.smtp_port == 465
        assert manager.slack_webhook_url == "https://hooks.slack.com/test"

    def test_check_and_alert_insufficient_requests(self, tmp_path, monkeypatch):
        """Test that alerts are not triggered with insufficient requests."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Clean environment
        monkeypatch.delenv("CIVICOS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)

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


class TestSlackAlertChannel:
    """Tests for Slack webhook alert channel."""

    def test_send_slack_alert_not_configured(self, tmp_path, monkeypatch):
        """Test Slack alert returns False when not configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.delenv("CIVICOS_SLACK_WEBHOOK_URL", raising=False)

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

        result = manager._send_slack_alert(alert, metrics)
        assert result is False

    def test_send_slack_alert_success(self, tmp_path, monkeypatch):
        """Test successful Slack webhook delivery."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

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

        # Mock urlopen to simulate successful webhook
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("civic_services.monitoring.error_alerting.urlopen", return_value=mock_response) as mock_urlopen:
            result = manager._send_slack_alert(alert, metrics)

        assert result is True
        mock_urlopen.assert_called_once()

        # Verify the payload structure
        call_args = mock_urlopen.call_args[0][0]
        payload = json.loads(call_args.data.decode('utf-8'))

        assert "blocks" in payload
        assert "text" in payload
        assert "CRITICAL" in payload["text"]
        assert "15.0%" in payload["text"]

    def test_send_slack_alert_http_error(self, tmp_path, monkeypatch):
        """Test Slack webhook handles HTTP errors gracefully."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics
        from urllib.error import HTTPError

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

        # Mock urlopen to raise HTTP error
        with patch("civic_services.monitoring.error_alerting.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                url="https://hooks.slack.com/test",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=None
            )
            result = manager._send_slack_alert(alert, metrics)

        assert result is False

    def test_slack_message_format_elevated(self, tmp_path, monkeypatch):
        """Test Slack message uses warning emoji for elevated alerts."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager, AlertEvent, ErrorMetrics

        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

        manager = ErrorAlertManager(
            log_file=str(tmp_path / "test.log"),
            alert_log_file=str(tmp_path / "alerts.json")
        )

        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type="error_rate_elevated",  # Not critical
            error_rate=6.0,
            threshold=5.0,
            total_requests=100,
            error_count=6,
            top_endpoints=[],
            notification_sent=False,
            notification_method="log_only"
        )

        metrics = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=6,
            client_error_count=2,
            error_rate_percent=6.0,
            status="elevated",
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[]
        )

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("civic_services.monitoring.error_alerting.urlopen", return_value=mock_response) as mock_urlopen:
            manager._send_slack_alert(alert, metrics)

        call_args = mock_urlopen.call_args[0][0]
        payload = json.loads(call_args.data.decode('utf-8'))

        assert "WARNING" in payload["text"]
        # Check header block contains warning emoji
        header_block = next((b for b in payload["blocks"] if b["type"] == "header"), None)
        assert header_block is not None
        assert ":warning:" in header_block["text"]["text"]


class TestMultiChannelAlerting:
    """Tests for multi-channel alert delivery."""

    def test_both_channels_configured(self, tmp_path, monkeypatch):
        """Test that alerts are sent to both email and Slack when configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Configure both channels
        monkeypatch.setenv("CIVICOS_ALERT_EMAILS", "test@example.com")
        monkeypatch.setenv("CIVICOS_SMTP_USERNAME", "user@test.com")
        monkeypatch.setenv("CIVICOS_SMTP_PASSWORD", "password")
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

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

        # Mock both email and Slack
        mock_slack_response = MagicMock()
        mock_slack_response.status = 200
        mock_slack_response.__enter__ = MagicMock(return_value=mock_slack_response)
        mock_slack_response.__exit__ = MagicMock(return_value=False)

        with patch("civic_services.monitoring.error_alerting.urlopen", return_value=mock_slack_response), \
             patch("smtplib.SMTP") as mock_smtp:
            mock_smtp_instance = MagicMock()
            mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            alert = manager.check_and_alert()

        assert alert is not None
        assert alert.notification_sent is True
        assert alert.notification_method == "email+slack"

    def test_slack_only_when_email_not_configured(self, tmp_path, monkeypatch):
        """Test that only Slack is used when email is not configured."""
        from civicos_services.monitoring.error_alerting import ErrorAlertManager

        # Only configure Slack
        monkeypatch.delenv("CIVICOS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("CIVICOS_SMTP_USERNAME", raising=False)
        monkeypatch.setenv("CIVICOS_SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")

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

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("civic_services.monitoring.error_alerting.urlopen", return_value=mock_response):
            alert = manager.check_and_alert()

        assert alert is not None
        assert alert.notification_sent is True
        assert alert.notification_method == "slack"

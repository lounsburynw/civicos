"""
Error rate monitoring and alerting for Civic platform.

Monitors application error rates and sends alerts when thresholds are exceeded.
Works with the structured JSON logs from logging_config.py.

Features:
- Reads error events from logs/civic.json.log
- Calculates error rate over configurable time windows
- Sends alerts via email and/or Slack when error rate exceeds thresholds
- Debounces alerts to prevent notification storms
- Logs alert history for audit

Usage:
    from civic_services.monitoring.error_alerting import ErrorAlertManager

    # Check error rates and send alerts if needed
    alert_manager = ErrorAlertManager()
    alert_manager.check_and_alert()

    # Get current error metrics (for /health endpoint)
    metrics = alert_manager.get_error_metrics()

Session 294: Initial error alerting implementation
Session 295: Added Slack webhook support (alert_channel)
"""

import json
import os
import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import logging

logger = logging.getLogger(__name__)


@dataclass
class ErrorMetrics:
    """Error rate metrics for a time window."""
    window_minutes: int
    total_requests: int
    error_count: int  # 5xx errors
    client_error_count: int  # 4xx errors
    error_rate_percent: float
    status: str  # "normal", "elevated", "critical"
    timestamp: str
    top_error_endpoints: List[Dict[str, Any]]


@dataclass
class AlertEvent:
    """Record of an alert being sent."""
    timestamp: str
    alert_type: str  # "error_rate_elevated", "error_rate_critical"
    error_rate: float
    threshold: float
    total_requests: int
    error_count: int
    top_endpoints: List[str]
    notification_sent: bool
    notification_method: str  # "email", "log_only"


class ErrorMetricsCollector:
    """
    Collects error metrics from structured JSON logs.

    Reads the civic.json.log file and calculates error rates
    over configurable time windows.
    """

    def __init__(self, log_file: str = "logs/civic.json.log"):
        self.log_file = Path(log_file)

    def get_recent_requests(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """
        Get request completion events from the last N minutes.

        Args:
            minutes: Time window in minutes

        Returns:
            List of request_complete log entries
        """
        if not self.log_file.exists():
            logger.debug(f"Log file not found: {self.log_file}")
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        requests = []

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Only process request_complete events
                        if entry.get('message') != 'request_complete':
                            continue

                        # Parse timestamp
                        timestamp_str = entry.get('timestamp', '')
                        try:
                            entry_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except ValueError:
                            continue

                        # Filter by time window
                        if entry_time >= cutoff_time:
                            requests.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading log file: {e}")
            return []

        return requests

    def calculate_metrics(self, minutes: int = 5) -> ErrorMetrics:
        """
        Calculate error metrics for the given time window.

        Args:
            minutes: Time window in minutes

        Returns:
            ErrorMetrics object with calculated rates
        """
        requests = self.get_recent_requests(minutes)

        total = len(requests)
        errors = 0  # 5xx
        client_errors = 0  # 4xx
        endpoint_errors: Dict[str, int] = {}

        for req in requests:
            extra = req.get('extra', {})
            status_code = extra.get('status_code', 0)
            path = extra.get('path', 'unknown')

            if 500 <= status_code < 600:
                errors += 1
                endpoint_errors[path] = endpoint_errors.get(path, 0) + 1
            elif 400 <= status_code < 500:
                client_errors += 1

        # Calculate error rate
        error_rate = (errors / total * 100) if total > 0 else 0.0

        # Determine status
        if error_rate >= 10:
            status = "critical"
        elif error_rate >= 5:
            status = "elevated"
        else:
            status = "normal"

        # Get top error endpoints
        top_endpoints = sorted(
            endpoint_errors.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return ErrorMetrics(
            window_minutes=minutes,
            total_requests=total,
            error_count=errors,
            client_error_count=client_errors,
            error_rate_percent=round(error_rate, 2),
            status=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            top_error_endpoints=[
                {"path": path, "count": count}
                for path, count in top_endpoints
            ]
        )


class ErrorAlertManager:
    """
    Manages error rate alerts with configurable thresholds and debouncing.

    Thresholds:
    - elevated: 5% error rate (5xx errors)
    - critical: 10% error rate

    Alert debouncing:
    - Minimum 15 minutes between alerts of the same type
    - Prevents notification storms during sustained issues
    """

    def __init__(
        self,
        log_file: str = "logs/civic.json.log",
        alert_log_file: str = "data/error_alerts.json",
        elevated_threshold: float = 5.0,
        critical_threshold: float = 10.0,
        min_requests: int = 10,
        debounce_minutes: int = 15,
        window_minutes: int = 5
    ):
        """
        Initialize alert manager.

        Args:
            log_file: Path to JSON log file
            alert_log_file: Path to store alert history
            elevated_threshold: Error rate % for elevated alert
            critical_threshold: Error rate % for critical alert
            min_requests: Minimum requests required to trigger alert
            debounce_minutes: Minimum time between alerts
            window_minutes: Time window for error rate calculation
        """
        self.collector = ErrorMetricsCollector(log_file)
        self.alert_log_file = Path(alert_log_file)
        self.elevated_threshold = elevated_threshold
        self.critical_threshold = critical_threshold
        self.min_requests = min_requests
        self.debounce_minutes = debounce_minutes
        self.window_minutes = window_minutes

        # Email configuration from environment
        self.alert_emails = os.environ.get('CIVIC_ALERT_EMAILS', '').split(',')
        self.alert_emails = [e.strip() for e in self.alert_emails if e.strip()]
        self.smtp_server = os.environ.get('CIVIC_SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('CIVIC_SMTP_PORT', '587'))
        self.smtp_username = os.environ.get('CIVIC_SMTP_USERNAME', '')
        self.smtp_password = os.environ.get('CIVIC_SMTP_PASSWORD', '')

        # Slack configuration from environment
        self.slack_webhook_url = os.environ.get('CIVIC_SLACK_WEBHOOK_URL', '')

    def get_error_metrics(self) -> Dict[str, Any]:
        """
        Get current error metrics for external consumption (e.g., /health endpoint).

        Returns:
            Dictionary with error metrics suitable for JSON serialization
        """
        metrics = self.collector.calculate_metrics(self.window_minutes)
        return asdict(metrics)

    def check_and_alert(self) -> Optional[AlertEvent]:
        """
        Check error rates and send alerts if thresholds exceeded.

        Returns:
            AlertEvent if an alert was triggered, None otherwise
        """
        metrics = self.collector.calculate_metrics(self.window_minutes)

        # Not enough data to alert
        if metrics.total_requests < self.min_requests:
            logger.debug(
                f"Insufficient requests for alerting: {metrics.total_requests} < {self.min_requests}"
            )
            return None

        # Determine alert type based on thresholds
        if metrics.error_rate_percent >= self.critical_threshold:
            alert_type = "error_rate_critical"
            threshold = self.critical_threshold
        elif metrics.error_rate_percent >= self.elevated_threshold:
            alert_type = "error_rate_elevated"
            threshold = self.elevated_threshold
        else:
            logger.debug(f"Error rate {metrics.error_rate_percent}% below thresholds")
            return None

        # Check debounce
        if self._should_debounce(alert_type):
            logger.info(
                f"Alert debounced: {alert_type} (rate: {metrics.error_rate_percent}%)"
            )
            return None

        # Create alert event
        alert = AlertEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            alert_type=alert_type,
            error_rate=metrics.error_rate_percent,
            threshold=threshold,
            total_requests=metrics.total_requests,
            error_count=metrics.error_count,
            top_endpoints=[ep['path'] for ep in metrics.top_error_endpoints],
            notification_sent=False,
            notification_method="log_only"
        )

        # Track which channels succeeded
        channels_sent = []

        # Attempt to send email notification
        if self._send_email_alert(alert, metrics):
            channels_sent.append("email")

        # Attempt to send Slack notification
        if self._send_slack_alert(alert, metrics):
            channels_sent.append("slack")

        # Update alert with notification status
        if channels_sent:
            alert.notification_sent = True
            alert.notification_method = "+".join(channels_sent)
        else:
            # Log-only alert when no channels configured
            logger.warning(
                f"ERROR ALERT: {alert_type} - {metrics.error_rate_percent}% error rate "
                f"({metrics.error_count}/{metrics.total_requests} requests) "
                f"Top endpoints: {alert.top_endpoints}"
            )

        # Record alert
        self._record_alert(alert)

        return alert

    def _should_debounce(self, alert_type: str) -> bool:
        """Check if we should suppress this alert due to recent similar alert."""
        recent_alerts = self._get_recent_alerts(self.debounce_minutes)
        return any(a.get('alert_type') == alert_type for a in recent_alerts)

    def _get_recent_alerts(self, minutes: int) -> List[Dict[str, Any]]:
        """Get alerts from the last N minutes."""
        if not self.alert_log_file.exists():
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        try:
            with open(self.alert_log_file, 'r') as f:
                alerts = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        recent = []
        for alert in alerts:
            try:
                alert_time = datetime.fromisoformat(
                    alert['timestamp'].replace('Z', '+00:00')
                )
                if alert_time >= cutoff_time:
                    recent.append(alert)
            except (KeyError, ValueError):
                continue

        return recent

    def _record_alert(self, alert: AlertEvent) -> None:
        """Record alert to history file."""
        # Ensure directory exists
        self.alert_log_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing alerts
        alerts = []
        if self.alert_log_file.exists():
            try:
                with open(self.alert_log_file, 'r') as f:
                    alerts = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                alerts = []

        # Add new alert
        alerts.append(asdict(alert))

        # Keep only last 30 days of alerts
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        alerts = [
            a for a in alerts
            if datetime.fromisoformat(a['timestamp'].replace('Z', '+00:00')) >= cutoff
        ]

        # Save
        with open(self.alert_log_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        logger.info(f"Alert recorded: {alert.alert_type}")

    def _send_email_alert(self, alert: AlertEvent, metrics: ErrorMetrics) -> bool:
        """
        Send email alert notification.

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.alert_emails or not self.smtp_username or not self.smtp_password:
            logger.debug("Email alerting not configured (missing credentials)")
            return False

        # Format severity
        severity = "CRITICAL" if alert.alert_type == "error_rate_critical" else "WARNING"

        subject = f"[Civic {severity}] Elevated error rate: {alert.error_rate}%"

        body = f"""Civic Platform Error Rate Alert

Severity: {severity}
Timestamp: {alert.timestamp}

Error Rate: {alert.error_rate}% (threshold: {alert.threshold}%)
Total Requests: {alert.total_requests} (last {self.window_minutes} minutes)
Server Errors (5xx): {alert.error_count}
Client Errors (4xx): {metrics.client_error_count}

Top Error Endpoints:
{self._format_endpoints(metrics.top_error_endpoints)}

Actions:
- Check application logs: logs/civic.json.log
- Review health endpoint: https://civic-api.fly.dev/health
- Check Fly.io logs: fly logs -a civic-api

---
This alert was generated by Civic error monitoring.
Alert type: {alert.alert_type}
"""

        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = ', '.join(self.alert_emails)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email alert sent to: {self.alert_emails}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _send_slack_alert(self, alert: AlertEvent, metrics: ErrorMetrics) -> bool:
        """
        Send Slack webhook alert notification.

        Returns:
            True if Slack message sent successfully, False otherwise
        """
        if not self.slack_webhook_url:
            logger.debug("Slack alerting not configured (missing webhook URL)")
            return False

        # Format severity
        severity = "CRITICAL" if alert.alert_type == "error_rate_critical" else "WARNING"
        emoji = ":rotating_light:" if severity == "CRITICAL" else ":warning:"

        # Build Slack Block Kit message
        # See: https://api.slack.com/block-kit
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Civic Error Rate Alert",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Error Rate:*\n{alert.error_rate}% (threshold: {alert.threshold}%)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Requests:*\n{alert.total_requests} (last {self.window_minutes}min)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Server Errors (5xx):*\n{alert.error_count}"
                    }
                ]
            }
        ]

        # Add top error endpoints if any
        if metrics.top_error_endpoints:
            endpoint_lines = [
                f"• `{ep['path']}`: {ep['count']} errors"
                for ep in metrics.top_error_endpoints[:3]
            ]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Top Error Endpoints:*\n" + "\n".join(endpoint_lines)
                }
            })

        # Add action links
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"<https://civic-api.fly.dev/health|View Health> | Alert type: `{alert.alert_type}`"
                }
            ]
        })

        payload = {
            "blocks": blocks,
            "text": f"{severity}: Civic error rate at {alert.error_rate}%"  # Fallback text
        }

        try:
            req = Request(
                self.slack_webhook_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urlopen(req, timeout=10) as response:
                if response.status == 200:
                    logger.info("Slack alert sent successfully")
                    return True
                else:
                    logger.warning(f"Slack webhook returned status {response.status}")
                    return False

        except HTTPError as e:
            logger.error(f"Slack webhook HTTP error: {e.code} - {e.reason}")
            return False
        except URLError as e:
            logger.error(f"Slack webhook URL error: {e.reason}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    def _format_endpoints(self, endpoints: List[Dict[str, Any]]) -> str:
        """Format endpoint list for email body."""
        if not endpoints:
            return "  (no specific endpoint data)"
        return '\n'.join(
            f"  - {ep['path']}: {ep['count']} errors"
            for ep in endpoints
        )

    def get_alert_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get alert history for the last N days.

        Args:
            days: Number of days of history to return

        Returns:
            List of alert events
        """
        if not self.alert_log_file.exists():
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            with open(self.alert_log_file, 'r') as f:
                alerts = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        return [
            a for a in alerts
            if datetime.fromisoformat(a['timestamp'].replace('Z', '+00:00')) >= cutoff
        ]


def check_error_rates() -> Dict[str, Any]:
    """
    Convenience function to check error rates and return metrics.

    This can be called from health checks or monitoring scripts.

    Returns:
        Dictionary with error metrics and any triggered alerts
    """
    manager = ErrorAlertManager()
    metrics = manager.get_error_metrics()

    # Also check and potentially send alerts
    alert = manager.check_and_alert()

    result = {
        "metrics": metrics,
        "alert_triggered": alert is not None
    }

    if alert:
        result["alert"] = asdict(alert)

    return result


if __name__ == "__main__":
    # CLI for testing
    import sys

    if "--check" in sys.argv:
        result = check_error_rates()
        print(json.dumps(result, indent=2))
    elif "--history" in sys.argv:
        manager = ErrorAlertManager()
        history = manager.get_alert_history()
        print(f"Alert history ({len(history)} alerts):")
        for alert in history[-10:]:
            print(f"  {alert['timestamp']}: {alert['alert_type']} - {alert['error_rate']}%")
    else:
        print("Error Alert Manager")
        print()
        print("Usage:")
        print("  python error_alerting.py --check   # Check error rates and alert if needed")
        print("  python error_alerting.py --history # Show recent alert history")
        print()
        print("Environment variables for email alerts:")
        print("  CIVIC_ALERT_EMAILS    - Comma-separated list of email addresses")
        print("  CIVIC_SMTP_SERVER     - SMTP server (default: smtp.gmail.com)")
        print("  CIVIC_SMTP_PORT       - SMTP port (default: 587)")
        print("  CIVIC_SMTP_USERNAME   - SMTP username")
        print("  CIVIC_SMTP_PASSWORD   - SMTP password/app password")
        print()
        print("Environment variables for Slack alerts:")
        print("  CIVIC_SLACK_WEBHOOK_URL - Slack incoming webhook URL")
        print("                            Create at: https://api.slack.com/messaging/webhooks")

"""
Tests for error_alerting.py — ErrorMetricsCollector, ErrorAlertManager,
threshold logic, debounce, alert recording, and notification dispatch.

Mocks external I/O (filesystem, SMTP, push notifications). Tests real
threshold logic, debounce behavior, metric calculations, and formatting.

To run:
    pytest packages/civicos-services/tests/test_error_alerting.py -q --override-ini="addopts="
"""

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.monitoring.error_alerting import (
    AlertEvent,
    ErrorAlertManager,
    ErrorMetrics,
    ErrorMetricsCollector,
    check_error_rates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _make_log_entry(
    status_code: int = 200,
    path: str = "/api/v2/civic/search",
    minutes_ago: int = 1,
) -> str:
    """Create a JSON log line matching the request_complete format."""
    entry = {
        "message": "request_complete",
        "timestamp": _minutes_ago_iso(minutes_ago),
        "extra": {
            "status_code": status_code,
            "path": path,
        },
    }
    return json.dumps(entry)


def _write_log_file(tmp_path: Path, lines: list[str]) -> Path:
    """Write log lines to a temp file, return its path."""
    log_file = tmp_path / "civic.json.log"
    log_file.write_text("\n".join(lines) + "\n")
    return log_file


def _make_alert_dict(
    alert_type: str = "error_rate_elevated",
    minutes_ago: int = 5,
) -> dict:
    return {
        "timestamp": _minutes_ago_iso(minutes_ago),
        "alert_type": alert_type,
        "error_rate": 7.5,
        "threshold": 5.0,
        "total_requests": 100,
        "error_count": 8,
        "top_endpoints": ["/api/search"],
        "notification_sent": True,
        "notification_method": "push",
    }


def _make_manager(tmp_path, **kwargs) -> ErrorAlertManager:
    """Create an ErrorAlertManager with temp file paths and no env vars."""
    defaults = {
        "log_file": str(tmp_path / "civic.json.log"),
        "alert_log_file": str(tmp_path / "error_alerts.json"),
        "elevated_threshold": 5.0,
        "critical_threshold": 10.0,
        "min_requests": 10,
        "debounce_minutes": 15,
        "window_minutes": 5,
    }
    defaults.update(kwargs)
    with patch.dict(os.environ, {
        "CIVICOS_ALERT_EMAILS": "",
        "CIVICOS_SMTP_USERNAME": "",
        "CIVICOS_SMTP_PASSWORD": "",
    }, clear=False):
        return ErrorAlertManager(**defaults)


# ---------------------------------------------------------------------------
# ErrorMetrics dataclass
# ---------------------------------------------------------------------------


class TestErrorMetricsDataclass:
    def test_asdict_round_trip(self):
        m = ErrorMetrics(
            window_minutes=5,
            total_requests=100,
            error_count=8,
            client_error_count=12,
            error_rate_percent=8.0,
            status="elevated",
            timestamp="2026-04-10T00:00:00+00:00",
            top_error_endpoints=[{"path": "/api/search", "count": 5}],
        )
        d = asdict(m)
        assert d["window_minutes"] == 5
        assert d["total_requests"] == 100
        assert d["error_count"] == 8
        assert d["client_error_count"] == 12
        assert d["error_rate_percent"] == 8.0
        assert d["status"] == "elevated"
        assert d["top_error_endpoints"] == [{"path": "/api/search", "count": 5}]

    def test_all_fields_present(self):
        m = ErrorMetrics(
            window_minutes=10,
            total_requests=0,
            error_count=0,
            client_error_count=0,
            error_rate_percent=0.0,
            status="normal",
            timestamp="2026-04-10T00:00:00+00:00",
            top_error_endpoints=[],
        )
        d = asdict(m)
        expected_keys = {
            "window_minutes", "total_requests", "error_count",
            "client_error_count", "error_rate_percent", "status",
            "timestamp", "top_error_endpoints",
        }
        assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# AlertEvent dataclass
# ---------------------------------------------------------------------------


class TestAlertEventDataclass:
    def test_asdict_preserves_values(self):
        a = AlertEvent(
            timestamp="2026-04-10T00:00:00+00:00",
            alert_type="error_rate_critical",
            error_rate=12.5,
            threshold=10.0,
            total_requests=200,
            error_count=25,
            top_endpoints=["/api/search", "/api/context"],
            notification_sent=True,
            notification_method="email+push",
        )
        d = asdict(a)
        assert d["alert_type"] == "error_rate_critical"
        assert d["error_rate"] == 12.5
        assert d["threshold"] == 10.0
        assert d["total_requests"] == 200
        assert d["error_count"] == 25
        assert d["top_endpoints"] == ["/api/search", "/api/context"]
        assert d["notification_sent"] is True
        assert d["notification_method"] == "email+push"


# ---------------------------------------------------------------------------
# ErrorMetricsCollector — get_recent_requests
# ---------------------------------------------------------------------------


class TestGetRecentRequests:
    def test_returns_empty_when_log_file_missing(self, tmp_path):
        collector = ErrorMetricsCollector(str(tmp_path / "nonexistent.log"))
        result = collector.get_recent_requests(minutes=5)
        assert result == []

    def test_parses_request_complete_entries_within_window(self, tmp_path):
        lines = [
            _make_log_entry(status_code=200, path="/api/search", minutes_ago=2),
            _make_log_entry(status_code=500, path="/api/context", minutes_ago=3),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 2
        assert result[0]["extra"]["status_code"] == 200
        assert result[1]["extra"]["status_code"] == 500

    def test_excludes_entries_outside_window(self, tmp_path):
        lines = [
            _make_log_entry(status_code=200, minutes_ago=2),
            _make_log_entry(status_code=500, minutes_ago=10),  # outside 5-min window
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 1
        assert result[0]["extra"]["status_code"] == 200

    def test_skips_non_request_complete_messages(self, tmp_path):
        lines = [
            json.dumps({
                "message": "server_start",
                "timestamp": _minutes_ago_iso(1),
            }),
            _make_log_entry(status_code=200, minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 1
        assert result[0]["message"] == "request_complete"

    def test_skips_malformed_json_lines(self, tmp_path):
        lines = [
            "not valid json",
            _make_log_entry(status_code=200, minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 1

    def test_skips_entries_with_invalid_timestamp(self, tmp_path):
        lines = [
            json.dumps({
                "message": "request_complete",
                "timestamp": "not-a-timestamp",
                "extra": {"status_code": 200, "path": "/test"},
            }),
            _make_log_entry(status_code=200, minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 1

    def test_skips_empty_lines(self, tmp_path):
        lines = [
            _make_log_entry(status_code=200, minutes_ago=1),
            "",
            "   ",
            _make_log_entry(status_code=201, minutes_ago=2),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        result = collector.get_recent_requests(minutes=5)

        assert len(result) == 2


# ---------------------------------------------------------------------------
# ErrorMetricsCollector — calculate_metrics
# ---------------------------------------------------------------------------


class TestCalculateMetrics:
    def test_zero_requests_yields_normal_status(self, tmp_path):
        log_file = _write_log_file(tmp_path, [])
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 0
        assert metrics.error_count == 0
        assert metrics.client_error_count == 0
        assert metrics.error_rate_percent == 0.0
        assert metrics.status == "normal"

    def test_counts_5xx_as_errors(self, tmp_path):
        lines = [
            _make_log_entry(status_code=200, minutes_ago=1),
            _make_log_entry(status_code=500, minutes_ago=1),
            _make_log_entry(status_code=502, minutes_ago=1),
            _make_log_entry(status_code=503, minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.total_requests == 4
        assert metrics.error_count == 3
        assert metrics.client_error_count == 0

    def test_counts_4xx_as_client_errors(self, tmp_path):
        lines = [
            _make_log_entry(status_code=400, minutes_ago=1),
            _make_log_entry(status_code=404, minutes_ago=1),
            _make_log_entry(status_code=422, minutes_ago=1),
            _make_log_entry(status_code=200, minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.client_error_count == 3
        assert metrics.error_count == 0

    def test_4xx_not_included_in_error_rate(self, tmp_path):
        # 10 requests, 5 are 4xx, 0 are 5xx → error_rate = 0%
        lines = (
            [_make_log_entry(status_code=400, minutes_ago=1) for _ in range(5)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(5)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.error_rate_percent == 0.0
        assert metrics.client_error_count == 5

    def test_error_rate_calculation(self, tmp_path):
        # 20 requests, 2 are 5xx → 10% error rate
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(2)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(18)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.error_rate_percent == 10.0

    def test_status_normal_below_5_percent(self, tmp_path):
        # 100 requests, 4 errors → 4%
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(4)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(96)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.status == "normal"
        assert metrics.error_rate_percent == 4.0

    def test_status_elevated_at_5_percent(self, tmp_path):
        # 20 requests, 1 error → 5%
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.status == "elevated"
        assert metrics.error_rate_percent == 5.0

    def test_status_critical_at_10_percent(self, tmp_path):
        # 10 requests, 1 error → 10%
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(9)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.status == "critical"
        assert metrics.error_rate_percent == 10.0

    def test_status_elevated_at_9_percent(self, tmp_path):
        # 100 requests, 9 errors → 9% (elevated, not critical)
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(9)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(91)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.status == "elevated"
        assert metrics.error_rate_percent == 9.0

    def test_top_error_endpoints_sorted_by_count(self, tmp_path):
        lines = [
            _make_log_entry(status_code=500, path="/api/search", minutes_ago=1),
            _make_log_entry(status_code=500, path="/api/search", minutes_ago=1),
            _make_log_entry(status_code=500, path="/api/search", minutes_ago=1),
            _make_log_entry(status_code=500, path="/api/context", minutes_ago=1),
            _make_log_entry(status_code=200, path="/api/health", minutes_ago=1),
        ]
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert len(metrics.top_error_endpoints) == 2
        assert metrics.top_error_endpoints[0]["path"] == "/api/search"
        assert metrics.top_error_endpoints[0]["count"] == 3
        assert metrics.top_error_endpoints[1]["path"] == "/api/context"
        assert metrics.top_error_endpoints[1]["count"] == 1

    def test_top_error_endpoints_limited_to_5(self, tmp_path):
        lines = []
        for i in range(7):
            lines.append(
                _make_log_entry(status_code=500, path=f"/api/ep{i}", minutes_ago=1)
            )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert len(metrics.top_error_endpoints) == 5

    def test_window_minutes_passed_through(self, tmp_path):
        log_file = _write_log_file(tmp_path, [])
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=15)
        assert metrics.window_minutes == 15

    def test_error_rate_rounded_to_2_decimals(self, tmp_path):
        # 3 errors out of 7 requests → 42.857142... → 42.86
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(3)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(4)]
        )
        log_file = _write_log_file(tmp_path, lines)
        collector = ErrorMetricsCollector(str(log_file))
        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.error_rate_percent == 42.86


# ---------------------------------------------------------------------------
# ErrorAlertManager — initialization
# ---------------------------------------------------------------------------


class TestAlertManagerInit:
    def test_thresholds_set_from_args(self, tmp_path):
        mgr = _make_manager(tmp_path, elevated_threshold=3.0, critical_threshold=8.0)
        assert mgr.elevated_threshold == 3.0
        assert mgr.critical_threshold == 8.0

    def test_min_requests_set_from_args(self, tmp_path):
        mgr = _make_manager(tmp_path, min_requests=50)
        assert mgr.min_requests == 50

    def test_debounce_minutes_set_from_args(self, tmp_path):
        mgr = _make_manager(tmp_path, debounce_minutes=30)
        assert mgr.debounce_minutes == 30

    def test_alert_emails_parsed_from_env(self, tmp_path):
        with patch.dict(os.environ, {
            "CIVICOS_ALERT_EMAILS": "alice@test.com, bob@test.com",
            "CIVICOS_SMTP_USERNAME": "",
            "CIVICOS_SMTP_PASSWORD": "",
        }, clear=False):
            mgr = ErrorAlertManager(
                log_file=str(tmp_path / "log"),
                alert_log_file=str(tmp_path / "alerts.json"),
            )
        assert mgr.alert_emails == ["alice@test.com", "bob@test.com"]

    def test_empty_alert_emails_yields_empty_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.alert_emails == []

    def test_smtp_defaults(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.smtp_server == "smtp.gmail.com"
        assert mgr.smtp_port == 587


# ---------------------------------------------------------------------------
# ErrorAlertManager — get_error_metrics
# ---------------------------------------------------------------------------


class TestGetErrorMetrics:
    def test_returns_dict_with_all_fields(self, tmp_path):
        lines = [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(5)]
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path)
        result = mgr.get_error_metrics()

        assert result["total_requests"] == 5
        assert result["error_count"] == 0
        assert result["error_rate_percent"] == 0.0
        assert result["status"] == "normal"
        assert result["window_minutes"] == 5

    def test_empty_log_returns_zero_metrics(self, tmp_path):
        _write_log_file(tmp_path, [])
        mgr = _make_manager(tmp_path)
        result = mgr.get_error_metrics()

        assert result["total_requests"] == 0
        assert result["error_count"] == 0


# ---------------------------------------------------------------------------
# ErrorAlertManager — check_and_alert thresholds
# ---------------------------------------------------------------------------


class TestCheckAndAlertThresholds:
    def test_returns_none_when_below_min_requests(self, tmp_path):
        # 5 requests < min_requests of 10
        lines = [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(5)]
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        result = mgr.check_and_alert()

        assert result is None

    def test_returns_none_when_error_rate_below_thresholds(self, tmp_path):
        # 20 requests, 0 errors → 0%
        lines = [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(20)]
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        result = mgr.check_and_alert()

        assert result is None

    def test_elevated_alert_at_5_percent(self, tmp_path):
        # 20 requests, 1 error → 5%
        lines = (
            [_make_log_entry(status_code=500, path="/api/search", minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_elevated"
        assert alert.error_rate == 5.0
        assert alert.threshold == 5.0
        assert alert.error_count == 1
        assert alert.total_requests == 20
        assert "/api/search" in alert.top_endpoints

    def test_critical_alert_at_10_percent(self, tmp_path):
        # 10 requests, 1 error → 10%
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(9)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_critical"
        assert alert.error_rate == 10.0
        assert alert.threshold == 10.0

    def test_critical_overrides_elevated(self, tmp_path):
        # 20% error rate should be critical, not elevated
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(4)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(16)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_critical"

    def test_just_below_elevated_returns_none(self, tmp_path):
        # 100 requests, 4 errors → 4% (below 5% threshold)
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(4)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(96)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        result = mgr.check_and_alert()

        assert result is None

    def test_elevated_between_5_and_10(self, tmp_path):
        # 100 requests, 7 errors → 7% (elevated)
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(7)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(93)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_elevated"
        assert alert.threshold == 5.0


# ---------------------------------------------------------------------------
# ErrorAlertManager — debounce
# ---------------------------------------------------------------------------


class TestDebounce:
    def test_debounces_same_alert_type_within_window(self, tmp_path):
        # Pre-populate alert log with recent alert
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text(json.dumps([
            _make_alert_dict(alert_type="error_rate_elevated", minutes_ago=5),
        ]))

        # Generate a condition that would trigger elevated alert
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10, debounce_minutes=15)
        result = mgr.check_and_alert()

        assert result is None

    def test_does_not_debounce_different_alert_type(self, tmp_path):
        # Recent elevated alert, but new condition is critical
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text(json.dumps([
            _make_alert_dict(alert_type="error_rate_elevated", minutes_ago=5),
        ]))

        # 50% error rate → critical
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1) for _ in range(5)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(5)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10, debounce_minutes=15)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_critical"

    def test_does_not_debounce_after_window_expires(self, tmp_path):
        # Alert from 20 minutes ago, debounce window is 15 minutes
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text(json.dumps([
            _make_alert_dict(alert_type="error_rate_elevated", minutes_ago=20),
        ]))

        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10, debounce_minutes=15)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_elevated"

    def test_missing_alert_log_does_not_debounce(self, tmp_path):
        # No alert log file exists
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_elevated"

    def test_corrupted_alert_log_does_not_debounce(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text("not valid json")

        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.alert_type == "error_rate_elevated"


# ---------------------------------------------------------------------------
# ErrorAlertManager — _record_alert
# ---------------------------------------------------------------------------


class TestRecordAlert:
    def test_records_alert_to_file(self, tmp_path):
        _write_log_file(tmp_path, [])
        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(),
            alert_type="error_rate_elevated",
            error_rate=7.5,
            threshold=5.0,
            total_requests=100,
            error_count=8,
            top_endpoints=["/api/search"],
            notification_sent=False,
            notification_method="log_only",
        )
        mgr._record_alert(alert)

        alert_log = tmp_path / "error_alerts.json"
        alerts = json.loads(alert_log.read_text())
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "error_rate_elevated"
        assert alerts[0]["error_rate"] == 7.5

    def test_appends_to_existing_alerts(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text(json.dumps([
            _make_alert_dict(minutes_ago=5),
        ]))
        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(),
            alert_type="error_rate_critical",
            error_rate=15.0,
            threshold=10.0,
            total_requests=50,
            error_count=8,
            top_endpoints=[],
            notification_sent=True,
            notification_method="push",
        )
        mgr._record_alert(alert)

        alerts = json.loads(alert_log.read_text())
        assert len(alerts) == 2
        assert alerts[1]["alert_type"] == "error_rate_critical"

    def test_prunes_alerts_older_than_30_days(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        old_alert = _make_alert_dict(minutes_ago=0)
        old_alert["timestamp"] = _days_ago_iso(35)  # 35 days ago

        recent_alert = _make_alert_dict(minutes_ago=5)
        alert_log.write_text(json.dumps([old_alert, recent_alert]))

        mgr = _make_manager(tmp_path)
        new_alert = AlertEvent(
            timestamp=_now_iso(),
            alert_type="error_rate_elevated",
            error_rate=6.0,
            threshold=5.0,
            total_requests=20,
            error_count=2,
            top_endpoints=[],
            notification_sent=False,
            notification_method="log_only",
        )
        mgr._record_alert(new_alert)

        alerts = json.loads(alert_log.read_text())
        # Old alert pruned, recent + new remain
        assert len(alerts) == 2
        for a in alerts:
            ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
            assert ts >= datetime.now(timezone.utc) - timedelta(days=30)

    def test_creates_directory_if_missing(self, tmp_path):
        mgr = _make_manager(
            tmp_path,
            alert_log_file=str(tmp_path / "subdir" / "alerts.json"),
        )
        alert = AlertEvent(
            timestamp=_now_iso(),
            alert_type="error_rate_elevated",
            error_rate=6.0,
            threshold=5.0,
            total_requests=20,
            error_count=2,
            top_endpoints=[],
            notification_sent=False,
            notification_method="log_only",
        )
        mgr._record_alert(alert)

        assert (tmp_path / "subdir" / "alerts.json").exists()
        alerts = json.loads((tmp_path / "subdir" / "alerts.json").read_text())
        assert len(alerts) == 1


# ---------------------------------------------------------------------------
# ErrorAlertManager — notification channels
# ---------------------------------------------------------------------------


class TestEmailNotification:
    def test_returns_false_when_no_recipients(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.alert_emails = []
        mgr.smtp_username = "user@test.com"
        mgr.smtp_password = "pass"

        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=6.0, threshold=5.0, total_requests=20,
            error_count=2, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=20, error_count=2,
            client_error_count=0, error_rate_percent=10.0, status="critical",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        assert mgr._send_email_alert(alert, metrics) is False

    def test_returns_false_when_no_smtp_password(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.alert_emails = ["a@b.com"]
        mgr.smtp_username = "user@test.com"
        mgr.smtp_password = ""

        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=6.0, threshold=5.0, total_requests=20,
            error_count=2, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=20, error_count=2,
            client_error_count=0, error_rate_percent=10.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        assert mgr._send_email_alert(alert, metrics) is False

    @patch("civicos_services.monitoring.error_alerting.smtplib.SMTP")
    def test_sends_email_with_correct_subject_for_critical(self, mock_smtp_cls, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.alert_emails = ["alert@test.com"]
        mgr.smtp_username = "sender@test.com"
        mgr.smtp_password = "secret"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_critical",
            error_rate=12.5, threshold=10.0, total_requests=100,
            error_count=13, top_endpoints=["/api/search"],
            notification_sent=False, notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=13,
            client_error_count=5, error_rate_percent=12.5, status="critical",
            timestamp=_now_iso(), top_error_endpoints=[{"path": "/api/search", "count": 10}],
        )
        result = mgr._send_email_alert(alert, metrics)

        assert result is True
        sent_msg = mock_server.send_message.call_args[0][0]
        assert "CRITICAL" in sent_msg["Subject"]
        assert "12.5%" in sent_msg["Subject"]
        assert sent_msg["From"] == "sender@test.com"
        assert "alert@test.com" in sent_msg["To"]

    @patch("civicos_services.monitoring.error_alerting.smtplib.SMTP")
    def test_warning_subject_for_elevated(self, mock_smtp_cls, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.alert_emails = ["a@b.com"]
        mgr.smtp_username = "u"
        mgr.smtp_password = "p"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=7.0, threshold=5.0, total_requests=100,
            error_count=7, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=7,
            client_error_count=0, error_rate_percent=7.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        result = mgr._send_email_alert(alert, metrics)

        assert result is True
        sent_msg = mock_server.send_message.call_args[0][0]
        assert "WARNING" in sent_msg["Subject"]

    @patch("civicos_services.monitoring.error_alerting.smtplib.SMTP")
    def test_returns_false_on_smtp_error(self, mock_smtp_cls, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.alert_emails = ["a@b.com"]
        mgr.smtp_username = "u"
        mgr.smtp_password = "p"
        mock_smtp_cls.side_effect = ConnectionRefusedError("refused")

        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=7.0, threshold=5.0, total_requests=100,
            error_count=7, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=7,
            client_error_count=0, error_rate_percent=7.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        assert mgr._send_email_alert(alert, metrics) is False


class TestPushNotification:
    @patch("civicos_services.monitoring.notify.send_notification")
    def test_critical_uses_urgent_priority(self, mock_notify, tmp_path):
        from civicos_services.monitoring.notify import Priority
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_critical",
            error_rate=15.0, threshold=10.0, total_requests=100,
            error_count=15, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=15,
            client_error_count=0, error_rate_percent=15.0, status="critical",
            timestamp=_now_iso(),
            top_error_endpoints=[{"path": "/api/search", "count": 10}],
        )
        result = mgr._send_push_alert(alert, metrics)

        assert result is True
        assert mock_notify.call_args[1]["priority"] == Priority.URGENT

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_elevated_uses_high_priority(self, mock_notify, tmp_path):
        from civicos_services.monitoring.notify import Priority
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=7.0, threshold=5.0, total_requests=100,
            error_count=7, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=7,
            client_error_count=0, error_rate_percent=7.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        result = mgr._send_push_alert(alert, metrics)

        assert result is True
        assert mock_notify.call_args[1]["priority"] == Priority.HIGH

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_body_contains_error_details(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_critical",
            error_rate=12.0, threshold=10.0, total_requests=50,
            error_count=6, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=50, error_count=6,
            client_error_count=3, error_rate_percent=12.0, status="critical",
            timestamp=_now_iso(),
            top_error_endpoints=[{"path": "/api/search", "count": 4}],
        )
        mgr._send_push_alert(alert, metrics)

        body = mock_notify.call_args[1]["body"]
        assert "CRITICAL" in body
        assert "12.0%" in body
        assert "50" in body
        assert "6" in body
        assert "/api/search" in body
        assert "4 errors" in body

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_tags_for_critical(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_critical",
            error_rate=15.0, threshold=10.0, total_requests=100,
            error_count=15, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=15,
            client_error_count=0, error_rate_percent=15.0, status="critical",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        mgr._send_push_alert(alert, metrics)

        tags = mock_notify.call_args[1]["tags"]
        assert "rotating_light" in tags
        assert "error" in tags

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_tags_for_elevated(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=7.0, threshold=5.0, total_requests=100,
            error_count=7, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=7,
            client_error_count=0, error_rate_percent=7.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        mgr._send_push_alert(alert, metrics)

        tags = mock_notify.call_args[1]["tags"]
        assert "warning" in tags
        assert "error" in tags

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_click_url(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_elevated",
            error_rate=7.0, threshold=5.0, total_requests=100,
            error_count=7, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=7,
            client_error_count=0, error_rate_percent=7.0, status="elevated",
            timestamp=_now_iso(), top_error_endpoints=[],
        )
        mgr._send_push_alert(alert, metrics)

        assert mock_notify.call_args[1]["click_url"] == "https://civic-api.fly.dev/health"

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_limits_endpoints_to_top_3(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        mgr = _make_manager(tmp_path)
        alert = AlertEvent(
            timestamp=_now_iso(), alert_type="error_rate_critical",
            error_rate=25.0, threshold=10.0, total_requests=100,
            error_count=25, top_endpoints=[], notification_sent=False,
            notification_method="log_only",
        )
        metrics = ErrorMetrics(
            window_minutes=5, total_requests=100, error_count=25,
            client_error_count=0, error_rate_percent=25.0, status="critical",
            timestamp=_now_iso(),
            top_error_endpoints=[
                {"path": "/api/ep1", "count": 10},
                {"path": "/api/ep2", "count": 8},
                {"path": "/api/ep3", "count": 5},
                {"path": "/api/ep4", "count": 2},
            ],
        )
        mgr._send_push_alert(alert, metrics)

        body = mock_notify.call_args[1]["body"]
        assert "/api/ep1" in body
        assert "/api/ep2" in body
        assert "/api/ep3" in body
        assert "/api/ep4" not in body


# ---------------------------------------------------------------------------
# ErrorAlertManager — check_and_alert notification integration
# ---------------------------------------------------------------------------


class TestCheckAndAlertNotifications:
    @patch("civicos_services.monitoring.notify.send_notification")
    def test_alert_records_push_channel(self, mock_notify, tmp_path):
        mock_notify.return_value = True

        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        mgr = _make_manager(tmp_path, min_requests=10)
        alert = mgr.check_and_alert()

        assert alert.notification_sent is True
        assert "push" in alert.notification_method

    def test_log_only_when_no_channels_configured(self, tmp_path):
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)
        # No email or push configured → log_only
        with patch(
            "civicos_services.monitoring.notify.send_notification",
            return_value=False,
        ):
            mgr = _make_manager(tmp_path, min_requests=10)
            alert = mgr.check_and_alert()

        assert alert.notification_sent is False
        assert alert.notification_method == "log_only"

    @patch("civicos_services.monitoring.error_alerting.smtplib.SMTP")
    @patch("civicos_services.monitoring.notify.send_notification")
    def test_both_channels_combined(self, mock_notify, mock_smtp_cls, tmp_path):
        mock_notify.return_value = True
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)

        with patch.dict(os.environ, {
            "CIVICOS_ALERT_EMAILS": "a@b.com",
            "CIVICOS_SMTP_USERNAME": "u",
            "CIVICOS_SMTP_PASSWORD": "p",
        }, clear=False):
            mgr = ErrorAlertManager(
                log_file=str(tmp_path / "civic.json.log"),
                alert_log_file=str(tmp_path / "error_alerts.json"),
                min_requests=10,
            )
        alert = mgr.check_and_alert()

        assert alert.notification_sent is True
        assert "email" in alert.notification_method
        assert "push" in alert.notification_method

    def test_alert_is_recorded_to_log_file(self, tmp_path):
        lines = (
            [_make_log_entry(status_code=500, minutes_ago=1)]
            + [_make_log_entry(status_code=200, minutes_ago=1) for _ in range(19)]
        )
        _write_log_file(tmp_path, lines)

        with patch(
            "civicos_services.monitoring.notify.send_notification",
            return_value=False,
        ):
            mgr = _make_manager(tmp_path, min_requests=10)
            mgr.check_and_alert()

        alert_log = tmp_path / "error_alerts.json"
        alerts = json.loads(alert_log.read_text())
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "error_rate_elevated"


# ---------------------------------------------------------------------------
# ErrorAlertManager — _format_endpoints
# ---------------------------------------------------------------------------


class TestFormatEndpoints:
    def test_formats_endpoints_as_bullet_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        endpoints = [
            {"path": "/api/search", "count": 5},
            {"path": "/api/context", "count": 3},
        ]
        result = mgr._format_endpoints(endpoints)

        assert "- /api/search: 5 errors" in result
        assert "- /api/context: 3 errors" in result

    def test_empty_endpoints_shows_no_data(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr._format_endpoints([])
        assert result == "  (no specific endpoint data)"


# ---------------------------------------------------------------------------
# ErrorAlertManager — get_alert_history
# ---------------------------------------------------------------------------


class TestGetAlertHistory:
    def test_returns_empty_when_no_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.get_alert_history(days=7)
        assert result == []

    def test_returns_alerts_within_days_window(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        alerts = [
            _make_alert_dict(minutes_ago=60),     # 1 hour ago → within 7 days
            _make_alert_dict(minutes_ago=1440),    # 1 day ago → within 7 days
        ]
        alert_log.write_text(json.dumps(alerts))

        mgr = _make_manager(tmp_path)
        result = mgr.get_alert_history(days=7)
        assert len(result) == 2

    def test_excludes_alerts_outside_days_window(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        old_alert = _make_alert_dict(minutes_ago=0)
        old_alert["timestamp"] = _days_ago_iso(10)

        recent_alert = _make_alert_dict(minutes_ago=60)

        alert_log.write_text(json.dumps([old_alert, recent_alert]))

        mgr = _make_manager(tmp_path)
        result = mgr.get_alert_history(days=7)
        assert len(result) == 1
        assert result[0]["timestamp"] == recent_alert["timestamp"]

    def test_returns_empty_on_corrupted_file(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        alert_log.write_text("not json at all")

        mgr = _make_manager(tmp_path)
        result = mgr.get_alert_history(days=7)
        assert result == []

    def test_custom_days_parameter(self, tmp_path):
        alert_log = tmp_path / "error_alerts.json"
        alert_2_days_ago = _make_alert_dict(minutes_ago=0)
        alert_2_days_ago["timestamp"] = _days_ago_iso(2)

        alert_log.write_text(json.dumps([alert_2_days_ago]))

        mgr = _make_manager(tmp_path)
        # Within 3-day window
        result = mgr.get_alert_history(days=3)
        assert len(result) == 1

        # Outside 1-day window
        result = mgr.get_alert_history(days=1)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# check_error_rates convenience function
# ---------------------------------------------------------------------------


class TestCheckErrorRates:
    @patch("civicos_services.monitoring.error_alerting.ErrorAlertManager")
    def test_returns_metrics_and_no_alert(self, mock_cls):
        mock_mgr = MagicMock()
        mock_mgr.get_error_metrics.return_value = {
            "total_requests": 50,
            "error_count": 0,
            "error_rate_percent": 0.0,
            "status": "normal",
        }
        mock_mgr.check_and_alert.return_value = None
        mock_cls.return_value = mock_mgr

        result = check_error_rates()

        assert result["metrics"]["total_requests"] == 50
        assert result["metrics"]["status"] == "normal"
        assert result["alert_triggered"] is False
        assert "alert" not in result

    @patch("civicos_services.monitoring.error_alerting.ErrorAlertManager")
    def test_includes_alert_when_triggered(self, mock_cls):
        mock_mgr = MagicMock()
        mock_mgr.get_error_metrics.return_value = {
            "total_requests": 100,
            "error_count": 12,
            "error_rate_percent": 12.0,
            "status": "critical",
        }
        alert = AlertEvent(
            timestamp=_now_iso(),
            alert_type="error_rate_critical",
            error_rate=12.0,
            threshold=10.0,
            total_requests=100,
            error_count=12,
            top_endpoints=["/api/search"],
            notification_sent=True,
            notification_method="push",
        )
        mock_mgr.check_and_alert.return_value = alert
        mock_cls.return_value = mock_mgr

        result = check_error_rates()

        assert result["alert_triggered"] is True
        assert result["alert"]["alert_type"] == "error_rate_critical"
        assert result["alert"]["error_rate"] == 12.0
        assert result["alert"]["notification_method"] == "push"

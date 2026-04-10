"""
Tests for request_metrics.py — log parsing, status code categorization,
path normalization, percentile calculation, time-window filtering, and
manager convenience methods.

Uses tmp_path for log file I/O. No mocks on the subject under test.
Pure-logic methods (normalize_path, percentiles) tested directly.

To run:
    pytest packages/civicos-services/tests/test_request_metrics.py -q --override-ini="addopts="
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from civicos_services.monitoring.request_metrics import (
    RequestMetrics,
    RequestMetricsCollector,
    RequestMetricsManager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago_iso(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _make_log_entry(
    path="/api/v2/civic/search",
    method="POST",
    status_code=200,
    duration_ms=45.0,
    timestamp=None,
):
    """Build a single request_complete log entry."""
    return json.dumps({
        "message": "request_complete",
        "timestamp": timestamp or _now_iso(),
        "extra": {
            "path": path,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
        },
    })


def _write_log(tmp_path, lines):
    """Write a list of JSON-line strings to a log file and return its path."""
    log_file = tmp_path / "civic.json.log"
    log_file.write_text("\n".join(lines) + "\n")
    return str(log_file)


def _make_collector(tmp_path, lines):
    """Create a RequestMetricsCollector backed by a temp log file."""
    log_path = _write_log(tmp_path, lines)
    return RequestMetricsCollector(log_file=log_path)


# ---------------------------------------------------------------------------
# Path normalization (pure logic — no I/O)
# ---------------------------------------------------------------------------


class TestNormalizePath:
    def setup_method(self):
        self.collector = RequestMetricsCollector(log_file="nonexistent")

    def test_strips_query_string(self):
        result = self.collector._normalize_path("/api/events?limit=10&offset=0")
        assert result == "/api/events"

    def test_replaces_numeric_id_with_placeholder(self):
        result = self.collector._normalize_path("/api/issues/123")
        assert result == "/api/issues/{id}"

    def test_replaces_uuid_with_placeholder(self):
        result = self.collector._normalize_path("/api/users/abc-def-12345678/profile")
        assert result == "/api/users/{id}/profile"

    def test_replaces_long_alphanumeric_hash_with_placeholder(self):
        # 32+ char alphanumeric (like a hex hash)
        long_hash = "a" * 32
        result = self.collector._normalize_path(f"/api/docs/{long_hash}")
        assert result == "/api/docs/{id}"

    def test_preserves_short_path_segments(self):
        result = self.collector._normalize_path("/api/v2/civic/search")
        assert result == "/api/v2/civic/search"

    def test_preserves_root_path(self):
        result = self.collector._normalize_path("/")
        assert result == "/"

    def test_preserves_empty_string(self):
        result = self.collector._normalize_path("")
        assert result == ""

    def test_query_string_with_id_in_path(self):
        result = self.collector._normalize_path("/api/issues/456?format=json")
        assert result == "/api/issues/{id}"

    def test_multiple_ids_in_path(self):
        result = self.collector._normalize_path("/api/users/999/posts/888")
        assert result == "/api/users/{id}/posts/{id}"

    def test_short_segment_with_dash_not_replaced(self):
        # "v2" has a dash-like shortness but no dash — should stay
        # A short segment WITH a dash like "a-b" (len 3) should NOT be replaced (< 8 chars)
        result = self.collector._normalize_path("/api/a-b/test")
        assert result == "/api/a-b/test"


# ---------------------------------------------------------------------------
# Percentile calculation (pure logic)
# ---------------------------------------------------------------------------


class TestCalculatePercentiles:
    def setup_method(self):
        self.collector = RequestMetricsCollector(log_file="nonexistent")

    def test_empty_list_returns_all_none(self):
        p50, p95, p99, avg = self.collector._calculate_percentiles([])
        assert p50 is None
        assert p95 is None
        assert p99 is None
        assert avg is None

    def test_single_value(self):
        p50, p95, p99, avg = self.collector._calculate_percentiles([100.0])
        assert p50 == 100.0
        assert p95 == 100.0
        assert p99 == 100.0
        assert avg == 100.0

    def test_two_values_median(self):
        # n=2, p50: idx=int(2*50/100)=1 → sorted_values[1]=90
        p50, p95, p99, avg = self.collector._calculate_percentiles([10.0, 90.0])
        assert p50 == 90.0
        assert avg == 50.0

    def test_percentiles_ordered_correctly(self):
        values = list(range(1, 101))  # 1..100
        p50, p95, p99, avg = self.collector._calculate_percentiles(
            [float(v) for v in values]
        )
        # n=100: p50 idx=50→val 51, p95 idx=95→val 96, p99 idx=99→val 100
        assert p50 == 51.0
        assert p95 == 96.0
        assert p99 == 100.0
        assert avg == 50.5

    def test_unsorted_input_still_correct(self):
        values = [100.0, 1.0, 50.0, 25.0, 75.0]
        p50, p95, p99, avg = self.collector._calculate_percentiles(values)
        # sorted: [1, 25, 50, 75, 100], n=5
        # p50: idx=int(5*50/100)=2 → 50.0
        assert p50 == 50.0
        assert avg == 50.2

    def test_all_same_values(self):
        p50, p95, p99, avg = self.collector._calculate_percentiles([42.0] * 10)
        assert p50 == 42.0
        assert p95 == 42.0
        assert p99 == 42.0
        assert avg == 42.0


# ---------------------------------------------------------------------------
# Log reading & time-window filtering
# ---------------------------------------------------------------------------


class TestGetRecentRequests:
    def test_nonexistent_log_returns_empty_list(self, tmp_path):
        collector = RequestMetricsCollector(log_file=str(tmp_path / "missing.log"))
        result = collector.get_recent_requests(minutes=5)
        assert result == []

    def test_empty_log_returns_empty_list(self, tmp_path):
        collector = _make_collector(tmp_path, [""])
        result = collector.get_recent_requests(minutes=5)
        assert result == []

    def test_filters_out_old_entries(self, tmp_path):
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        recent_ts = _now_iso()
        lines = [
            _make_log_entry(timestamp=old_ts, path="/old"),
            _make_log_entry(timestamp=recent_ts, path="/recent"),
        ]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 1
        assert result[0]["extra"]["path"] == "/recent"

    def test_ignores_non_request_complete_events(self, tmp_path):
        non_request = json.dumps({
            "message": "server_started",
            "timestamp": _now_iso(),
            "extra": {},
        })
        lines = [
            non_request,
            _make_log_entry(path="/api/health"),
        ]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 1
        assert result[0]["extra"]["path"] == "/api/health"

    def test_skips_malformed_json_lines(self, tmp_path):
        lines = [
            "this is not json",
            _make_log_entry(path="/api/valid"),
            "{invalid json here",
        ]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 1
        assert result[0]["extra"]["path"] == "/api/valid"

    def test_skips_entries_with_invalid_timestamps(self, tmp_path):
        bad_ts_entry = json.dumps({
            "message": "request_complete",
            "timestamp": "not-a-date",
            "extra": {"path": "/bad-ts", "method": "GET", "status_code": 200},
        })
        lines = [
            bad_ts_entry,
            _make_log_entry(path="/good"),
        ]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 1
        assert result[0]["extra"]["path"] == "/good"

    def test_handles_z_suffix_timestamps(self, tmp_path):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        lines = [_make_log_entry(timestamp=ts, path="/z-suffix")]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 1

    def test_all_entries_within_window_returned(self, tmp_path):
        lines = [
            _make_log_entry(path="/a", timestamp=_minutes_ago_iso(1)),
            _make_log_entry(path="/b", timestamp=_minutes_ago_iso(2)),
            _make_log_entry(path="/c", timestamp=_minutes_ago_iso(4)),
        ]
        collector = _make_collector(tmp_path, lines)
        result = collector.get_recent_requests(minutes=5)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Metrics calculation
# ---------------------------------------------------------------------------


class TestCalculateMetrics:
    def test_empty_log_returns_zero_counts(self, tmp_path):
        collector = RequestMetricsCollector(log_file=str(tmp_path / "missing.log"))
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.total_requests == 0
        assert metrics.success_count == 0
        assert metrics.redirect_count == 0
        assert metrics.client_error_count == 0
        assert metrics.server_error_count == 0
        assert metrics.requests_per_minute == 0.0
        assert metrics.response_time_p50 is None
        assert metrics.top_endpoints == []
        assert metrics.requests_by_method == {}

    def test_status_code_categorization(self, tmp_path):
        lines = [
            _make_log_entry(status_code=200),
            _make_log_entry(status_code=201),
            _make_log_entry(status_code=301),
            _make_log_entry(status_code=404),
            _make_log_entry(status_code=403),
            _make_log_entry(status_code=500),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.total_requests == 6
        assert metrics.success_count == 2
        assert metrics.redirect_count == 1
        assert metrics.client_error_count == 2
        assert metrics.server_error_count == 1

    def test_requests_per_minute_calculation(self, tmp_path):
        lines = [_make_log_entry() for _ in range(10)]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.requests_per_minute == 2.0

    def test_requests_per_minute_zero_window(self, tmp_path):
        # Edge case: minutes=0 should not divide by zero
        collector = RequestMetricsCollector(log_file=str(tmp_path / "missing.log"))
        metrics = collector.calculate_metrics(minutes=0)
        assert metrics.requests_per_minute == 0.0

    def test_response_time_percentiles_populated(self, tmp_path):
        lines = [
            _make_log_entry(duration_ms=10.0),
            _make_log_entry(duration_ms=20.0),
            _make_log_entry(duration_ms=30.0),
            _make_log_entry(duration_ms=40.0),
            _make_log_entry(duration_ms=50.0),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.response_time_avg == 30.0
        assert metrics.response_time_p50 == 30.0

    def test_entries_without_duration_excluded_from_percentiles(self, tmp_path):
        entry_no_duration = json.dumps({
            "message": "request_complete",
            "timestamp": _now_iso(),
            "extra": {
                "path": "/api/health",
                "method": "GET",
                "status_code": 200,
            },
        })
        lines = [
            entry_no_duration,
            _make_log_entry(duration_ms=100.0),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.total_requests == 2
        # Only the one entry with duration_ms contributes
        assert metrics.response_time_avg == 100.0

    def test_method_counting(self, tmp_path):
        lines = [
            _make_log_entry(method="GET"),
            _make_log_entry(method="GET"),
            _make_log_entry(method="POST"),
            _make_log_entry(method="DELETE"),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.requests_by_method == {"GET": 2, "POST": 1, "DELETE": 1}

    def test_top_endpoints_ranked_by_count(self, tmp_path):
        lines = [
            _make_log_entry(path="/api/search"),
            _make_log_entry(path="/api/search"),
            _make_log_entry(path="/api/search"),
            _make_log_entry(path="/api/health"),
            _make_log_entry(path="/api/health"),
            _make_log_entry(path="/api/context"),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert len(metrics.top_endpoints) == 3
        assert metrics.top_endpoints[0] == {"path": "/api/search", "count": 3}
        assert metrics.top_endpoints[1] == {"path": "/api/health", "count": 2}
        assert metrics.top_endpoints[2] == {"path": "/api/context", "count": 1}

    def test_top_endpoints_capped_at_ten(self, tmp_path):
        # 12 unique endpoints — only top 10 should appear
        # Use short alpha-only segments that won't be normalized to {id}
        letters = "abcdefghijkl"
        lines = [
            _make_log_entry(path=f"/api/{ch}")
            for ch in letters
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        assert len(metrics.top_endpoints) == 10

    def test_endpoint_normalization_aggregates_paths(self, tmp_path):
        lines = [
            _make_log_entry(path="/api/issues/123"),
            _make_log_entry(path="/api/issues/456"),
            _make_log_entry(path="/api/issues/789"),
        ]
        collector = _make_collector(tmp_path, lines)
        metrics = collector.calculate_metrics(minutes=5)
        # All three should aggregate under /api/issues/{id}
        assert len(metrics.top_endpoints) == 1
        assert metrics.top_endpoints[0] == {"path": "/api/issues/{id}", "count": 3}

    def test_window_minutes_stored_in_result(self, tmp_path):
        collector = RequestMetricsCollector(log_file=str(tmp_path / "missing.log"))
        metrics = collector.calculate_metrics(minutes=15)
        assert metrics.window_minutes == 15

    def test_status_code_zero_uncategorized(self, tmp_path):
        # An entry with status_code=0 (default) should not count in any category
        entry = json.dumps({
            "message": "request_complete",
            "timestamp": _now_iso(),
            "extra": {"path": "/api/test", "method": "GET", "status_code": 0},
        })
        collector = _make_collector(tmp_path, [entry])
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.total_requests == 1
        assert metrics.success_count == 0
        assert metrics.redirect_count == 0
        assert metrics.client_error_count == 0
        assert metrics.server_error_count == 0

    def test_missing_extra_fields_use_defaults(self, tmp_path):
        # Entry with empty extra dict
        entry = json.dumps({
            "message": "request_complete",
            "timestamp": _now_iso(),
            "extra": {},
        })
        collector = _make_collector(tmp_path, [entry])
        metrics = collector.calculate_metrics(minutes=5)
        assert metrics.total_requests == 1
        assert metrics.requests_by_method == {"unknown": 1}
        assert metrics.top_endpoints[0]["path"] == "unknown"


# ---------------------------------------------------------------------------
# RequestMetricsManager
# ---------------------------------------------------------------------------


class TestRequestMetricsManager:
    def test_get_request_metrics_returns_dict(self, tmp_path):
        lines = [_make_log_entry(status_code=200, duration_ms=25.0)]
        log_path = _write_log(tmp_path, lines)
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)
        result = manager.get_request_metrics()
        assert result["total_requests"] == 1
        assert result["success_count"] == 1
        assert result["response_time_avg"] == 25.0
        assert result["window_minutes"] == 5

    def test_get_request_metrics_override_window(self, tmp_path):
        lines = [
            _make_log_entry(timestamp=_minutes_ago_iso(3)),
            _make_log_entry(timestamp=_minutes_ago_iso(8)),
        ]
        log_path = _write_log(tmp_path, lines)
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)

        # Default window (5 min) should only see the 3-min-old entry
        result_5 = manager.get_request_metrics()
        assert result_5["total_requests"] == 1

        # Explicit 10-min window should see both
        result_10 = manager.get_request_metrics(window_minutes=10)
        assert result_10["total_requests"] == 2

    def test_get_request_count(self, tmp_path):
        lines = [_make_log_entry() for _ in range(7)]
        log_path = _write_log(tmp_path, lines)
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)
        assert manager.get_request_count() == 7

    def test_get_requests_per_minute(self, tmp_path):
        lines = [_make_log_entry() for _ in range(10)]
        log_path = _write_log(tmp_path, lines)
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)
        assert manager.get_requests_per_minute() == 2.0

    def test_get_requests_per_minute_override_window(self, tmp_path):
        lines = [_make_log_entry() for _ in range(10)]
        log_path = _write_log(tmp_path, lines)
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)
        # 10 requests / 10 minutes = 1.0
        assert manager.get_requests_per_minute(window_minutes=10) == 1.0

    def test_empty_log_returns_zero_metrics(self, tmp_path):
        log_path = str(tmp_path / "empty.log")
        manager = RequestMetricsManager(log_file=log_path, window_minutes=5)
        assert manager.get_request_count() == 0
        assert manager.get_requests_per_minute() == 0.0
        result = manager.get_request_metrics()
        assert result["total_requests"] == 0
        assert result["response_time_p50"] is None


# ---------------------------------------------------------------------------
# Singleton manager
# ---------------------------------------------------------------------------


class TestGetRequestMetricsManagerSingleton:
    def test_returns_same_instance(self):
        import civicos_services.monitoring.request_metrics as mod

        # Reset singleton
        mod._request_metrics_manager = None
        m1 = mod.get_request_metrics_manager()
        m2 = mod.get_request_metrics_manager()
        assert m1 is m2
        # Cleanup
        mod._request_metrics_manager = None

    def test_creates_instance_when_none(self):
        import civicos_services.monitoring.request_metrics as mod

        mod._request_metrics_manager = None
        m = mod.get_request_metrics_manager()
        assert m.window_minutes == 5  # default
        # Cleanup
        mod._request_metrics_manager = None


# ---------------------------------------------------------------------------
# RequestMetrics dataclass
# ---------------------------------------------------------------------------


class TestRequestMetricsDataclass:
    def test_asdict_round_trip(self):
        from dataclasses import asdict

        metrics = RequestMetrics(
            window_minutes=5,
            total_requests=100,
            requests_per_minute=20.0,
            timestamp="2026-04-10T00:00:00+00:00",
            success_count=90,
            redirect_count=2,
            client_error_count=5,
            server_error_count=3,
            response_time_p50=25.0,
            response_time_p95=150.0,
            response_time_p99=500.0,
            response_time_avg=45.0,
            top_endpoints=[{"path": "/api/search", "count": 50}],
            requests_by_method={"GET": 60, "POST": 40},
        )
        d = asdict(metrics)
        assert d["total_requests"] == 100
        assert d["success_count"] == 90
        assert d["requests_per_minute"] == 20.0
        assert d["top_endpoints"] == [{"path": "/api/search", "count": 50}]
        assert d["requests_by_method"]["GET"] == 60

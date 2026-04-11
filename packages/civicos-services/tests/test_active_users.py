"""
Tests for active_users.py — reading JSON request logs and computing unique-user
metrics per time window.

Mocks only the log file I/O via `tmp_path` (real filesystem, synthetic log
content). Exercises all real logic: cutoff filtering, user_id vs client_ip
priority, deduplication, per-hour rate arithmetic, daily active users, and
singleton caching.

To run:
    pytest packages/civicos-services/tests/test_active_users.py -q --override-ini="addopts="
"""

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import civicos_services.monitoring.active_users as active_users_module
from civicos_services.monitoring.active_users import (
    ActiveUsersCollector,
    ActiveUsersManager,
    ActiveUsersMetrics,
    get_active_users_manager,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """Render a datetime with 'Z' suffix like the real log writer does."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _entry(
    minutes_ago: float = 0.0,
    message: str = "request_start",
    user_id: str | None = None,
    client_ip: str | None = None,
    timestamp: str | None = None,
    omit_extra: bool = False,
) -> dict:
    """Build a single log entry dict."""
    ts = timestamp if timestamp is not None else _iso(
        datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    )
    entry: dict = {"message": message, "timestamp": ts}
    if not omit_extra:
        extra: dict = {}
        if user_id is not None:
            extra["user_id"] = user_id
        if client_ip is not None:
            extra["client_ip"] = client_ip
        entry["extra"] = extra
    return entry


def _write_log(path: Path, entries: list) -> None:
    """Write a list of entries (dicts or raw strings) as a JSONL file."""
    lines = []
    for e in entries:
        if isinstance(e, str):
            lines.append(e)
        else:
            lines.append(json.dumps(e))
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# ActiveUsersCollector.get_user_identifiers — missing / empty files
# ---------------------------------------------------------------------------


class TestGetUserIdentifiersMissingFile:
    def test_missing_log_file_returns_empty_sets(self, tmp_path):
        collector = ActiveUsersCollector(str(tmp_path / "nonexistent.log"))

        result = collector.get_user_identifiers(minutes=5)

        assert result == {"authenticated": set(), "anonymous": set()}

    def test_missing_log_file_both_keys_present(self, tmp_path):
        collector = ActiveUsersCollector(str(tmp_path / "nope.log"))

        result = collector.get_user_identifiers(minutes=5)

        # Explicitly verify structure — both keys always present, even missing file.
        assert set(result.keys()) == {"authenticated", "anonymous"}

    def test_empty_log_file_returns_empty_sets(self, tmp_path):
        log = tmp_path / "civic.json.log"
        log.write_text("")
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == set()
        assert result["anonymous"] == set()

    def test_file_with_only_whitespace_lines_returns_empty(self, tmp_path):
        log = tmp_path / "civic.json.log"
        log.write_text("\n   \n\t\n")
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == set()
        assert result["anonymous"] == set()


# ---------------------------------------------------------------------------
# ActiveUsersCollector.get_user_identifiers — line filtering
# ---------------------------------------------------------------------------


class TestGetUserIdentifiersLineFiltering:
    def test_invalid_json_lines_skipped(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                "not valid json at all",
                _entry(client_ip="10.0.0.1"),
                "{broken",
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.1"}
        assert result["authenticated"] == set()

    def test_non_request_messages_skipped(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(message="startup", client_ip="10.0.0.99"),
                _entry(message="audit", user_id="u-ignored"),
                _entry(message="request_start", client_ip="10.0.0.1"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.1"}
        assert "u-ignored" not in result["authenticated"]
        assert "10.0.0.99" not in result["anonymous"]

    def test_request_complete_entries_counted(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [_entry(message="request_complete", client_ip="10.0.0.5")],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.5"}

    def test_unparseable_timestamp_skipped(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(timestamp="not-a-timestamp", client_ip="10.0.0.99"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        # Bad-timestamp line dropped, good line kept.
        assert result["anonymous"] == {"10.0.0.1"}

    def test_iso_timestamp_with_z_suffix_is_parsed(self, tmp_path):
        # The code replaces 'Z' with '+00:00' before fromisoformat — verify this path.
        ts = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + "Z"
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(timestamp=ts, client_ip="10.0.0.42")])
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.42"}


# ---------------------------------------------------------------------------
# ActiveUsersCollector.get_user_identifiers — time window filtering
# ---------------------------------------------------------------------------


class TestGetUserIdentifiersTimeWindow:
    def test_entries_outside_window_excluded(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=30, client_ip="10.0.0.old"),  # outside 5m
                _entry(minutes_ago=1, client_ip="10.0.0.new"),  # inside 5m
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.new"}
        assert "10.0.0.old" not in result["anonymous"]

    def test_wider_window_includes_older_entries(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=30, client_ip="10.0.0.old"),
                _entry(minutes_ago=1, client_ip="10.0.0.new"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=60)

        assert result["anonymous"] == {"10.0.0.old", "10.0.0.new"}

    def test_entry_exactly_at_cutoff_excluded(self, tmp_path):
        # Code uses strict `entry_time < cutoff_time` (excludes older).
        # An entry just slightly older than the cutoff window is excluded.
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [_entry(minutes_ago=10.001, client_ip="10.0.0.edge")],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=10)

        assert result["anonymous"] == set()


# ---------------------------------------------------------------------------
# ActiveUsersCollector.get_user_identifiers — user_id vs client_ip precedence
# ---------------------------------------------------------------------------


class TestGetUserIdentifiersPrecedence:
    def test_user_id_takes_priority_over_client_ip(self, tmp_path):
        # When both present, the entry counts as authenticated ONLY.
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [_entry(user_id="alice", client_ip="10.0.0.1")],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == {"alice"}
        assert result["anonymous"] == set()

    def test_client_ip_used_when_no_user_id(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(client_ip="10.0.0.2")])
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.2"}
        assert result["authenticated"] == set()

    def test_no_user_id_or_client_ip_ignored(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry()])
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == set()
        assert result["anonymous"] == set()

    def test_missing_extra_block_ignored(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(omit_extra=True)])
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == set()
        assert result["anonymous"] == set()

    def test_deduplicates_same_user_id_across_entries(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(user_id="alice"),
                _entry(user_id="alice"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == {"alice"}
        assert len(result["authenticated"]) == 1

    def test_deduplicates_same_client_ip_across_entries(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(client_ip="10.0.0.1"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["anonymous"] == {"10.0.0.1"}
        assert len(result["anonymous"]) == 1

    def test_distinct_users_are_separately_counted(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(user_id="bob"),
                _entry(client_ip="10.0.0.1"),
                _entry(client_ip="10.0.0.2"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        result = collector.get_user_identifiers(minutes=5)

        assert result["authenticated"] == {"alice", "bob"}
        assert result["anonymous"] == {"10.0.0.1", "10.0.0.2"}


# ---------------------------------------------------------------------------
# ActiveUsersCollector.get_user_identifiers — read-error handling
# ---------------------------------------------------------------------------


class TestGetUserIdentifiersReadErrors:
    def test_file_read_exception_returns_empty_sets(self, tmp_path):
        log = tmp_path / "civic.json.log"
        log.write_text(json.dumps(_entry(client_ip="10.0.0.1")) + "\n")
        collector = ActiveUsersCollector(str(log))

        # Force open() to raise at read time — simulates permission errors / I/O fault.
        with patch(
            "civicos_services.monitoring.active_users.open",
            side_effect=OSError("disk on fire"),
        ):
            result = collector.get_user_identifiers(minutes=5)

        assert result == {"authenticated": set(), "anonymous": set()}


# ---------------------------------------------------------------------------
# ActiveUsersCollector.calculate_metrics
# ---------------------------------------------------------------------------


class TestCalculateMetrics:
    def test_counts_authenticated_and_anonymous_separately(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(user_id="bob"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.authenticated_users == 2
        assert metrics.anonymous_users == 1
        assert metrics.unique_users == 3

    def test_users_per_hour_scaled_from_window(self, tmp_path):
        # 3 users in 5 minutes = 36 users/hour.
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(user_id="bob"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.active_users_per_hour == 36.0

    def test_users_per_hour_rounded_to_two_decimals(self, tmp_path):
        # 1 user / 7 minutes * 60 = 8.571428... -> rounded to 8.57.
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=7)

        assert metrics.active_users_per_hour == 8.57

    def test_zero_window_minutes_yields_zero_rate(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=0)

        assert metrics.active_users_per_hour == 0.0
        # With minutes=0, cutoff equals now so all earlier entries are excluded.
        assert metrics.unique_users == 0

    def test_window_minutes_field_preserved_on_result(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=15)

        assert metrics.window_minutes == 15

    def test_daily_active_users_uses_1440_minute_window(self, tmp_path):
        # Entry is 6 hours old: outside a 5-minute window but inside a 24-hour (1440) window.
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=1, user_id="fresh"),
                _entry(minutes_ago=360, user_id="six_hours_old"),
            ],
        )
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        # 5-minute window only sees the fresh user.
        assert metrics.unique_users == 1
        # 1440-minute DAU window sees both users.
        assert metrics.daily_active_users == 2

    def test_empty_log_file_yields_zero_metrics(self, tmp_path):
        log = tmp_path / "civic.json.log"
        log.write_text("")
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        assert metrics.unique_users == 0
        assert metrics.authenticated_users == 0
        assert metrics.anonymous_users == 0
        assert metrics.daily_active_users == 0
        assert metrics.active_users_per_hour == 0.0

    def test_timestamp_is_rfc3339_utc(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        # Must be round-trippable as an ISO timestamp and carry UTC offset.
        parsed = datetime.fromisoformat(metrics.timestamp)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_returns_active_users_metrics_instance(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        collector = ActiveUsersCollector(str(log))

        metrics = collector.calculate_metrics(minutes=5)

        # Verify the dataclass contract by checking a concrete field access.
        assert isinstance(metrics, ActiveUsersMetrics)
        assert metrics.window_minutes == 5
        assert metrics.unique_users == 1


# ---------------------------------------------------------------------------
# ActiveUsersManager
# ---------------------------------------------------------------------------


class TestActiveUsersManager:
    def test_get_active_users_returns_metrics_dict(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        result = manager.get_active_users()

        assert result["authenticated_users"] == 1
        assert result["anonymous_users"] == 1
        assert result["unique_users"] == 2
        assert result["window_minutes"] == 5
        # 2 users / 5 min * 60 = 24.0/hr
        assert result["active_users_per_hour"] == 24.0

    def test_get_active_users_returns_serializable_dict(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        result = manager.get_active_users()

        # JSON round-trip guarantees dict-of-primitives (no sets, no datetimes).
        round_tripped = json.loads(json.dumps(result))
        assert round_tripped["unique_users"] == 1
        assert round_tripped["authenticated_users"] == 1

    def test_get_active_users_dict_has_all_dataclass_fields(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        result = manager.get_active_users()

        # Exact field set — any drift in ActiveUsersMetrics must update this.
        assert set(result.keys()) == {
            "window_minutes",
            "unique_users",
            "active_users_per_hour",
            "timestamp",
            "authenticated_users",
            "anonymous_users",
            "daily_active_users",
        }

    def test_get_active_users_override_window_is_used(self, tmp_path):
        # Manager default window = 5min; override to 60min to capture older entry.
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=30, user_id="alice"),
                _entry(minutes_ago=1, user_id="bob"),
            ],
        )
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        result_default = manager.get_active_users()
        result_override = manager.get_active_users(window_minutes=60)

        assert result_default["unique_users"] == 1  # only bob (fresh)
        assert result_override["unique_users"] == 2  # both alice and bob
        assert result_override["window_minutes"] == 60

    def test_get_active_users_override_zero_falls_back_to_default(self, tmp_path):
        # `window_minutes or self.window_minutes` — 0 is falsy, uses default.
        log = tmp_path / "civic.json.log"
        _write_log(log, [_entry(user_id="alice")])
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        result = manager.get_active_users(window_minutes=0)

        # With default (5 min), alice is counted.
        assert result["unique_users"] == 1
        assert result["window_minutes"] == 5

    def test_get_unique_users_count_returns_integer_total(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(user_id="alice"),
                _entry(user_id="bob"),
                _entry(client_ip="10.0.0.1"),
            ],
        )
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        count = manager.get_unique_users_count()

        assert count == 3

    def test_get_unique_users_count_with_override(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=45, user_id="old"),
                _entry(minutes_ago=1, user_id="new"),
            ],
        )
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        assert manager.get_unique_users_count() == 1
        assert manager.get_unique_users_count(window_minutes=60) == 2

    def test_get_daily_active_users_uses_24h_window(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=1, user_id="fresh"),
                _entry(minutes_ago=360, user_id="six_hours_old"),
                _entry(minutes_ago=720, user_id="twelve_hours_old"),
                _entry(minutes_ago=3000, user_id="outside_24h"),  # > 1440 min
            ],
        )
        manager = ActiveUsersManager(log_file=str(log), window_minutes=5)

        dau = manager.get_daily_active_users()

        # 3 users within last 24h; the 50-hour-old entry is excluded.
        assert dau == 3

    def test_get_daily_active_users_independent_of_window_minutes(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(
            log,
            [
                _entry(minutes_ago=200, user_id="older_than_window"),
                _entry(minutes_ago=1, user_id="recent"),
            ],
        )
        # Even with tiny 1-minute window, DAU still uses 24h.
        manager = ActiveUsersManager(log_file=str(log), window_minutes=1)

        assert manager.get_daily_active_users() == 2

    def test_default_window_minutes_is_five(self, tmp_path):
        log = tmp_path / "civic.json.log"
        _write_log(log, [])
        manager = ActiveUsersManager(log_file=str(log))

        assert manager.window_minutes == 5


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_active_users_manager_returns_same_instance(self):
        # Reset singleton to guarantee clean state.
        active_users_module._active_users_manager = None

        first = get_active_users_manager()
        second = get_active_users_manager()

        assert first is second

    def test_get_active_users_manager_instantiates_when_none(self):
        active_users_module._active_users_manager = None

        manager = get_active_users_manager()

        assert isinstance(manager, ActiveUsersManager)
        # Default instantiation uses the configured default window.
        assert manager.window_minutes == 5

    def test_get_active_users_manager_reuses_existing_instance(self):
        sentinel = ActiveUsersManager(log_file="sentinel.log", window_minutes=99)
        active_users_module._active_users_manager = sentinel
        try:
            got = get_active_users_manager()
            assert got is sentinel
            assert got.window_minutes == 99
        finally:
            active_users_module._active_users_manager = None


# ---------------------------------------------------------------------------
# ActiveUsersMetrics dataclass
# ---------------------------------------------------------------------------


class TestActiveUsersMetrics:
    def test_asdict_round_trip_preserves_field_values(self):
        metrics = ActiveUsersMetrics(
            window_minutes=5,
            unique_users=10,
            active_users_per_hour=120.0,
            timestamp="2026-04-10T00:00:00+00:00",
            authenticated_users=6,
            anonymous_users=4,
            daily_active_users=50,
        )

        d = asdict(metrics)

        assert d == {
            "window_minutes": 5,
            "unique_users": 10,
            "active_users_per_hour": 120.0,
            "timestamp": "2026-04-10T00:00:00+00:00",
            "authenticated_users": 6,
            "anonymous_users": 4,
            "daily_active_users": 50,
        }

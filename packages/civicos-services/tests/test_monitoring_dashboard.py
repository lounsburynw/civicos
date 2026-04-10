"""
Tests for monitoring_dashboard.py — budget status classification, cost entry
filtering, failure rate calculation, system health assessment, jurisdiction
health aggregation, budget projection, and text report formatting.

Mocks only I/O (filesystem, CITY_CONFIGS import). Tests real logic: budget
threshold classification, time-window filtering, health determination,
projection arithmetic, and report content.

To run:
    pytest packages/civicos-services/tests/test_monitoring_dashboard.py -q --override-ini="addopts="
"""

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.monitoring.monitoring_dashboard import (
    CivicMonitoringDashboard,
    JurisdictionStatus,
    SystemHealth,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CITY_CONFIGS = {
    "san-rafael": {
        "jurisdiction_id": "city-san-rafael",
        "agent_type": "legistar",
        "meeting_urls": ["https://sanrafael.legistar.com/Calendar.aspx"],
    },
    "berkeley": {
        "jurisdiction_id": "city-berkeley",
        "agent_type": "berkeley_cms",
        "meeting_urls": ["https://berkeleyca.gov/meetings"],
    },
}


def _make_dashboard(tmp_path, monthly_budget=50.0):
    """Create a CivicMonitoringDashboard with file paths pointing to tmp_path."""
    dashboard = CivicMonitoringDashboard()
    dashboard.cost_log_file = str(tmp_path / "cost_monitoring.json")
    dashboard.failure_log_file = str(tmp_path / "system_failures.json")
    dashboard.alert_log_file = str(tmp_path / "alert_log.json")
    dashboard.monthly_budget_limit = monthly_budget
    return dashboard


def _write_json(path, data):
    """Write JSON data to a file."""
    with open(path, "w") as f:
        json.dump(data, f)


def _now_iso():
    return datetime.now().isoformat()


def _hours_ago_iso(hours):
    return (datetime.now() - timedelta(hours=hours)).isoformat()


def _days_ago_iso(days):
    return (datetime.now() - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Budget status classification
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    def test_missing_cost_file_returns_zero_budget(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        result = dashboard._get_budget_status()

        assert result["total_cost"] == 0.0
        assert result["budget_percentage"] == 0.0
        assert result["budget_status"] == "under_budget"
        assert result["entries"] == []

    def test_invalid_json_returns_zero_budget(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with open(dashboard.cost_log_file, "w") as f:
            f.write("not valid json{{{")
        result = dashboard._get_budget_status()

        assert result["total_cost"] == 0.0
        assert result["budget_status"] == "under_budget"

    def test_under_budget_when_below_70_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 30.0},
            {"timestamp": f"{current_month}-02T10:00:00", "estimated_cost": 39.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["total_cost"] == 69.0
        assert result["budget_percentage"] == 69.0
        assert result["budget_status"] == "under_budget"

    def test_warning_at_70_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 70.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_percentage"] == 70.0
        assert result["budget_status"] == "warning"

    def test_warning_at_84_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 84.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_status"] == "warning"

    def test_critical_warning_at_85_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 85.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_percentage"] == 85.0
        assert result["budget_status"] == "critical_warning"

    def test_critical_warning_at_94_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 94.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_status"] == "critical_warning"

    def test_over_budget_at_95_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 95.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_percentage"] == 95.0
        assert result["budget_status"] == "over_budget"

    def test_over_budget_at_120_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 120.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["budget_percentage"] == 120.0
        assert result["budget_status"] == "over_budget"

    def test_filters_to_current_month_only(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-05T10:00:00", "estimated_cost": 20.0},
            {"timestamp": "2020-01-15T10:00:00", "estimated_cost": 999.0},  # old month
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["total_cost"] == 20.0
        assert len(result["entries"]) == 1

    def test_sums_multiple_current_month_entries(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        entries = [
            {"timestamp": f"{current_month}-01T08:00:00", "estimated_cost": 10.0},
            {"timestamp": f"{current_month}-02T08:00:00", "estimated_cost": 15.0},
            {"timestamp": f"{current_month}-03T08:00:00", "estimated_cost": 5.0},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_budget_status()
        assert result["total_cost"] == 30.0
        assert result["budget_percentage"] == 30.0
        assert result["budget_limit"] == 100.0


# ---------------------------------------------------------------------------
# Cost entry time filtering
# ---------------------------------------------------------------------------


class TestCostEntryFiltering:
    def test_missing_file_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        assert dashboard._get_cost_entries_since(hours=24) == []

    def test_invalid_json_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with open(dashboard.cost_log_file, "w") as f:
            f.write("broken")
        assert dashboard._get_cost_entries_since(hours=24) == []

    def test_filters_entries_within_window(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        entries = [
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 1.0, "city_id": "a"},
            {"timestamp": _hours_ago_iso(48), "estimated_cost": 2.0, "city_id": "b"},
            {"timestamp": _hours_ago_iso(12), "estimated_cost": 3.0, "city_id": "c"},
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._get_cost_entries_since(hours=24)
        assert len(result) == 2
        costs = sorted(e["estimated_cost"] for e in result)
        assert costs == [1.0, 3.0]

    def test_empty_log_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        _write_json(dashboard.cost_log_file, [])
        assert dashboard._get_cost_entries_since(hours=24) == []

    def test_all_entries_old_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        entries = [
            {"timestamp": _hours_ago_iso(100), "estimated_cost": 5.0, "city_id": "x"},
        ]
        _write_json(dashboard.cost_log_file, entries)
        assert dashboard._get_cost_entries_since(hours=24) == []

    def test_cost_entries_today_delegates_to_since_24h(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.5, "city_id": "sr"},
        ]
        _write_json(dashboard.cost_log_file, entries)

        today = dashboard._get_cost_entries_today()
        assert len(today) == 1
        assert today[0]["estimated_cost"] == 1.5


# ---------------------------------------------------------------------------
# Failure entry filtering
# ---------------------------------------------------------------------------


class TestFailureEntryFiltering:
    def test_missing_file_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        assert dashboard._get_failure_entries_24h() == []

    def test_invalid_json_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with open(dashboard.failure_log_file, "w") as f:
            f.write("{{bad")
        assert dashboard._get_failure_entries_24h() == []

    def test_filters_failures_within_24h(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        entries = [
            {"timestamp": _hours_ago_iso(5), "context": "city-san-rafael error"},
            {"timestamp": _hours_ago_iso(48), "context": "old failure"},
        ]
        _write_json(dashboard.failure_log_file, entries)

        result = dashboard._get_failure_entries_24h()
        assert len(result) == 1
        assert "san-rafael" in result[0]["context"]


# ---------------------------------------------------------------------------
# Failure rate calculation
# ---------------------------------------------------------------------------


class TestFailureRate:
    def test_zero_cost_entries_returns_zero(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        # No files at all
        assert dashboard._get_failure_rate_24h() == 0.0

    def test_no_failures_returns_zero(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "a"},
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 1.0, "city_id": "b"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)
        # No failure file

        assert dashboard._get_failure_rate_24h() == 0.0

    def test_half_failures_returns_50_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "a"},
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 1.0, "city_id": "b"},
            {"timestamp": _hours_ago_iso(3), "estimated_cost": 1.0, "city_id": "c"},
            {"timestamp": _hours_ago_iso(4), "estimated_cost": 1.0, "city_id": "d"},
        ]
        failure_entries = [
            {"timestamp": _hours_ago_iso(1), "context": "fail1"},
            {"timestamp": _hours_ago_iso(2), "context": "fail2"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)
        _write_json(dashboard.failure_log_file, failure_entries)

        assert dashboard._get_failure_rate_24h() == 50.0

    def test_all_failures_returns_100_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        ts = _hours_ago_iso(1)
        cost_entries = [{"timestamp": ts, "estimated_cost": 1.0, "city_id": "a"}]
        failure_entries = [{"timestamp": ts, "context": "fail"}]
        _write_json(dashboard.cost_log_file, cost_entries)
        _write_json(dashboard.failure_log_file, failure_entries)

        assert dashboard._get_failure_rate_24h() == 100.0


# ---------------------------------------------------------------------------
# Recent alerts
# ---------------------------------------------------------------------------


class TestRecentAlerts:
    def test_missing_file_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        assert dashboard._get_recent_alerts() == []

    def test_invalid_json_returns_empty(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with open(dashboard.alert_log_file, "w") as f:
            f.write("xxx")
        assert dashboard._get_recent_alerts() == []

    def test_filters_to_last_7_days(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        alerts = [
            {"timestamp": _days_ago_iso(2), "type": "budget", "details": "recent", "date": "2026-04-08"},
            {"timestamp": _days_ago_iso(10), "type": "failure", "details": "old", "date": "2026-03-31"},
            {"timestamp": _days_ago_iso(1), "type": "health", "details": "today", "date": "2026-04-09"},
        ]
        _write_json(dashboard.alert_log_file, alerts)

        result = dashboard._get_recent_alerts()
        assert len(result) == 2
        details = [a["details"] for a in result]
        assert "recent" in details
        assert "today" in details
        assert "old" not in details


# ---------------------------------------------------------------------------
# System health assessment
# ---------------------------------------------------------------------------


class TestSystemHealth:
    def _setup_dashboard(self, tmp_path, budget_pct, failure_rate_pct, healthy_fraction):
        """Set up a dashboard where we control the three needs_attention inputs."""
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)

        # Budget entries for current month
        current_month = datetime.now().strftime("%Y-%m")
        cost_total = budget_pct  # budget_pct of 100 = budget_pct%
        cost_entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": cost_total}
        ]
        _write_json(dashboard.cost_log_file, cost_entries)

        # For failure rate: need recent entries in 24h window
        recent_cost = [
            {"timestamp": _hours_ago_iso(i), "estimated_cost": 0.5, "city_id": f"city-{i}"}
            for i in range(1, 11)
        ]
        # Overwrite with entries that cover both monthly and 24h
        all_cost = cost_entries + recent_cost
        _write_json(dashboard.cost_log_file, all_cost)

        # Failure entries for failure_rate calculation
        num_failures = int(failure_rate_pct / 100.0 * len(recent_cost))
        failures = [
            {"timestamp": _hours_ago_iso(i), "context": f"fail-{i}"}
            for i in range(1, num_failures + 1)
        ]
        _write_json(dashboard.failure_log_file, failures)

        return dashboard

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_healthy_system_no_attention(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 50.0},
        ])
        # No failures
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
            JurisdictionStatus("bk", "Berkeley", _now_iso(), 5, 0.3, 100.0, True),
        ]

        health = dashboard.get_system_health()
        assert health.needs_attention is False
        assert health.healthy_jurisdictions == 2
        assert health.total_jurisdictions == 2
        assert health.budget_status == "under_budget"

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_needs_attention_when_budget_over_80(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 81.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        health = dashboard.get_system_health()
        assert health.needs_attention is True
        assert health.budget_usage == 81.0

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_no_attention_at_exactly_80_percent_budget(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 80.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        health = dashboard.get_system_health()
        # 80% is not > 80, so no attention from budget alone
        assert health.needs_attention is False

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_needs_attention_when_failure_rate_over_20(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        # Low budget to not trigger budget attention
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "a"},
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 1.0, "city_id": "b"},
            {"timestamp": _hours_ago_iso(3), "estimated_cost": 1.0, "city_id": "c"},
            {"timestamp": _hours_ago_iso(4), "estimated_cost": 1.0, "city_id": "d"},
        ])
        # 2 failures out of 4 recent = 50% > 20%
        _write_json(dashboard.failure_log_file, [
            {"timestamp": _hours_ago_iso(1), "context": "fail1"},
            {"timestamp": _hours_ago_iso(2), "context": "fail2"},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        health = dashboard.get_system_health()
        assert health.needs_attention is True
        assert health.failure_rate_24h > 20.0

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_needs_attention_when_low_healthy_fraction(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        # 2 out of 10 healthy = 20% < 70%
        healthy = [JurisdictionStatus(f"h{i}", f"H{i}", _now_iso(), 5, 0.1, 100.0, True) for i in range(2)]
        unhealthy = [JurisdictionStatus(f"u{i}", f"U{i}", None, 0, 0.0, 50.0, False) for i in range(8)]
        mock_jurisdictions.return_value = healthy + unhealthy

        health = dashboard.get_system_health()
        assert health.needs_attention is True
        assert health.healthy_jurisdictions == 2
        assert health.total_jurisdictions == 10

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_today_cost_sums_jurisdiction_costs(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 1.25, 100.0, True),
            JurisdictionStatus("bk", "Berkeley", _now_iso(), 5, 0.75, 100.0, True),
        ]

        health = dashboard.get_system_health()
        assert health.today_cost == 2.0


# ---------------------------------------------------------------------------
# Jurisdiction health determination
# ---------------------------------------------------------------------------


class TestJurisdictionHealth:
    """Test the is_healthy determination within _get_jurisdiction_statuses."""

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_healthy_when_all_conditions_met(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "san-rafael"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 5)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        assert sr.is_healthy is True
        assert sr.last_refresh is not None
        assert sr.opportunities_count == 5
        assert sr.success_rate == 100.0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_unhealthy_when_no_refresh(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(None, 0)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        assert sr.is_healthy is False
        assert sr.last_refresh is None

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_unhealthy_when_zero_opportunities(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 0)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        assert sr.is_healthy is False
        assert sr.opportunities_count == 0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_unhealthy_when_low_success_rate(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(i), "estimated_cost": 1.0, "city_id": "san-rafael"}
            for i in range(1, 5)
        ]
        failure_entries = [
            {"timestamp": _hours_ago_iso(1), "context": "san-rafael timeout"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)
        _write_json(dashboard.failure_log_file, failure_entries)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 5)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        assert sr.is_healthy is False
        assert sr.success_rate == 75.0


# ---------------------------------------------------------------------------
# Jurisdiction statuses aggregation
# ---------------------------------------------------------------------------


class TestJurisdictionStatuses:
    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_status_for_each_city(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        # No cost or failure files → all defaults
        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(None, 0)):
            statuses = dashboard._get_jurisdiction_statuses()

        assert len(statuses) == 2
        ids = {s.id for s in statuses}
        assert ids == {"san-rafael", "berkeley"}

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_city_name_derived_from_jurisdiction_id(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(None, 0)):
            statuses = dashboard._get_jurisdiction_statuses()

        names = {s.name for s in statuses}
        assert "City San Rafael" in names
        assert "City Berkeley" in names

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_cost_attributed_to_correct_city(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 2.0, "city_id": "san-rafael"},
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 3.0, "city_id": "berkeley"},
            {"timestamp": _hours_ago_iso(3), "estimated_cost": 1.0, "city_id": "san-rafael"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 5)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        bk = next(s for s in statuses if s.id == "berkeley")
        assert sr.cost_today == 3.0  # 2.0 + 1.0
        assert bk.cost_today == 3.0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_success_rate_100_when_no_failures(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "san-rafael"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)
        # No failure file

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 5)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        assert sr.success_rate == 100.0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_success_rate_decreases_with_failures(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        cost_entries = [
            {"timestamp": _hours_ago_iso(1), "estimated_cost": 1.0, "city_id": "san-rafael"},
            {"timestamp": _hours_ago_iso(2), "estimated_cost": 1.0, "city_id": "san-rafael"},
        ]
        failure_entries = [
            {"timestamp": _hours_ago_iso(1), "context": "san-rafael timeout"},
        ]
        _write_json(dashboard.cost_log_file, cost_entries)
        _write_json(dashboard.failure_log_file, failure_entries)

        with patch.object(dashboard, "_get_latest_data_for_city", return_value=(_now_iso(), 5)):
            statuses = dashboard._get_jurisdiction_statuses()

        sr = next(s for s in statuses if s.id == "san-rafael")
        # 2 attempts, 1 failure → 50% success
        assert sr.success_rate == 50.0


# ---------------------------------------------------------------------------
# Latest data for city
# ---------------------------------------------------------------------------


class TestLatestDataForCity:
    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_no_schema_files_returns_none_zero(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        with patch("civicos_services.monitoring.monitoring_dashboard.glob.glob", return_value=[]):
            last_refresh, count = dashboard._get_latest_data_for_city("san-rafael")
        assert last_refresh is None
        assert count == 0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_matching_schema_file_returns_data(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        schema_file = str(tmp_path / "newsletter_sr.json")
        schema_data = {
            "jurisdiction": {"id": "city-san-rafael"},
            "events": [{"title": "Council Meeting"}, {"title": "Budget Hearing"}],
        }
        _write_json(schema_file, schema_data)

        with patch("civicos_services.monitoring.monitoring_dashboard.glob.glob", return_value=[schema_file]):
            last_refresh, count = dashboard._get_latest_data_for_city("san-rafael")

        assert last_refresh is not None
        assert count == 2

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_non_matching_jurisdiction_returns_none(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        schema_file = str(tmp_path / "newsletter_other.json")
        schema_data = {
            "jurisdiction": {"id": "city-oakland"},
            "events": [{"title": "Some Meeting"}],
        }
        _write_json(schema_file, schema_data)

        with patch("civicos_services.monitoring.monitoring_dashboard.glob.glob", return_value=[schema_file]):
            last_refresh, count = dashboard._get_latest_data_for_city("san-rafael")

        assert last_refresh is None
        assert count == 0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_picks_latest_file_when_multiple_match(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)

        # Create two schema files with different mtimes
        old_file = str(tmp_path / "newsletter_old.json")
        new_file = str(tmp_path / "newsletter_new.json")

        old_data = {
            "jurisdiction": {"id": "city-san-rafael"},
            "events": [{"title": "Old Meeting"}],
        }
        new_data = {
            "jurisdiction": {"id": "city-san-rafael"},
            "events": [{"title": "A"}, {"title": "B"}, {"title": "C"}],
        }
        _write_json(old_file, old_data)
        _write_json(new_file, new_data)

        # Make "new" file have a later mtime
        import time
        old_time = time.time() - 3600
        os.utime(old_file, (old_time, old_time))

        with patch("civicos_services.monitoring.monitoring_dashboard.glob.glob", return_value=[old_file, new_file]):
            last_refresh, count = dashboard._get_latest_data_for_city("san-rafael")

        assert count == 3  # From the newer file


# ---------------------------------------------------------------------------
# Budget projection
# ---------------------------------------------------------------------------


class TestBudgetProjection:
    def test_no_entries_shows_no_data(self, tmp_path):
        dashboard = _make_dashboard(tmp_path)
        result = dashboard._generate_budget_projection()
        assert "No data available" in result

    def test_on_track_when_projected_under_90_percent(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        day_of_month = datetime.now().day
        # Spend 1.0 per day → projected ~31.0, which is under 90% of 100
        entries = [
            {"timestamp": f"{current_month}-{str(d).zfill(2)}T10:00:00", "estimated_cost": 1.0}
            for d in range(1, day_of_month + 1)
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._generate_budget_projection()
        assert "ON TRACK" in result
        assert "PASS" in result

    def test_approaching_limit_when_projected_near_budget(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        day_of_month = datetime.now().day
        # Spend enough per day that projection > 90 but <= 100
        # daily_avg = total / day_of_month; projected = total + daily_avg * (31 - day_of_month)
        # Want 90 < projected <= 100 → daily_avg ~ 95/31 ≈ 3.06
        daily_spend = 95.0 / 31.0
        entries = [
            {"timestamp": f"{current_month}-{str(d).zfill(2)}T10:00:00", "estimated_cost": daily_spend}
            for d in range(1, day_of_month + 1)
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._generate_budget_projection()
        assert "APPROACHING LIMIT" in result

    def test_over_budget_when_projected_exceeds_limit(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=50.0)
        current_month = datetime.now().strftime("%Y-%m")
        day_of_month = datetime.now().day
        # Spend 5.0/day → projected ~155.0 >> 50
        entries = [
            {"timestamp": f"{current_month}-{str(d).zfill(2)}T10:00:00", "estimated_cost": 5.0}
            for d in range(1, day_of_month + 1)
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._generate_budget_projection()
        assert "OVER BUDGET" in result
        assert "FAIL" in result

    def test_projection_includes_daily_average(self, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        day_of_month = datetime.now().day
        total = 10.0 * day_of_month
        entries = [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": total}
        ]
        _write_json(dashboard.cost_log_file, entries)

        result = dashboard._generate_budget_projection()
        expected_daily_avg = total / day_of_month  # 10.0
        assert f"${expected_daily_avg:.2f}" in result


# ---------------------------------------------------------------------------
# Text report formatting
# ---------------------------------------------------------------------------


class TestTextReport:
    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_contains_health_status(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        report = dashboard.generate_text_report()
        assert "HEALTHY" in report
        assert "MONITORING REPORT" in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_contains_jurisdiction_details(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 1.50, 95.0, True),
        ]

        report = dashboard.generate_text_report()
        assert "San Rafael" in report
        assert "95.0%" in report
        assert "$1.50" in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_shows_never_for_no_refresh(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 5.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", None, 0, 0.0, 100.0, False),
        ]

        report = dashboard.generate_text_report()
        assert "Never" in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_shows_needs_attention_when_unhealthy(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        # 90% budget triggers needs_attention
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 90.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        report = dashboard.generate_text_report()
        assert "NEEDS ATTENTION" in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_includes_alerts_section(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        _write_json(dashboard.alert_log_file, [
            {"timestamp": _days_ago_iso(1), "type": "budget_warning", "details": "Approaching limit", "date": "2026-04-09"},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        report = dashboard.generate_text_report()
        assert "RECENT ALERTS" in report
        assert "budget_warning" in report
        assert "Approaching limit" in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_omits_alerts_section_when_no_alerts(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        report = dashboard.generate_text_report()
        assert "RECENT ALERTS" not in report

    @patch("civicos_services.monitoring.monitoring_dashboard.CivicMonitoringDashboard._get_jurisdiction_statuses")
    def test_report_limits_alerts_to_5(self, mock_jurisdictions, tmp_path):
        dashboard = _make_dashboard(tmp_path, monthly_budget=100.0)
        current_month = datetime.now().strftime("%Y-%m")
        _write_json(dashboard.cost_log_file, [
            {"timestamp": f"{current_month}-01T10:00:00", "estimated_cost": 10.0},
        ])
        alerts = [
            {"timestamp": _days_ago_iso(1), "type": f"alert_{i}", "details": f"detail_{i}", "date": "2026-04-09"}
            for i in range(10)
        ]
        _write_json(dashboard.alert_log_file, alerts)
        mock_jurisdictions.return_value = [
            JurisdictionStatus("sr", "San Rafael", _now_iso(), 10, 0.5, 100.0, True),
        ]

        report = dashboard.generate_text_report()
        # Only last 5 alerts should appear (from [-5:] slice)
        assert "alert_5" in report
        assert "alert_9" in report
        # alert_0 through alert_4 should NOT appear
        assert "alert_0" not in report
        assert "alert_4" not in report


# ---------------------------------------------------------------------------
# Dataclass field access
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_jurisdiction_status_fields(self):
        j = JurisdictionStatus(
            id="sr", name="San Rafael", last_refresh="2026-04-10T10:00:00",
            opportunities_count=12, cost_today=1.50, success_rate=95.0, is_healthy=True,
        )
        assert j.id == "sr"
        assert j.name == "San Rafael"
        assert j.last_refresh == "2026-04-10T10:00:00"
        assert j.opportunities_count == 12
        assert j.cost_today == 1.50
        assert j.success_rate == 95.0
        assert j.is_healthy is True

    def test_system_health_fields(self):
        h = SystemHealth(
            budget_usage=45.0, budget_status="under_budget",
            total_jurisdictions=5, healthy_jurisdictions=4,
            today_refresh_count=10, today_cost=2.50,
            failure_rate_24h=5.0, needs_attention=False,
        )
        assert h.budget_usage == 45.0
        assert h.budget_status == "under_budget"
        assert h.total_jurisdictions == 5
        assert h.healthy_jurisdictions == 4
        assert h.today_refresh_count == 10
        assert h.today_cost == 2.50
        assert h.failure_rate_24h == 5.0
        assert h.needs_attention is False

    def test_system_health_dict_conversion(self):
        h = SystemHealth(
            budget_usage=70.0, budget_status="warning",
            total_jurisdictions=3, healthy_jurisdictions=2,
            today_refresh_count=5, today_cost=1.0,
            failure_rate_24h=10.0, needs_attention=False,
        )
        d = h.__dict__
        assert d["budget_usage"] == 70.0
        assert d["budget_status"] == "warning"
        assert d["failure_rate_24h"] == 10.0


# ---------------------------------------------------------------------------
# Init defaults
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_monthly_budget(self):
        dashboard = CivicMonitoringDashboard()
        assert dashboard.monthly_budget_limit == 50.0

    def test_default_file_paths(self):
        dashboard = CivicMonitoringDashboard()
        assert dashboard.cost_log_file == "data/cost_monitoring.json"
        assert dashboard.failure_log_file == "data/system_failures.json"
        assert dashboard.alert_log_file == "data/alert_log.json"

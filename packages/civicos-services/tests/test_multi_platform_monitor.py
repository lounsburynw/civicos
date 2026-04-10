"""
Tests for multi_platform_monitor.py — cost calculation, platform comparison,
report generation, monitoring data persistence, and budget compliance.

Mocks only I/O (filesystem, imports of external clients, datetime.now()).
Exercises real logic: cost arithmetic, date filtering, platform efficiency
sorting, report composition, data pruning, and budget threshold classification.

To run:
    pytest packages/civicos-services/tests/test_multi_platform_monitor.py -q --override-ini="addopts="
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

from civicos_services.monitoring.multi_platform_monitor import (
    MultiPlatformMonitor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor():
    return MultiPlatformMonitor()


@pytest.fixture
def frozen_now():
    """A fixed datetime for deterministic tests."""
    return datetime(2026, 4, 10, 12, 0, 0)


def _make_cost_entry(city_id, timestamp, estimated_cost=0.08, opportunities=0):
    """Helper to create a cost monitoring entry."""
    entry = {
        "city_id": city_id,
        "timestamp": timestamp.isoformat(),
        "estimated_cost": estimated_cost,
    }
    if opportunities:
        entry["opportunities_generated"] = opportunities
    return entry


# ---------------------------------------------------------------------------
# __init__ — file path setup
# ---------------------------------------------------------------------------

class TestInit:
    def test_cost_file_path(self, monitor):
        assert monitor.cost_file == Path("data/cost_monitoring.json")

    def test_multi_platform_file_path(self, monitor):
        assert monitor.multi_platform_file == Path("data/multi_platform_monitoring.json")


# ---------------------------------------------------------------------------
# get_legistar_costs — when legistar client is unavailable
# ---------------------------------------------------------------------------

class TestGetLegistarCostsNoClient:
    @patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", None)
    def test_returns_zero_clients_when_import_missing(self, monitor):
        result = monitor.get_legistar_costs()
        assert result["total_clients"] == 0
        assert result["working_clients"] == 0
        assert result["estimated_monthly_cost"] == 0.0
        assert result["client_details"] == []

    @patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", None)
    def test_cost_per_session_is_five_cents(self, monitor):
        result = monitor.get_legistar_costs()
        assert result["cost_per_session"] == 0.05


# ---------------------------------------------------------------------------
# get_legistar_costs — with working clients
# ---------------------------------------------------------------------------

class TestGetLegistarCostsWithClients:
    def test_counts_working_and_failed_clients(self, monitor):
        mock_working_client = MagicMock()
        mock_working_client.probe_capabilities.return_value = {"api_accessible": True}
        mock_working_client.get_recent_events.return_value = [{"id": 1}, {"id": 2}]

        mock_broken_client = MagicMock()
        mock_broken_client.probe_capabilities.return_value = {"api_accessible": False}

        known_clients = {
            "san-rafael": {"base_url": "https://sanrafael.legistar.com"},
            "broken-city": {"base_url": "https://broken.legistar.com"},
        }

        def fake_create(name):
            return mock_working_client if name == "san-rafael" else mock_broken_client

        with patch("civicos_services.monitoring.multi_platform_monitor.KNOWN_LEGISTAR_CLIENTS", known_clients), \
             patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", fake_create):
            result = monitor.get_legistar_costs()

        assert result["total_clients"] == 2
        assert result["working_clients"] == 1
        assert result["estimated_monthly_cost"] == 1 * 30 * 0.05  # 1 working * 30 days * $0.05
        assert len(result["client_details"]) == 2

        working = [d for d in result["client_details"] if d["status"] == "working"]
        failed = [d for d in result["client_details"] if d["status"] == "failed"]
        assert len(working) == 1
        assert len(failed) == 1
        assert working[0]["client_name"] == "san-rafael"
        assert working[0]["current_events"] == 2
        assert working[0]["data_quality"] == "good"
        assert working[0]["monthly_cost"] == 30 * 0.05

    def test_data_quality_no_current_data_when_events_empty(self, monitor):
        mock_client = MagicMock()
        mock_client.probe_capabilities.return_value = {"api_accessible": True}
        mock_client.get_recent_events.return_value = []

        known = {"empty-city": {"base_url": "https://empty.legistar.com"}}

        with patch("civicos_services.monitoring.multi_platform_monitor.KNOWN_LEGISTAR_CLIENTS", known), \
             patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", lambda _: mock_client):
            result = monitor.get_legistar_costs()

        detail = result["client_details"][0]
        assert detail["data_quality"] == "no_current_data"
        assert detail["current_events"] == 0

    def test_client_exception_recorded_as_error(self, monitor):
        known = {"error-city": {"base_url": "https://error.legistar.com"}}

        def raise_on_create(name):
            raise ConnectionError("timeout connecting to API")

        with patch("civicos_services.monitoring.multi_platform_monitor.KNOWN_LEGISTAR_CLIENTS", known), \
             patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", raise_on_create):
            result = monitor.get_legistar_costs()

        assert result["total_clients"] == 1
        assert result["working_clients"] == 0
        detail = result["client_details"][0]
        assert detail["status"] == "error"
        assert "timeout" in detail["error"]

    def test_client_returns_none_not_counted_as_working(self, monitor):
        known = {"none-city": {}}

        with patch("civicos_services.monitoring.multi_platform_monitor.KNOWN_LEGISTAR_CLIENTS", known), \
             patch("civicos_services.monitoring.multi_platform_monitor.create_legistar_client", lambda _: None):
            result = monitor.get_legistar_costs()

        assert result["total_clients"] == 1
        assert result["working_clients"] == 0


# ---------------------------------------------------------------------------
# get_html_parsing_costs
# ---------------------------------------------------------------------------

class TestGetHtmlParsingCosts:
    def test_returns_zeros_when_no_cost_file(self, monitor):
        with patch.object(Path, "exists", return_value=False):
            result = monitor.get_html_parsing_costs()

        assert result["total_sessions"] == 0
        assert result["total_cost"] == 0.0
        assert result["average_cost_per_session"] == 0.0
        assert result["monthly_estimate"] == 0.0

    def test_filters_entries_to_last_7_days(self, monitor, frozen_now):
        recent = _make_cost_entry("city-a", frozen_now - timedelta(days=2), 0.10)
        old = _make_cost_entry("city-b", frozen_now - timedelta(days=10), 0.50)
        cost_data = [recent, old]

        with patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt, \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(cost_data))):
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_html_parsing_costs()

        assert result["total_sessions"] == 1
        assert result["total_cost"] == 0.10
        assert result["cities_tracked"] == ["city-a"]

    def test_calculates_average_and_monthly_estimate(self, monitor, frozen_now):
        entries = [
            _make_cost_entry("city-x", frozen_now - timedelta(days=1), 0.10),
            _make_cost_entry("city-y", frozen_now - timedelta(days=2), 0.20),
            _make_cost_entry("city-x", frozen_now - timedelta(days=3), 0.30),
        ]

        with patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt, \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(entries))):
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_html_parsing_costs()

        assert result["total_sessions"] == 3
        assert result["total_cost"] == pytest.approx(0.60)
        assert result["average_cost_per_session"] == pytest.approx(0.20)
        # monthly = avg * 30 * num_cities; 0.20 * 30 * 2 = 12.0
        assert result["monthly_estimate"] == pytest.approx(12.0)
        assert sorted(result["cities_tracked"]) == ["city-x", "city-y"]

    def test_handles_corrupt_cost_file_gracefully(self, monitor):
        with patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="not valid json")):
            result = monitor.get_html_parsing_costs()

        assert result["total_sessions"] == 0
        assert result["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# get_civicplus_costs
# ---------------------------------------------------------------------------

class TestGetCivicplusCosts:
    def test_returns_defaults_when_import_fails(self, monitor):
        with patch(
            "civicos_services.monitoring.multi_platform_monitor.MultiPlatformMonitor.get_civicplus_costs",
            wraps=monitor.get_civicplus_costs,
        ):
            # Simulate ImportError of CITY_CONFIGS
            with patch.dict("sys.modules", {"civicos_services.monitoring.automated_civic_refresh": None}):
                result = monitor.get_civicplus_costs()

        assert result["total_cities"] == 0
        assert result["platform_type"] == "civicplus_cms"

    def test_counts_civicplus_cities_from_config(self, monitor, frozen_now):
        fake_configs = {
            "larkspur": {"agent_type": "civicplus_cms"},
            "corte-madera": {"agent_type": "civicplus_cms"},
            "san-rafael": {"agent_type": "legistar"},  # not civicplus
        }
        cost_entries = [
            {**_make_cost_entry("larkspur", frozen_now - timedelta(days=1), 0.15, opportunities=3)},
        ]

        with patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", fake_configs), \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(cost_entries))), \
             patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_civicplus_costs()

        assert result["total_cities"] == 2  # larkspur + corte-madera
        assert result["working_cities"] == 1  # only larkspur has opportunities > 0

    def test_calculates_cost_per_opportunity_from_real_data(self, monitor, frozen_now):
        fake_configs = {"city-a": {"agent_type": "civicplus_cms"}}
        entries = [
            _make_cost_entry("city-a", frozen_now - timedelta(days=1), 0.30, opportunities=6),
            _make_cost_entry("city-a", frozen_now - timedelta(days=2), 0.20, opportunities=4),
        ]

        with patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", fake_configs), \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(entries))), \
             patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_civicplus_costs()

        # (0.30 + 0.20) / (6 + 4) = 0.05
        assert result["cost_per_opportunity"] == pytest.approx(0.05)
        # monthly: 1 city * 3 opps/month * 0.05 = 0.15
        assert result["estimated_monthly_cost"] == pytest.approx(0.15)

    def test_efficiency_rating_high_when_cost_under_five_cents(self, monitor, frozen_now):
        fake_configs = {"cheap-city": {"agent_type": "civicplus_cms"}}
        entries = [
            _make_cost_entry("cheap-city", frozen_now - timedelta(days=1), 0.04, opportunities=1),
        ]

        with patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", fake_configs), \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(entries))), \
             patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_civicplus_costs()

        detail = result["city_details"][0]
        assert detail["efficiency_rating"] == "high"

    def test_efficiency_rating_medium_when_cost_over_five_cents(self, monitor, frozen_now):
        fake_configs = {"pricey-city": {"agent_type": "civicplus_cms"}}
        entries = [
            _make_cost_entry("pricey-city", frozen_now - timedelta(days=1), 0.60, opportunities=5),
        ]

        with patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", fake_configs), \
             patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(entries))), \
             patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = monitor.get_civicplus_costs()

        # 0.60 / 5 = 0.12, which is > 0.05
        detail = result["city_details"][0]
        assert detail["efficiency_rating"] == "medium"

    def test_no_cost_file_returns_zero_working_cities(self, monitor):
        fake_configs = {"some-city": {"agent_type": "civicplus_cms"}}

        with patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", fake_configs), \
             patch.object(Path, "exists", return_value=False):
            result = monitor.get_civicplus_costs()

        assert result["total_cities"] == 1
        assert result["working_cities"] == 0
        assert result["city_details"] == []


# ---------------------------------------------------------------------------
# _generate_cost_comparison
# ---------------------------------------------------------------------------

class TestGenerateCostComparison:
    def test_identifies_cheapest_platform(self, monitor):
        legistar = {"cost_per_session": 0.05}
        html = {"average_cost_per_session": 0.10}
        civicplus = {"cost_per_opportunity": 0.03}

        result = monitor._generate_cost_comparison(legistar, html, civicplus)
        assert result.startswith("CivicPlus CMS most efficient")
        assert "$0.030" in result

    def test_calculates_efficiency_ratio(self, monitor):
        legistar = {"cost_per_session": 0.10}
        html = {"average_cost_per_session": 0.20}
        civicplus = {"cost_per_opportunity": 0.05}

        result = monitor._generate_cost_comparison(legistar, html, civicplus)
        # Ratio: 0.20 / 0.05 = 4.0x
        assert "4.0x" in result
        assert "HTML parsing" in result  # least efficient

    def test_defaults_html_cost_to_eight_cents_when_zero(self, monitor):
        legistar = {"cost_per_session": 0.05}
        html = {"average_cost_per_session": 0.0}
        civicplus = {"cost_per_opportunity": 0.10}

        result = monitor._generate_cost_comparison(legistar, html, civicplus)
        # With html defaulted to 0.08, civicplus at 0.10 is most expensive
        # Legistar 0.05 is cheapest, ratio = 0.10 / 0.05 = 2.0
        assert "Legistar API most efficient" in result
        assert "2.0x" in result

    def test_handles_all_equal_costs(self, monitor):
        legistar = {"cost_per_session": 0.05}
        html = {"average_cost_per_session": 0.05}
        civicplus = {"cost_per_opportunity": 0.05}

        result = monitor._generate_cost_comparison(legistar, html, civicplus)
        # Ratio = 1.0x (all same cost)
        assert "1.0x" in result

    def test_handles_zero_cheapest_cost(self, monitor):
        legistar = {"cost_per_session": 0.0}
        html = {"average_cost_per_session": 0.0}
        civicplus = {"cost_per_opportunity": 0.0}

        result = monitor._generate_cost_comparison(legistar, html, civicplus)
        # html defaults to $0.08 when zero, so legistar ($0) is cheapest
        # ratio = 0 because cheapest cost is 0 (division guard)
        assert result.startswith("Legistar API most efficient")
        assert "$0.000" in result
        assert "0.0x" in result


# ---------------------------------------------------------------------------
# generate_monitoring_report — report structure
# ---------------------------------------------------------------------------

class TestGenerateMonitoringReport:
    def test_report_aggregates_all_platform_costs(self, monitor):
        legistar_data = {
            "working_clients": 2, "estimated_monthly_cost": 3.0,
            "cost_per_session": 0.05, "client_details": [],
        }
        html_data = {
            "cities_tracked": ["city-a", "city-b"], "monthly_estimate": 5.0,
            "average_cost_per_session": 0.08, "last_7_days": [],
        }
        civicplus_data = {
            "working_cities": 1, "total_cities": 3,
            "estimated_monthly_cost": 0.15, "cost_per_opportunity": 0.048,
            "city_details": [],
        }

        with patch.object(monitor, "get_legistar_costs", return_value=legistar_data), \
             patch.object(monitor, "get_html_parsing_costs", return_value=html_data), \
             patch.object(monitor, "get_civicplus_costs", return_value=civicplus_data):
            report = monitor.generate_monitoring_report()

        summary = report["summary"]
        assert summary["total_working_platforms"] == 2 + 2 + 1  # legistar + html cities + civicplus
        assert summary["estimated_monthly_cost"] == pytest.approx(3.0 + 5.0 + 0.15)
        assert summary["cost_breakdown"]["legistar_api"] == 3.0
        assert summary["cost_breakdown"]["html_parsing"] == 5.0
        assert summary["cost_breakdown"]["civicplus_cms"] == pytest.approx(0.15)
        assert "CivicPlus CMS most efficient" in summary["platform_efficiency"]["cost_comparison"]

    def test_report_contains_timestamp(self, monitor):
        empty_legistar = {
            "working_clients": 0, "estimated_monthly_cost": 0.0,
            "cost_per_session": 0.05, "client_details": [],
        }
        empty_html = {
            "cities_tracked": [], "monthly_estimate": 0.0,
            "average_cost_per_session": 0.0, "last_7_days": [],
        }
        empty_civicplus = {
            "working_cities": 0, "total_cities": 0,
            "estimated_monthly_cost": 0.0, "cost_per_opportunity": 0.048,
            "city_details": [],
        }

        with patch.object(monitor, "get_legistar_costs", return_value=empty_legistar), \
             patch.object(monitor, "get_html_parsing_costs", return_value=empty_html), \
             patch.object(monitor, "get_civicplus_costs", return_value=empty_civicplus):
            report = monitor.generate_monitoring_report()

        # Verify timestamp is a valid ISO format and recent
        ts = datetime.fromisoformat(report["timestamp"])
        assert (datetime.now() - ts).total_seconds() < 5


# ---------------------------------------------------------------------------
# save_monitoring_data
# ---------------------------------------------------------------------------

class TestSaveMonitoringData:
    def test_prunes_entries_older_than_30_days(self, monitor, frozen_now, tmp_path):
        old_entry = {"timestamp": (frozen_now - timedelta(days=35)).isoformat()}
        recent_entry = {"timestamp": (frozen_now - timedelta(days=5)).isoformat()}
        new_report = {"timestamp": frozen_now.isoformat()}

        monitoring_file = tmp_path / "multi_platform_monitoring.json"
        monitoring_file.write_text(json.dumps([old_entry, recent_entry]))
        monitor.multi_platform_file = monitoring_file

        with patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            monitor.save_monitoring_data(new_report)

        saved = json.loads(monitoring_file.read_text())
        # old_entry (35 days ago) should be pruned, recent and new remain
        assert len(saved) == 2
        timestamps = [e["timestamp"] for e in saved]
        assert old_entry["timestamp"] not in timestamps
        assert recent_entry["timestamp"] in timestamps
        assert new_report["timestamp"] in timestamps

    def test_creates_new_file_when_none_exists(self, monitor, frozen_now, tmp_path):
        report = {"timestamp": frozen_now.isoformat()}
        monitoring_file = tmp_path / "subdir" / "monitoring.json"
        monitor.multi_platform_file = monitoring_file

        with patch("civicos_services.monitoring.multi_platform_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            mock_dt.fromisoformat = datetime.fromisoformat
            monitor.save_monitoring_data(report)

        assert monitoring_file.exists()
        saved = json.loads(monitoring_file.read_text())
        assert len(saved) == 1
        assert saved[0]["timestamp"] == frozen_now.isoformat()

    def test_handles_save_error_gracefully(self, monitor, capsys):
        report = {"timestamp": datetime(2026, 4, 10).isoformat()}

        with patch.object(Path, "exists", return_value=False), \
             patch("os.makedirs", side_effect=PermissionError("read-only fs")):
            # Should not raise — error is caught internally
            monitor.save_monitoring_data(report)

        captured = capsys.readouterr()
        assert "Error saving monitoring data" in captured.out
        assert "read-only fs" in captured.out


# ---------------------------------------------------------------------------
# check_foundation_budget_compliance
# ---------------------------------------------------------------------------

class TestCheckFoundationBudgetCompliance:
    def test_under_pilot_budget(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 25.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "EXCELLENT" in captured.out
        assert "pilot budget" in captured.out.lower()

    def test_between_pilot_and_scaling_budget(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 100.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "GOOD" in captured.out
        assert "Phase 2" in captured.out

    def test_over_scaling_budget(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 300.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "HIGH COST" in captured.out

    def test_exactly_at_pilot_threshold(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 50.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        # $50 <= $50 pilot, so should be EXCELLENT
        assert "EXCELLENT" in captured.out

    def test_just_over_pilot_threshold(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 50.01}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        # $50.01 > $50 pilot but <= $200 scaling
        assert "GOOD" in captured.out

    def test_exactly_at_scaling_threshold(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 200.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "GOOD" in captured.out

    def test_just_over_scaling_threshold(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 200.01}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "HIGH COST" in captured.out

    def test_prints_all_phase_thresholds(self, monitor, capsys):
        report = {"summary": {"estimated_monthly_cost": 0.0}}
        monitor.check_foundation_budget_compliance(report)
        captured = capsys.readouterr()
        assert "Pilot" in captured.out
        assert "Scaling" in captured.out
        assert "Production" in captured.out
        assert "$50.00" in captured.out
        assert "$200.00" in captured.out
        assert "$500.00" in captured.out

"""
Tests for automated_civic_refresh.py — URL-jurisdiction matching, exponential
backoff retry, failure logging, cost monitoring with budget thresholds, alert
deduplication, cached data fallback, and schema validation.

Mocks only I/O (filesystem, SMTP, subprocess, CITY_CONFIGS).
Exercises real logic: domain matching, cost arithmetic, threshold classification,
retry counting, alert dedup, and graceful degradation.

To run:
    pytest packages/civicos-services/tests/test_automated_civic_refresh.py -q --override-ini="addopts="
"""

import email
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call

import pytest

from civicos_services.monitoring.automated_civic_refresh import (
    get_jurisdiction_agent_type,
    get_jurisdiction_by_url,
    ProductionErrorHandler,
    ProductionAlertManager,
    TemporalCostManager,
    validate_schema_output,
    _get_cached_data,
    refresh_city_data,
)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

FAKE_CITY_CONFIGS = {
    "berkeley": {
        "jurisdiction_id": "city-berkeley",
        "agent_type": "berkeley_cms",
        "meeting_urls": ["https://berkeleyca.gov/meetings"],
    },
    "san-rafael": {
        "jurisdiction_id": "city-san-rafael",
        "agent_type": "legistar",
        "meeting_urls": [
            "https://sanrafael.legistar.com/Calendar.aspx",
            "https://cityofsanrafael.granicus.com/meetings",
        ],
    },
}


# ---------------------------------------------------------------------------
# get_jurisdiction_agent_type
# ---------------------------------------------------------------------------

class TestGetJurisdictionAgentType:
    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_agent_type_for_exact_domain_match(self):
        result = get_jurisdiction_agent_type("https://berkeleyca.gov/meetings/2026")
        assert result == "berkeley_cms"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_agent_type_for_subdomain_match(self):
        result = get_jurisdiction_agent_type("https://sanrafael.legistar.com/Calendar.aspx")
        assert result == "legistar"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_standard_when_no_domain_matches(self):
        result = get_jurisdiction_agent_type("https://unknown-city.gov/meetings")
        assert result == "standard"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_handles_url_without_protocol(self):
        # URL without '//' triggers IndexError, falls through to default
        result = get_jurisdiction_agent_type("no-protocol-url")
        assert result == "standard"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", {})
    def test_returns_standard_for_empty_configs(self):
        result = get_jurisdiction_agent_type("https://berkeleyca.gov/meetings")
        assert result == "standard"


# ---------------------------------------------------------------------------
# get_jurisdiction_by_url
# ---------------------------------------------------------------------------

class TestGetJurisdictionByUrl:
    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_jurisdiction_id_for_matching_url(self):
        result = get_jurisdiction_by_url("https://sanrafael.legistar.com/Calendar.aspx")
        assert result == "city-san-rafael"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_unknown_for_unmatched_url(self):
        result = get_jurisdiction_by_url("https://no-match.example.com/page")
        assert result == "unknown"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_returns_correct_jurisdiction_among_multiple(self):
        result = get_jurisdiction_by_url("https://berkeleyca.gov/meetings/agenda")
        assert result == "city-berkeley"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    def test_handles_malformed_url_gracefully(self):
        result = get_jurisdiction_by_url("")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# ProductionErrorHandler
# ---------------------------------------------------------------------------

class TestProductionErrorHandler:
    @pytest.fixture
    def handler(self, tmp_path):
        h = ProductionErrorHandler()
        h.failure_log_file = str(tmp_path / "failures.json")
        return h

    def test_retry_succeeds_on_first_attempt(self, handler):
        counter = {"calls": 0}

        def succeed():
            counter["calls"] += 1
            return "ok"

        result = handler.exponential_backoff_retry(succeed)
        assert result == "ok"
        assert counter["calls"] == 1

    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_retry_succeeds_after_transient_failure(self, mock_sleep, handler):
        call_count = {"n": 0}

        def fail_then_succeed():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("transient error")
            return "recovered"

        result = handler.exponential_backoff_retry(fail_then_succeed)
        assert result == "recovered"
        assert call_count["n"] == 3
        assert mock_sleep.call_count == 2

    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_retry_raises_after_max_attempts(self, mock_sleep, handler):
        def always_fail():
            raise RuntimeError("persistent error")

        with pytest.raises(RuntimeError, match="persistent error"):
            handler.exponential_backoff_retry(always_fail)
        assert mock_sleep.call_count == 2  # max_retries - 1 sleeps

    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_retry_handles_timeout_expired(self, mock_sleep, handler):
        import subprocess

        def timeout():
            raise subprocess.TimeoutExpired(cmd="test", timeout=5)

        with pytest.raises(subprocess.TimeoutExpired):
            handler.exponential_backoff_retry(timeout)

    def test_log_failure_creates_file_and_writes_entry(self, handler):
        handler.log_failure("error", "test message", ("arg1",))

        with open(handler.failure_log_file, "r") as f:
            failures = json.load(f)

        assert len(failures) == 1
        assert failures[0]["failure_type"] == "error"
        assert failures[0]["error_message"] == "test message"
        assert failures[0]["retry_count"] == 3

    def test_log_failure_truncates_to_100_entries(self, handler):
        # Pre-populate with 100 entries
        existing = [
            {"timestamp": "2025-01-01T00:00:00", "failure_type": "old",
             "error_message": f"old-{i}", "context": "", "retry_count": 3}
            for i in range(100)
        ]
        os.makedirs(os.path.dirname(handler.failure_log_file), exist_ok=True)
        with open(handler.failure_log_file, "w") as f:
            json.dump(existing, f)

        handler.log_failure("error", "new entry", ())

        with open(handler.failure_log_file, "r") as f:
            failures = json.load(f)

        assert len(failures) == 100
        assert failures[-1]["error_message"] == "new entry"
        # Oldest entry was pushed out
        assert failures[0]["error_message"] == "old-1"

    def test_log_failure_truncates_long_context(self, handler):
        long_context = "x" * 1000
        handler.log_failure("error", "msg", long_context)

        with open(handler.failure_log_file, "r") as f:
            failures = json.load(f)

        assert len(failures[0]["context"]) <= 500

    def test_check_persistent_failures_no_file(self, handler):
        result = handler.check_persistent_failures()
        assert result["needs_alert"] is False
        assert result["failure_count"] == 0

    def test_check_persistent_failures_under_threshold(self, handler):
        now = datetime.now()
        failures = [
            {"timestamp": now.isoformat(), "failure_type": "error",
             "error_message": f"fail-{i}", "retry_count": 3}
            for i in range(3)
        ]
        os.makedirs(os.path.dirname(handler.failure_log_file), exist_ok=True)
        with open(handler.failure_log_file, "w") as f:
            json.dump(failures, f)

        result = handler.check_persistent_failures()
        assert result["needs_alert"] is False
        assert result["failure_count"] == 3

    def test_check_persistent_failures_over_threshold_triggers_alert(self, handler):
        now = datetime.now()
        failures = [
            {"timestamp": now.isoformat(), "failure_type": "error",
             "error_message": f"fail-{i}", "retry_count": 3}
            for i in range(6)
        ]
        os.makedirs(os.path.dirname(handler.failure_log_file), exist_ok=True)
        with open(handler.failure_log_file, "w") as f:
            json.dump(failures, f)

        result = handler.check_persistent_failures()
        assert result["needs_alert"] is True
        assert result["failure_count"] == 6
        assert len(result["recent_failures"]) == 3  # last 3 only

    def test_check_persistent_failures_ignores_old_entries(self, handler):
        old = datetime.now() - timedelta(hours=48)
        failures = [
            {"timestamp": old.isoformat(), "failure_type": "error",
             "error_message": f"old-{i}", "retry_count": 3}
            for i in range(10)
        ]
        os.makedirs(os.path.dirname(handler.failure_log_file), exist_ok=True)
        with open(handler.failure_log_file, "w") as f:
            json.dump(failures, f)

        result = handler.check_persistent_failures()
        assert result["needs_alert"] is False
        assert result["failure_count"] == 0


# ---------------------------------------------------------------------------
# ProductionAlertManager
# ---------------------------------------------------------------------------

class TestProductionAlertManager:
    @patch.object(ProductionAlertManager, "_send_email")
    def test_send_budget_alert_skips_when_unconfigured(self, mock_send):
        mgr = ProductionAlertManager()
        mgr.alert_recipients = [""]
        mgr.smtp_username = ""

        mgr.send_budget_alert({
            "budget_percentage": 95.0,
            "total_cost": 47.50,
            "budget_limit": 50.0,
            "budget_status": "over_budget",
            "entries": [],
        })
        mock_send.assert_not_called()

    @patch.object(ProductionAlertManager, "_send_email")
    def test_send_failure_alert_skips_when_no_alert_needed(self, mock_send):
        mgr = ProductionAlertManager()
        mgr.send_failure_alert({"needs_alert": False})
        mock_send.assert_not_called()

    @patch("civicos_services.monitoring.automated_civic_refresh.smtplib.SMTP")
    def test_send_budget_alert_sends_email_when_configured(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        mgr = ProductionAlertManager()
        mgr.alert_recipients = ["admin@example.com"]
        mgr.smtp_username = "bot@example.com"
        mgr.smtp_password = "secret"
        mgr.smtp_server = "smtp.example.com"
        mgr.smtp_port = 587

        mgr.send_budget_alert({
            "budget_percentage": 96.0,
            "total_cost": 48.0,
            "budget_limit": 50.0,
            "budget_status": "over_budget",
            "entries": [1, 2, 3],
        })

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("bot@example.com", "secret")
        # Verify the email was actually sent
        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "bot@example.com"
        assert args[1] == ["admin@example.com"]
        # Parse the MIME message to check decoded content
        msg = email.message_from_string(args[2])
        decoded_subject = str(email.header.make_header(email.header.decode_header(msg["Subject"])))
        assert "96.0% Used" in decoded_subject
        body = msg.get_payload(0).get_payload(decode=True).decode()
        assert "$48.00" in body
        assert "over_budget" in body

    @patch.object(ProductionAlertManager, "_send_email")
    def test_send_daily_cost_alert_skips_when_unconfigured(self, mock_send):
        mgr = ProductionAlertManager()
        mgr.alert_recipients = [""]
        mgr.smtp_username = ""

        mgr.send_daily_cost_alert({
            "total_cost": 7.50,
            "daily_limit": 5.0,
            "budget_percentage": 150.0,
            "budget_status": "over_limit",
            "entries": [],
        })
        mock_send.assert_not_called()

    @patch("civicos_services.monitoring.automated_civic_refresh.smtplib.SMTP")
    def test_send_failure_alert_sends_email_with_failure_details(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        mgr = ProductionAlertManager()
        mgr.alert_recipients = ["ops@example.com"]
        mgr.smtp_username = "bot@example.com"
        mgr.smtp_password = "secret"

        mgr.send_failure_alert({
            "needs_alert": True,
            "failure_count": 8,
            "recent_failures": [
                {"timestamp": "2026-04-09T10:00:00", "failure_type": "timeout",
                 "error_message": "Connection timed out"},
            ],
        })

        mock_server.sendmail.assert_called_once()
        email_text = mock_server.sendmail.call_args[0][2]
        assert "8 failures" in email_text
        assert "Connection timed out" in email_text


# ---------------------------------------------------------------------------
# TemporalCostManager
# ---------------------------------------------------------------------------

class TestTemporalCostManager:
    @pytest.fixture
    def cost_mgr(self, tmp_path):
        mgr = TemporalCostManager()
        mgr.cost_log_file = str(tmp_path / "costs.json")
        mgr.alert_manager = MagicMock()
        return mgr

    def test_log_refresh_cost_creates_entry_with_correct_fields(self, cost_mgr):
        cost_mgr.log_refresh_cost("city-san-rafael", "current_active_only", 0.12, 5)

        with open(cost_mgr.cost_log_file, "r") as f:
            log = json.load(f)

        assert len(log) == 1
        assert log[0]["city_id"] == "city-san-rafael"
        assert log[0]["temporal_scope"] == "current_active_only"
        assert log[0]["estimated_cost"] == 0.12
        assert log[0]["opportunities_generated"] == 5
        assert log[0]["cost_per_opportunity"] == pytest.approx(0.024, rel=1e-3)

    def test_log_refresh_cost_zero_opportunities_no_division_error(self, cost_mgr):
        cost_mgr.log_refresh_cost("city-berkeley", "future_meetings_only", 0.10, 0)

        with open(cost_mgr.cost_log_file, "r") as f:
            log = json.load(f)

        assert log[0]["cost_per_opportunity"] == pytest.approx(0.10, rel=1e-3)
        assert log[0]["opportunities_generated"] == 0

    def test_log_refresh_cost_appends_to_existing(self, cost_mgr):
        cost_mgr.log_refresh_cost("city-a", "scope1", 0.05, 2)
        cost_mgr.log_refresh_cost("city-b", "scope2", 0.08, 3)

        with open(cost_mgr.cost_log_file, "r") as f:
            log = json.load(f)

        assert len(log) == 2
        assert log[0]["city_id"] == "city-a"
        assert log[1]["city_id"] == "city-b"

    def test_get_monthly_costs_no_file_returns_zero(self, cost_mgr):
        result = cost_mgr.get_monthly_costs()
        assert result["total_cost"] == 0.0
        assert result["budget_percentage"] == 0.0
        assert result["budget_status"] == "under_budget"
        assert result["entries"] == []

    def test_get_monthly_costs_sums_current_month_entries(self, cost_mgr):
        now = datetime.now()
        entries = [
            {"timestamp": now.isoformat(), "estimated_cost": 10.0},
            {"timestamp": now.isoformat(), "estimated_cost": 15.0},
            # Old entry from 2 months ago — should be excluded
            {"timestamp": (now - timedelta(days=65)).isoformat(), "estimated_cost": 100.0},
        ]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_monthly_costs()
        assert result["total_cost"] == pytest.approx(25.0)
        assert result["budget_percentage"] == pytest.approx(50.0)
        assert result["budget_status"] == "under_budget"
        assert len(result["entries"]) == 2

    def test_get_monthly_costs_warning_at_70_percent(self, cost_mgr):
        now = datetime.now()
        entries = [{"timestamp": now.isoformat(), "estimated_cost": 36.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_monthly_costs()
        # 36/50 = 72%
        assert result["budget_status"] == "warning"

    def test_get_monthly_costs_critical_warning_at_85_percent(self, cost_mgr):
        now = datetime.now()
        entries = [{"timestamp": now.isoformat(), "estimated_cost": 43.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_monthly_costs()
        # 43/50 = 86%
        assert result["budget_status"] == "critical_warning"

    def test_get_monthly_costs_over_budget_at_95_percent(self, cost_mgr):
        now = datetime.now()
        entries = [{"timestamp": now.isoformat(), "estimated_cost": 48.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_monthly_costs()
        # 48/50 = 96%
        assert result["budget_status"] == "over_budget"
        assert result["budget_percentage"] == pytest.approx(96.0)

    def test_get_daily_costs_no_file_returns_zero(self, cost_mgr):
        result = cost_mgr.get_daily_costs()
        assert result["total_cost"] == 0.0
        assert result["budget_percentage"] == 0.0
        assert result["budget_status"] == "under_limit"
        assert result["daily_limit"] == 5.0

    def test_get_daily_costs_sums_todays_entries_only(self, cost_mgr):
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        entries = [
            {"timestamp": today.isoformat(), "estimated_cost": 2.0},
            {"timestamp": today.isoformat(), "estimated_cost": 1.5},
            {"timestamp": yesterday.isoformat(), "estimated_cost": 10.0},
        ]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_daily_costs()
        assert result["total_cost"] == pytest.approx(3.5)
        assert result["budget_percentage"] == pytest.approx(70.0)
        assert result["budget_status"] == "under_limit"

    def test_get_daily_costs_warning_at_80_percent(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 4.2}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_daily_costs()
        # 4.2/5.0 = 84%
        assert result["budget_status"] == "warning"

    def test_get_daily_costs_over_limit_at_100_percent(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 6.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_daily_costs()
        # 6.0/5.0 = 120%
        assert result["budget_status"] == "over_limit"
        assert result["budget_percentage"] == pytest.approx(120.0)

    def test_get_cost_status_combines_daily_and_monthly(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 2.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_cost_status()
        assert result["overall_status"] == "healthy"
        assert result["daily"]["cost"] == pytest.approx(2.0)
        assert result["daily"]["limit"] == 5.0
        assert result["monthly"]["cost"] == pytest.approx(2.0)
        assert result["monthly"]["limit"] == 50.0

    def test_get_cost_status_critical_when_daily_over_limit(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 6.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_cost_status()
        assert result["overall_status"] == "critical"
        assert result["daily"]["status"] == "over_limit"

    def test_get_cost_status_critical_when_monthly_over_budget(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 48.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_cost_status()
        assert result["overall_status"] == "critical"
        assert result["monthly"]["status"] == "over_budget"

    def test_get_cost_status_warning_when_daily_warning(self, cost_mgr):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 4.2}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        result = cost_mgr.get_cost_status()
        assert result["overall_status"] == "warning"

    def test_daily_over_limit_triggers_alert_via_alert_manager(self, cost_mgr, tmp_path):
        """When daily costs exceed the limit, the alert manager is called."""
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": 6.0}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

        # Patch the hardcoded alert_log_file path to use a temp dir (no prior alerts)
        fake_alert_log = str(tmp_path / "alert_log.json")
        with patch("civicos_services.monitoring.automated_civic_refresh.TemporalCostManager._log_alert"):
            # Make os.path.exists return False for the alert log so dedup is skipped
            original_exists = os.path.exists

            def patched_exists(p):
                if "alert_log.json" in str(p):
                    return False
                return original_exists(p)

            with patch("civicos_services.monitoring.automated_civic_refresh.os.path.exists",
                        side_effect=patched_exists):
                result = cost_mgr.get_daily_costs()

        assert result["budget_status"] == "over_limit"
        # Alert manager should have been called with the daily status
        cost_mgr.alert_manager.send_daily_cost_alert.assert_called_once()
        alert_arg = cost_mgr.alert_manager.send_daily_cost_alert.call_args[0][0]
        assert alert_arg["total_cost"] == pytest.approx(6.0)
        assert alert_arg["budget_status"] == "over_limit"


# ---------------------------------------------------------------------------
# validate_schema_output
# ---------------------------------------------------------------------------

class TestValidateSchemaOutput:
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    def test_returns_false_when_no_schema_files(self, mock_glob):
        assert validate_schema_output() is False

    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    @patch("builtins.open")
    def test_returns_false_when_missing_required_fields(self, mock_open, mock_mtime, mock_glob):
        mock_glob.return_value = ["/tmp/events_001.json"]
        mock_mtime.return_value = 1000.0
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value='{"events": []}')

        import io
        mock_file = io.StringIO(json.dumps({"events": []}))
        mock_open.return_value.__enter__ = lambda s: mock_file

        result = validate_schema_output()
        assert result is False

    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    def test_returns_true_for_valid_schema(self, mock_mtime, mock_glob, tmp_path):
        schema_file = str(tmp_path / "events_valid.json")
        valid_data = {
            "id": "test-1",
            "jurisdiction": {"id": "city-test"},
            "events": [
                {"id": "e-1", "title": "Council Meeting",
                 "description": "Regular session", "when": "2026-04-15T18:00:00"}
            ],
            "created_at": "2026-04-09T10:00:00",
        }
        with open(schema_file, "w") as f:
            json.dump(valid_data, f)

        mock_glob.return_value = [schema_file]
        mock_mtime.return_value = 1000.0

        result = validate_schema_output()
        assert result is True

    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    def test_returns_false_when_event_missing_required_fields(self, mock_mtime, mock_glob, tmp_path):
        schema_file = str(tmp_path / "events_bad.json")
        data = {
            "id": "test-1",
            "jurisdiction": {"id": "city-test"},
            "events": [
                {"id": "e-1", "title": "Council Meeting"}
                # Missing 'description' and 'when'
            ],
            "created_at": "2026-04-09T10:00:00",
        }
        with open(schema_file, "w") as f:
            json.dump(data, f)

        mock_glob.return_value = [schema_file]
        mock_mtime.return_value = 1000.0

        result = validate_schema_output()
        assert result is False


# ---------------------------------------------------------------------------
# _get_cached_data
# ---------------------------------------------------------------------------

class TestGetCachedData:
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    def test_returns_none_when_no_files(self, mock_glob):
        result = _get_cached_data("berkeley")
        assert result is None

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    def test_returns_most_recent_matching_file(self, mock_mtime, mock_glob, tmp_path):
        older = str(tmp_path / "events_old.json")
        newer = str(tmp_path / "events_new.json")

        now_ts = time.time()
        one_day_ago_ts = now_ts - 86400

        for fpath, n_events in [(older, 2), (newer, 5)]:
            data = {
                "jurisdiction": {"id": "city-berkeley"},
                "events": [{"id": f"e-{i}"} for i in range(n_events)],
            }
            with open(fpath, "w") as f:
                json.dump(data, f)

        mock_glob.return_value = [older, newer]
        mock_mtime.side_effect = lambda p: now_ts if "new" in p else one_day_ago_ts

        result = _get_cached_data("berkeley", days_back=30)
        assert len(result["events"]) == 5  # Should return newer file
        assert result["jurisdiction"]["id"] == "city-berkeley"

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    def test_returns_none_when_jurisdiction_does_not_match(self, mock_mtime, mock_glob, tmp_path):
        fpath = str(tmp_path / "events_sr.json")
        data = {"jurisdiction": {"id": "city-san-rafael"}, "events": []}
        with open(fpath, "w") as f:
            json.dump(data, f)

        mock_glob.return_value = [fpath]
        mock_mtime.return_value = time.time()

        result = _get_cached_data("berkeley", days_back=30)
        assert result is None

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", FAKE_CITY_CONFIGS)
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob")
    @patch("civicos_services.monitoring.automated_civic_refresh.os.path.getmtime")
    def test_returns_none_when_files_are_too_old(self, mock_mtime, mock_glob, tmp_path):
        fpath = str(tmp_path / "events_old.json")
        data = {"jurisdiction": {"id": "city-berkeley"}, "events": [{"id": "e-1"}]}
        with open(fpath, "w") as f:
            json.dump(data, f)

        mock_glob.return_value = [fpath]
        # 30 days ago
        mock_mtime.return_value = (datetime.now() - timedelta(days=30)).timestamp()

        result = _get_cached_data("berkeley", days_back=7)
        assert result is None


# ---------------------------------------------------------------------------
# refresh_city_data — temporal scope and cost multiplier logic
# ---------------------------------------------------------------------------

class TestRefreshCityData:
    SINGLE_URL_CONFIG = {
        "test-city": {
            "jurisdiction_id": "city-test",
            "agent_type": "standard",
            "meeting_urls": ["https://testcity.gov/meetings"],
        }
    }

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_future_only_scope_uses_0_4_cost_multiplier(self, mock_sleep, mock_glob, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost") as mock_log:
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city", "future_meetings_only")

        assert len(result["success"]) == 1
        assert result["success"][0] == "https://testcity.gov/meetings"
        # 0.12 * 0.4 = 0.048
        assert result["estimated_cost"] == pytest.approx(0.048, rel=1e-2)

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_include_recent_past_scope_uses_1_0_cost_multiplier(self, mock_sleep, mock_glob, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost") as mock_log:
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city", "include_recent_past")

        # 0.12 * 1.0 = 0.12
        assert result["estimated_cost"] == pytest.approx(0.12, rel=1e-2)

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_default_scope_uses_0_6_cost_multiplier(self, mock_sleep, mock_glob, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost") as mock_log:
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city", "current_active_only")

        # 0.12 * 0.6 = 0.072
        assert result["estimated_cost"] == pytest.approx(0.072, rel=1e-2)

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_failed_url_recorded_in_failures(self, mock_sleep, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Connection refused", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost"):
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city")

        assert len(result["failures"]) == 1
        assert "testcity.gov" in result["failures"][0]
        assert result["estimated_cost"] == 0.0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh._get_cached_data")
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_graceful_degradation_uses_cached_data_on_total_failure(self, mock_sleep, mock_cache, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Error", stdout="")
        mock_cache.return_value = {
            "events": [{"id": "e-1"}, {"id": "e-2"}],
            "created_at": "2026-04-08T10:00:00",
        }

        with patch.object(TemporalCostManager, "log_refresh_cost"):
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city")

        assert result["fallback_used"] is True
        assert result["filtered_count"] == 2

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", SINGLE_URL_CONFIG)
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh._get_cached_data", return_value=None)
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_no_fallback_when_cache_empty_and_all_fail(self, mock_sleep, mock_cache, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="Error", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost"):
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("test-city")

        assert result["fallback_used"] is False
        assert result["filtered_count"] == 0

    @patch("civicos_services.monitoring.automated_civic_refresh.CITY_CONFIGS", {
        "multi-url": {
            "jurisdiction_id": "city-multi",
            "agent_type": "standard",
            "meeting_urls": ["https://a.gov/m", "https://b.gov/m"],
        }
    })
    @patch("civicos_services.monitoring.automated_civic_refresh.subprocess.run")
    @patch("civicos_services.monitoring.automated_civic_refresh.glob.glob", return_value=[])
    @patch("civicos_services.monitoring.automated_civic_refresh.time.sleep")
    def test_accumulates_cost_across_multiple_urls(self, mock_sleep, mock_glob, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch.object(TemporalCostManager, "log_refresh_cost"):
            with patch.object(ProductionErrorHandler, "check_persistent_failures",
                              return_value={"needs_alert": False}):
                result = refresh_city_data("multi-url", "future_meetings_only")

        assert len(result["success"]) == 2
        # 2 URLs * 0.12 * 0.4 = 0.096
        assert result["estimated_cost"] == pytest.approx(0.096, rel=1e-2)


# ---------------------------------------------------------------------------
# Budget threshold boundary tests
# ---------------------------------------------------------------------------

class TestBudgetThresholdBoundaries:
    """Verify exact boundary values for budget classification."""

    @pytest.fixture
    def cost_mgr(self, tmp_path):
        mgr = TemporalCostManager()
        mgr.cost_log_file = str(tmp_path / "costs.json")
        mgr.alert_manager = MagicMock()
        return mgr

    def _write_cost(self, cost_mgr, amount):
        entries = [{"timestamp": datetime.now().isoformat(), "estimated_cost": amount}]
        os.makedirs(os.path.dirname(cost_mgr.cost_log_file), exist_ok=True)
        with open(cost_mgr.cost_log_file, "w") as f:
            json.dump(entries, f)

    def test_monthly_69_percent_is_under_budget(self, cost_mgr):
        self._write_cost(cost_mgr, 34.5)  # 34.5/50 = 69%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "under_budget"

    def test_monthly_70_percent_is_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 35.0)  # 35/50 = 70%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "warning"

    def test_monthly_84_percent_is_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 42.0)  # 42/50 = 84%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "warning"

    def test_monthly_85_percent_is_critical_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 42.5)  # 42.5/50 = 85%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "critical_warning"

    def test_monthly_94_percent_is_critical_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 47.0)  # 47/50 = 94%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "critical_warning"

    def test_monthly_95_percent_is_over_budget(self, cost_mgr):
        self._write_cost(cost_mgr, 47.5)  # 47.5/50 = 95%
        result = cost_mgr.get_monthly_costs()
        assert result["budget_status"] == "over_budget"

    def test_daily_79_percent_is_under_limit(self, cost_mgr):
        self._write_cost(cost_mgr, 3.95)  # 3.95/5 = 79%
        result = cost_mgr.get_daily_costs()
        assert result["budget_status"] == "under_limit"

    def test_daily_80_percent_is_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 4.0)  # 4/5 = 80%
        result = cost_mgr.get_daily_costs()
        assert result["budget_status"] == "warning"

    def test_daily_99_percent_is_warning(self, cost_mgr):
        self._write_cost(cost_mgr, 4.95)  # 4.95/5 = 99%
        result = cost_mgr.get_daily_costs()
        assert result["budget_status"] == "warning"

    def test_daily_100_percent_is_over_limit(self, cost_mgr):
        self._write_cost(cost_mgr, 5.0)  # 5/5 = 100%
        result = cost_mgr.get_daily_costs()
        assert result["budget_status"] == "over_limit"

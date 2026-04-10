"""
Tests for daily_cost_digest.py — DailyCostDigest cost collection, trend/budget
logic, formatting, and send orchestration.

Mocks external I/O (CivicOS API, SMTP, push notifications). Tests real
formatting logic, threshold calculations, and orchestration.

To run:
    pytest packages/civicos-services/tests/test_daily_cost_digest.py -q --override-ini="addopts="
"""

from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.monitoring.daily_cost_digest import (
    CostDigestData,
    DailyCostDigest,
    send_daily_digest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Use today's actual date so time_series comparisons work without datetime mocking
_TODAY_STR = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _make_digest_data(
    date="2026-04-10",
    total_cost_usd=1.50,
    by_service=None,
    by_category=None,
    record_count=42,
    yesterday_cost_usd=1.20,
    weekly_avg_usd=1.35,
    daily_budget=5.0,
    monthly_budget=50.0,
    monthly_total_usd=12.0,
    budget_status="healthy",
    trend="up",
    trend_percent=25.0,
):
    return CostDigestData(
        date=date,
        total_cost_usd=total_cost_usd,
        by_service={"openai": 1.0, "supabase": 0.50} if by_service is None else by_service,
        by_category={"llm": 1.0, "storage": 0.50} if by_category is None else by_category,
        record_count=record_count,
        yesterday_cost_usd=yesterday_cost_usd,
        weekly_avg_usd=weekly_avg_usd,
        daily_budget=daily_budget,
        monthly_budget=monthly_budget,
        monthly_total_usd=monthly_total_usd,
        budget_status=budget_status,
        trend=trend,
        trend_percent=trend_percent,
    )


def _make_mock_civic(
    today_cost=1.50,
    by_service=None,
    by_category=None,
    record_count=42,
    time_series=None,
    monthly_total=12.0,
):
    """Return a mock CivicOS instance with get_operating_cost_dashboard."""
    mock = MagicMock()

    if time_series is None:
        time_series = [
            {"date": "2020-01-01", "total_usd": 1.10},
            {"date": "2020-01-02", "total_usd": 1.20},
        ]

    def dashboard(period="day"):
        if period == "day":
            return {
                "summary": {
                    "total_cost_usd": today_cost,
                    "by_service": by_service or {"openai": 1.0, "supabase": 0.50},
                    "by_category": by_category or {"llm": 1.0, "storage": 0.50},
                    "record_count": record_count,
                }
            }
        elif period == "week":
            return {"time_series": time_series}
        elif period == "month":
            return {"summary": {"total_cost_usd": monthly_total}}
        return {}

    mock.get_operating_cost_dashboard = MagicMock(side_effect=dashboard)
    return mock


def _collect(digest_or_kwargs, mock_civic):
    """Run collect_data with mocked CivicOS and dotenv."""
    if isinstance(digest_or_kwargs, DailyCostDigest):
        d = digest_or_kwargs
    else:
        with patch.dict(
            "os.environ",
            {"CIVICOS_ALERT_EMAILS": "", "CIVICOS_COST_DIGEST_ENABLED": "true"},
            clear=False,
        ):
            d = DailyCostDigest(**digest_or_kwargs)

    with patch("civicos.CivicOS", return_value=mock_civic):
        with patch("dotenv.load_dotenv"):
            return d.collect_data()


@pytest.fixture
def digest():
    """DailyCostDigest with test budgets and no env var pollution."""
    with patch.dict(
        "os.environ",
        {
            "CIVICOS_ALERT_EMAILS": "",
            "CIVICOS_SMTP_USERNAME": "",
            "CIVICOS_SMTP_PASSWORD": "",
            "CIVICOS_COST_DIGEST_ENABLED": "true",
        },
        clear=False,
    ):
        return DailyCostDigest(
            jurisdiction_id="city-san-rafael",
            daily_budget=5.0,
            monthly_budget=50.0,
        )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_budgets_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "CIVICOS_DAILY_BUDGET": "10.0",
                "CIVICOS_MONTHLY_BUDGET": "100.0",
                "CIVICOS_ALERT_EMAILS": "",
                "CIVICOS_COST_DIGEST_ENABLED": "true",
            },
            clear=False,
        ):
            d = DailyCostDigest(jurisdiction_id="city-test")

        assert d.daily_budget == 10.0
        assert d.monthly_budget == 100.0

    def test_explicit_budgets_override_env(self):
        with patch.dict(
            "os.environ",
            {
                "CIVICOS_DAILY_BUDGET": "10.0",
                "CIVICOS_MONTHLY_BUDGET": "100.0",
                "CIVICOS_ALERT_EMAILS": "",
                "CIVICOS_COST_DIGEST_ENABLED": "true",
            },
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=3.0, monthly_budget=30.0)

        assert d.daily_budget == 3.0
        assert d.monthly_budget == 30.0

    def test_alert_emails_parsed_and_stripped(self):
        with patch.dict(
            "os.environ",
            {
                "CIVICOS_ALERT_EMAILS": " alice@test.com , bob@test.com , ",
                "CIVICOS_COST_DIGEST_ENABLED": "true",
            },
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        assert d.alert_emails == ["alice@test.com", "bob@test.com"]

    def test_empty_alert_emails_results_in_empty_list(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_ALERT_EMAILS": "", "CIVICOS_COST_DIGEST_ENABLED": "true"},
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        assert d.alert_emails == []

    def test_disabled_via_env_var(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_COST_DIGEST_ENABLED": "false", "CIVICOS_ALERT_EMAILS": ""},
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        assert d.enabled is False

    def test_enabled_by_default(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_ALERT_EMAILS": ""},
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        assert d.enabled is True

    def test_smtp_defaults(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_ALERT_EMAILS": "", "CIVICOS_COST_DIGEST_ENABLED": "true"},
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        assert d.smtp_server == "smtp.gmail.com"
        assert d.smtp_port == 587


# ---------------------------------------------------------------------------
# Budget status logic (via collect_data with mocked CivicOS)
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    def _collect_with_costs(self, daily_cost, monthly_total, daily_budget=5.0, monthly_budget=50.0):
        mock_civic = _make_mock_civic(today_cost=daily_cost, monthly_total=monthly_total)
        return _collect(
            {"daily_budget": daily_budget, "monthly_budget": monthly_budget},
            mock_civic,
        )

    def test_healthy_when_under_80_percent(self):
        data = self._collect_with_costs(daily_cost=3.0, monthly_total=30.0)
        assert data.budget_status == "healthy"

    def test_warning_when_daily_at_80_percent(self):
        data = self._collect_with_costs(daily_cost=4.0, monthly_total=30.0)
        assert data.budget_status == "warning"

    def test_warning_when_monthly_at_80_percent(self):
        data = self._collect_with_costs(daily_cost=1.0, monthly_total=40.0)
        assert data.budget_status == "warning"

    def test_critical_when_daily_at_100_percent(self):
        data = self._collect_with_costs(daily_cost=5.0, monthly_total=30.0)
        assert data.budget_status == "critical"

    def test_critical_when_monthly_at_95_percent(self):
        data = self._collect_with_costs(daily_cost=1.0, monthly_total=47.5)
        assert data.budget_status == "critical"

    def test_critical_when_daily_over_budget(self):
        data = self._collect_with_costs(daily_cost=7.0, monthly_total=20.0)
        assert data.budget_status == "critical"

    def test_healthy_at_79_percent_daily(self):
        data = self._collect_with_costs(daily_cost=3.95, monthly_total=20.0)
        assert data.budget_status == "healthy"


# ---------------------------------------------------------------------------
# Trend calculation
# ---------------------------------------------------------------------------


class TestTrendCalculation:
    def _collect_with_yesterday(self, today_cost, yesterday_cost):
        """Use _TODAY_STR so the code's datetime.now matches our time_series."""
        time_series = [
            {"date": "2020-01-01", "total_usd": yesterday_cost},
            {"date": _TODAY_STR, "total_usd": today_cost},
        ]
        mock_civic = _make_mock_civic(today_cost=today_cost, time_series=time_series)
        return _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)

    def test_trend_up_when_increase_over_10_percent(self):
        data = self._collect_with_yesterday(today_cost=1.50, yesterday_cost=1.20)
        assert data.trend == "up"
        assert data.trend_percent == pytest.approx(25.0, abs=0.1)

    def test_trend_down_when_decrease_over_10_percent(self):
        data = self._collect_with_yesterday(today_cost=0.80, yesterday_cost=1.20)
        assert data.trend == "down"
        assert data.trend_percent == pytest.approx(-33.33, abs=0.1)

    def test_trend_flat_when_change_within_10_percent(self):
        data = self._collect_with_yesterday(today_cost=1.10, yesterday_cost=1.05)
        assert data.trend == "flat"
        assert abs(data.trend_percent) <= 10.0

    def test_trend_flat_when_yesterday_is_zero(self):
        # All entries are non-today, but yesterday_cost=0
        time_series = [{"date": "2020-01-01", "total_usd": 0.0}]
        mock_civic = _make_mock_civic(today_cost=1.50, time_series=time_series)
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)
        assert data.trend == "flat"
        assert data.trend_percent == 0.0

    def test_trend_boundary_at_10_percent_is_up(self):
        # Floating point: (1.10-1.0)/1.0*100 ≈ 10.000000000000009 → "up"
        data = self._collect_with_yesterday(today_cost=1.10, yesterday_cost=1.0)
        assert data.trend == "up"

    def test_trend_boundary_just_under_10_percent(self):
        # 1.09 / 1.0 = 9% → flat
        data = self._collect_with_yesterday(today_cost=1.09, yesterday_cost=1.0)
        assert data.trend == "flat"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


class TestCollectData:
    def test_collects_service_breakdown(self):
        services = {"openai": 0.80, "supabase": 0.40, "modal": 0.30}
        mock_civic = _make_mock_civic(today_cost=1.50, by_service=services)
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)

        assert data.by_service["openai"] == 0.80
        assert data.by_service["supabase"] == 0.40
        assert data.by_service["modal"] == 0.30

    def test_collects_record_count(self):
        mock_civic = _make_mock_civic(record_count=123)
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)
        assert data.record_count == 123

    def test_weekly_avg_excludes_today(self):
        time_series = [
            {"date": "2020-01-01", "total_usd": 2.0},
            {"date": "2020-01-02", "total_usd": 4.0},
            {"date": _TODAY_STR, "total_usd": 10.0},
        ]
        mock_civic = _make_mock_civic(today_cost=10.0, time_series=time_series)
        data = _collect({"daily_budget": 20.0, "monthly_budget": 200.0}, mock_civic)

        # Average of [2.0, 4.0] = 3.0 (today's 10.0 excluded)
        assert data.weekly_avg_usd == pytest.approx(3.0, abs=0.01)

    def test_empty_time_series_yields_zero_yesterday_and_avg(self):
        mock_civic = _make_mock_civic(time_series=[])
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)

        assert data.yesterday_cost_usd == 0.0
        assert data.weekly_avg_usd == 0.0

    def test_monthly_total_from_api(self):
        mock_civic = _make_mock_civic(monthly_total=35.75)
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)
        assert data.monthly_total_usd == 35.75

    def test_yesterday_is_last_non_today_entry(self):
        time_series = [
            {"date": "2020-01-01", "total_usd": 0.50},
            {"date": "2020-01-02", "total_usd": 0.75},
            {"date": "2020-01-03", "total_usd": 1.25},
            {"date": _TODAY_STR, "total_usd": 2.00},
        ]
        mock_civic = _make_mock_civic(today_cost=2.0, time_series=time_series)
        data = _collect({"daily_budget": 5.0, "monthly_budget": 50.0}, mock_civic)

        # Last non-today entry is 2020-01-03 with cost 1.25
        assert data.yesterday_cost_usd == 1.25


# ---------------------------------------------------------------------------
# Plaintext formatting
# ---------------------------------------------------------------------------


class TestFormatPlaintext:
    def test_contains_date_and_status(self, digest):
        data = _make_digest_data(date="2026-04-10", budget_status="healthy")
        text = digest.format_plaintext(data)

        assert "Date: 2026-04-10" in text
        assert "Status: OK" in text

    def test_warning_status_label(self, digest):
        data = _make_digest_data(budget_status="warning")
        text = digest.format_plaintext(data)
        assert "Status: WARNING" in text

    def test_critical_status_label(self, digest):
        data = _make_digest_data(budget_status="critical")
        text = digest.format_plaintext(data)
        assert "Status: CRITICAL" in text

    def test_contains_cost_and_budget_percentage(self, digest):
        data = _make_digest_data(total_cost_usd=2.50, daily_budget=5.0)
        text = digest.format_plaintext(data)

        assert "$2.5000" in text
        assert "50.0% used" in text

    def test_trend_up_arrow(self, digest):
        data = _make_digest_data(trend="up", trend_percent=25.0)
        text = digest.format_plaintext(data)
        assert "^ 25.0%" in text

    def test_trend_down_arrow(self, digest):
        data = _make_digest_data(trend="down", trend_percent=-15.0)
        text = digest.format_plaintext(data)
        assert "v 15.0%" in text

    def test_trend_flat_arrow(self, digest):
        data = _make_digest_data(trend="flat", trend_percent=3.0)
        text = digest.format_plaintext(data)
        assert "- 3.0%" in text

    def test_services_sorted_by_cost_descending(self, digest):
        data = _make_digest_data(
            by_service={"supabase": 0.30, "openai": 1.20, "modal": 0.50}
        )
        text = digest.format_plaintext(data)

        openai_pos = text.index("openai")
        modal_pos = text.index("modal")
        supabase_pos = text.index("supabase")
        assert openai_pos < modal_pos < supabase_pos

    def test_empty_services_shows_no_data(self, digest):
        data = _make_digest_data(by_service={})
        text = digest.format_plaintext(data)
        assert "(no data)" in text

    def test_monthly_status_section(self, digest):
        data = _make_digest_data(monthly_total_usd=25.0, monthly_budget=50.0)
        text = digest.format_plaintext(data)
        assert "$25.0000" in text
        assert "50.0%" in text

    def test_record_count_in_output(self, digest):
        data = _make_digest_data(record_count=99)
        text = digest.format_plaintext(data)
        assert "Operations: 99" in text


# ---------------------------------------------------------------------------
# HTML formatting
# ---------------------------------------------------------------------------


class TestFormatHtml:
    def test_html_contains_status_color_for_healthy(self, digest):
        data = _make_digest_data(budget_status="healthy")
        html = digest.format_html(data)
        assert "#22c55e" in html

    def test_html_contains_status_color_for_warning(self, digest):
        data = _make_digest_data(budget_status="warning")
        html = digest.format_html(data)
        assert "#f59e0b" in html

    def test_html_contains_status_color_for_critical(self, digest):
        data = _make_digest_data(budget_status="critical")
        html = digest.format_html(data)
        assert "#ef4444" in html

    def test_html_contains_trend_up_arrow(self, digest):
        data = _make_digest_data(trend="up")
        html = digest.format_html(data)
        assert "&uarr;" in html

    def test_html_contains_trend_down_arrow(self, digest):
        data = _make_digest_data(trend="down")
        html = digest.format_html(data)
        assert "&darr;" in html

    def test_html_service_rows_present(self, digest):
        data = _make_digest_data(
            by_service={"openai": 1.0, "supabase": 0.50},
            total_cost_usd=1.50,
        )
        html = digest.format_html(data)
        assert "openai" in html
        assert "supabase" in html
        assert "66.7%" in html  # openai: 1.0/1.5

    def test_html_empty_services_shows_no_data(self, digest):
        data = _make_digest_data(by_service={}, total_cost_usd=0.0)
        html = digest.format_html(data)
        assert "No data" in html

    def test_html_monthly_progress_bar_capped_at_100(self, digest):
        data = _make_digest_data(monthly_total_usd=75.0, monthly_budget=50.0)
        html = digest.format_html(data)
        assert "width: 100.0%;" in html

    def test_html_daily_percentage_computed(self, digest):
        data = _make_digest_data(total_cost_usd=2.0, daily_budget=5.0)
        html = digest.format_html(data)
        assert "40.0% of budget" in html

    def test_html_contains_dashboard_link(self, digest):
        data = _make_digest_data()
        html = digest.format_html(data)
        assert "https://civic-api.fly.dev/admin/cost-status" in html


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------


class TestSendEmail:
    def test_returns_false_when_no_recipients(self, digest):
        digest.alert_emails = []
        digest.smtp_username = "user@test.com"
        digest.smtp_password = "pass"
        assert digest.send_email(_make_digest_data()) is False

    def test_returns_false_when_no_smtp_username(self, digest):
        digest.alert_emails = ["recipient@test.com"]
        digest.smtp_username = ""
        digest.smtp_password = "pass"
        assert digest.send_email(_make_digest_data()) is False

    def test_returns_false_when_no_smtp_password(self, digest):
        digest.alert_emails = ["recipient@test.com"]
        digest.smtp_username = "user@test.com"
        digest.smtp_password = ""
        assert digest.send_email(_make_digest_data()) is False

    @patch("civicos_services.monitoring.daily_cost_digest.smtplib.SMTP")
    def test_sends_email_when_configured(self, mock_smtp_cls, digest):
        digest.alert_emails = ["alice@test.com"]
        digest.smtp_username = "sender@test.com"
        digest.smtp_password = "secret"

        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        data = _make_digest_data(budget_status="warning", total_cost_usd=3.50, date="2026-04-10")
        result = digest.send_email(data)

        assert result is True
        sent_msg = mock_server.send_message.call_args[0][0]
        assert "Warning" in sent_msg["Subject"]
        assert "$3.5000" in sent_msg["Subject"]
        assert sent_msg["From"] == "sender@test.com"
        assert "alice@test.com" in sent_msg["To"]

    @patch("civicos_services.monitoring.daily_cost_digest.smtplib.SMTP")
    def test_subject_includes_critical_label(self, mock_smtp_cls, digest):
        digest.alert_emails = ["a@b.com"]
        digest.smtp_username = "u"
        digest.smtp_password = "p"
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        digest.send_email(_make_digest_data(budget_status="critical"))
        sent_msg = mock_server.send_message.call_args[0][0]
        assert "CRITICAL" in sent_msg["Subject"]

    @patch("civicos_services.monitoring.daily_cost_digest.smtplib.SMTP")
    def test_subject_no_suffix_for_healthy(self, mock_smtp_cls, digest):
        digest.alert_emails = ["a@b.com"]
        digest.smtp_username = "u"
        digest.smtp_password = "p"
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        digest.send_email(_make_digest_data(budget_status="healthy"))
        sent_msg = mock_server.send_message.call_args[0][0]
        assert "Warning" not in sent_msg["Subject"]
        assert "CRITICAL" not in sent_msg["Subject"]

    @patch("civicos_services.monitoring.daily_cost_digest.smtplib.SMTP")
    def test_returns_false_on_smtp_error(self, mock_smtp_cls, digest):
        digest.alert_emails = ["a@b.com"]
        digest.smtp_username = "u"
        digest.smtp_password = "p"
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")
        assert digest.send_email(_make_digest_data()) is False


# ---------------------------------------------------------------------------
# Push notification sending
# ---------------------------------------------------------------------------


class TestSendPush:
    @patch("civicos_services.monitoring.notify.send_notification")
    def test_healthy_uses_default_priority(self, mock_notify, digest):
        from civicos_services.monitoring.notify import Priority
        mock_notify.return_value = True

        result = digest.send_push(_make_digest_data(budget_status="healthy"))

        assert result is True
        assert mock_notify.call_args[1]["priority"] == Priority.DEFAULT

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_warning_uses_high_priority(self, mock_notify, digest):
        from civicos_services.monitoring.notify import Priority
        mock_notify.return_value = True

        digest.send_push(_make_digest_data(budget_status="warning"))
        assert mock_notify.call_args[1]["priority"] == Priority.HIGH

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_critical_uses_urgent_priority(self, mock_notify, digest):
        from civicos_services.monitoring.notify import Priority
        mock_notify.return_value = True

        digest.send_push(_make_digest_data(budget_status="critical"))
        assert mock_notify.call_args[1]["priority"] == Priority.URGENT

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_body_contains_cost_summary(self, mock_notify, digest):
        mock_notify.return_value = True
        data = _make_digest_data(
            total_cost_usd=2.50, daily_budget=5.0,
            yesterday_cost_usd=2.00, weekly_avg_usd=1.80,
            record_count=55, monthly_total_usd=18.0, monthly_budget=50.0,
        )
        digest.send_push(data)

        body = mock_notify.call_args[1]["body"]
        assert "$2.5000" in body
        assert "$2.0000" in body
        assert "$1.8000" in body
        assert "Operations: 55" in body
        assert "$18.0000" in body

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_title_includes_status(self, mock_notify, digest):
        mock_notify.return_value = True
        digest.send_push(_make_digest_data(budget_status="critical", date="2026-04-10", total_cost_usd=6.0))

        title = mock_notify.call_args[1]["title"]
        assert "CRITICAL" in title
        assert "$6.0000" in title

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_tags_for_warning(self, mock_notify, digest):
        mock_notify.return_value = True
        digest.send_push(_make_digest_data(budget_status="warning"))

        tags = mock_notify.call_args[1]["tags"]
        assert "warning" in tags
        assert "cost" in tags

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_limits_services_to_top_3(self, mock_notify, digest):
        mock_notify.return_value = True
        digest.send_push(_make_digest_data(by_service={"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}))

        body = mock_notify.call_args[1]["body"]
        assert "a:" in body
        assert "b:" in body
        assert "c:" in body
        assert "d:" not in body

    @patch("civicos_services.monitoring.notify.send_notification")
    def test_push_click_url(self, mock_notify, digest):
        mock_notify.return_value = True
        digest.send_push(_make_digest_data())
        assert mock_notify.call_args[1]["click_url"] == "https://civic-api.fly.dev/admin/cost-status"


# ---------------------------------------------------------------------------
# Send orchestration
# ---------------------------------------------------------------------------


class TestSend:
    def test_disabled_returns_early(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_COST_DIGEST_ENABLED": "false", "CIVICOS_ALERT_EMAILS": ""},
            clear=False,
        ):
            d = DailyCostDigest(daily_budget=5.0, monthly_budget=50.0)

        result = d.send()
        assert result["success"] is False
        assert result["reason"] == "disabled"
        assert result["channels"] == []

    def test_data_collection_failure_returns_error(self, digest):
        with patch.object(digest, "collect_data", side_effect=RuntimeError("DB down")):
            result = digest.send()

        assert result["success"] is False
        assert "data_collection_failed" in result["reason"]
        assert "DB down" in result["reason"]
        assert result["channels"] == []

    def test_no_channels_returns_success_false(self, digest):
        mock_data = _make_digest_data()
        with patch.object(digest, "collect_data", return_value=mock_data):
            with patch.object(digest, "send_email", return_value=False):
                with patch.object(digest, "send_push", return_value=False):
                    result = digest.send()

        assert result["success"] is False
        assert result["channels"] == []
        assert result["data"]["total_cost_usd"] == 1.50

    def test_email_only_channel(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data()):
            with patch.object(digest, "send_email", return_value=True):
                with patch.object(digest, "send_push", return_value=False):
                    result = digest.send()

        assert result["success"] is True
        assert result["channels"] == ["email"]

    def test_push_only_channel(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data()):
            with patch.object(digest, "send_email", return_value=False):
                with patch.object(digest, "send_push", return_value=True):
                    result = digest.send()

        assert result["success"] is True
        assert result["channels"] == ["push"]

    def test_both_channels_sent(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data()):
            with patch.object(digest, "send_email", return_value=True):
                with patch.object(digest, "send_push", return_value=True):
                    result = digest.send()

        assert result["success"] is True
        assert "email" in result["channels"]
        assert "push" in result["channels"]
        assert len(result["channels"]) == 2

    def test_send_result_contains_data(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data(total_cost_usd=3.25, budget_status="warning")):
            with patch.object(digest, "send_email", return_value=False):
                with patch.object(digest, "send_push", return_value=True):
                    result = digest.send()

        assert result["data"]["total_cost_usd"] == 3.25
        assert result["data"]["budget_status"] == "warning"


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_returns_all_sections(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data(total_cost_usd=1.50)):
            preview = digest.preview()

        assert preview["data"]["total_cost_usd"] == 1.50
        assert "$1.5000" in preview["plaintext"]
        assert "$1.5000" in preview["html"]

    def test_preview_data_matches_collect(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data(total_cost_usd=4.20, date="2026-04-10")):
            preview = digest.preview()

        assert preview["data"]["total_cost_usd"] == 4.20
        assert preview["data"]["date"] == "2026-04-10"

    def test_preview_plaintext_contains_cost(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data(total_cost_usd=2.75)):
            preview = digest.preview()

        assert "$2.7500" in preview["plaintext"]

    def test_preview_html_contains_cost(self, digest):
        with patch.object(digest, "collect_data", return_value=_make_digest_data(total_cost_usd=2.75)):
            preview = digest.preview()

        assert "$2.7500" in preview["html"]


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


class TestSendDailyDigest:
    def test_disabled_digest_returns_immediately(self):
        with patch.dict(
            "os.environ",
            {"CIVICOS_ALERT_EMAILS": "", "CIVICOS_COST_DIGEST_ENABLED": "false"},
            clear=False,
        ):
            result = send_daily_digest(jurisdiction_id="city-test")

        assert result["success"] is False
        assert result["reason"] == "disabled"

    def test_default_jurisdiction_is_san_rafael(self):
        with patch(
            "civicos_services.monitoring.daily_cost_digest.DailyCostDigest"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.send.return_value = {"success": False, "reason": "disabled", "channels": []}
            mock_cls.return_value = mock_instance

            result = send_daily_digest()

            # Verifies the correct jurisdiction was passed
            call_args = mock_cls.call_args
            assert call_args[1]["jurisdiction_id"] == "city-san-rafael"
            # And the result is forwarded from send()
            assert result["success"] is False


# ---------------------------------------------------------------------------
# CostDigestData dataclass
# ---------------------------------------------------------------------------


class TestCostDigestData:
    def test_asdict_round_trip(self):
        data = _make_digest_data(total_cost_usd=3.14, budget_status="warning")
        d = asdict(data)
        assert d["total_cost_usd"] == 3.14
        assert d["budget_status"] == "warning"
        assert d["by_service"] == {"openai": 1.0, "supabase": 0.50}

    def test_all_fields_present(self):
        data = _make_digest_data()
        d = asdict(data)
        expected_keys = {
            "date", "total_cost_usd", "by_service", "by_category",
            "record_count", "yesterday_cost_usd", "weekly_avg_usd",
            "daily_budget", "monthly_budget", "monthly_total_usd",
            "budget_status", "trend", "trend_percent",
        }
        assert set(d.keys()) == expected_keys

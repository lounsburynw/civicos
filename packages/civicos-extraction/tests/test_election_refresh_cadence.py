"""Tests for calendar-aware election refresh cadence.

The scheduled_election_refresh() function uses determine_refresh_cadence() and
should_run_today() to vary its behavior based on proximity to known election dates.
The GH Actions cron fires daily; the function itself decides what to run.

Since the helpers live in modal_ingest.py (which requires the modal package),
we replicate the logic here for testing — same pattern as test_ballot_preview_scheduling.py.

Cadence levels:
- daily  (≤7 days to election): all sources fire every run
- weekly (8–90 days): officials/ballot/deadlines on Mondays + 1st
- monthly (>90 days or no date): all sources on 1st of month only
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


# --- Replicated logic from scripts/modal_ingest.py ---

def determine_refresh_cadence(
    election_sources: dict,
    daily_threshold: int = 7,
    weekly_threshold: int = 90,
    today: date | None = None,
) -> tuple:
    """Replicate cadence logic from scheduled_election_refresh()."""
    if today is None:
        today = date.today()
    nearest_days = None
    nearest_date_str = None

    for _source_name, source_config in election_sources.items():
        if not isinstance(source_config, dict):
            continue
        election_date_str = source_config.get("election_date")
        if not election_date_str:
            continue
        try:
            election_date = date.fromisoformat(election_date_str)
            days_until = (election_date - today).days
            if days_until >= 0 and (nearest_days is None or days_until < nearest_days):
                nearest_days = days_until
                nearest_date_str = election_date_str
        except ValueError:
            continue

    if nearest_days is not None and nearest_days <= daily_threshold:
        return ("daily", nearest_days, nearest_date_str)
    elif nearest_days is not None and nearest_days <= weekly_threshold:
        return ("weekly", nearest_days, nearest_date_str)
    else:
        return ("monthly", nearest_days, nearest_date_str)


def should_run_today(cadence: str, today: date | None = None) -> bool:
    """Replicate should-run-today logic from scheduled_election_refresh().

    Accepts optional today param for testability (production uses date.today()).
    """
    if today is None:
        today = date.today()
    if cadence == "daily":
        return True
    elif cadence == "weekly":
        return today.weekday() == 0 or today.day == 1
    else:
        return today.day == 1


def _make_config(election_date_str: str | None = None, **extra) -> dict:
    """Build a minimal election_sources config for testing."""
    config = {}
    if election_date_str is not None:
        config["ca_sos_ballot_preview"] = {
            "election_slug": "test",
            "election_date": election_date_str,
            **extra,
        }
    return config


# --- Tests ---

class TestDetermineRefreshCadence:
    """Test cadence determination from election_date proximity."""

    def test_daily_cadence_election_tomorrow(self):
        """≤7 days → daily."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        cadence, days, nearest = determine_refresh_cadence(_make_config(tomorrow))
        assert cadence == "daily"
        assert days == 1
        assert nearest == tomorrow

    def test_daily_cadence_election_today(self):
        """Election day itself → daily."""
        today_str = date.today().isoformat()
        cadence, days, nearest = determine_refresh_cadence(_make_config(today_str))
        assert cadence == "daily"
        assert days == 0

    def test_daily_cadence_boundary_7_days(self):
        """Exactly 7 days → daily."""
        d = (date.today() + timedelta(days=7)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "daily"
        assert days == 7

    def test_weekly_cadence_boundary_8_days(self):
        """8 days → weekly (just past daily threshold)."""
        d = (date.today() + timedelta(days=8)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "weekly"
        assert days == 8

    def test_weekly_cadence_60_days(self):
        """60 days → weekly."""
        d = (date.today() + timedelta(days=60)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "weekly"
        assert days == 60

    def test_weekly_cadence_boundary_90_days(self):
        """Exactly 90 days → weekly."""
        d = (date.today() + timedelta(days=90)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "weekly"
        assert days == 90

    def test_monthly_cadence_boundary_91_days(self):
        """91 days → monthly (just past weekly threshold)."""
        d = (date.today() + timedelta(days=91)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "monthly"
        assert days == 91

    def test_monthly_cadence_far_future(self):
        """200 days → monthly."""
        d = (date.today() + timedelta(days=200)).isoformat()
        cadence, days, _ = determine_refresh_cadence(_make_config(d))
        assert cadence == "monthly"
        assert days == 200

    def test_monthly_cadence_no_dates(self):
        """No election_date fields → monthly with None."""
        cadence, days, nearest = determine_refresh_cadence({"ca_sos_results": {"county": "marin"}})
        assert cadence == "monthly"
        assert days is None
        assert nearest is None

    def test_monthly_cadence_empty_config(self):
        """Empty election_sources → monthly."""
        cadence, days, nearest = determine_refresh_cadence({})
        assert cadence == "monthly"
        assert days is None

    def test_past_elections_ignored(self):
        """Past election dates are not considered."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cadence, days, nearest = determine_refresh_cadence(_make_config(yesterday))
        assert cadence == "monthly"
        assert days is None

    def test_invalid_date_ignored(self):
        """Invalid date strings are skipped gracefully."""
        cadence, days, nearest = determine_refresh_cadence(_make_config("not-a-date"))
        assert cadence == "monthly"
        assert days is None

    def test_nearest_of_multiple_sources(self):
        """When multiple sources have dates, nearest wins."""
        near = (date.today() + timedelta(days=5)).isoformat()
        far = (date.today() + timedelta(days=60)).isoformat()
        config = {
            "ca_sos_ballot_preview": {"election_date": far},
            "some_other_source": {"election_date": near},
        }
        cadence, days, nearest = determine_refresh_cadence(config)
        assert cadence == "daily"
        assert days == 5
        assert nearest == near

    def test_boolean_config_skipped(self):
        """Source config that is True (not a dict) is skipped."""
        cadence, _, _ = determine_refresh_cadence({"ca_sos_results": True})
        assert cadence == "monthly"

    def test_real_2026_primary(self):
        """Real config: 2026-06-02 primary, tested from a fixed reference date."""
        cadence, days, nearest = determine_refresh_cadence(
            _make_config("2026-06-02"), today=date(2026, 3, 31),
        )
        # 63 days away from 2026-03-31 → weekly
        assert cadence == "weekly"
        assert days == 63
        assert nearest == "2026-06-02"


class TestShouldRunToday:
    """Test the should_run_today() day-of-week/month gating."""

    def test_daily_always_runs(self):
        """Daily cadence always returns True, any day."""
        for day_offset in range(31):
            d = date(2026, 3, 1) + timedelta(days=day_offset)
            assert should_run_today("daily", today=d) is True

    def test_weekly_runs_on_mondays(self):
        """Weekly cadence runs on Mondays."""
        # 2026-03-02 is a Monday
        assert should_run_today("weekly", today=date(2026, 3, 2)) is True
        assert should_run_today("weekly", today=date(2026, 3, 9)) is True
        assert should_run_today("weekly", today=date(2026, 3, 16)) is True

    def test_weekly_skips_non_monday_non_first(self):
        """Weekly cadence skips non-Monday, non-1st days."""
        # 2026-03-03 is Tuesday, not 1st
        assert should_run_today("weekly", today=date(2026, 3, 3)) is False
        # 2026-03-04 is Wednesday
        assert should_run_today("weekly", today=date(2026, 3, 4)) is False
        # 2026-03-15 is Sunday
        assert should_run_today("weekly", today=date(2026, 3, 15)) is False

    def test_weekly_runs_on_first_of_month(self):
        """Weekly cadence also runs on 1st of month (for historical sources)."""
        # 2026-04-01 is a Wednesday — not Monday but is 1st
        assert should_run_today("weekly", today=date(2026, 4, 1)) is True
        # 2026-05-01 is a Friday
        assert should_run_today("weekly", today=date(2026, 5, 1)) is True

    def test_monthly_runs_on_first(self):
        """Monthly cadence runs on 1st of month."""
        assert should_run_today("monthly", today=date(2026, 3, 1)) is True
        assert should_run_today("monthly", today=date(2026, 4, 1)) is True

    def test_monthly_skips_non_first(self):
        """Monthly cadence skips all other days."""
        for day in range(2, 29):
            assert should_run_today("monthly", today=date(2026, 3, day)) is False


class TestPerSourceGating:
    """Test per-source gating logic.

    Sources have different gating to minimize redundant writes:
    - Civera: pure historical data — monthly only (1st of month)
    - CA SOS Results: election-night data — daily near election, monthly otherwise
    - Officials, ballot preview, deadlines: always run when jurisdiction runs
    """

    @staticmethod
    def _run_civera(day_of_month: int) -> bool:
        """Civera only runs on 1st of month (historical, never changes near election)."""
        return day_of_month == 1

    @staticmethod
    def _run_sos_results(cadence: str, day_of_month: int) -> bool:
        """CA SOS Results runs daily near election, monthly otherwise."""
        return (cadence == "daily") or (day_of_month == 1)

    # --- Civera gating ---

    def test_civera_runs_on_first(self):
        """Civera runs on 1st of month regardless of cadence."""
        assert self._run_civera(1) is True

    def test_civera_skips_non_first(self):
        """Civera skips all non-1st days, even during daily cadence."""
        for day in range(2, 29):
            assert self._run_civera(day) is False

    # --- CA SOS Results gating ---

    def test_sos_results_daily_cadence_always_runs(self):
        """Daily cadence → SOS results runs every day (election-night data)."""
        for day in range(1, 29):
            assert self._run_sos_results("daily", day) is True

    def test_sos_results_weekly_cadence_first_only(self):
        """Weekly cadence → SOS results only on 1st."""
        assert self._run_sos_results("weekly", 1) is True
        for day in range(2, 29):
            assert self._run_sos_results("weekly", day) is False

    def test_sos_results_monthly_cadence_first_only(self):
        """Monthly cadence → SOS results only on 1st."""
        assert self._run_sos_results("monthly", 1) is True
        assert self._run_sos_results("monthly", 15) is False


class TestCustomThresholds:
    """Test that cadence thresholds are configurable."""

    def test_custom_daily_threshold(self):
        """Custom daily threshold of 3 days."""
        d = (date.today() + timedelta(days=5)).isoformat()
        # Default (7): should be daily
        cadence_default, _, _ = determine_refresh_cadence(_make_config(d))
        assert cadence_default == "daily"
        # Custom (3): should be weekly
        cadence_custom, _, _ = determine_refresh_cadence(
            _make_config(d), daily_threshold=3,
        )
        assert cadence_custom == "weekly"

    def test_custom_weekly_threshold(self):
        """Custom weekly threshold of 60 days."""
        d = (date.today() + timedelta(days=75)).isoformat()
        # Default (90): should be weekly
        cadence_default, _, _ = determine_refresh_cadence(_make_config(d))
        assert cadence_default == "weekly"
        # Custom (60): should be monthly
        cadence_custom, _, _ = determine_refresh_cadence(
            _make_config(d), weekly_threshold=60,
        )
        assert cadence_custom == "monthly"

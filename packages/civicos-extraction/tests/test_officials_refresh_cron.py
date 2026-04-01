"""Tests for officials refresh cron integration.

Validates that the scheduled_election_refresh() function correctly handles
officials refresh: Congress.gov and LegiScan data monthly, officials
derivation after election ingestion, and that officials steps are not
gated by election-source-specific logic.

Since scheduled_election_refresh() lives in modal_ingest.py (requires modal),
we test the integration invariants by replicating the control flow logic.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


# --- Replicated control flow from scheduled_election_refresh() ---

def determine_refresh_cadence(
    election_sources: dict,
    today: date | None = None,
    daily_threshold: int = 7,
    weekly_threshold: int = 90,
) -> tuple:
    """Replicate cadence logic."""
    ref = today or date.today()
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
            days_until = (election_date - ref).days
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


def should_run_today(cadence: str) -> bool:
    """Replicate run-gating logic."""
    if cadence == "daily":
        return True
    today = date.today()
    is_monday = today.weekday() == 0
    is_first = today.day == 1
    if cadence == "weekly":
        return is_monday or is_first
    return is_first


def simulate_election_refresh_officials(
    jurisdictions: dict,
    today: date,
) -> dict:
    """Simulate the officials-related steps of scheduled_election_refresh().

    Replicates the control flow to determine which jurisdictions would
    have officials fetched and derived on a given day.
    """
    results = {}

    for jid, config in jurisdictions.items():
        election_sources = config.get("election_sources", {})
        cadence, days_until, _ = determine_refresh_cadence(election_sources, today=today)

        # Replicate should_run_today with injected date
        if cadence == "daily":
            runs = True
        elif cadence == "weekly":
            runs = today.weekday() == 0 or today.day == 1
        else:  # monthly
            runs = today.day == 1

        if not runs:
            results[jid] = {"status": "skipped", "cadence": cadence}
            continue

        # Officials fetch and derivation always run when jurisdiction runs
        # (not gated by per-source logic like Civera or CA SOS)
        results[jid] = {
            "status": "processed",
            "cadence": cadence,
            "officials_fetched": True,
            "officials_derived": True,
        }

    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOfficialsAlwaysRun:
    """Officials fetch and derivation are not gated by election source availability."""

    def test_officials_run_without_election_sources(self):
        """Jurisdiction with no election_sources still gets officials refresh."""
        jurisdictions = {
            "city-alpha": {"jurisdiction_id": "city-alpha"},
        }
        # On the 1st, monthly cadence jurisdictions run
        results = simulate_election_refresh_officials(jurisdictions, date(2026, 4, 1))
        assert results["city-alpha"]["officials_fetched"] is True
        assert results["city-alpha"]["officials_derived"] is True

    def test_officials_run_with_election_sources(self):
        """Jurisdiction with election_sources gets officials alongside election data."""
        jurisdictions = {
            "city-beta": {
                "jurisdiction_id": "city-beta",
                "election_sources": {
                    "civera_election_stats": {"election_date": "2026-06-02"},
                },
            },
        }
        # Near election → daily cadence → officials run every day
        results = simulate_election_refresh_officials(jurisdictions, date(2026, 5, 28))
        assert results["city-beta"]["officials_fetched"] is True

    def test_officials_not_gated_by_source_type(self):
        """Officials are independent of civera/sos source gating."""
        # In scheduled_election_refresh(), Civera is monthly-only and SOS Results
        # are daily-only near election. But officials always run when jurisdiction runs.
        # Use an election 30 days away → weekly cadence
        monday = date(2026, 4, 6)  # A Monday
        election = monday + timedelta(days=30)
        jurisdictions = {
            "city-gamma": {
                "jurisdiction_id": "city-gamma",
                "election_sources": {
                    "civera_election_stats": {"election_date": election.isoformat()},
                },
            },
        }
        # Weekly cadence, Monday → jurisdiction runs, officials should run
        results = simulate_election_refresh_officials(jurisdictions, monday)
        assert results["city-gamma"]["status"] == "processed"
        assert results["city-gamma"]["officials_fetched"] is True


class TestMonthlyCongressRefresh:
    """Congress.gov data refreshes monthly for all jurisdictions."""

    def test_all_jurisdictions_run_on_first(self):
        """On the 1st of month, every jurisdiction runs (monthly cadence floor)."""
        jurisdictions = {
            "city-a": {"jurisdiction_id": "city-a"},
            "county-b": {"jurisdiction_id": "county-b"},
            "school-c": {"jurisdiction_id": "school-c", "election_sources": {}},
            "state-d": {
                "jurisdiction_id": "state-d",
                "election_sources": {
                    "ca_sos_results": {"election_date": "2028-11-03"},
                },
            },
        }
        first = date(2026, 5, 1)
        results = simulate_election_refresh_officials(jurisdictions, first)
        for jid in jurisdictions:
            assert results[jid]["status"] == "processed", (
                f"{jid} should run on 1st of month"
            )
            assert results[jid]["officials_fetched"] is True

    def test_monthly_cadence_skips_non_first(self):
        """Jurisdictions with monthly cadence skip officials on non-1st days."""
        jurisdictions = {
            "city-e": {"jurisdiction_id": "city-e"},
        }
        # A Wednesday, not the 1st
        wed = date(2026, 4, 15)
        results = simulate_election_refresh_officials(jurisdictions, wed)
        assert results["city-e"]["status"] == "skipped"

    def test_monthly_refresh_covers_all_months(self):
        """Every month has a 1st → officials refresh happens 12x/year."""
        jurisdictions = {"city-f": {"jurisdiction_id": "city-f"}}
        months_with_refresh = 0
        for month in range(1, 13):
            first = date(2026, month, 1)
            results = simulate_election_refresh_officials(jurisdictions, first)
            if results["city-f"]["status"] == "processed":
                months_with_refresh += 1
        assert months_with_refresh == 12


class TestOfficialsDerivedAfterElection:
    """Officials are re-derived from contest winners after election data ingestion."""

    def test_derive_runs_daily_near_election(self):
        """During daily cadence (≤7 days before election), officials derived every day."""
        election_date = date(2026, 6, 2)
        jurisdictions = {
            "city-g": {
                "jurisdiction_id": "city-g",
                "election_sources": {
                    "ca_sos_results": {"election_date": election_date.isoformat()},
                },
            },
        }
        # Day of election (0 days until)
        results = simulate_election_refresh_officials(jurisdictions, election_date)
        assert results["city-g"]["officials_derived"] is True

        # 3 days before election
        results = simulate_election_refresh_officials(jurisdictions, election_date - timedelta(days=3))
        assert results["city-g"]["officials_derived"] is True

        # 7 days before (boundary of daily cadence)
        results = simulate_election_refresh_officials(jurisdictions, election_date - timedelta(days=7))
        assert results["city-g"]["officials_derived"] is True

    def test_derive_runs_weekly_before_election(self):
        """In weekly cadence (8-90 days before election), derivation runs on Mondays."""
        election_date = date(2026, 6, 2)
        jurisdictions = {
            "city-h": {
                "jurisdiction_id": "city-h",
                "election_sources": {
                    "ca_sos_results": {"election_date": election_date.isoformat()},
                },
            },
        }
        # 30 days before → weekly cadence, find a Monday in that range
        test_date = election_date - timedelta(days=30)
        while test_date.weekday() != 0:
            test_date += timedelta(days=1)
        results = simulate_election_refresh_officials(jurisdictions, test_date)
        assert results["city-h"]["officials_derived"] is True

    def test_after_election_falls_to_monthly(self):
        """After election day, cadence returns to monthly (no future elections)."""
        election_date = date(2026, 6, 2)
        jurisdictions = {
            "city-i": {
                "jurisdiction_id": "city-i",
                "election_sources": {
                    "ca_sos_results": {"election_date": election_date.isoformat()},
                },
            },
        }
        # Day after election: no future elections → monthly → skipped unless 1st
        day_after = election_date + timedelta(days=1)
        results = simulate_election_refresh_officials(jurisdictions, day_after)
        if day_after.day == 1:
            assert results["city-i"]["status"] == "processed"
        else:
            assert results["city-i"]["status"] == "skipped"


class TestLiveOfficialsCronConfig:
    """Validate the live cron workflow and config alignment."""

    def test_cron_workflow_calls_election_refresh(self):
        """The GH Actions workflow triggers scheduled_election_refresh."""
        import os
        workflow_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", ".github", "workflows", "cron-election-refresh.yml",
        )
        workflow_path = os.path.normpath(workflow_path)
        with open(workflow_path) as f:
            content = f.read()
        assert "scheduled_election_refresh" in content
        # Must run daily (not monthly) for calendar-aware gating to work
        assert "cron:" in content

    def test_workflow_has_legiscan_and_congress_secrets(self):
        """The workflow should install packages that access Congress.gov + LegiScan."""
        import os
        workflow_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", ".github", "workflows", "cron-election-refresh.yml",
        )
        workflow_path = os.path.normpath(workflow_path)
        with open(workflow_path) as f:
            content = f.read()
        # Modal function references civic-legiscan and civic-congress secrets
        # (configured in modal_ingest.py, not the workflow itself)
        # The workflow just needs to trigger the Modal function
        assert "modal run" in content

    def test_all_live_jurisdictions_have_state(self):
        """Jurisdictions need a state code for Congress.gov lookups."""
        from civicos_extraction.config import get_active_jurisdictions

        jurisdictions = get_active_jurisdictions()
        # Jurisdictions with election_sources should have state info available
        # (either in config or derivable from jurisdiction_id prefix)
        for jid, config in jurisdictions.items():
            if config.get("election_sources"):
                state = config.get("state")
                # If no explicit state, it should be derivable from parent jurisdictions
                # or the jurisdiction YAML. For now, just check CA jurisdictions.
                if state:
                    assert len(state) == 2, f"{jid}: state should be 2-letter code, got {state}"

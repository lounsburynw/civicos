"""Tests for ballot preview smart scheduling — date-based window guard.

The guard in scheduled_election_refresh() skips ca_sos_ballot_preview fetch
unless today is within 90 days before election_date. Past elections are skipped too.

Since the guard logic lives inline in modal_ingest.py, we extract and test
the same date math independently.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest


def ballot_preview_skip_reason(
    election_date_str: str | None, window_days: int = 90
) -> str | None:
    """Replicate the skip logic from scheduled_election_refresh().

    Returns None if fetch should proceed, or a reason string if it should be skipped.
    """
    if not election_date_str:
        return "no election_date configured"
    try:
        election_date = date.fromisoformat(election_date_str)
        days_until = (election_date - date.today()).days
        if days_until < 0:
            return f"already passed ({-days_until} days ago)"
        elif days_until > window_days:
            return f"too early ({days_until} days away)"
    except ValueError:
        return f"invalid date: {election_date_str!r}"
    return None


class TestBallotPreviewWindow:
    """Test the 90-day pre-election window guard."""

    def test_within_window_proceeds(self):
        """Election 60 days away — should fetch."""
        future = (date.today() + timedelta(days=60)).isoformat()
        assert ballot_preview_skip_reason(future) is None

    def test_election_tomorrow_proceeds(self):
        """Election tomorrow — should fetch."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert ballot_preview_skip_reason(tomorrow) is None

    def test_election_today_proceeds(self):
        """Election day — should fetch (days_until=0, not < 0)."""
        today = date.today().isoformat()
        assert ballot_preview_skip_reason(today) is None

    def test_boundary_90_days_proceeds(self):
        """Exactly 90 days away — should fetch (not > 90)."""
        boundary = (date.today() + timedelta(days=90)).isoformat()
        assert ballot_preview_skip_reason(boundary) is None

    def test_boundary_91_days_skipped(self):
        """91 days away — too early, should skip."""
        boundary = (date.today() + timedelta(days=91)).isoformat()
        reason = ballot_preview_skip_reason(boundary)
        assert reason is not None
        assert "too early" in reason

    def test_far_future_skipped(self):
        """Election 200 days away — should skip."""
        far = (date.today() + timedelta(days=200)).isoformat()
        reason = ballot_preview_skip_reason(far)
        assert reason is not None
        assert "too early" in reason

    def test_past_election_skipped(self):
        """Election was yesterday — should skip."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        reason = ballot_preview_skip_reason(yesterday)
        assert reason is not None
        assert "passed" in reason

    def test_long_past_election_skipped(self):
        """Election was 6 months ago — should skip."""
        past = (date.today() - timedelta(days=180)).isoformat()
        reason = ballot_preview_skip_reason(past)
        assert reason is not None
        assert "passed" in reason

    def test_no_election_date_skipped(self):
        """No election_date configured — should skip."""
        reason = ballot_preview_skip_reason(None)
        assert reason is not None
        assert "no election_date" in reason

    def test_empty_election_date_skipped(self):
        """Empty string election_date — should skip."""
        reason = ballot_preview_skip_reason("")
        assert reason is not None
        assert "no election_date" in reason

    def test_invalid_date_format_skipped(self):
        """Malformed date — should skip."""
        reason = ballot_preview_skip_reason("not-a-date")
        assert reason is not None
        assert "invalid date" in reason

    def test_real_2026_primary(self):
        """Real config: 2026-06-02 primary. Should proceed today (2026-03-31 = 63 days)."""
        reason = ballot_preview_skip_reason("2026-06-02")
        # 63 days away — within window
        assert reason is None


class TestCustomWindowDays:
    """Test configurable window_days parameter."""

    def test_custom_window_30_days(self):
        """30-day window — 60 days away should skip."""
        future = (date.today() + timedelta(days=60)).isoformat()
        reason = ballot_preview_skip_reason(future, window_days=30)
        assert reason is not None
        assert "too early" in reason

    def test_custom_window_30_within(self):
        """30-day window — 20 days away should proceed."""
        future = (date.today() + timedelta(days=20)).isoformat()
        assert ballot_preview_skip_reason(future, window_days=30) is None

    def test_custom_window_120_days(self):
        """120-day window — 100 days away should proceed."""
        future = (date.today() + timedelta(days=100)).isoformat()
        assert ballot_preview_skip_reason(future, window_days=120) is None

    def test_custom_window_boundary(self):
        """Custom window boundary — exactly at window proceeds, window+1 skips."""
        at_boundary = (date.today() + timedelta(days=45)).isoformat()
        past_boundary = (date.today() + timedelta(days=46)).isoformat()
        assert ballot_preview_skip_reason(at_boundary, window_days=45) is None
        past_reason = ballot_preview_skip_reason(past_boundary, window_days=45)
        assert past_reason is not None
        assert "too early" in past_reason
        assert "46 days away" in past_reason

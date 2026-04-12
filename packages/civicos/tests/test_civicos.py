"""
Tests for the main CivicOS class.

Tests the unified API entry point.
"""

import pytest

# Mark all tests in this module as fast (smoke tests, <30s total)
pytestmark = pytest.mark.fast
from civicos import CivicOS
from civicos.civicos import (
    RegulatoryStack,
    Decision,
    DecisionWithContext,
    Meeting,
    UpcomingElection,
    BudgetItem,
    BudgetSummary,
)


class TestCivicInstantiation:
    """Test CivicOS class instantiation."""

    def test_create_civic_instance(self):
        """Can create a CivicOS instance with jurisdiction."""
        c = CivicOS("san-rafael-ca")
        # Jurisdiction is normalized to canonical format
        assert c.jurisdiction == "city-san-rafael"

    def test_civic_has_storage_backend(self):
        """CivicOS instance has a recognized storage backend."""
        c = CivicOS("san-rafael-ca")
        backend_type = type(c.storage).__name__
        assert backend_type in ("PostgresBackend", "SQLiteBackend")

    def test_civic_custom_db_path(self):
        """Can specify custom database path."""
        c = CivicOS("san-rafael-ca", db_path="/tmp/test_civicos.db")
        assert c.db_path == "/tmp/test_civicos.db"


class TestQueryMethods:
    """Test query methods (learn)."""

    def test_what_applies_returns_regulatory_stack(self):
        """what_applies() returns RegulatoryStack."""
        c = CivicOS("san-rafael-ca")
        result = c.what_applies("housing")
        assert isinstance(result, RegulatoryStack)
        assert result.topic == "housing"
        # Jurisdiction is normalized to canonical format
        assert result.jurisdiction == "city-san-rafael"

    def test_what_happened_returns_decisions(self):
        """what_happened() returns list of Decision objects with required fields."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened("bike lanes")
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, Decision)
            assert item.title  # Non-empty
            assert item.outcome  # Non-empty

    def test_whats_next_returns_meetings(self):
        """whats_next() returns list of Meeting objects with required fields."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, Meeting)
            assert item.id
            assert item.title

    def test_whats_next_with_topics(self):
        """whats_next() topic filter returns subset of all meetings."""
        c = CivicOS("san-rafael-ca")
        all_meetings = c.whats_next()
        filtered = c.whats_next(topics=["transportation"])
        assert isinstance(filtered, list)
        assert len(filtered) <= len(all_meetings)
        for item in filtered:
            assert isinstance(item, Meeting)

    def test_whats_next_with_elections(self):
        """whats_next(include_elections=True) includes elections."""
        c = CivicOS("san-rafael-ca")
        # Get results with elections
        result = c.whats_next(include_elections=True, days=365)
        assert isinstance(result, list)
        # Results can contain both Meeting and UpcomingElection objects
        for item in result:
            assert isinstance(item, (Meeting, UpcomingElection))

    def test_whats_next_election_structure(self):
        """UpcomingElection objects have correctly typed, non-empty fields."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]
        for election in elections:
            assert isinstance(election.id, str) and election.id
            assert isinstance(election.name, str) and election.name
            assert election.election_date is not None
            assert isinstance(election.election_type, str) and election.election_type
            assert isinstance(election.deadlines, list)

    def test_whats_next_backward_compatible(self):
        """whats_next() without include_elections returns only meetings."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next()
        # All results should be Meeting objects (backward compatible)
        for item in result:
            assert isinstance(item, Meeting)

    def test_what_happened_full_context_returns_list(self):
        """what_happened_full_context() returns list of DecisionWithContext with decision+links."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened_full_context("bike lanes")
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, DecisionWithContext)
            assert isinstance(item.decision, Decision)
            assert isinstance(item.transcript_links, list)

    def test_what_happened_full_context_structure(self):
        """what_happened_full_context() returns properly structured results."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened_full_context("housing", top_k=2)
        assert isinstance(result, list)
        # Verify we don't get more than requested
        assert len(result) <= 2

    def test_budget_returns_list(self):
        """budget() returns list of BudgetItem with valid fields."""
        c = CivicOS("san-rafael-ca")
        result = c.budget()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, BudgetItem)
            assert item.id  # Non-empty ID
            assert item.budgeted_dollars >= 0  # Valid dollar amount

    def test_budget_with_department_filter(self):
        """budget() accepts department filter."""
        c = CivicOS("san-rafael-ca")
        result = c.budget(department="Police")
        assert isinstance(result, list)
        # All results should be from Police department
        for item in result:
            assert item.department == "Police"

    def test_budget_with_amount_filter(self):
        """budget() accepts min_amount filter."""
        c = CivicOS("san-rafael-ca")
        result = c.budget(min_amount=1_000_000)
        assert isinstance(result, list)
        # All results should be >= $1M
        for item in result:
            assert item.budgeted_dollars >= 1_000_000

    def test_budget_summary_returns_list(self):
        """budget_summary() returns list of BudgetSummary with valid fields."""
        c = CivicOS("san-rafael-ca")
        result = c.budget_summary()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, BudgetSummary)
            assert item.budgeted_dollars >= 0  # Valid dollar total
            assert item.item_count >= 1  # At least 1 item per group


class TestDataclasses:
    """Test result dataclasses are properly defined."""

    def test_regulatory_stack_dataclass(self):
        """RegulatoryStack has expected fields."""
        stack = RegulatoryStack(
            topic="housing",
            jurisdiction="san-rafael-ca",
            federal=[{"program": "CDBG"}],
            state=[{"bill": "SB 35"}],
            local=[{"ordinance": "Zoning Code"}],
        )
        assert stack.topic == "housing"
        assert len(stack.federal) == 1
        assert len(stack.state) == 1

    def test_meeting_dataclass(self):
        """Meeting has expected fields."""
        from datetime import datetime
        meeting = Meeting(
            id="mtg_123",
            title="City Council",
            date=datetime.now(),
            body="Regular meeting",
        )
        assert meeting.id == "mtg_123"
        assert meeting.agenda_items == []


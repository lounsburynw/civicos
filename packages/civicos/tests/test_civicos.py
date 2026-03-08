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
    TranscriptLink,
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

    def test_civic_has_state_manager(self):
        """CivicOS instance has StateManager."""
        c = CivicOS("san-rafael-ca")
        assert c._state is not None

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

    def test_what_happened_returns_list(self):
        """what_happened() returns list of decisions."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened("bike lanes")
        assert isinstance(result, list)

    def test_whats_next_returns_meetings(self):
        """whats_next() returns list of meetings."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next()
        assert isinstance(result, list)

    def test_whats_next_with_topics(self):
        """whats_next() accepts topic filter."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next(topics=["transportation"])
        assert isinstance(result, list)

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
        """UpcomingElection objects have required fields."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next(include_elections=True, days=365)
        elections = [x for x in result if isinstance(x, UpcomingElection)]
        for election in elections:
            assert hasattr(election, 'id')
            assert hasattr(election, 'name')
            assert hasattr(election, 'election_date')
            assert hasattr(election, 'election_type')
            assert hasattr(election, 'deadlines')
            assert isinstance(election.deadlines, list)

    def test_whats_next_backward_compatible(self):
        """whats_next() without include_elections returns only meetings."""
        c = CivicOS("san-rafael-ca")
        result = c.whats_next()
        # All results should be Meeting objects (backward compatible)
        for item in result:
            assert isinstance(item, Meeting)

    def test_what_happened_full_context_returns_list(self):
        """what_happened_full_context() returns list of DecisionWithContext."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened_full_context("bike lanes")
        assert isinstance(result, list)
        # Each item should be DecisionWithContext if results exist
        # (may be empty list if no matching decisions)

    def test_what_happened_full_context_structure(self):
        """what_happened_full_context() returns properly structured results."""
        c = CivicOS("san-rafael-ca")
        result = c.what_happened_full_context("housing", top_k=2)
        assert isinstance(result, list)
        # Verify we don't get more than requested
        assert len(result) <= 2

    def test_decision_with_context_types_exist(self):
        """DecisionWithContext and TranscriptLink can be imported from civicos.civicos."""
        # This verifies the types are properly exported
        assert DecisionWithContext is not None
        assert TranscriptLink is not None

    def test_budget_returns_list(self):
        """budget() returns list of BudgetItem."""
        c = CivicOS("san-rafael-ca")
        result = c.budget()
        assert isinstance(result, list)
        # If results exist, verify type
        if result:
            assert isinstance(result[0], BudgetItem)

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
        """budget_summary() returns list of BudgetSummary."""
        c = CivicOS("san-rafael-ca")
        result = c.budget_summary()
        assert isinstance(result, list)
        # If results exist, verify type
        if result:
            assert isinstance(result[0], BudgetSummary)

    def test_budget_item_and_summary_types_exist(self):
        """BudgetItem and BudgetSummary can be imported from civicos.civicos."""
        assert BudgetItem is not None
        assert BudgetSummary is not None


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


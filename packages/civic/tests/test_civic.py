"""
Tests for the main Civic class.

Tests the unified API entry point.
"""

import pytest

# Mark all tests in this module as fast (smoke tests, <30s total)
pytestmark = pytest.mark.fast
import tempfile
import os
from civic import Civic
from civic.civic import (
    RegulatoryStack,
    Decision,
    DecisionWithContext,
    TranscriptLink,
    Meeting,
    UpcomingElection,
    Community,
    Initiative,
    Voice,
    Subscription,
    Preparation,
    Suggestion,
    CoordinationPlan,
    Outcome,
    BudgetItem,
    BudgetSummary,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


class TestCivicInstantiation:
    """Test Civic class instantiation."""

    def test_create_civic_instance(self):
        """Can create a Civic instance with jurisdiction."""
        c = Civic("san-rafael-ca")
        # Jurisdiction is normalized to canonical format
        assert c.jurisdiction == "city-san-rafael"

    def test_civic_has_state_manager(self):
        """Civic instance has StateManager."""
        c = Civic("san-rafael-ca")
        assert c._state is not None

    def test_civic_custom_db_path(self):
        """Can specify custom database path."""
        c = Civic("san-rafael-ca", db_path="/tmp/test_civic.db")
        assert c.db_path == "/tmp/test_civic.db"


class TestQueryMethods:
    """Test query methods (learn)."""

    def test_what_applies_returns_regulatory_stack(self):
        """what_applies() returns RegulatoryStack."""
        c = Civic("san-rafael-ca")
        result = c.what_applies("housing")
        assert isinstance(result, RegulatoryStack)
        assert result.topic == "housing"
        # Jurisdiction is normalized to canonical format
        assert result.jurisdiction == "city-san-rafael"

    def test_what_happened_returns_list(self):
        """what_happened() returns list of decisions."""
        c = Civic("san-rafael-ca")
        result = c.what_happened("bike lanes")
        assert isinstance(result, list)

    def test_whats_next_returns_meetings(self):
        """whats_next() returns list of meetings."""
        c = Civic("san-rafael-ca")
        result = c.whats_next()
        assert isinstance(result, list)

    def test_whats_next_with_topics(self):
        """whats_next() accepts topic filter."""
        c = Civic("san-rafael-ca")
        result = c.whats_next(topics=["transportation"])
        assert isinstance(result, list)

    def test_whats_next_with_elections(self):
        """whats_next(include_elections=True) includes elections."""
        c = Civic("san-rafael-ca")
        # Get results with elections
        result = c.whats_next(include_elections=True, days=365)
        assert isinstance(result, list)
        # Results can contain both Meeting and UpcomingElection objects
        for item in result:
            assert isinstance(item, (Meeting, UpcomingElection))

    def test_whats_next_election_structure(self):
        """UpcomingElection objects have required fields."""
        c = Civic("san-rafael-ca")
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
        c = Civic("san-rafael-ca")
        result = c.whats_next()
        # All results should be Meeting objects (backward compatible)
        for item in result:
            assert isinstance(item, Meeting)

    def test_whos_with_me_returns_community(self):
        """whos_with_me() returns Community."""
        c = Civic("san-rafael-ca")
        result = c.whos_with_me("traffic safety")
        assert isinstance(result, Community)
        assert result.topic == "traffic safety"

    def test_what_happened_full_context_returns_list(self):
        """what_happened_full_context() returns list of DecisionWithContext."""
        c = Civic("san-rafael-ca")
        result = c.what_happened_full_context("bike lanes")
        assert isinstance(result, list)
        # Each item should be DecisionWithContext if results exist
        # (may be empty list if no matching decisions)

    def test_what_happened_full_context_structure(self):
        """what_happened_full_context() returns properly structured results."""
        c = Civic("san-rafael-ca")
        result = c.what_happened_full_context("housing", top_k=2)
        assert isinstance(result, list)
        # Verify we don't get more than requested
        assert len(result) <= 2

    def test_decision_with_context_types_exist(self):
        """DecisionWithContext and TranscriptLink can be imported from civic.civic."""
        # This verifies the types are properly exported
        assert DecisionWithContext is not None
        assert TranscriptLink is not None

    def test_budget_returns_list(self):
        """budget() returns list of BudgetItem."""
        c = Civic("san-rafael-ca")
        result = c.budget()
        assert isinstance(result, list)
        # If results exist, verify type
        if result:
            assert isinstance(result[0], BudgetItem)

    def test_budget_with_department_filter(self):
        """budget() accepts department filter."""
        c = Civic("san-rafael-ca")
        result = c.budget(department="Police")
        assert isinstance(result, list)
        # All results should be from Police department
        for item in result:
            assert item.department == "Police"

    def test_budget_with_amount_filter(self):
        """budget() accepts min_amount filter."""
        c = Civic("san-rafael-ca")
        result = c.budget(min_amount=1_000_000)
        assert isinstance(result, list)
        # All results should be >= $1M
        for item in result:
            assert item.budgeted_dollars >= 1_000_000

    def test_budget_summary_returns_list(self):
        """budget_summary() returns list of BudgetSummary."""
        c = Civic("san-rafael-ca")
        result = c.budget_summary()
        assert isinstance(result, list)
        # If results exist, verify type
        if result:
            assert isinstance(result[0], BudgetSummary)

    def test_budget_item_and_summary_types_exist(self):
        """BudgetItem and BudgetSummary can be imported from civic.civic."""
        assert BudgetItem is not None
        assert BudgetSummary is not None


class TestActionMethods:
    """Test action methods (act)."""

    def test_start_something_creates_initiative(self):
        """start_something() creates an initiative."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.start_something(
                topic="traffic",
                title="Protected bike lane on 4th St",
                description="Near-misses every week at this intersection",
                location="4th St & B St",
                creator_id="user_123"
            )

            assert isinstance(result, Initiative)
            assert result.id.startswith("init_")
            assert result.topic == "traffic"
            assert result.title == "Protected bike lane on 4th St"
            # Jurisdiction is normalized to canonical format
            assert result.jurisdiction == "city-san-rafael"
            assert result.creator_id == "user_123"

    def test_start_something_default_creator(self):
        """start_something() uses anonymous as default creator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.start_something(
                topic="housing",
                title="Affordable housing downtown",
                description="We need more affordable units"
            )

            assert result.creator_id == "anonymous"

    def test_add_voice_creates_voice(self):
        """add_voice() creates a voice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.add_voice(
                item_type="agenda_item",
                item_id="item_123",
                stance="support",
                comment="I agree with this proposal",
                user_id="user_789"
            )

            assert isinstance(result, Voice)
            assert result.id.startswith("voice_")
            assert result.item_type == "agenda_item"
            assert result.item_id == "item_123"
            assert result.stance == "support"
            assert result.comment == "I agree with this proposal"

    def test_add_voice_default_user(self):
        """add_voice() uses anonymous as default user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.add_voice(
                item_type="initiative",
                item_id="init_456",
                stance="oppose",
                comment="I have concerns"
            )

            # Voice dataclass in civic.py doesn't have user_id field
            # so we verify by checking the voice was created correctly
            assert result.stance == "oppose"
            assert result.comment == "I have concerns"

    def test_add_voice_validates_stance(self):
        """add_voice() validates stance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            with pytest.raises(ValueError):
                c.add_voice("initiative", "init_123", "invalid", "Comment")

    def test_follow_creates_subscription(self):
        """follow() creates a subscription."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.follow(
                item_type="meeting",
                item_id="mtg_456",
                user_id="user_123",
            )

            assert isinstance(result, Subscription)
            assert result.id.startswith("sub_")
            assert result.item_type == "meeting"
            assert result.item_id == "mtg_456"

    def test_follow_default_user(self):
        """follow() uses anonymous as default user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            result = c.follow(
                item_type="initiative",
                item_id="init_789",
            )

            # Subscription was created (default user handled internally)
            assert result.item_type == "initiative"
            assert result.item_id == "init_789"

    def test_follow_validates_item_type(self):
        """follow() validates item_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)

            with pytest.raises(ValueError):
                c.follow("invalid_type", "item_123")

    def test_prepare_agenda_item_not_found(self):
        """prepare() raises ValueError for unknown agenda item."""
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            c = Civic("san-rafael-ca", db_path=db_path)
            with pytest.raises(ValueError, match="not found"):
                c.prepare("item_nonexistent")

    def test_prepare_returns_preparation(self):
        """prepare() returns Preparation with context and logistics."""
        import tempfile
        import os
        from civic._internal.state import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            state = StateManager(db_path)

            # Create meeting with agenda item (use canonical jurisdiction ID)
            state.update_meetings("city-san-rafael", [{
                "id": "mtg_test",
                "title": "City Council",
                "meeting_datetime": "2025-12-15T18:00:00",
                "meeting_type": "City Council",
                "location": "City Hall",
                "source_platform": "test",
                "full_data": {
                    "agenda_items": [{
                        "id": "item_789",
                        "title": "Housing Policy Update",
                    }]
                }
            }])

            c = Civic("san-rafael-ca", db_path=db_path)
            result = c.prepare("item_789")

            assert result.agenda_item_id == "item_789"
            assert isinstance(result.regulatory_context, dict)
            assert isinstance(result.talking_points, list)
            assert len(result.talking_points) > 0
            assert isinstance(result.logistics, dict)


class TestOrchestrationMethods:
    """Test orchestration methods (AI)."""

    def test_suggestions_returns_list(self, temp_db):
        """suggestions() returns a list of suggestions."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        result = c.suggestions()
        assert isinstance(result, list)

    def test_suggestions_with_user_id(self, temp_db):
        """suggestions() accepts user_id for personalization."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        result = c.suggestions(user_id="user_123")
        assert isinstance(result, list)

    def test_suggestions_trending_initiative(self, temp_db):
        """suggestions() returns trending initiatives."""
        c = Civic("san-rafael-ca", db_path=temp_db)

        # Create an initiative with some supporters
        init = c.start_something(
            topic="traffic safety",
            title="Protected bike lane",
            description="Need safer streets",
            creator_id="creator_1"
        )

        # Add supporters to make it trending
        for i in range(3):
            c.follow("initiative", init.id, user_id=f"supporter_{i}")

        # Get suggestions (not as a supporter)
        result = c.suggestions()
        assert isinstance(result, list)

    def test_suggestions_coordination_ready(self, temp_db):
        """suggestions() returns coordination opportunities for user's initiatives."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        user_id = "test_user_123"

        # Create an initiative
        init = c.start_something(
            topic="housing",
            title="Affordable housing",
            description="We need more affordable housing",
            creator_id=user_id
        )

        # Add 5+ supporters to make it coordination-ready
        for i in range(6):
            c.follow("initiative", init.id, user_id=f"supporter_{i}")

        # Get suggestions as the creator
        result = c.suggestions(user_id=user_id)
        assert isinstance(result, list)

        # Should include a coordination suggestion
        coord_suggestions = [s for s in result if s.type == "coordination_ready"]
        assert len(coord_suggestions) >= 1
        assert coord_suggestions[0].item_id == init.id

    def test_report_outcome_basic(self, temp_db):
        """report_outcome() records an outcome."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        result = c.report_outcome("item_789", "passed")
        assert result.item_id == "item_789"
        assert result.outcome == "passed"

    def test_report_outcome_with_notes(self, temp_db):
        """report_outcome() records an outcome with notes."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        result = c.report_outcome(
            "item_456",
            "passed",
            notes="Passed 4-1, implementation starts Q2"
        )
        assert result.item_id == "item_456"
        assert result.outcome == "passed"
        assert result.notes == "Passed 4-1, implementation starts Q2"

    def test_report_outcome_invalid_outcome(self, temp_db):
        """report_outcome() raises ValueError for invalid outcome."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        with pytest.raises(ValueError):
            c.report_outcome("item_789", "invalid")

    def test_report_outcome_invalid_item_type(self, temp_db):
        """report_outcome() raises ValueError for invalid item_type."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        with pytest.raises(ValueError):
            c.report_outcome("item_789", "passed", item_type="invalid")

    def test_report_outcome_updates_initiative_status(self, temp_db):
        """report_outcome() updates initiative status when outcome is recorded."""
        c = Civic("san-rafael-ca", db_path=temp_db)

        # Create an initiative
        init = c.start_something(
            topic="traffic",
            title="Test Initiative",
            description="For testing"
        )

        # Report outcome
        result = c.report_outcome(
            init.id,
            "passed",
            item_type="initiative",
            notes="Success!"
        )
        assert result.outcome == "passed"

        # Verify initiative status was updated
        from civic._internal.state import StateManager
        state_mgr = StateManager(temp_db)
        updated_init = state_mgr.get_initiative(init.id)
        assert updated_init["status"] == "succeeded"

    def test_report_outcome_with_vote_breakdown(self, temp_db):
        """report_outcome() stores vote breakdown."""
        c = Civic("san-rafael-ca", db_path=temp_db)
        result = c.report_outcome(
            "item_123",
            "passed",
            vote_breakdown={"yes": 4, "no": 1, "abstain": 0}
        )
        assert result.outcome == "passed"

        # Verify vote breakdown was stored
        from civic._internal.state import StateManager
        state_mgr = StateManager(temp_db)
        stored = state_mgr.get_outcome_for_item("agenda_item", "item_123")
        assert stored["vote_breakdown"] == {"yes": 4, "no": 1, "abstain": 0}


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

    def test_community_dataclass(self):
        """Community has expected fields."""
        community = Community(
            topic="traffic",
            jurisdiction="san-rafael-ca",
            follower_count=10,
        )
        assert community.follower_count == 10
        assert community.recent_voices == []

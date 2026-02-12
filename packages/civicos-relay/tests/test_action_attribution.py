"""
Tests for action attribution system.

Verifies:
- Outcome recording for initiatives
- Auto-generation of attributions when outcomes are recorded
- User impact queries (attributions for a pubkey)
- Attribution messages
- Edge cases: no actions, no completions, withdrawn commitments
"""

import pytest
from civicos_relay.storage.memory import (
    InMemoryCivicActionEventStorage,
    InMemoryCivicCommitmentStorage,
    InMemoryCivicCompletionStorage,
    InMemoryOutcomeStorage,
    InMemoryAttributionStorage,
)
from civicos_relay.voice.civic_action_service import CivicActionService
from civicos_relay.voice.models import (
    CivicActionType,
    CommitmentStatus,
    ContributionType,
    EvidenceType,
    OutcomeType,
)

# Test keys (not real)
CREATOR_KEY = "a" * 64
CREATOR_SIG = "b" * 128
USER1_KEY = "c" * 64
USER1_SIG = "d" * 128
USER2_KEY = "e" * 64
USER2_SIG = "f" * 128
USER3_KEY = "1" * 64
USER3_SIG = "2" * 128


@pytest.fixture
def service():
    """Create a CivicActionService with in-memory storage including outcome/attribution."""
    return CivicActionService(
        action_storage=InMemoryCivicActionEventStorage(),
        commitment_storage=InMemoryCivicCommitmentStorage(),
        completion_storage=InMemoryCivicCompletionStorage(),
        outcome_storage=InMemoryOutcomeStorage(),
        attribution_storage=InMemoryAttributionStorage(),
    )


@pytest.fixture
def populated_service(service):
    """Service with an initiative that has actions, commitments, and completions."""
    initiative_id = "initiative:city-san-rafael:housing-policy-2026"

    # Create two actions for the initiative
    action1 = service.create_action(
        initiative_id=initiative_id,
        action_type=CivicActionType.WRITTEN_COMMENT,
        description="Submit written comment on housing density proposal",
        public_key=CREATOR_KEY,
        signature=CREATOR_SIG,
        target_count=10,
    )

    action2 = service.create_action(
        initiative_id=initiative_id,
        action_type=CivicActionType.ATTEND_MEETING,
        description="Attend planning commission hearing Feb 15",
        public_key=CREATOR_KEY,
        signature=CREATOR_SIG,
    )

    # User1: commits and completes action1
    service.commit_to_action(action1.id, USER1_KEY, USER1_SIG)
    service.complete_action(
        action1.id, USER1_KEY, USER1_SIG,
        EvidenceType.EMAIL_CONFIRMATION, "confirmation@city.gov"
    )

    # User2: commits and completes both actions
    service.commit_to_action(action1.id, USER2_KEY, USER2_SIG)
    service.complete_action(
        action1.id, USER2_KEY, USER2_SIG,
        EvidenceType.SELF_REPORT, None
    )
    service.commit_to_action(action2.id, USER2_KEY, USER2_SIG)
    service.complete_action(
        action2.id, USER2_KEY, USER2_SIG,
        EvidenceType.ATTENDANCE_CHECK, "checked in"
    )

    # User3: commits to action1 but doesn't complete
    service.commit_to_action(action1.id, USER3_KEY, USER3_SIG)

    return service, initiative_id, action1, action2


class TestOutcomeRecording:
    """Tests for recording initiative outcomes."""

    def test_record_simple_outcome(self, service):
        """Can record an outcome for an initiative."""
        outcome = service.record_outcome(
            initiative_id="initiative:test",
            outcome=OutcomeType.PASSED,
            notes="Approved unanimously",
        )

        assert outcome.id.startswith("outcome:initiative:test:")
        assert outcome.initiative_id == "initiative:test"
        assert outcome.outcome == OutcomeType.PASSED
        assert outcome.notes == "Approved unanimously"

    def test_record_outcome_with_vote_breakdown(self, service):
        """Can record an outcome with vote details."""
        outcome = service.record_outcome(
            initiative_id="initiative:test",
            outcome=OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
            decision_reference="decision:city-san-rafael:2026-02-15:item-3",
        )

        assert outcome.vote_breakdown == {"yes": 4, "no": 1}
        assert outcome.decision_reference == "decision:city-san-rafael:2026-02-15:item-3"

    def test_retrieve_outcome(self, service):
        """Can retrieve a recorded outcome by ID."""
        outcome = service.record_outcome(
            initiative_id="initiative:test",
            outcome=OutcomeType.FAILED,
        )

        retrieved = service.get_outcome(outcome.id)
        assert retrieved is not None
        assert retrieved.id == outcome.id
        assert retrieved.outcome == OutcomeType.FAILED

    def test_list_outcomes_for_initiative(self, service):
        """Can list all outcomes for an initiative."""
        service.record_outcome("initiative:test", OutcomeType.CONTINUED)
        service.record_outcome("initiative:test", OutcomeType.PASSED)
        service.record_outcome("initiative:other", OutcomeType.FAILED)

        outcomes = service.get_outcomes_for_initiative("initiative:test")
        assert len(outcomes) == 2

    def test_all_outcome_types(self, service):
        """All outcome types are valid."""
        for otype in OutcomeType:
            outcome = service.record_outcome(
                initiative_id=f"initiative:{otype.value}",
                outcome=otype,
            )
            assert outcome.outcome == otype

    def test_outcome_requires_storage(self):
        """Recording outcome fails without outcome storage."""
        service = CivicActionService(
            action_storage=InMemoryCivicActionEventStorage(),
            commitment_storage=InMemoryCivicCommitmentStorage(),
            completion_storage=InMemoryCivicCompletionStorage(),
        )
        with pytest.raises(RuntimeError, match="Outcome storage not configured"):
            service.record_outcome("initiative:test", OutcomeType.PASSED)


class TestAttributionGeneration:
    """Tests for automatic attribution generation."""

    def test_completers_get_attribution(self, populated_service):
        """Users who completed actions get completion attributions."""
        service, initiative_id, action1, action2 = populated_service

        outcome = service.record_outcome(
            initiative_id=initiative_id,
            outcome=OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        attributions = service.get_attributions_for_outcome(outcome.id)
        # User1: completed action1 (1 attribution)
        # User2: completed action1 + action2 (2 attributions)
        # User3: committed but didn't complete action1 (1 commitment attribution)
        assert len(attributions) == 4

    def test_completer_attribution_type(self, populated_service):
        """Completers get 'completion' contribution type."""
        service, initiative_id, action1, _ = populated_service

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        assert len(user1_attrs) >= 1
        completion_attrs = [a for a in user1_attrs if a.contribution_type == ContributionType.COMPLETION]
        assert len(completion_attrs) >= 1

    def test_commitment_only_attribution(self, populated_service):
        """Users who committed but didn't complete get commitment attribution."""
        service, initiative_id, _, _ = populated_service

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        user3_attrs = service.get_attributions_for_user(USER3_KEY)
        assert len(user3_attrs) == 1
        assert user3_attrs[0].contribution_type == ContributionType.COMMITMENT

    def test_no_duplicate_for_commit_and_complete(self, populated_service):
        """Users who both committed and completed get only completion attribution (not both)."""
        service, initiative_id, action1, _ = populated_service

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        # User1 committed and completed action1 — should get completion only, not both
        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        action1_attrs = [a for a in user1_attrs if a.action_id == action1.id]
        assert len(action1_attrs) == 1
        assert action1_attrs[0].contribution_type == ContributionType.COMPLETION

    def test_no_attribution_for_no_actions(self, service):
        """Outcome with no actions generates no attributions."""
        outcome = service.record_outcome(
            initiative_id="initiative:empty",
            outcome=OutcomeType.PASSED,
        )

        attributions = service.get_attributions_for_outcome(outcome.id)
        assert len(attributions) == 0

    def test_withdrawn_commitment_no_attribution(self, service):
        """Withdrawn commitments don't generate attributions."""
        initiative_id = "initiative:withdrawn-test"
        action = service.create_action(
            initiative_id=initiative_id,
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Test action",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.commit_to_action(action.id, USER1_KEY, USER1_SIG)
        service.withdraw_commitment(action.id, USER1_KEY)

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        attributions = service.get_attributions_for_outcome(outcome.id)
        assert len(attributions) == 0

    def test_revoked_action_no_attribution(self, service):
        """Revoked actions don't generate attributions."""
        initiative_id = "initiative:revoked-test"
        action = service.create_action(
            initiative_id=initiative_id,
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Test action",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )
        service.revoke_action(action.id, CREATOR_KEY)

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        attributions = service.get_attributions_for_outcome(outcome.id)
        assert len(attributions) == 0


class TestAttributionMessages:
    """Tests for personalized attribution messages."""

    def test_completion_message(self, populated_service):
        """Completion attributions include action description and outcome."""
        service, initiative_id, _, _ = populated_service

        outcome = service.record_outcome(
            initiative_id, OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        assert len(user1_attrs) >= 1
        msg = user1_attrs[0].message
        assert "contributed to outcome" in msg
        assert "passed" in msg

    def test_commitment_message(self, populated_service):
        """Commitment attributions have 'supported' wording."""
        service, initiative_id, _, _ = populated_service

        outcome = service.record_outcome(initiative_id, OutcomeType.PASSED)

        user3_attrs = service.get_attributions_for_user(USER3_KEY)
        assert len(user3_attrs) == 1
        assert "commitment" in user3_attrs[0].message.lower() or "supported" in user3_attrs[0].message.lower()

    def test_vote_breakdown_in_message(self, populated_service):
        """Vote breakdown appears in attribution message."""
        service, initiative_id, _, _ = populated_service

        outcome = service.record_outcome(
            initiative_id, OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        msg = user1_attrs[0].message
        assert "yes" in msg and "4" in msg


class TestUserImpact:
    """Tests for user impact queries."""

    def test_multi_initiative_impact(self, service):
        """User impact spans multiple initiatives."""
        # Create and populate two initiatives
        for i in range(2):
            init_id = f"initiative:test-{i}"
            action = service.create_action(
                initiative_id=init_id,
                action_type=CivicActionType.WRITTEN_COMMENT,
                description=f"Test action {i}",
                public_key=CREATOR_KEY,
                signature=CREATOR_SIG,
            )
            service.complete_action(
                action.id, USER1_KEY, USER1_SIG,
                EvidenceType.SELF_REPORT, None
            )
            service.record_outcome(init_id, OutcomeType.PASSED)

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert len(attrs) == 2

    def test_no_impact_for_non_participant(self, populated_service):
        """Non-participants have no attributions."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        # Random key that didn't participate
        attrs = service.get_attributions_for_user("0" * 64)
        assert len(attrs) == 0

    def test_user2_gets_multiple_attributions(self, populated_service):
        """User who completed multiple actions gets attribution for each."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user2_attrs = service.get_attributions_for_user(USER2_KEY)
        # User2 completed action1 + action2
        assert len(user2_attrs) == 2
        assert all(a.contribution_type == ContributionType.COMPLETION for a in user2_attrs)

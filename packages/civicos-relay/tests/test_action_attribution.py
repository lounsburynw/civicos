"""
Tests for action attribution system.

Verifies:
- Activity-based attributions (immediate, on completion)
- Outcome-based attributions (when initiative outcome is recorded)
- User impact queries spanning both types
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
    """Service with an initiative that has actions, commitments, and completions.

    After this fixture runs, activity attributions already exist for completers:
    - User1: 1 activity attribution (completed action1)
    - User2: 2 activity attributions (completed action1 + action2)
    - User3: 0 (committed only, no completion)
    """
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


# ============================================================================
# Activity-Based Attribution Tests
# ============================================================================


class TestActivityAttribution:
    """Tests for immediate attribution on action completion."""

    def test_completion_generates_activity_attribution(self, service):
        """Completing an action immediately generates an activity attribution."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit public comment",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert len(attrs) == 1
        assert attrs[0].is_activity_based
        assert attrs[0].outcome_id is None
        assert attrs[0].action_id == action.id
        assert attrs[0].contribution_type == ContributionType.COMPLETION

    def test_activity_message_includes_description(self, service):
        """Activity attribution message includes the action description."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit public comment on housing",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert "Submit public comment on housing" in attrs[0].message

    def test_activity_message_includes_progress(self, service):
        """Activity attribution message includes completion progress with target."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit comment",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
            target_count=10,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert "1 of 10" in attrs[0].message

    def test_activity_message_without_target(self, service):
        """Activity attribution works when action has no target_count."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.ATTEND_MEETING,
            description="Attend hearing",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert "1 completed" in attrs[0].message

    def test_activity_attribution_updates_progress(self, service):
        """Later completions see updated progress counts."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit comment",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
            target_count=5,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )
        service.complete_action(
            action.id, USER2_KEY, USER2_SIG,
            EvidenceType.SELF_REPORT, None
        )

        user2_attrs = service.get_attributions_for_user(USER2_KEY)
        assert "2 of 5" in user2_attrs[0].message

    def test_no_activity_attribution_without_storage(self):
        """Completing action without attribution storage succeeds but stores no attributions."""
        service = CivicActionService(
            action_storage=InMemoryCivicActionEventStorage(),
            commitment_storage=InMemoryCivicCommitmentStorage(),
            completion_storage=InMemoryCivicCompletionStorage(),
        )
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Test",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )
        completion = service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )
        assert completion.public_key == USER1_KEY
        assert completion.evidence_type == EvidenceType.SELF_REPORT
        # No attribution storage → graceful degradation, not error
        assert service.get_attributions_for_user(USER1_KEY) == []

    def test_activity_attribution_upsert_on_recomplete(self, service):
        """Re-completing an action updates the activity attribution, not duplicates."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit comment",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
            target_count=10,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )
        # Complete again (same user, same action)
        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.EMAIL_CONFIRMATION, "new evidence"
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        activity_attrs = [a for a in attrs if a.is_activity_based]
        assert len(activity_attrs) == 1

    def test_populated_service_has_activity_attributions(self, populated_service):
        """The populated_service fixture already has activity attributions."""
        service, _, _, _ = populated_service

        # User1 completed 1 action -> 1 activity attribution
        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        activity_attrs = [a for a in user1_attrs if a.is_activity_based]
        assert len(activity_attrs) == 1

        # User2 completed 2 actions -> 2 activity attributions
        user2_attrs = service.get_attributions_for_user(USER2_KEY)
        activity_attrs = [a for a in user2_attrs if a.is_activity_based]
        assert len(activity_attrs) == 2

        # User3 only committed -> 0 activity attributions
        user3_attrs = service.get_attributions_for_user(USER3_KEY)
        assert len(user3_attrs) == 0


# ============================================================================
# Outcome Recording Tests
# ============================================================================


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


# ============================================================================
# Outcome-Based Attribution Tests
# ============================================================================


class TestOutcomeAttribution:
    """Tests for attribution generation when outcomes are recorded."""

    def test_completers_get_outcome_attribution(self, populated_service):
        """Users who completed actions get outcome attributions."""
        service, initiative_id, action1, action2 = populated_service

        outcome = service.record_outcome(
            initiative_id=initiative_id,
            outcome=OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        # get_attributions_for_outcome returns ONLY outcome-based attributions
        attributions = service.get_attributions_for_outcome(outcome.id)
        # User1: completed action1 (1)
        # User2: completed action1 + action2 (2)
        # User3: committed but didn't complete (1 commitment)
        assert len(attributions) == 4

    def test_completer_gets_outcome_attribution_type(self, populated_service):
        """Completers get 'completion' contribution type for outcome attributions."""
        service, initiative_id, action1, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        outcome_attrs = [a for a in user1_attrs if not a.is_activity_based]
        assert len(outcome_attrs) == 1
        assert outcome_attrs[0].contribution_type == ContributionType.COMPLETION

    def test_commitment_only_gets_outcome_attribution(self, populated_service):
        """Users who committed but didn't complete get commitment attribution."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user3_attrs = service.get_attributions_for_user(USER3_KEY)
        # User3 has no activity attributions (no completions) but 1 outcome attribution
        assert len(user3_attrs) == 1
        assert not user3_attrs[0].is_activity_based
        assert user3_attrs[0].contribution_type == ContributionType.COMMITMENT

    def test_no_duplicate_outcome_attr_for_commit_and_complete(self, populated_service):
        """Users who both committed and completed get only completion outcome attribution."""
        service, initiative_id, action1, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        outcome_attrs = [a for a in user1_attrs if not a.is_activity_based and a.action_id == action1.id]
        assert len(outcome_attrs) == 1
        assert outcome_attrs[0].contribution_type == ContributionType.COMPLETION

    def test_no_outcome_attribution_for_no_actions(self, service):
        """Outcome with no actions generates no outcome attributions."""
        outcome = service.record_outcome(
            initiative_id="initiative:empty",
            outcome=OutcomeType.PASSED,
        )

        attributions = service.get_attributions_for_outcome(outcome.id)
        assert len(attributions) == 0

    def test_withdrawn_commitment_no_outcome_attribution(self, service):
        """Withdrawn commitments don't generate outcome attributions."""
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

    def test_revoked_action_no_outcome_attribution(self, service):
        """Revoked actions don't generate outcome attributions."""
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


# ============================================================================
# Attribution Message Tests
# ============================================================================


class TestAttributionMessages:
    """Tests for personalized attribution messages."""

    def test_outcome_completion_message(self, populated_service):
        """Outcome completion attributions reference the outcome."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(
            initiative_id, OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        outcome_attrs = [a for a in user1_attrs if not a.is_activity_based]
        assert len(outcome_attrs) == 1
        msg = outcome_attrs[0].message
        assert "contributed to outcome" in msg
        assert "passed" in msg

    def test_outcome_commitment_message(self, populated_service):
        """Commitment attributions have 'supported' wording."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user3_attrs = service.get_attributions_for_user(USER3_KEY)
        assert len(user3_attrs) == 1
        assert "commitment" in user3_attrs[0].message.lower() or "supported" in user3_attrs[0].message.lower()

    def test_vote_breakdown_in_outcome_message(self, populated_service):
        """Vote breakdown appears in outcome attribution message."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(
            initiative_id, OutcomeType.PASSED,
            vote_breakdown={"yes": 4, "no": 1},
        )

        user1_attrs = service.get_attributions_for_user(USER1_KEY)
        outcome_attrs = [a for a in user1_attrs if not a.is_activity_based]
        msg = outcome_attrs[0].message
        assert "yes" in msg and "4" in msg

    def test_activity_message_format(self, service):
        """Activity attribution message starts with 'You completed:'."""
        action = service.create_action(
            initiative_id="initiative:test",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Submit comment to city council",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )

        attrs = service.get_attributions_for_user(USER1_KEY)
        assert attrs[0].message.startswith("You completed:")


# ============================================================================
# User Impact (Combined) Tests
# ============================================================================


class TestUserImpact:
    """Tests for combined user impact queries (activity + outcome)."""

    def test_both_activity_and_outcome_in_impact(self, populated_service):
        """User impact includes both activity and outcome attributions."""
        service, initiative_id, _, _ = populated_service

        # Before outcome: User1 has 1 activity attribution
        before = service.get_attributions_for_user(USER1_KEY)
        assert len(before) == 1
        assert all(a.is_activity_based for a in before)

        # Record outcome
        service.record_outcome(initiative_id, OutcomeType.PASSED)

        # After outcome: User1 has 1 activity + 1 outcome = 2
        after = service.get_attributions_for_user(USER1_KEY)
        assert len(after) == 2
        activity = [a for a in after if a.is_activity_based]
        outcome = [a for a in after if not a.is_activity_based]
        assert len(activity) == 1
        assert len(outcome) == 1

    def test_multi_initiative_impact(self, service):
        """User impact spans multiple initiatives."""
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
        # 2 activity + 2 outcome = 4
        assert len(attrs) == 4

    def test_no_impact_for_non_participant(self, populated_service):
        """Non-participants have no attributions of any kind."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        attrs = service.get_attributions_for_user("0" * 64)
        assert len(attrs) == 0

    def test_user2_gets_multiple_of_each_type(self, populated_service):
        """User who completed multiple actions gets activity + outcome attrs for each."""
        service, initiative_id, _, _ = populated_service

        service.record_outcome(initiative_id, OutcomeType.PASSED)

        user2_attrs = service.get_attributions_for_user(USER2_KEY)
        activity = [a for a in user2_attrs if a.is_activity_based]
        outcome = [a for a in user2_attrs if not a.is_activity_based]
        # User2 completed 2 actions -> 2 activity + 2 outcome = 4
        assert len(activity) == 2
        assert len(outcome) == 2

    def test_activity_only_when_no_outcome(self, service):
        """Actions without outcomes still have activity attributions."""
        action = service.create_action(
            initiative_id="initiative:no-outcome",
            action_type=CivicActionType.WRITTEN_COMMENT,
            description="Comment on ongoing issue",
            public_key=CREATOR_KEY,
            signature=CREATOR_SIG,
        )

        service.complete_action(
            action.id, USER1_KEY, USER1_SIG,
            EvidenceType.SELF_REPORT, None
        )
        # No outcome recorded — user still gets activity attribution
        attrs = service.get_attributions_for_user(USER1_KEY)
        assert len(attrs) == 1
        assert attrs[0].is_activity_based
        assert "You completed" in attrs[0].message

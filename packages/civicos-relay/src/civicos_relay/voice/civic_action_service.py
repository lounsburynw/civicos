"""Civic Action Service - manages action events, commitments, and completions.

This module implements the full Nostr action event specification:
- Kind 30810: CivicActionEvent - defines the action itself
- Kind 30811: CivicCommitment - user commits to action
- Kind 30812: CivicCompletion - user reports completion

These are addressable events that can be reused across initiatives and
federated to other relays.
"""

import hashlib
from datetime import datetime
from typing import Optional, Protocol

from civicos_relay.voice.models import (
    Attribution,
    CivicActionEvent,
    CivicActionType,
    CivicCommitment,
    CivicCompletion,
    CivicActionProgress,
    CommitmentStatus,
    ContributionType,
    EvidenceType,
    InitiativeOutcome,
    OutcomeType,
)


# ============================================================================
# Storage Protocols
# ============================================================================


class CivicActionEventStorage(Protocol):
    """Protocol for action event persistence (Kind 30810)."""

    def save_action_event(self, action: CivicActionEvent) -> None:
        """Store an action event."""
        ...

    def get_action_event(self, action_id: str) -> Optional[CivicActionEvent]:
        """Get an action event by ID."""
        ...

    def get_actions_for_initiative(self, initiative_id: str) -> list[CivicActionEvent]:
        """Get all actions for an initiative."""
        ...

    def revoke_action_event(self, action_id: str, public_key: str) -> bool:
        """Revoke an action event. Only creator can revoke. Returns True if revoked."""
        ...


class CivicCommitmentStorage(Protocol):
    """Protocol for commitment persistence (Kind 30811)."""

    def save_commitment(self, commitment: CivicCommitment) -> None:
        """Store a commitment."""
        ...

    def get_commitment(
        self, public_key: str, action_ref: str
    ) -> Optional[CivicCommitment]:
        """Get existing commitment for a user and action."""
        ...

    def get_commitments_for_action(self, action_ref: str) -> list[CivicCommitment]:
        """Get all commitments for an action."""
        ...

    def update_commitment_status(
        self, public_key: str, action_ref: str, status: CommitmentStatus
    ) -> bool:
        """Update commitment status. Returns True if updated."""
        ...


class CivicCompletionStorage(Protocol):
    """Protocol for completion persistence (Kind 30812)."""

    def save_completion(self, completion: CivicCompletion) -> None:
        """Store a completion."""
        ...

    def get_completion(
        self, public_key: str, action_ref: str
    ) -> Optional[CivicCompletion]:
        """Get existing completion for a user and action."""
        ...

    def get_completions_for_action(self, action_ref: str) -> list[CivicCompletion]:
        """Get all completions for an action."""
        ...


class OutcomeStorage(Protocol):
    """Protocol for outcome persistence."""

    def save_outcome(self, outcome: InitiativeOutcome) -> None: ...
    def get_outcome(self, outcome_id: str) -> Optional[InitiativeOutcome]: ...
    def get_outcomes_for_initiative(self, initiative_id: str) -> list[InitiativeOutcome]: ...


class AttributionStorage(Protocol):
    """Protocol for attribution persistence."""

    def save_attribution(self, attribution: Attribution) -> None: ...
    def get_attributions_for_outcome(self, outcome_id: str) -> list[Attribution]: ...
    def get_attributions_for_user(self, public_key: str) -> list[Attribution]: ...


# ============================================================================
# Civic Action Service
# ============================================================================


class CivicActionService:
    """
    Service for managing civic action events, commitments, and completions.

    Handles creation, verification, storage, and progress tracking for
    the full Nostr action event specification.
    """

    def __init__(
        self,
        action_storage: CivicActionEventStorage,
        commitment_storage: CivicCommitmentStorage,
        completion_storage: CivicCompletionStorage,
        outcome_storage: Optional[OutcomeStorage] = None,
        attribution_storage: Optional[AttributionStorage] = None,
    ):
        self._action_storage = action_storage
        self._commitment_storage = commitment_storage
        self._completion_storage = completion_storage
        self._outcome_storage = outcome_storage
        self._attribution_storage = attribution_storage

    # ========================================================================
    # Action Event Methods (Kind 30810)
    # ========================================================================

    def create_action(
        self,
        initiative_id: str,
        action_type: CivicActionType,
        description: str,
        public_key: str,
        signature: str,
        target: Optional[str] = None,
        deadline: Optional[datetime] = None,
        template: Optional[str] = None,
        target_count: Optional[int] = None,
        deadline_context: Optional[str] = None,
        coordination_url: Optional[str] = None,
    ) -> CivicActionEvent:
        """
        Create a new civic action event.

        Returns the created action with its generated ID.
        """
        # Generate deterministic action ID
        action_id = self._generate_action_id(initiative_id, action_type, description)

        # Create action event
        action = CivicActionEvent(
            id=action_id,
            initiative_id=initiative_id,
            action_type=action_type,
            description=description,
            target=target,
            deadline=deadline,
            template=template,
            target_count=target_count,
            deadline_context=deadline_context,
            coordination_url=coordination_url,
            public_key=public_key,
            signature=signature,
        )

        self._action_storage.save_action_event(action)
        return action

    def get_action(self, action_id: str) -> Optional[CivicActionEvent]:
        """Get an action event by ID."""
        return self._action_storage.get_action_event(action_id)

    def get_actions_for_initiative(self, initiative_id: str) -> list[CivicActionEvent]:
        """Get all actions for an initiative."""
        actions = self._action_storage.get_actions_for_initiative(initiative_id)
        return [a for a in actions if not a.revoked]

    def revoke_action(self, action_id: str, public_key: str) -> bool:
        """Revoke an action event. Only creator can revoke."""
        return self._action_storage.revoke_action_event(action_id, public_key)

    # ========================================================================
    # Commitment Methods (Kind 30811)
    # ========================================================================

    def commit_to_action(
        self,
        action_id: str,
        public_key: str,
        signature: str,
    ) -> CivicCommitment:
        """
        Record a user's commitment to an action.

        If the user has already committed, the old commitment is replaced.
        """
        # Build the action reference (a-tag format)
        action = self._action_storage.get_action_event(action_id)
        if not action:
            raise ValueError(f"Action not found: {action_id}")

        action_ref = f"30810:{action.public_key}:{action_id}"

        # Generate commitment ID
        commitment_id = f"commit:{public_key[:16]}:{action_id}"

        # Create commitment
        commitment = CivicCommitment(
            id=commitment_id,
            action_ref=action_ref,
            status=CommitmentStatus.COMMITTED,
            public_key=public_key,
            signature=signature,
        )

        self._commitment_storage.save_commitment(commitment)
        return commitment

    def get_commitment(
        self, public_key: str, action_id: str
    ) -> Optional[CivicCommitment]:
        """Get a user's commitment to an action."""
        action = self._action_storage.get_action_event(action_id)
        if not action:
            return None
        action_ref = f"30810:{action.public_key}:{action_id}"
        return self._commitment_storage.get_commitment(public_key, action_ref)

    def get_commitments_for_action(self, action_id: str) -> list[CivicCommitment]:
        """Get all commitments for an action."""
        action = self._action_storage.get_action_event(action_id)
        if not action:
            return []
        action_ref = f"30810:{action.public_key}:{action_id}"
        commitments = self._commitment_storage.get_commitments_for_action(action_ref)
        return [c for c in commitments if not c.revoked]

    def withdraw_commitment(self, action_id: str, public_key: str) -> bool:
        """Withdraw a commitment to an action."""
        action = self._action_storage.get_action_event(action_id)
        if not action:
            return False
        action_ref = f"30810:{action.public_key}:{action_id}"
        return self._commitment_storage.update_commitment_status(
            public_key, action_ref, CommitmentStatus.WITHDRAWN
        )

    # ========================================================================
    # Completion Methods (Kind 30812)
    # ========================================================================

    def complete_action(
        self,
        action_id: str,
        public_key: str,
        signature: str,
        evidence_type: EvidenceType,
        evidence_content: Optional[str] = None,
    ) -> CivicCompletion:
        """
        Record completion of an action with evidence.

        If the user has already completed, the old completion is replaced.
        Also updates commitment status to COMPLETED if one exists.
        """
        # Build the action reference
        action = self._action_storage.get_action_event(action_id)
        if not action:
            raise ValueError(f"Action not found: {action_id}")

        action_ref = f"30810:{action.public_key}:{action_id}"

        # Generate completion ID
        completion_id = f"complete:{public_key[:16]}:{action_id}"

        # Create completion
        completion = CivicCompletion(
            id=completion_id,
            action_ref=action_ref,
            evidence_type=evidence_type,
            evidence_content=evidence_content,
            public_key=public_key,
            signature=signature,
        )

        self._completion_storage.save_completion(completion)

        # Update commitment status if one exists
        self._commitment_storage.update_commitment_status(
            public_key, action_ref, CommitmentStatus.COMPLETED
        )

        # Generate activity-based attribution immediately
        if self._attribution_storage:
            self._generate_activity_attribution(action, action_ref, public_key)

        return completion

    def get_completion(
        self, public_key: str, action_id: str
    ) -> Optional[CivicCompletion]:
        """Get a user's completion record for an action."""
        action = self._action_storage.get_action_event(action_id)
        if not action:
            return None
        action_ref = f"30810:{action.public_key}:{action_id}"
        return self._completion_storage.get_completion(public_key, action_ref)

    def get_completions_for_action(self, action_id: str) -> list[CivicCompletion]:
        """Get all completions for an action."""
        action = self._action_storage.get_action_event(action_id)
        if not action:
            return []
        action_ref = f"30810:{action.public_key}:{action_id}"
        completions = self._completion_storage.get_completions_for_action(action_ref)
        return [c for c in completions if not c.revoked]

    # ========================================================================
    # Progress Methods
    # ========================================================================

    def get_action_progress(self, action_id: str) -> CivicActionProgress:
        """Get progress for an action (commitments, completions, target)."""
        action = self._action_storage.get_action_event(action_id)

        commitments = self.get_commitments_for_action(action_id)
        completions = self.get_completions_for_action(action_id)

        return CivicActionProgress(
            action_id=action_id,
            commitment_count=len(commitments),
            completion_count=len(completions),
            target_count=action.target_count if action else None,
        )

    # ========================================================================
    # Outcome & Attribution Methods
    # ========================================================================

    def record_outcome(
        self,
        initiative_id: str,
        outcome: OutcomeType,
        notes: Optional[str] = None,
        vote_breakdown: Optional[dict] = None,
        decision_reference: Optional[str] = None,
    ) -> InitiativeOutcome:
        """
        Record the outcome of an initiative and auto-generate attributions.

        When an initiative reaches a conclusion, this records the result and
        creates personalized attributions for every user who completed actions.
        """
        if not self._outcome_storage:
            raise RuntimeError("Outcome storage not configured")
        if not self._attribution_storage:
            raise RuntimeError("Attribution storage not configured")

        # Generate outcome ID
        outcome_hash = hashlib.sha256(
            f"{initiative_id}:{outcome.value}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:12]
        outcome_id = f"outcome:{initiative_id}:{outcome_hash}"

        outcome_record = InitiativeOutcome(
            id=outcome_id,
            initiative_id=initiative_id,
            outcome=outcome,
            notes=notes,
            vote_breakdown=vote_breakdown,
            decision_reference=decision_reference,
        )
        self._outcome_storage.save_outcome(outcome_record)

        # Auto-generate attributions for all users who completed actions
        actions = self._action_storage.get_actions_for_initiative(initiative_id)
        for action in actions:
            if action.revoked:
                continue
            action_ref = f"30810:{action.public_key}:{action.id}"

            # Attribute completions (strongest signal)
            completions = self._completion_storage.get_completions_for_action(action_ref)
            for completion in completions:
                if completion.revoked:
                    continue
                message = self._generate_attribution_message(
                    outcome_record, action, ContributionType.COMPLETION,
                )
                attr_id = f"attr:{outcome_id}:{action.id}:{completion.public_key[:8]}"
                attribution = Attribution(
                    id=attr_id,
                    outcome_id=outcome_id,
                    action_id=action.id,
                    public_key=completion.public_key,
                    contribution_type=ContributionType.COMPLETION,
                    message=message,
                )
                self._attribution_storage.save_attribution(attribution)

            # Attribute commitments (for users who committed but didn't complete)
            completers = {c.public_key for c in completions if not c.revoked}
            commitments = self._commitment_storage.get_commitments_for_action(action_ref)
            for commitment in commitments:
                if commitment.revoked or commitment.public_key in completers:
                    continue
                if commitment.status == CommitmentStatus.WITHDRAWN:
                    continue
                message = self._generate_attribution_message(
                    outcome_record, action, ContributionType.COMMITMENT,
                )
                attr_id = f"attr:{outcome_id}:{action.id}:{commitment.public_key[:8]}"
                attribution = Attribution(
                    id=attr_id,
                    outcome_id=outcome_id,
                    action_id=action.id,
                    public_key=commitment.public_key,
                    contribution_type=ContributionType.COMMITMENT,
                    message=message,
                )
                self._attribution_storage.save_attribution(attribution)

        return outcome_record

    def get_outcome(self, outcome_id: str) -> Optional[InitiativeOutcome]:
        """Get an outcome by ID."""
        if not self._outcome_storage:
            return None
        return self._outcome_storage.get_outcome(outcome_id)

    def get_outcomes_for_initiative(self, initiative_id: str) -> list[InitiativeOutcome]:
        """Get all outcomes for an initiative."""
        if not self._outcome_storage:
            return []
        return self._outcome_storage.get_outcomes_for_initiative(initiative_id)

    def get_attributions_for_outcome(self, outcome_id: str) -> list[Attribution]:
        """Get all attributions for an outcome."""
        if not self._attribution_storage:
            return []
        return self._attribution_storage.get_attributions_for_outcome(outcome_id)

    def get_attributions_for_user(self, public_key: str) -> list[Attribution]:
        """Get a user's impact history — all outcomes they contributed to."""
        if not self._attribution_storage:
            return []
        return self._attribution_storage.get_attributions_for_user(public_key)

    def _generate_attribution_message(
        self,
        outcome: InitiativeOutcome,
        action: CivicActionEvent,
        contribution_type: ContributionType,
    ) -> str:
        """Generate a personalized attribution message."""
        outcome_label = outcome.outcome.value.replace("_", " ")

        if outcome.vote_breakdown:
            vote_str = ", ".join(
                f"{k}: {v}" for k, v in outcome.vote_breakdown.items()
            )
            outcome_desc = f"{outcome_label} ({vote_str})"
        else:
            outcome_desc = outcome_label

        action_desc = action.description
        if contribution_type == ContributionType.COMPLETION:
            return f"Your {action_desc} contributed to outcome: {outcome_desc}"
        else:
            return f"Your commitment to {action_desc} supported outcome: {outcome_desc}"

    def _generate_activity_attribution(
        self,
        action: CivicActionEvent,
        action_ref: str,
        public_key: str,
    ) -> None:
        """Generate an activity-based attribution when a user completes an action.

        Activity attributions are immediate — no outcome needed. They tell the
        user what they did and how it fits into the bigger picture.
        """
        # Get current completion count for progress context
        completions = self._completion_storage.get_completions_for_action(action_ref)
        completion_count = len([c for c in completions if not c.revoked])

        if action.target_count:
            progress = f"{completion_count} of {action.target_count}"
        else:
            progress = f"{completion_count} completed"

        message = f"You completed: {action.description} ({progress})"

        attr_id = f"activity:{action.id}:{public_key[:8]}"
        attribution = Attribution(
            id=attr_id,
            outcome_id=None,  # Activity-based — no outcome yet
            action_id=action.id,
            public_key=public_key,
            contribution_type=ContributionType.COMPLETION,
            message=message,
        )
        self._attribution_storage.save_attribution(attribution)

    # ========================================================================
    # Signature Verification
    # ========================================================================

    def verify_action_signature(self, action: CivicActionEvent) -> bool:
        """Verify an action event signature."""
        from civicos_relay.voice.crypto import verify_signature

        message = self._create_action_message(action)
        return verify_signature(action.public_key, action.signature, message)

    def verify_commitment_signature(self, commitment: CivicCommitment) -> bool:
        """Verify a commitment signature."""
        from civicos_relay.voice.crypto import verify_signature

        message = f"civicos:commitment:v1:{commitment.id}:{commitment.action_ref}"
        return verify_signature(commitment.public_key, commitment.signature, message)

    def verify_completion_signature(self, completion: CivicCompletion) -> bool:
        """Verify a completion signature."""
        from civicos_relay.voice.crypto import verify_signature

        message = f"civicos:completion:v1:{completion.id}:{completion.action_ref}:{completion.evidence_type.value}"
        return verify_signature(completion.public_key, completion.signature, message)

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _generate_action_id(
        self, initiative_id: str, action_type: CivicActionType, description: str
    ) -> str:
        """Generate deterministic action ID from initiative + type + description hash."""
        desc_hash = hashlib.sha256(description.encode()).hexdigest()[:8]
        return f"action:{initiative_id}:{action_type.value}:{desc_hash}"

    def _create_action_message(self, action: CivicActionEvent) -> str:
        """Create the canonical message that must be signed for action creation."""
        desc_hash = hashlib.sha256(action.description.encode()).hexdigest()[:16]
        return (
            f"civicos:action:v1:{action.id}:{action.action_type.value}:"
            f"{desc_hash}:{action.timestamp.isoformat()}"
        )

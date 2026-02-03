"""Action service - manages action commitments and completions."""

from typing import Optional, Protocol

from civicos_relay.voice.models import Action, ActionType, ActionCount


class ActionStorage(Protocol):
    """Protocol for action persistence."""

    def save_action(self, action: Action) -> None:
        """Store an action record."""
        ...

    def get_action(
        self, public_key: str, action_id: str, action_type: ActionType
    ) -> Optional[Action]:
        """Get existing action for key+action_id+type tuple."""
        ...

    def get_actions_for_id(self, action_id: str) -> list[Action]:
        """Get all actions for an action ID."""
        ...

    def get_commitments_for_id(self, action_id: str) -> list[Action]:
        """Get all commitments for an action ID."""
        ...

    def get_completions_for_id(self, action_id: str) -> list[Action]:
        """Get all completions for an action ID."""
        ...

    def revoke_action(
        self, public_key: str, action_id: str, action_type: ActionType
    ) -> bool:
        """Revoke an action. Returns True if action existed."""
        ...


class ActionService:
    """
    Service for managing civic action commitments and completions.

    Handles action creation, verification, storage, and aggregation.
    """

    def __init__(self, storage: ActionStorage):
        self._storage = storage

    def record_commitment(
        self, action_id: str, public_key: str, signature: str
    ) -> Action:
        """
        Record a commitment to an action.

        If the key has already committed to this action, the old commitment
        is revoked and replaced.
        """
        # Check for existing commitment
        existing = self._storage.get_action(
            public_key, action_id, ActionType.COMMITMENT
        )
        if existing and not existing.revoked:
            self._storage.revoke_action(public_key, action_id, ActionType.COMMITMENT)

        # Create new commitment
        action = Action(
            action_id=action_id,
            action_type=ActionType.COMMITMENT,
            public_key=public_key,
            signature=signature,
        )
        self._storage.save_action(action)
        return action

    def record_completion(
        self,
        action_id: str,
        public_key: str,
        signature: str,
        evidence_url: Optional[str] = None,
    ) -> Action:
        """
        Record completion of an action.

        A user can only have one completion record per action.
        """
        # Check for existing completion
        existing = self._storage.get_action(
            public_key, action_id, ActionType.COMPLETION
        )
        if existing and not existing.revoked:
            self._storage.revoke_action(public_key, action_id, ActionType.COMPLETION)

        # Create new completion
        action = Action(
            action_id=action_id,
            action_type=ActionType.COMPLETION,
            public_key=public_key,
            signature=signature,
            evidence_url=evidence_url,
        )
        self._storage.save_action(action)
        return action

    def get_counts(self, action_id: str, target: Optional[int] = None) -> ActionCount:
        """Get aggregated action counts for an action ID."""
        commitments = self._storage.get_commitments_for_id(action_id)
        completions = self._storage.get_completions_for_id(action_id)

        return ActionCount(
            action_id=action_id,
            commitments=len([c for c in commitments if not c.revoked]),
            completions=len([c for c in completions if not c.revoked]),
            target=target,
        )

    def get_commitments(self, action_id: str) -> list[Action]:
        """Get all commitments for an action."""
        return [
            a for a in self._storage.get_commitments_for_id(action_id)
            if not a.revoked
        ]

    def get_completions(self, action_id: str) -> list[Action]:
        """Get all completions for an action."""
        return [
            a for a in self._storage.get_completions_for_id(action_id)
            if not a.revoked
        ]

    def verify(self, action: Action) -> bool:
        """
        Verify an action signature is valid.

        Uses the same verification logic as voices.
        """
        # Import here to avoid circular dependency
        from civicos_relay.voice.crypto import verify_signature

        # Construct the canonical message
        message = f"civicos:action:v1:{action.action_id}:{action.action_type.value}"
        return verify_signature(action.public_key, action.signature, message)

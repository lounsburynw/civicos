"""In-memory storage implementations for testing."""

from datetime import datetime
from typing import Optional

from civicos_relay.voice.models import (
    Voice,
    Stance,
    Action,
    ActionType,
    Comment,
    CivicActionEvent,
    CivicCommitment,
    CivicCompletion,
    CommitmentStatus,
)
from civicos_relay.relay.models import (
    Event,
    EventType,
    Subscription,
    MatchCriteria,
    DeliveryConfig,
    DeliveryMethod,
    Initiative,
    InitiativeStatus,
)
from civicos_relay.provenance.models import KeyProvenance


class InMemoryVoiceStorage:
    """In-memory voice storage for testing."""

    def __init__(self):
        self._voices: dict[tuple[str, str], Voice] = {}  # (public_key, entity) -> Voice

    def save_voice(self, voice: Voice) -> None:
        key = (voice.public_key, voice.entity)
        self._voices[key] = voice

    def get_voice(self, public_key: str, entity: str) -> Optional[Voice]:
        return self._voices.get((public_key, entity))

    def get_voices_for_entity(self, entity: str) -> list[Voice]:
        return [v for v in self._voices.values() if v.entity == entity and not v.revoked]

    def revoke_voice(self, public_key: str, entity: str) -> bool:
        key = (public_key, entity)
        if key in self._voices:
            old = self._voices[key]
            self._voices[key] = Voice(
                entity=old.entity,
                stance=old.stance,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                revoked=True,
            )
            return True
        return False

    def get_voices_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Voice], Optional[str]]:
        """Get voices for sync export."""
        voices = [
            v for v in self._voices.values()
            if v.timestamp > since
            and (namespace is None or v.entity.startswith(namespace.rstrip("*")))
        ]
        voices.sort(key=lambda v: v.timestamp)

        if len(voices) > limit:
            return voices[:limit], voices[limit - 1].timestamp.isoformat()
        return voices, None

    def import_voice(self, voice: Voice) -> str:
        """Import a voice. Returns 'accepted', 'rejected', or 'duplicate'."""
        key = (voice.public_key, voice.entity)
        if key in self._voices:
            existing = self._voices[key]
            if existing.timestamp >= voice.timestamp:
                return "duplicate"
        self._voices[key] = voice
        return "accepted"


class InMemorySubscriptionStorage:
    """In-memory subscription storage for testing."""

    def __init__(self):
        self._subscriptions: dict[str, Subscription] = {}

    def save_subscription(self, subscription: Subscription) -> None:
        self._subscriptions[subscription.id] = subscription

    def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        return self._subscriptions.get(subscription_id)

    def get_subscriptions_for_jurisdiction(self, jurisdiction: str) -> list[Subscription]:
        return [
            s for s in self._subscriptions.values()
            if s.jurisdiction == jurisdiction and s.active
        ]

    def deactivate_subscription(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            sub = self._subscriptions[subscription_id]
            self._subscriptions[subscription_id] = Subscription(
                id=sub.id,
                jurisdiction=sub.jurisdiction,
                match=sub.match,
                delivery=sub.delivery,
                created_at=sub.created_at,
                active=False,
                public_key=sub.public_key,
            )
            return True
        return False


class InMemoryProvenanceStorage:
    """In-memory provenance storage for testing."""

    def __init__(self):
        self._provenance: dict[str, KeyProvenance] = {}

    def get_provenance(self, public_key: str) -> Optional[KeyProvenance]:
        return self._provenance.get(public_key)

    def save_provenance(self, provenance: KeyProvenance) -> None:
        self._provenance[provenance.public_key] = provenance

    def get_provenance_for_entity(self, entity: str) -> list[KeyProvenance]:
        # This needs access to voices to know which keys voiced on entity
        # In real impl, this would be a join query
        return list(self._provenance.values())


class InMemoryInitiativeStorage:
    """In-memory initiative storage for testing."""

    def __init__(self):
        self._initiatives: dict[str, Initiative] = {}  # id -> Initiative

    def save_initiative(self, initiative: Initiative) -> None:
        self._initiatives[initiative.id] = initiative

    def get_initiative(self, initiative_id: str) -> Optional[Initiative]:
        return self._initiatives.get(initiative_id)

    def get_initiatives_for_jurisdiction(
        self,
        jurisdiction: str,
        topic: Optional[str] = None,
        status: Optional[InitiativeStatus] = None,
        limit: int = 100,
    ) -> list[Initiative]:
        results = [
            i
            for i in self._initiatives.values()
            if i.jurisdiction == jurisdiction
            and (topic is None or i.topic == topic)
            and (status is None or i.status == status)
        ]
        # Sort by voice_count desc, then timestamp desc
        results.sort(key=lambda i: (-i.voice_count, -i.timestamp.timestamp()))
        return results[:limit]

    def update_voice_count(self, initiative_id: str, count: int) -> bool:
        if initiative_id in self._initiatives:
            old = self._initiatives[initiative_id]
            # Create new frozen instance with updated count
            self._initiatives[initiative_id] = Initiative(
                id=old.id,
                jurisdiction=old.jurisdiction,
                topic=old.topic,
                title=old.title,
                description=old.description,
                location=old.location,
                coordination_url=old.coordination_url,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                status=old.status,
                voice_count=count,
            )
            return True
        return False

    def update_status(
        self, initiative_id: str, status: InitiativeStatus, public_key: str
    ) -> bool:
        if initiative_id in self._initiatives:
            old = self._initiatives[initiative_id]
            if old.public_key != public_key:
                return False  # Only creator can update
            self._initiatives[initiative_id] = Initiative(
                id=old.id,
                jurisdiction=old.jurisdiction,
                topic=old.topic,
                title=old.title,
                description=old.description,
                location=old.location,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                status=status,
                voice_count=old.voice_count,
            )
            return True
        return False


class InMemoryEventStorage:
    """In-memory event storage for testing."""

    def __init__(self):
        self._events: list[Event] = []

    def save_event(self, event: Event) -> None:
        self._events.append(event)

    def get_events_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Event], Optional[str]]:
        """Get events for sync export."""
        events = [
            e for e in self._events
            if e.timestamp > since
            and (namespace is None or e.jurisdiction.startswith(namespace.rstrip("*")))
        ]
        events.sort(key=lambda e: e.timestamp)

        if len(events) > limit:
            return events[:limit], events[limit - 1].timestamp.isoformat()
        return events, None

    def import_event(self, event: Event) -> str:
        """Import an event. Returns 'accepted', 'rejected', or 'duplicate'."""
        # Check for duplicates based on type+entity+timestamp
        for existing in self._events:
            if (
                existing.type == event.type
                and existing.entity == event.entity
                and existing.timestamp == event.timestamp
            ):
                return "duplicate"
        self._events.append(event)
        return "accepted"


class InMemorySyncStorage:
    """In-memory sync state storage for testing."""

    def __init__(
        self,
        voice_storage: InMemoryVoiceStorage,
        event_storage: Optional["InMemoryEventStorage"] = None,
    ):
        self._voice_storage = voice_storage
        self._event_storage = event_storage or InMemoryEventStorage()
        self._cursors: dict[str, str] = {}

    def get_sync_cursor(self, peer_url: str) -> Optional[str]:
        return self._cursors.get(peer_url)

    def set_sync_cursor(self, peer_url: str, cursor: str) -> None:
        self._cursors[peer_url] = cursor

    def get_voices_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Voice], Optional[str]]:
        return self._voice_storage.get_voices_since(since, namespace, limit)

    def import_voice(self, voice: Voice) -> str:
        return self._voice_storage.import_voice(voice)

    def get_events_since(
        self, since: datetime, namespace: Optional[str], limit: int
    ) -> tuple[list[Event], Optional[str]]:
        return self._event_storage.get_events_since(since, namespace, limit)

    def import_event(self, event: Event) -> str:
        return self._event_storage.import_event(event)


class InMemoryActionStorage:
    """In-memory action storage for testing."""

    def __init__(self):
        # (public_key, action_id, action_type) -> Action
        self._actions: dict[tuple[str, str, ActionType], Action] = {}

    def save_action(self, action: Action) -> None:
        key = (action.public_key, action.action_id, action.action_type)
        self._actions[key] = action

    def get_action(
        self, public_key: str, action_id: str, action_type: ActionType
    ) -> Optional[Action]:
        return self._actions.get((public_key, action_id, action_type))

    def get_actions_for_id(self, action_id: str) -> list[Action]:
        return [
            a for a in self._actions.values()
            if a.action_id == action_id and not a.revoked
        ]

    def get_commitments_for_id(self, action_id: str) -> list[Action]:
        return [
            a for a in self._actions.values()
            if a.action_id == action_id
            and a.action_type == ActionType.COMMITMENT
            and not a.revoked
        ]

    def get_completions_for_id(self, action_id: str) -> list[Action]:
        return [
            a for a in self._actions.values()
            if a.action_id == action_id
            and a.action_type == ActionType.COMPLETION
            and not a.revoked
        ]

    def revoke_action(
        self, public_key: str, action_id: str, action_type: ActionType
    ) -> bool:
        key = (public_key, action_id, action_type)
        if key in self._actions:
            old = self._actions[key]
            self._actions[key] = Action(
                action_id=old.action_id,
                action_type=old.action_type,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                evidence_url=old.evidence_url,
                revoked=True,
            )
            return True
        return False


class InMemoryCommentStorage:
    """In-memory comment storage for testing."""

    def __init__(self):
        self._comments: dict[tuple[str, str], Comment] = {}  # (public_key, entity) -> Comment

    def save_comment(self, comment: Comment) -> None:
        key = (comment.public_key, comment.entity)
        self._comments[key] = comment

    def get_comments_for_entity(self, entity: str) -> list[Comment]:
        comments = [
            c for c in self._comments.values()
            if c.entity == entity and not c.deleted
        ]
        comments.sort(key=lambda c: c.timestamp, reverse=True)
        return comments

    def get_comment_count(self, entity: str) -> int:
        return len([
            c for c in self._comments.values()
            if c.entity == entity and not c.deleted
        ])

    def delete_comment(self, public_key: str, entity: str) -> bool:
        key = (public_key, entity)
        if key in self._comments:
            old = self._comments[key]
            self._comments[key] = Comment(
                entity=old.entity,
                comment_text=old.comment_text,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                jurisdiction=old.jurisdiction,
                stance=old.stance,
                created_at=old.created_at,
                deleted=True,
            )
            return True
        return False


class InMemoryCivicActionEventStorage:
    """In-memory storage for civic action events (Kind 30810)."""

    def __init__(self):
        self._actions: dict[str, CivicActionEvent] = {}  # action_id -> CivicActionEvent

    def save_action_event(self, action: CivicActionEvent) -> None:
        self._actions[action.id] = action

    def get_action_event(self, action_id: str) -> CivicActionEvent | None:
        return self._actions.get(action_id)

    def get_actions_for_initiative(self, initiative_id: str) -> list[CivicActionEvent]:
        return [
            a for a in self._actions.values()
            if a.initiative_id == initiative_id and not a.revoked
        ]

    def revoke_action_event(self, action_id: str, public_key: str) -> bool:
        if action_id in self._actions:
            old = self._actions[action_id]
            if old.public_key != public_key:
                return False  # Only creator can revoke
            self._actions[action_id] = CivicActionEvent(
                id=old.id,
                initiative_id=old.initiative_id,
                action_type=old.action_type,
                description=old.description,
                target=old.target,
                deadline=old.deadline,
                template=old.template,
                target_count=old.target_count,
                deadline_context=old.deadline_context,
                coordination_url=old.coordination_url,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                revoked=True,
            )
            return True
        return False


class InMemoryCivicCommitmentStorage:
    """In-memory storage for civic commitments (Kind 30811)."""

    def __init__(self):
        # (public_key, action_ref) -> CivicCommitment
        self._commitments: dict[tuple[str, str], CivicCommitment] = {}

    def save_commitment(self, commitment: CivicCommitment) -> None:
        key = (commitment.public_key, commitment.action_ref)
        self._commitments[key] = commitment

    def get_commitment(
        self, public_key: str, action_ref: str
    ) -> CivicCommitment | None:
        return self._commitments.get((public_key, action_ref))

    def get_commitments_for_action(self, action_ref: str) -> list[CivicCommitment]:
        return [
            c for c in self._commitments.values()
            if c.action_ref == action_ref and not c.revoked
            and c.status != CommitmentStatus.WITHDRAWN
        ]

    def update_commitment_status(
        self, public_key: str, action_ref: str, status: CommitmentStatus
    ) -> bool:
        key = (public_key, action_ref)
        if key in self._commitments:
            old = self._commitments[key]
            self._commitments[key] = CivicCommitment(
                id=old.id,
                action_ref=old.action_ref,
                status=status,
                public_key=old.public_key,
                signature=old.signature,
                timestamp=old.timestamp,
                revoked=old.revoked,
            )
            return True
        return False


class InMemoryCivicCompletionStorage:
    """In-memory storage for civic completions (Kind 30812)."""

    def __init__(self):
        # (public_key, action_ref) -> CivicCompletion
        self._completions: dict[tuple[str, str], CivicCompletion] = {}

    def save_completion(self, completion: CivicCompletion) -> None:
        key = (completion.public_key, completion.action_ref)
        self._completions[key] = completion

    def get_completion(
        self, public_key: str, action_ref: str
    ) -> CivicCompletion | None:
        return self._completions.get((public_key, action_ref))

    def get_completions_for_action(self, action_ref: str) -> list[CivicCompletion]:
        return [
            c for c in self._completions.values()
            if c.action_ref == action_ref and not c.revoked
        ]


class InMemoryOutcomeStorage:
    """In-memory storage for initiative outcomes."""

    def __init__(self):
        self._outcomes: dict[str, "InitiativeOutcome"] = {}  # outcome_id -> InitiativeOutcome

    def save_outcome(self, outcome) -> None:
        self._outcomes[outcome.id] = outcome

    def get_outcome(self, outcome_id: str):
        return self._outcomes.get(outcome_id)

    def get_outcomes_for_initiative(self, initiative_id: str) -> list:
        return [
            o for o in self._outcomes.values()
            if o.initiative_id == initiative_id
        ]


class InMemoryAttributionStorage:
    """In-memory storage for action attributions."""

    def __init__(self):
        self._attributions: dict[str, "Attribution"] = {}  # attribution_id -> Attribution

    def save_attribution(self, attribution) -> None:
        if attribution.outcome_id is None:
            # Activity-based: upsert by (action_id, public_key)
            for existing_id, existing in list(self._attributions.items()):
                if (existing.outcome_id is None
                        and existing.action_id == attribution.action_id
                        and existing.public_key == attribution.public_key):
                    del self._attributions[existing_id]
                    break
        self._attributions[attribution.id] = attribution

    def get_attributions_for_outcome(self, outcome_id: str) -> list:
        return [
            a for a in self._attributions.values()
            if a.outcome_id == outcome_id
        ]

    def get_attributions_for_user(self, public_key: str) -> list:
        return [
            a for a in self._attributions.values()
            if a.public_key == public_key
        ]


class InMemoryAttestationStorage:
    """In-memory attestation storage for testing."""

    def __init__(self):
        self._codes: dict[str, dict] = {}  # code -> code record
        self._attestations: dict[tuple[str, str], dict] = {}  # (pubkey, jurisdiction) -> record

    def get_code(self, code: str) -> dict | None:
        return self._codes.get(code)

    def redeem_code(self, code: str, public_key: str) -> bool:
        record = self._codes.get(code)
        if not record or record.get("redeemed_by") is not None:
            return False
        record["redeemed_by"] = public_key
        record["redeemed_at"] = datetime.utcnow()
        return True

    def save_attestation(self, attestation: dict) -> None:
        key = (attestation["public_key"], attestation["jurisdiction"])
        self._attestations[key] = attestation

    def get_attestation(self, public_key: str, jurisdiction: str) -> dict | None:
        att = self._attestations.get((public_key, jurisdiction))
        if att and not att.get("revoked", False):
            return att
        return None

    def is_attested(self, public_key: str, jurisdiction: str) -> bool:
        return self.get_attestation(public_key, jurisdiction) is not None

    def get_attested_count(self, jurisdiction: str) -> int:
        return sum(
            1 for (_, j), a in self._attestations.items()
            if j == jurisdiction and not a.get("revoked", False)
        )

    def count_attested_voices(self, entity: str, jurisdiction: str) -> dict:
        # Would need voice storage reference for full impl; simplified for testing
        return {"attested": 0, "unattested": 0}

    def get_code_stats(self, jurisdiction: str) -> dict:
        codes = [c for c in self._codes.values() if c["jurisdiction"] == jurisdiction]
        redeemed = sum(1 for c in codes if c.get("redeemed_by") is not None)
        return {"total_issued": len(codes), "total_redeemed": redeemed}

    def add_code(self, code: str, jurisdiction: str, batch_id: str, expires_at=None) -> None:
        """Add a code (for testing convenience)."""
        self._codes[code] = {
            "code": code,
            "jurisdiction": jurisdiction,
            "batch_id": batch_id,
            "redeemed_by": None,
            "redeemed_at": None,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at,
        }


class InMemoryStorage:
    """Combined in-memory storage for all relay data."""

    def __init__(self):
        self.voices = InMemoryVoiceStorage()
        self.events = InMemoryEventStorage()
        self.actions = InMemoryActionStorage()
        self.subscriptions = InMemorySubscriptionStorage()
        self.provenance = InMemoryProvenanceStorage()
        self.initiatives = InMemoryInitiativeStorage()
        self.sync = InMemorySyncStorage(self.voices, self.events)
        self.comments = InMemoryCommentStorage()
        # New action event storage (Kind 30810/30811/30812)
        self.civic_action_events = InMemoryCivicActionEventStorage()
        self.civic_commitments = InMemoryCivicCommitmentStorage()
        self.civic_completions = InMemoryCivicCompletionStorage()
        self.outcomes = InMemoryOutcomeStorage()
        self.attributions = InMemoryAttributionStorage()
        self.attestations = InMemoryAttestationStorage()

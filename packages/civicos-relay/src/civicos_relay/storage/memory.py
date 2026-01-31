"""In-memory storage implementations for testing."""

from datetime import datetime
from typing import Optional

from civicos_relay.voice.models import Voice, Stance
from civicos_relay.relay.models import (
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


class InMemorySyncStorage:
    """In-memory sync state storage for testing."""

    def __init__(self, voice_storage: InMemoryVoiceStorage):
        self._voice_storage = voice_storage
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


class InMemoryStorage:
    """Combined in-memory storage for all relay data."""

    def __init__(self):
        self.voices = InMemoryVoiceStorage()
        self.subscriptions = InMemorySubscriptionStorage()
        self.provenance = InMemoryProvenanceStorage()
        self.initiatives = InMemoryInitiativeStorage()
        self.sync = InMemorySyncStorage(self.voices)

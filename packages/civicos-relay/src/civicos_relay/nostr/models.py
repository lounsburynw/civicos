"""
Nostr event models for CivicOS.

Provides Pydantic models for Nostr events with civic-specific validation.
All models implement NIP-01 event structure with type-safe civic extensions.
"""

import json
from datetime import datetime
from enum import Enum
from typing import Literal, Any

from pydantic import BaseModel, Field, field_validator, model_validator

from civicos_relay.nostr.crypto import (
    compute_event_id,
    verify_event_signature,
    verify_event_id,
    NostrKeyPair,
    sign_event,
)
from civicos_relay.nostr.kinds import (
    CIVIC_VOICE,
    CIVIC_ENTITY,
    CIVIC_SUBSCRIPTION,
    CIVIC_PROVENANCE,
    CIVIC_VOUCH,
    CIVIC_EVENT_NOTIFICATION,
    KEY_LINK_ATTESTATION,
    VALID_STANCES,
    VALID_ENTITY_TYPES,
    VALID_OUTCOMES,
    TAG_D,
    TAG_J,
    TAG_T,
    TAG_P,
    TAG_STANCE,
    TAG_TYPE,
    TAG_TITLE,
    TAG_OLD_KEY,
    TAG_OLD_SIG,
    TAG_EVENT_TYPE,
    TAG_A,
    TAG_THRESHOLD,
    is_addressable,
)


class Stance(str, Enum):
    """Civic voice stance values."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    WATCHING = "watching"


class EntityType(str, Enum):
    """Civic entity types."""

    DECISION = "decision"
    INITIATIVE = "initiative"
    AGENDA_ITEM = "agenda_item"
    MEETING = "meeting"


class Outcome(str, Enum):
    """Entity outcome values."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    DEFERRED = "deferred"
    PASSED = "passed"
    FAILED = "failed"


class NostrEvent(BaseModel):
    """
    Base Nostr event model per NIP-01.

    All events have: id, pubkey, created_at, kind, tags, content, sig
    """

    id: str = Field(..., description="32-byte hex event ID (SHA256 of serialized event)")
    pubkey: str = Field(..., description="32-byte hex x-only public key")
    created_at: int = Field(..., description="Unix timestamp in seconds")
    kind: int = Field(..., description="Event kind number")
    tags: list[list[str]] = Field(default_factory=list, description="Event tags")
    content: str = Field(default="", description="Event content")
    sig: str = Field(..., description="64-byte hex Schnorr signature")

    @field_validator("id", "pubkey", "sig")
    @classmethod
    def validate_hex(cls, v: str, info) -> str:
        """Validate hex string format."""
        field_name = info.field_name
        expected_len = {"id": 64, "pubkey": 64, "sig": 128}[field_name]
        if len(v) != expected_len:
            raise ValueError(f"{field_name} must be {expected_len} hex chars")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError(f"{field_name} must be valid hex")
        return v

    @field_validator("created_at")
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Validate timestamp is reasonable."""
        if v < 0:
            raise ValueError("created_at must be non-negative")
        # Allow timestamps up to year 2100
        if v > 4102444800:
            raise ValueError("created_at too far in future")
        return v

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: int) -> int:
        """Validate kind is non-negative."""
        if v < 0:
            raise ValueError("kind must be non-negative")
        return v

    def verify_id(self) -> bool:
        """Verify event ID matches content."""
        return verify_event_id(
            self.id, self.pubkey, self.created_at, self.kind, self.tags, self.content
        )

    def verify_signature(self) -> bool:
        """Verify Schnorr signature."""
        return verify_event_signature(self.id, self.pubkey, self.sig)

    def verify(self) -> bool:
        """Verify both ID and signature."""
        return self.verify_id() and self.verify_signature()

    def get_tag(self, name: str) -> str | None:
        """Get first tag value by name."""
        for tag in self.tags:
            if len(tag) >= 2 and tag[0] == name:
                return tag[1]
        return None

    def get_tags(self, name: str) -> list[str]:
        """Get all tag values by name."""
        return [tag[1] for tag in self.tags if len(tag) >= 2 and tag[0] == name]

    def get_d_tag(self) -> str | None:
        """Get d-tag for addressable events."""
        return self.get_tag(TAG_D)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NostrEvent":
        """Create event from dictionary."""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "pubkey": self.pubkey,
            "created_at": self.created_at,
            "kind": self.kind,
            "tags": self.tags,
            "content": self.content,
            "sig": self.sig,
        }


# =============================================================================
# Tag Builder Helpers
# =============================================================================


def build_tags(
    d_tag: str | None = None,
    jurisdiction: str | None = None,
    topics: list[str] | None = None,
    **kwargs: str | list[str],
) -> list[list[str]]:
    """
    Build a tag list with common civic tags.

    Args:
        d_tag: Identifier for addressable events
        jurisdiction: Jurisdiction code
        topics: List of topic tags
        **kwargs: Additional tags (key=value or key=[values])

    Returns:
        List of tag arrays
    """
    tags = []

    if d_tag is not None:
        tags.append([TAG_D, d_tag])

    if jurisdiction is not None:
        tags.append([TAG_J, jurisdiction])

    if topics:
        for topic in topics:
            tags.append([TAG_T, topic])

    for key, value in kwargs.items():
        if isinstance(value, list):
            for v in value:
                tags.append([key, str(v)])
        else:
            tags.append([key, str(value)])

    return tags


# =============================================================================
# Civic Voice Event (Kind 30800)
# =============================================================================


class CivicVoiceEvent(NostrEvent):
    """
    Civic Voice event (kind 30800).

    Represents a citizen's stance on a civic entity.
    Addressable by kind:pubkey:d-tag (one voice per key per entity).
    """

    kind: Literal[30800] = CIVIC_VOICE

    @property
    def entity_id(self) -> str:
        """Get the entity identifier from d-tag."""
        d = self.get_d_tag()
        if d is None:
            raise ValueError("Voice event missing d-tag")
        return d

    @property
    def jurisdiction(self) -> str:
        """Get jurisdiction from j-tag."""
        j = self.get_tag(TAG_J)
        if j is None:
            raise ValueError("Voice event missing j-tag")
        return j

    @property
    def stance(self) -> Stance:
        """Get stance from stance tag."""
        s = self.get_tag(TAG_STANCE)
        if s is None:
            raise ValueError("Voice event missing stance tag")
        return Stance(s)

    @property
    def topics(self) -> list[str]:
        """Get all topic tags."""
        return self.get_tags(TAG_T)

    @property
    def is_revoked(self) -> bool:
        """Check if voice has been revoked."""
        return self.content.lower() == "revoked"

    @model_validator(mode="after")
    def validate_voice_tags(self) -> "CivicVoiceEvent":
        """Validate required voice tags are present."""
        if self.get_d_tag() is None:
            raise ValueError("Voice event requires d-tag")
        if self.get_tag(TAG_J) is None:
            raise ValueError("Voice event requires j-tag (jurisdiction)")
        stance = self.get_tag(TAG_STANCE)
        if stance is None:
            raise ValueError("Voice event requires stance tag")
        if stance not in VALID_STANCES:
            raise ValueError(f"Invalid stance: {stance}")
        return self

    @classmethod
    def create(
        cls,
        keypair: NostrKeyPair,
        entity_id: str,
        jurisdiction: str,
        stance: Stance | str,
        topics: list[str] | None = None,
        content: str = "",
        created_at: int | None = None,
    ) -> "CivicVoiceEvent":
        """
        Create a new signed voice event.

        Args:
            keypair: Nostr keypair for signing
            entity_id: Entity identifier (d-tag)
            jurisdiction: Jurisdiction code (j-tag)
            stance: Voice stance
            topics: Optional topic tags
            content: Optional content (or "revoked" to revoke)
            created_at: Optional timestamp (defaults to now)

        Returns:
            Signed CivicVoiceEvent
        """
        if created_at is None:
            created_at = int(datetime.utcnow().timestamp())

        if isinstance(stance, Stance):
            stance_str = stance.value
        else:
            stance_str = stance

        tags = build_tags(
            d_tag=entity_id,
            jurisdiction=jurisdiction,
            topics=topics,
            stance=stance_str,
        )

        event_id, pubkey, sig = sign_event(
            keypair, created_at, CIVIC_VOICE, tags, content
        )

        return cls(
            id=event_id,
            pubkey=pubkey,
            created_at=created_at,
            kind=CIVIC_VOICE,
            tags=tags,
            content=content,
            sig=sig,
        )


# =============================================================================
# Civic Entity Event (Kind 30801)
# =============================================================================


class EntityContent(BaseModel):
    """Content structure for civic entity events."""

    description: str = ""
    outcome: Outcome | None = None

    model_config = {"extra": "allow"}  # Allow additional fields


class CivicEntityEvent(NostrEvent):
    """
    Civic Entity event (kind 30801).

    Represents a civic decision, initiative, meeting, or agenda item.
    """

    kind: Literal[30801] = CIVIC_ENTITY

    @property
    def entity_id(self) -> str:
        """Get the entity identifier from d-tag."""
        d = self.get_d_tag()
        if d is None:
            raise ValueError("Entity event missing d-tag")
        return d

    @property
    def jurisdiction(self) -> str:
        """Get jurisdiction from j-tag."""
        j = self.get_tag(TAG_J)
        if j is None:
            raise ValueError("Entity event missing j-tag")
        return j

    @property
    def entity_type(self) -> EntityType:
        """Get entity type from type tag."""
        t = self.get_tag(TAG_TYPE)
        if t is None:
            raise ValueError("Entity event missing type tag")
        return EntityType(t)

    @property
    def title(self) -> str:
        """Get title from title tag."""
        t = self.get_tag(TAG_TITLE)
        if t is None:
            raise ValueError("Entity event missing title tag")
        return t

    @property
    def topics(self) -> list[str]:
        """Get all topic tags."""
        return self.get_tags(TAG_T)

    @property
    def parsed_content(self) -> EntityContent:
        """Parse content as EntityContent."""
        if not self.content:
            return EntityContent()
        try:
            data = json.loads(self.content)
            return EntityContent(**data)
        except (json.JSONDecodeError, ValueError):
            return EntityContent()

    @model_validator(mode="after")
    def validate_entity_tags(self) -> "CivicEntityEvent":
        """Validate required entity tags are present."""
        if self.get_d_tag() is None:
            raise ValueError("Entity event requires d-tag")
        if self.get_tag(TAG_J) is None:
            raise ValueError("Entity event requires j-tag (jurisdiction)")
        etype = self.get_tag(TAG_TYPE)
        if etype is None:
            raise ValueError("Entity event requires type tag")
        if etype not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {etype}")
        if self.get_tag(TAG_TITLE) is None:
            raise ValueError("Entity event requires title tag")
        return self

    @classmethod
    def create(
        cls,
        keypair: NostrKeyPair,
        entity_id: str,
        jurisdiction: str,
        entity_type: EntityType | str,
        title: str,
        topics: list[str] | None = None,
        description: str = "",
        outcome: Outcome | str | None = None,
        extra_content: dict[str, Any] | None = None,
        created_at: int | None = None,
    ) -> "CivicEntityEvent":
        """Create a new signed entity event."""
        if created_at is None:
            created_at = int(datetime.utcnow().timestamp())

        if isinstance(entity_type, EntityType):
            type_str = entity_type.value
        else:
            type_str = entity_type

        tags = build_tags(
            d_tag=entity_id,
            jurisdiction=jurisdiction,
            topics=topics,
            type=type_str,
            title=title,
        )

        # Build content JSON
        content_dict: dict[str, Any] = {"description": description}
        if outcome:
            content_dict["outcome"] = outcome.value if isinstance(outcome, Outcome) else outcome
        if extra_content:
            content_dict.update(extra_content)
        content = json.dumps(content_dict)

        event_id, pubkey, sig = sign_event(
            keypair, created_at, CIVIC_ENTITY, tags, content
        )

        return cls(
            id=event_id,
            pubkey=pubkey,
            created_at=created_at,
            kind=CIVIC_ENTITY,
            tags=tags,
            content=content,
            sig=sig,
        )


# =============================================================================
# Civic Subscription Event (Kind 30802)
# =============================================================================


class CivicSubscriptionEvent(NostrEvent):
    """
    Civic Subscription event (kind 30802).

    User's subscription criteria for notifications.
    """

    kind: Literal[30802] = CIVIC_SUBSCRIPTION

    @property
    def subscription_id(self) -> str:
        """Get subscription identifier from d-tag."""
        d = self.get_d_tag()
        if d is None:
            raise ValueError("Subscription event missing d-tag")
        return d

    @property
    def jurisdiction_filter(self) -> str | None:
        """Get jurisdiction filter."""
        return self.get_tag(TAG_J)

    @property
    def topic_filters(self) -> list[str]:
        """Get topic filters."""
        return self.get_tags(TAG_T)

    @property
    def type_filter(self) -> str | None:
        """Get entity type filter."""
        return self.get_tag(TAG_TYPE)

    @property
    def threshold(self) -> int | None:
        """Get voice count threshold."""
        t = self.get_tag(TAG_THRESHOLD)
        if t is None:
            return None
        try:
            return int(t)
        except ValueError:
            return None

    @model_validator(mode="after")
    def validate_subscription_tags(self) -> "CivicSubscriptionEvent":
        """Validate subscription has d-tag."""
        if self.get_d_tag() is None:
            raise ValueError("Subscription event requires d-tag")
        return self


# =============================================================================
# Civic Provenance Event (Kind 10800)
# =============================================================================


class CivicProvenanceEvent(NostrEvent):
    """
    Civic Provenance event (kind 10800).

    Self-signed reputation record for a pubkey.
    Replaceable (one per pubkey).
    """

    kind: Literal[10800] = CIVIC_PROVENANCE

    @property
    def first_voice_date(self) -> str | None:
        """Get date of first voice."""
        return self.get_tag("first-voice")

    @property
    def total_voices(self) -> int | None:
        """Get total voice count."""
        v = self.get_tag("total-voices")
        if v is None:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    @property
    def entities_touched(self) -> int | None:
        """Get count of entities voiced on."""
        v = self.get_tag("entities-touched")
        if v is None:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    @property
    def primary_jurisdiction(self) -> str | None:
        """Get primary jurisdiction."""
        return self.get_tag(TAG_J)

    @property
    def attestations(self) -> list[tuple[str, str, str]]:
        """
        Get attestation records.

        Returns list of (type, jurisdiction, date) tuples.
        """
        result = []
        for tag in self.tags:
            if len(tag) >= 4 and tag[0] == "attestation":
                result.append((tag[1], tag[2], tag[3]))
        return result


# =============================================================================
# Civic Vouch Event (Kind 1800)
# =============================================================================


class CivicVouchEvent(NostrEvent):
    """
    Civic Vouch event (kind 1800).

    One citizen vouching for another.
    """

    kind: Literal[1800] = CIVIC_VOUCH

    @property
    def vouchee(self) -> str:
        """Get vouchee pubkey."""
        p = self.get_tag(TAG_P)
        if p is None:
            raise ValueError("Vouch event missing p-tag")
        return p

    @property
    def jurisdiction(self) -> str | None:
        """Get jurisdiction context."""
        return self.get_tag(TAG_J)

    @model_validator(mode="after")
    def validate_vouch_tags(self) -> "CivicVouchEvent":
        """Validate vouch has p-tag."""
        if self.get_tag(TAG_P) is None:
            raise ValueError("Vouch event requires p-tag (vouchee)")
        return self

    @classmethod
    def create(
        cls,
        keypair: NostrKeyPair,
        vouchee_pubkey: str,
        jurisdiction: str | None = None,
        content: str = "",
        created_at: int | None = None,
    ) -> "CivicVouchEvent":
        """Create a new signed vouch event."""
        if created_at is None:
            created_at = int(datetime.utcnow().timestamp())

        tags: list[list[str]] = [[TAG_P, vouchee_pubkey]]
        if jurisdiction:
            tags.append([TAG_J, jurisdiction])

        event_id, pubkey, sig = sign_event(
            keypair, created_at, CIVIC_VOUCH, tags, content
        )

        return cls(
            id=event_id,
            pubkey=pubkey,
            created_at=created_at,
            kind=CIVIC_VOUCH,
            tags=tags,
            content=content,
            sig=sig,
        )


# =============================================================================
# Civic Event Notification (Kind 1801)
# =============================================================================


class CivicEventNotificationEvent(NostrEvent):
    """
    Civic Event Notification (kind 1801).

    Relay notification about civic events.
    """

    kind: Literal[1801] = CIVIC_EVENT_NOTIFICATION

    @property
    def event_type(self) -> str:
        """Get notification event type."""
        t = self.get_tag(TAG_EVENT_TYPE)
        if t is None:
            raise ValueError("Notification event missing event-type tag")
        return t

    @property
    def jurisdiction(self) -> str:
        """Get jurisdiction."""
        j = self.get_tag(TAG_J)
        if j is None:
            raise ValueError("Notification event missing j-tag")
        return j

    @property
    def referenced_event(self) -> str | None:
        """Get referenced addressable event."""
        return self.get_tag(TAG_A)

    @model_validator(mode="after")
    def validate_notification_tags(self) -> "CivicEventNotificationEvent":
        """Validate notification has required tags."""
        if self.get_tag(TAG_EVENT_TYPE) is None:
            raise ValueError("Notification event requires event-type tag")
        if self.get_tag(TAG_J) is None:
            raise ValueError("Notification event requires j-tag")
        return self


# =============================================================================
# Key Link Attestation Event (Kind 1802)
# =============================================================================


class KeyLinkAttestationEvent(NostrEvent):
    """
    Key Link Attestation event (kind 1802).

    Links old CivicOS key (SECP256R1) to new Nostr key (secp256k1).
    """

    kind: Literal[1802] = KEY_LINK_ATTESTATION

    @property
    def old_key(self) -> str:
        """Get old SECP256R1 pubkey hex."""
        k = self.get_tag(TAG_OLD_KEY)
        if k is None:
            raise ValueError("Key link event missing old-key tag")
        return k

    @property
    def old_signature(self) -> str:
        """Get ECDSA signature from old key."""
        s = self.get_tag(TAG_OLD_SIG)
        if s is None:
            raise ValueError("Key link event missing old-sig tag")
        return s

    @model_validator(mode="after")
    def validate_key_link_tags(self) -> "KeyLinkAttestationEvent":
        """Validate key link has required tags."""
        if self.get_tag(TAG_OLD_KEY) is None:
            raise ValueError("Key link event requires old-key tag")
        if self.get_tag(TAG_OLD_SIG) is None:
            raise ValueError("Key link event requires old-sig tag")
        return self


# =============================================================================
# Event Type Detection
# =============================================================================


def parse_event(data: dict[str, Any]) -> NostrEvent:
    """
    Parse a raw event dict into the appropriate typed model.

    Args:
        data: Raw event dictionary

    Returns:
        Typed NostrEvent subclass based on kind
    """
    kind = data.get("kind")

    if kind == CIVIC_VOICE:
        return CivicVoiceEvent(**data)
    elif kind == CIVIC_ENTITY:
        return CivicEntityEvent(**data)
    elif kind == CIVIC_SUBSCRIPTION:
        return CivicSubscriptionEvent(**data)
    elif kind == CIVIC_PROVENANCE:
        return CivicProvenanceEvent(**data)
    elif kind == CIVIC_VOUCH:
        return CivicVouchEvent(**data)
    elif kind == CIVIC_EVENT_NOTIFICATION:
        return CivicEventNotificationEvent(**data)
    elif kind == KEY_LINK_ATTESTATION:
        return KeyLinkAttestationEvent(**data)
    else:
        return NostrEvent(**data)

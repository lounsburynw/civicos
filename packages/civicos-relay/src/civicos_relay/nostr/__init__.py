"""
Nostr protocol implementation for CivicOS.

This module provides NIP-01 compliant cryptographic operations and event handling
for civic coordination through the Nostr network.
"""

from civicos_relay.nostr.crypto import (
    NostrKeyPair,
    compute_event_id,
    sign_event,
    verify_event_signature,
    verify_event_id,
    verify_event,
)

from civicos_relay.nostr.kinds import (
    CIVIC_VOICE,
    CIVIC_ENTITY,
    CIVIC_SUBSCRIPTION,
    CIVIC_PROVENANCE,
    CIVIC_VOUCH,
    CIVIC_EVENT_NOTIFICATION,
    KEY_LINK_ATTESTATION,
    is_addressable,
    is_replaceable,
    is_civic_kind,
)

from civicos_relay.nostr.models import (
    NostrEvent,
    CivicVoiceEvent,
    CivicEntityEvent,
    CivicSubscriptionEvent,
    CivicProvenanceEvent,
    CivicVouchEvent,
    CivicEventNotificationEvent,
    KeyLinkAttestationEvent,
    Stance,
    EntityType,
    Outcome,
    parse_event,
    build_tags,
)

from civicos_relay.nostr.storage import (
    NostrEventStorage,
    NostrKeyLinkStorage,
    EventFilter,
    VoiceCounts,
)

from civicos_relay.nostr.relay import (
    NostrRelay,
    Connection,
    Subscription as RelaySubscription,
    create_websocket_handler,
)

from civicos_relay.nostr.migration import (
    KeyLinkService,
    LinkedProvenanceService,
    build_link_message,
    verify_old_key_signature,
    create_key_link_handler,
)

from civicos_relay.nostr.compat import (
    NostrCompatAdapter,
    LegacyVoice,
    LegacyVoiceCount,
    LegacyVoiceRequest,
    create_compat_router,
    nostr_event_to_legacy_voice,
)

__all__ = [
    # Crypto
    "NostrKeyPair",
    "compute_event_id",
    "sign_event",
    "verify_event_signature",
    "verify_event_id",
    "verify_event",
    # Kinds
    "CIVIC_VOICE",
    "CIVIC_ENTITY",
    "CIVIC_SUBSCRIPTION",
    "CIVIC_PROVENANCE",
    "CIVIC_VOUCH",
    "CIVIC_EVENT_NOTIFICATION",
    "KEY_LINK_ATTESTATION",
    "is_addressable",
    "is_replaceable",
    "is_civic_kind",
    # Models
    "NostrEvent",
    "CivicVoiceEvent",
    "CivicEntityEvent",
    "CivicSubscriptionEvent",
    "CivicProvenanceEvent",
    "CivicVouchEvent",
    "CivicEventNotificationEvent",
    "KeyLinkAttestationEvent",
    "Stance",
    "EntityType",
    "Outcome",
    "parse_event",
    "build_tags",
    # Storage
    "NostrEventStorage",
    "NostrKeyLinkStorage",
    "EventFilter",
    "VoiceCounts",
    # Relay
    "NostrRelay",
    "Connection",
    "RelaySubscription",
    "create_websocket_handler",
    # Migration
    "KeyLinkService",
    "LinkedProvenanceService",
    "build_link_message",
    "verify_old_key_signature",
    "create_key_link_handler",
    # Compatibility
    "NostrCompatAdapter",
    "LegacyVoice",
    "LegacyVoiceCount",
    "LegacyVoiceRequest",
    "create_compat_router",
    "nostr_event_to_legacy_voice",
]

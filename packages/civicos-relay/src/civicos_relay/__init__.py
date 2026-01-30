"""
CivicOS Relay

Federation-ready civic coordination relay:
- Voice: Public expression of civic interest with cryptographic signing
- Relay: Event routing and subscription management
- Provenance: Trust signals for voice quality
- Sync: Voice and event synchronization between peer relays
- Identity: Relay keypair management and signing
"""

# Voice
from civicos_relay.voice.models import Voice, Stance, VoiceCount
from civicos_relay.voice.service import VoiceService
from civicos_relay.voice.crypto import KeyPair, sign_voice, verify_voice

# Relay
from civicos_relay.relay.models import (
    Subscription,
    Event,
    EventType,
    MatchCriteria,
    DeliveryConfig,
    DeliveryMethod,
)
from civicos_relay.relay.service import RelayService

# Provenance
from civicos_relay.provenance.models import KeyProvenance, ProvenanceSummary
from civicos_relay.provenance.service import ProvenanceService

# Identity
from civicos_relay.identity import RelayIdentity, RelayConfig, PeerConfig

# Sync
from civicos_relay.sync import SyncService, SyncProtocol

__all__ = [
    # Voice
    "Voice",
    "Stance",
    "VoiceCount",
    "VoiceService",
    "KeyPair",
    "sign_voice",
    "verify_voice",
    # Relay
    "Subscription",
    "Event",
    "EventType",
    "MatchCriteria",
    "DeliveryConfig",
    "DeliveryMethod",
    "RelayService",
    # Provenance
    "KeyProvenance",
    "ProvenanceSummary",
    "ProvenanceService",
    # Identity
    "RelayIdentity",
    "RelayConfig",
    "PeerConfig",
    # Sync
    "SyncService",
    "SyncProtocol",
]

"""
Nostr kind constants for CivicOS.

Defines civic-specific NIP kinds in the 30800-30899 addressable range
and 1800-1899 regular range.

Kind ranges per NIP-01:
- 0: Metadata
- 1: Short text note
- 30000-39999: Addressable (replaceable by kind:pubkey:d-tag)
- 10000-19999: Replaceable (replaced by kind:pubkey)
- 1000-9999: Regular events
"""

# =============================================================================
# Addressable Civic Kinds (30800-30899)
# These use d-tag for unique addressing: kind:pubkey:d-tag
# =============================================================================

CIVIC_VOICE = 30800
"""
Civic Voice - A citizen's stance on a civic entity.

Tags:
- d: Entity identifier (required, e.g., "decision:city-san-rafael:2026-02-03:item-6a")
- j: Jurisdiction (required, e.g., "city-san-rafael")
- stance: "support" | "oppose" | "watching" (required)
- t: Topic tags (optional, multiple allowed)

Content: Empty string (voice is in tags) or optional comment

Addressable by kind:pubkey:d-tag, so one voice per key per entity.
Revocation: Publish with content: "revoked"
"""

CIVIC_ENTITY = 30801
"""
Civic Entity - A civic decision, initiative, meeting, or agenda item.

Tags:
- d: Entity identifier (required)
- j: Jurisdiction (required)
- type: "decision" | "initiative" | "agenda_item" | "meeting" (required)
- title: Human-readable title (required)
- t: Topic tags (optional, multiple allowed)

Content: JSON object with entity details:
- description: string
- outcome: "pending" | "approved" | "denied" | "deferred" | "passed" | "failed"
- Additional type-specific fields

Official entities signed by jurisdiction key (NIP-05 verified).
Community initiatives signed by creator key.
"""

CIVIC_SUBSCRIPTION = 30802
"""
Civic Subscription - User's subscription criteria for notifications.

Tags:
- d: Subscription identifier (e.g., "sub:city-san-rafael:housing")
- j: Jurisdiction filter (optional)
- t: Topic filters (optional, multiple allowed)
- type: Entity type filter (optional)
- threshold: Voice count threshold for notification (optional)

Content: NIP-44 encrypted delivery configuration JSON:
- endpoint: Webhook URL or push notification config
- preferences: Notification frequency, format, etc.

Criteria in public tags enable relay-side filtering.
Delivery config encrypted for user privacy.
"""

CIVIC_COMMENT = 30803
"""
Civic Comment - A public comment on a civic entity.

Tags:
- d: Entity identifier (required)
- j: Jurisdiction (optional)
- stance: "support" | "oppose" | "watching" (optional)

Content: The comment text

Addressable by kind:pubkey:d-tag (one comment per key per entity).
Revocation: Publish with content "deleted"
"""

# =============================================================================
# Replaceable Civic Kinds (10800-10899)
# These are replaced by kind:pubkey (one per pubkey)
# =============================================================================

CIVIC_PROVENANCE = 10800
"""
Civic Provenance - Self-signed reputation record for a pubkey.

Tags:
- first-voice: ISO date of first voice (e.g., "2025-09-01")
- total-voices: Total voice count
- entities-touched: Number of unique entities voiced on
- j: Primary jurisdiction (optional)
- attestation: Attestation type, jurisdiction, date (optional, multiple allowed)
  e.g., ["attestation", "physical", "city-san-rafael", "2026-01-15"]

Content: Empty string

Self-signed by the subject pubkey. Replaceable (one per pubkey).
Relay computes and validates these values from voice history.
"""

# =============================================================================
# Regular Civic Kinds (1800-1899)
# These are regular events, not replaceable
# =============================================================================

CIVIC_VOUCH = 1800
"""
Civic Vouch - One citizen vouching for another.

Tags:
- p: Vouchee pubkey (required)
- j: Jurisdiction context (optional)

Content: Optional description of relationship

Used for social attestation in the web of trust.
"""

CIVIC_EVENT_NOTIFICATION = 1801
"""
Civic Event Notification - Relay notification about civic events.

Tags:
- event-type: Type of notification (required)
  e.g., "agenda_published", "voice_threshold", "meeting_scheduled"
- j: Jurisdiction (required)
- a: Reference to addressable event (optional)
  e.g., "30801:<pubkey>:meeting:city-san-rafael:2026-02-03"

Content: JSON notification payload with event-specific details

Signed by relay's pubkey to establish notification provenance.
"""

KEY_LINK_ATTESTATION = 1802
"""
Key Link Attestation - Links old CivicOS key to new Nostr key.

Tags:
- old-key: Old SECP256R1 pubkey hex (required)
- old-sig: ECDSA signature proving old key ownership (required)
  The old key signs: "civicos:link:v1:<new_pubkey>"

Content: "Key migration attestation: I control both keys"

The new (secp256k1) key signs this Nostr event normally.
Relay validates both signatures and merges provenance.
"""

# =============================================================================
# Tag Names
# =============================================================================

TAG_D = "d"  # Identifier for addressable events
TAG_J = "j"  # Jurisdiction
TAG_T = "t"  # Topic
TAG_P = "p"  # Pubkey reference
TAG_E = "e"  # Event reference
TAG_A = "a"  # Addressable event reference (kind:pubkey:d-tag)
TAG_STANCE = "stance"
TAG_TYPE = "type"
TAG_TITLE = "title"
TAG_THRESHOLD = "threshold"
TAG_OLD_KEY = "old-key"
TAG_OLD_SIG = "old-sig"
TAG_EVENT_TYPE = "event-type"
TAG_ATTESTATION = "attestation"
TAG_FIRST_VOICE = "first-voice"
TAG_TOTAL_VOICES = "total-voices"
TAG_ENTITIES_TOUCHED = "entities-touched"

# =============================================================================
# Stance Values
# =============================================================================

STANCE_SUPPORT = "support"
STANCE_OPPOSE = "oppose"
STANCE_WATCHING = "watching"

VALID_STANCES = {STANCE_SUPPORT, STANCE_OPPOSE, STANCE_WATCHING}

# =============================================================================
# Entity Types
# =============================================================================

ENTITY_DECISION = "decision"
ENTITY_INITIATIVE = "initiative"
ENTITY_AGENDA_ITEM = "agenda_item"
ENTITY_MEETING = "meeting"

VALID_ENTITY_TYPES = {ENTITY_DECISION, ENTITY_INITIATIVE, ENTITY_AGENDA_ITEM, ENTITY_MEETING}

# =============================================================================
# Outcome Values
# =============================================================================

OUTCOME_PENDING = "pending"
OUTCOME_APPROVED = "approved"
OUTCOME_DENIED = "denied"
OUTCOME_DEFERRED = "deferred"
OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"

VALID_OUTCOMES = {
    OUTCOME_PENDING,
    OUTCOME_APPROVED,
    OUTCOME_DENIED,
    OUTCOME_DEFERRED,
    OUTCOME_PASSED,
    OUTCOME_FAILED,
}

# =============================================================================
# Kind Ranges
# =============================================================================


def is_addressable(kind: int) -> bool:
    """Check if kind is addressable (30000-39999)."""
    return 30000 <= kind < 40000


def is_replaceable(kind: int) -> bool:
    """Check if kind is replaceable (10000-19999)."""
    return 10000 <= kind < 20000


def is_civic_kind(kind: int) -> bool:
    """Check if kind is a CivicOS-defined kind."""
    return kind in {
        CIVIC_VOICE,
        CIVIC_ENTITY,
        CIVIC_SUBSCRIPTION,
        CIVIC_COMMENT,
        CIVIC_PROVENANCE,
        CIVIC_VOUCH,
        CIVIC_EVENT_NOTIFICATION,
        KEY_LINK_ATTESTATION,
    }

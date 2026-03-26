# Nostr Event Schema Reference

CivicOS uses Nostr event kinds in the 1800-1899, 10800-10899, and 30800-30899 ranges. All events use **secp256k1 Schnorr signatures** (BIP-340).

This document provides the exact tag structures needed to construct valid CivicOS events in any language.

## Event Categories

| Range | Category | Behavior |
|-------|----------|----------|
| 30800-30899 | Addressable | Replaced by `kind:pubkey:d-tag` — one per identity per d-tag |
| 10800-10899 | Replaceable | Replaced by `kind:pubkey` — one per identity |
| 1800-1899 | Regular | Not replaceable — multiple allowed per identity |

---

## Addressable Events (30800-30899)

### Kind 30800: Voice

A citizen's stance on a civic entity. One voice per key per entity (new stance replaces old).

**Tags:**
```json
[
  ["d", "decision:city-san-rafael:proudcity-city-san-rafael-city-council-february-3-2026-tuesday:06"],
  ["j", "city-san-rafael"],
  ["stance", "support"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Entity identifier |
| `j` | Yes | Jurisdiction ID |
| `stance` | Yes | `support`, `oppose`, `watching` |
| `t` | No | Topic tags (multiple allowed) |

**Content:** Empty string (or `"revoked"` to revoke)

### Kind 30803: Comment

A public comment on a civic entity. One comment per key per entity.

**Tags:**
```json
[
  ["d", "decision:city-san-rafael:proudcity-city-san-rafael-city-council-february-3-2026-tuesday:06"],
  ["j", "city-san-rafael"],
  ["stance", "support"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Entity identifier |
| `j` | No | Jurisdiction ID |
| `stance` | No | `support`, `oppose`, `watching` |

**Content:** Comment text (or `"deleted"` to soft-delete)

### Kind 30810: Civic Action

Defines an action that users can commit to and complete (e.g., attend a meeting, write a letter).

**Tags:**
```json
[
  ["d", "action:initiative-id:written_comment:a1b2c3"],
  ["j", "city-san-rafael"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Format: `action:{initiative}:{type}:{hash}` |
| `j` | Yes | Jurisdiction ID |

**Content:** JSON object:
```json
{
  "initiative_id": "initiative:city-san-rafael:2026-03-01:abc123",
  "action_type": "written_comment",
  "description": "Write to the planning commission about the housing proposal",
  "target": "planning@cityofsanrafael.org",
  "deadline": "2026-03-15T00:00:00",
  "template": "Dear Commissioners, ...",
  "target_count": 50,
  "coordination_url": "https://signal.group/..."
}
```

**Action types:** `written_comment`, `attend_meeting`, `public_comment`, `contact_official`, `signature`, `share`, `custom`

### Kind 30811: Commitment

A user's commitment to take a civic action.

**Tags:**
```json
[
  ["d", "commit:pubkey_hex:action-d-tag"],
  ["a", "30810:creator_pubkey:action-d-tag"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Format: `commit:{pubkey}:{action-d-tag}` |
| `a` | Yes | Reference to kind 30810 action |

**Content:** Empty string

### Kind 30812: Completion

Evidence of completing a civic action.

**Tags:**
```json
[
  ["d", "complete:pubkey_hex:action-d-tag"],
  ["a", "30810:creator_pubkey:action-d-tag"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Format: `complete:{pubkey}:{action-d-tag}` |
| `a` | Yes | Reference to kind 30810 action |

**Content:** JSON object:
```json
{
  "evidence_type": "email_confirmation",
  "evidence_content": "Confirmation #12345",
  "completed_at": "2026-03-10T14:30:00"
}
```

**Evidence types:** `self_report`, `email_confirmation`, `attendance_check`, `verified`

### Kind 30850: Attestation

Proof of physical presence, issued by a trusted organization's signer (not the subject).

**Tags:**
```json
[
  ["d", "attest:city-san-rafael:subject_pubkey_hex"],
  ["p", "subject_pubkey_hex"],
  ["j", "city-san-rafael"],
  ["type", "physical"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Format: `attest:{jurisdiction}:{subject_pubkey}` |
| `p` | Yes | Subject's public key |
| `j` | Yes | Jurisdiction |
| `type` | Yes | `physical`, `community-vouched`, `mail` |

**Content:** `"civicos:attestation:v1:{jurisdiction}:{type}:{created_at}"`

**Signed by:** Issuer keypair (not the subject). One attestation per pubkey per jurisdiction.

### Kind 30801: Entity

A civic entity record (decision, meeting, agenda item, initiative).

**Tags:**
```json
[
  ["d", "decision:city-san-rafael:proudcity-city-san-rafael-city-council-february-3-2026-tuesday:06"],
  ["j", "city-san-rafael"],
  ["type", "decision"],
  ["title", "Housing Accountability Act Amendment"],
  ["t", "housing"],
  ["t", "zoning"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Entity identifier |
| `j` | Yes | Jurisdiction |
| `type` | Yes | `decision`, `initiative`, `agenda_item`, `meeting` |
| `title` | Yes | Human-readable title |
| `t` | No | Topic tags (multiple allowed) |

**Content:** JSON with type-specific fields

### Kind 30802: Subscription

Topic/event subscription with encrypted delivery config.

**Tags:**
```json
[
  ["d", "sub:city-san-rafael:housing"],
  ["j", "city-san-rafael"],
  ["t", "housing"],
  ["threshold", "10"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `d` | Yes | Subscription identifier |
| `j` | No | Jurisdiction filter |
| `t` | No | Topic filters (multiple allowed) |
| `type` | No | Entity type filter |
| `threshold` | No | Voice count threshold for notification |

**Content:** NIP-44 encrypted JSON with delivery config (endpoint, preferences)

---

## Replaceable Events (10800-10899)

### Kind 10800: Provenance

Self-signed reputation record. One per pubkey, updated as participation grows.

**Tags:**
```json
[
  ["first-voice", "2025-09-01"],
  ["total-voices", "42"],
  ["entities-touched", "15"],
  ["j", "city-san-rafael"],
  ["attestation", "physical", "city-san-rafael", "2026-01-15"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `first-voice` | No | ISO date of first voice |
| `total-voices` | No | Total voice count |
| `entities-touched` | No | Unique entities count |
| `j` | No | Primary jurisdiction |
| `attestation` | No | Format: `[type, jurisdiction, date]` (multiple allowed) |

**Content:** Empty string

---

## Regular Events (1800-1899)

### Kind 1800: Vouch

One citizen vouching for another (social attestation).

**Tags:**
```json
[
  ["p", "vouchee_pubkey_hex"],
  ["j", "city-san-rafael"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `p` | Yes | Vouchee's public key |
| `j` | No | Jurisdiction context |

**Content:** Optional description of relationship

### Kind 1801: Event Notification

Relay-generated notification about civic events.

**Tags:**
```json
[
  ["event-type", "agenda_published"],
  ["j", "city-san-rafael"],
  ["a", "30801:pubkey:meeting:city-san-rafael:2026-02-03"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `event-type` | Yes | `agenda_published`, `decision_made`, `meeting_scheduled`, `public_comment_opened`, `public_comment_closing`, `voice_threshold_reached`, `initiative_created` |
| `j` | Yes | Jurisdiction |
| `a` | No | Reference to addressable event |

**Content:** JSON notification payload

**Signed by:** Relay's keypair

### Kind 1802: Key Link Attestation

Links an old CivicOS key (SECP256R1) to a new Nostr key (secp256k1).

**Tags:**
```json
[
  ["old-key", "old_p256_pubkey_hex"],
  ["old-sig", "ecdsa_signature_hex"]
]
```

The `old-sig` signs the string `"civicos:link:v1:{new_pubkey}"`. The new key signs the Nostr event normally. The relay validates both signatures and merges provenance.

### Kind 1804: Feedback

User feedback on the platform. Multiple submissions per user allowed.

**Tags:**
```json
[
  ["t", "bug"],
  ["j", "city-san-rafael"],
  ["v", "1"]
]
```

| Tag | Required | Values |
|-----|----------|--------|
| `t` | Yes | `bug`, `feature`, `general` |
| `j` | Yes | Jurisdiction |
| `v` | Yes | Schema version (currently `"1"`) |

**Content:** Free-text feedback body

---

## Tag Reference

| Tag | Name | Used In |
|-----|------|---------|
| `d` | Identifier | All addressable events |
| `j` | Jurisdiction | All events |
| `t` | Topic | Voices, entities, subscriptions, feedback |
| `p` | Pubkey reference | Attestations, vouches |
| `e` | Event reference | General |
| `a` | Addressable event ref | Commitments, completions, notifications |
| `stance` | Stance | Voices, comments |
| `type` | Type | Entities, attestations |
| `title` | Title | Entities |
| `threshold` | Threshold | Subscriptions |
| `event-type` | Event type | Notifications |
| `old-key` | Legacy key | Key link attestations |
| `old-sig` | Legacy signature | Key link attestations |
| `first-voice` | First voice date | Provenance |
| `total-voices` | Voice count | Provenance |
| `entities-touched` | Entity count | Provenance |
| `attestation` | Attestation record | Provenance |
| `v` | Version | Feedback |

## Signature Verification

All events use BIP-340 Schnorr signatures over secp256k1. The relay verifies every write:

1. Reconstruct the serialized event: `[0, pubkey, created_at, kind, tags, content]`
2. SHA-256 hash the JSON serialization
3. Verify the Schnorr signature against the public key
4. Check `created_at` is present and within acceptable range
5. Check `jurisdiction` tag is present (required for all civic events)

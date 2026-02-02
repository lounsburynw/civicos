# Nostr Civic NIPs Specification

CivicOS extends the Nostr protocol with civic-specific event kinds for local governance coordination.

## Overview

CivicOS implements a full NIP-01 compliant relay with civic extensions. Users manage keys via external Nostr clients (Damus, Primal, Amethyst, nos2x) and interact with civic entities through standard Nostr events.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Nostr Ecosystem                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │  Damus  │  │ Primal  │  │Amethyst │  │  nos2x  │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       └────────────┴─────┬──────┴────────────┘              │
│                          │                                  │
│              WebSocket (NIP-01)                             │
│                          │                                  │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │           CivicOS Nostr Relay                         │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────┐     │  │
│  │  │ Voice Count │  │ Provenance  │  │Subscription│     │  │
│  │  │ Aggregation │  │  Tracking   │  │  Matching  │     │  │
│  │  └─────────────┘  └─────────────┘  └───────────┘     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Civic Event Kinds

| Kind | Type | Purpose | Status |
|------|------|---------|--------|
| 30800 | Addressable | Civic Voice (stance on entity) | ✅ Complete |
| 30801 | Addressable | Civic Entity (decisions, initiatives) | ✅ Complete |
| 30802 | Addressable | Civic Subscription (notifications) | ✅ Complete |
| 30810 | Addressable | Civic Action (defined tasks) | 🚧 In Progress |
| 30811 | Addressable | Civic Commitment (intent to act) | 🚧 In Progress |
| 30812 | Addressable | Civic Completion (evidence) | 🚧 In Progress |
| 10800 | Replaceable | Civic Provenance (reputation) | ✅ Complete |
| 1800 | Regular | Civic Vouch (social attestation) | ✅ Complete |
| 1801 | Regular | Civic Event Notification | ✅ Complete |
| 1802 | Regular | Key Link Attestation | ✅ Complete |

### Kind 30800: Civic Voice

A citizen's stance on a civic entity. Addressable by `kind:pubkey:d-tag`.

```json
{
  "kind": 30800,
  "pubkey": "<32-byte hex secp256k1 pubkey>",
  "created_at": 1738464000,
  "tags": [
    ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
    ["j", "city-san-rafael"],
    ["stance", "support"],
    ["t", "housing"]
  ],
  "content": "",
  "sig": "<64-byte schnorr signature>"
}
```

**Required Tags:**
- `d`: Entity identifier (unique per voice)
- `j`: Jurisdiction code
- `stance`: One of `support`, `oppose`, `watching`

**Optional Tags:**
- `t`: Topic tags (multiple allowed)

**Behavior:**
- One voice per pubkey per entity (addressable)
- Revocation: publish with `content: "revoked"`
- Newer events replace older ones

### Kind 30801: Civic Entity

A civic decision, initiative, meeting, or agenda item.

```json
{
  "kind": 30801,
  "pubkey": "<jurisdiction or creator pubkey>",
  "tags": [
    ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
    ["j", "city-san-rafael"],
    ["type", "decision"],
    ["title", "4th Street Rezoning"],
    ["t", "housing"]
  ],
  "content": "{\"description\": \"...\", \"outcome\": \"approved\"}"
}
```

**Required Tags:**
- `d`: Entity identifier
- `j`: Jurisdiction
- `type`: One of `decision`, `initiative`, `agenda_item`, `meeting`
- `title`: Human-readable title

**Content JSON:**
- `description`: Detailed description
- `outcome`: One of `pending`, `approved`, `denied`, `deferred`, `passed`, `failed`

**Notes:**
- Official entities signed by jurisdiction key (NIP-05 verified)
- Community initiatives signed by creator key

### Kind 30802: Civic Subscription

User's subscription criteria for notifications.

```json
{
  "kind": 30802,
  "tags": [
    ["d", "sub:city-san-rafael:housing"],
    ["j", "city-san-rafael"],
    ["t", "housing"],
    ["threshold", "10"]
  ],
  "content": "<NIP-44 encrypted delivery config>"
}
```

**Tags:**
- `d`: Subscription identifier
- `j`: Jurisdiction filter (optional)
- `t`: Topic filters (optional, multiple)
- `type`: Entity type filter (optional)
- `threshold`: Voice count threshold (optional)

**Content:** NIP-44 encrypted JSON with delivery configuration.

### Kind 10800: Civic Provenance

Self-signed reputation record for a pubkey. Replaceable (one per pubkey).

```json
{
  "kind": 10800,
  "pubkey": "<subject pubkey>",
  "tags": [
    ["first-voice", "2025-09-01"],
    ["total-voices", "23"],
    ["entities-touched", "12"],
    ["j", "city-san-rafael"],
    ["attestation", "physical", "city-san-rafael", "2026-01-15"]
  ],
  "content": ""
}
```

**Tags:**
- `first-voice`: Date of first voice
- `total-voices`: Total voice count
- `entities-touched`: Unique entities count
- `j`: Primary jurisdiction
- `attestation`: [type, jurisdiction, date] tuples

### Kind 1800: Civic Vouch

One citizen vouching for another (social attestation).

```json
{
  "kind": 1800,
  "pubkey": "<voucher pubkey>",
  "tags": [
    ["p", "<vouchee pubkey>"],
    ["j", "city-san-rafael"]
  ],
  "content": "I know this person from neighborhood meetings"
}
```

### Kind 1801: Civic Event Notification

Relay notification about civic events.

```json
{
  "kind": 1801,
  "pubkey": "<relay pubkey>",
  "tags": [
    ["event-type", "agenda_published"],
    ["j", "city-san-rafael"],
    ["a", "30801:<pubkey>:meeting:city-san-rafael:2026-02-03"]
  ],
  "content": "{\"title\": \"City Council Meeting\", ...}"
}
```

**Event Types:**
- `agenda_published`: New agenda available
- `voice_threshold`: Entity reached voice threshold
- `meeting_scheduled`: Upcoming meeting
- `outcome_recorded`: Decision outcome recorded

### Kind 1802: Key Link Attestation

Links old CivicOS key (SECP256R1) to new Nostr key (secp256k1).

```json
{
  "kind": 1802,
  "pubkey": "<new secp256k1 pubkey>",
  "tags": [
    ["old-key", "<old SECP256R1 pubkey hex>"],
    ["old-sig", "<ECDSA signature proving old key ownership>"]
  ],
  "content": "Key migration attestation: I control both keys"
}
```

**Verification:**
1. Old key signs message: `civicos:link:v1:<new_pubkey>`
2. New key signs Nostr event normally
3. Relay validates both signatures
4. Provenance merges to new key

---

## Action Primitives

Action primitives bridge the gap from signal to outcome. Voices express intent; actions accomplish change. These kinds enable coordination that catalyzes real-world civic action.

### Kind 30810: Civic Action

A defined task that moves an initiative forward. Addressable by `kind:pubkey:d-tag`.

```json
{
  "kind": 30810,
  "pubkey": "<organizer pubkey>",
  "created_at": 1739520000,
  "tags": [
    ["d", "action:marin-housing:written-comment"],
    ["a", "30801:<pubkey>:initiative:marin-housing"],
    ["j", "marin-county"],
    ["type", "written_comment"],
    ["target", "clerk@marincounty.org"],
    ["deadline", "2026-02-14T17:00:00Z"],
    ["template", "<base64 encoded template or URI>"],
    ["target_count", "30"]
  ],
  "content": "Submit written comment supporting proportional housing allocation",
  "sig": "<64-byte schnorr signature>"
}
```

**Required Tags:**
- `d`: Action identifier (unique per action)
- `a`: Reference to parent entity (initiative, agenda item)
- `j`: Jurisdiction code
- `type`: Action type (see below)

**Optional Tags:**
- `target`: Email, form URL, or contact for action
- `deadline`: ISO 8601 deadline for action
- `template`: Base64 template or URI for action content
- `target_count`: Goal number of completions

**Action Types:**
- `written_comment` — submit to official email/form
- `attend_meeting` — show up physically
- `public_comment` — speak at meeting
- `contact_official` — call/email specific person
- `signature` — sign petition/letter
- `share` — distribute information
- `custom` — anything else

### Kind 30811: Civic Commitment

Binding intent to complete an action. Addressable by `kind:pubkey:d-tag`.

```json
{
  "kind": 30811,
  "pubkey": "<committer pubkey>",
  "created_at": 1739520000,
  "tags": [
    ["d", "commit:<pubkey>:marin-housing:written-comment"],
    ["a", "30810:<organizer_pubkey>:action:marin-housing:written-comment"],
    ["j", "marin-county"],
    ["status", "committed"]
  ],
  "content": "",
  "sig": "<64-byte schnorr signature>"
}
```

**Required Tags:**
- `d`: Commitment identifier (includes pubkey for uniqueness)
- `a`: Reference to action being committed to
- `j`: Jurisdiction code
- `status`: One of `committed`, `completed`, `withdrawn`

**Behavior:**
- One commitment per pubkey per action (addressable)
- Status progression: `committed` → `completed` | `withdrawn`
- Enables progress tracking: "12 committed, 8 completed"

### Kind 30812: Civic Completion

Evidence that an action was completed. Addressable by `kind:pubkey:d-tag`.

```json
{
  "kind": 30812,
  "pubkey": "<completer pubkey>",
  "created_at": 1739606400,
  "tags": [
    ["d", "complete:<pubkey>:marin-housing:written-comment"],
    ["a", "30810:<organizer_pubkey>:action:marin-housing:written-comment"],
    ["j", "marin-county"],
    ["evidence", "self_report"],
    ["completed_at", "2026-02-13T14:30:00Z"]
  ],
  "content": "",
  "sig": "<64-byte schnorr signature>"
}
```

**Required Tags:**
- `d`: Completion identifier
- `a`: Reference to action completed
- `j`: Jurisdiction code
- `evidence`: Evidence type (see below)
- `completed_at`: ISO 8601 timestamp of completion

**Evidence Types:**
- `self_report` — user clicked "I did it"
- `email_confirmation` — forwarded confirmation
- `attendance_check` — checked in at meeting
- `verified` — organizer confirmed

**Notes:**
- Completion updates the corresponding commitment status to `completed`
- Multiple completions by same pubkey for same action are ignored (idempotent)

### Action Accounting

Relays maintain derived views showing progress toward targets:

```
Initiative: Regional Housing
Actions:
├── Written Comment (deadline: Feb 14)
│   └── 24 completed / 27 committed / 30 target
├── Attend Meeting (deadline: Feb 18 2pm)
│   └── 0 completed / 11 committed / 15 target
└── Contact Rodoni (deadline: Feb 17)
    └── 8 completed / 10 committed / 10 target

Overall: 68% of target actions completed
```

---

## Relay Behavior

### Event Storage

- **Regular events (1-9999):** Stored, duplicates rejected by ID
- **Replaceable events (10000-19999):** One per `kind:pubkey`, newer replaces older
- **Addressable events (30000-39999):** One per `kind:pubkey:d-tag`, newer replaces older

### Voice Count Aggregation

The relay maintains materialized views of voice counts per entity:

```sql
-- Voice counts per entity
entity_id | jurisdiction | support | oppose | watching | total
----------|--------------|---------|--------|----------|------
decision:... | city-sr | 10 | 3 | 5 | 18
```

### Subscription Matching

Subscriptions filter events by:
- `kinds`: Event kind numbers
- `authors`: Pubkey list
- `#d`, `#j`, `#t`: Tag values
- `since`/`until`: Time range

## Client Integration

### Connecting

```javascript
const ws = new WebSocket('wss://relay.civicos.org');

// Subscribe to San Rafael voices
ws.send(JSON.stringify([
  "REQ", "sr-voices",
  {"kinds": [30800], "#j": ["city-san-rafael"]}
]));
```

### Publishing a Voice

```javascript
// Using nostr-tools or similar
const event = {
  kind: 30800,
  created_at: Math.floor(Date.now() / 1000),
  tags: [
    ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
    ["j", "city-san-rafael"],
    ["stance", "support"],
    ["t", "housing"]
  ],
  content: ""
};

// Sign and publish
const signedEvent = await signEvent(event, privateKey);
ws.send(JSON.stringify(["EVENT", signedEvent]));
```

### Revoking a Voice

```javascript
const revocation = {
  kind: 30800,
  tags: [
    ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
    ["j", "city-san-rafael"],
    ["stance", "support"]
  ],
  content: "revoked"
};
```

## Migration from CivicOS v1

Existing users with SECP256R1 keys can migrate to Nostr:

1. Generate new Nostr key in preferred client
2. Sign link message with old key: `civicos:link:v1:<new_pubkey>`
3. Publish kind 1802 attestation event
4. Relay validates and links keys
5. Provenance transfers to new key

See `docs/user_guides/KEY_MIGRATION_GUIDE.md` for detailed instructions.

## NIP-05 Jurisdiction Verification

NIP-05 enables human-readable identity verification for CivicOS relays and jurisdictions.

### CivicOS Relay Verification

The CivicOS API serves `/.well-known/nostr.json` for identity verification:

```
GET https://api.civicos.org/.well-known/nostr.json?name=civicos

Response:
{
  "names": {"civicos": "abc123..."},
  "relays": {"abc123...": ["wss://relay.civicos.org"]}
}
```

**Configuration:**
- `NOSTR_RELAY_PUBKEY`: 64-char hex public key for the relay identity
- `NOSTR_RELAY_URL`: WebSocket URL (default: `wss://relay.civicos.org`)

### City Self-Hosted Verification

Cities can verify their official accounts by hosting `/.well-known/nostr.json` on their domain:

```
# Example: sanrafael.gov verifies civicos@sanrafael.gov
GET https://sanrafael.gov/.well-known/nostr.json?name=civicos

Response:
{
  "names": {"civicos": "<city_official_pubkey>"},
  "relays": {"<city_official_pubkey>": ["wss://relay.civicos.org"]}
}
```

**For City IT Teams:**

1. Generate a Nostr keypair (32-byte secret → 32-byte x-only pubkey)
2. Create static JSON at `/.well-known/nostr.json`:
   ```json
   {
     "names": {
       "civicos": "<your_64_char_hex_pubkey>"
     },
     "relays": {
       "<your_64_char_hex_pubkey>": ["wss://relay.civicos.org"]
     }
   }
   ```
3. Serve with CORS headers: `Access-Control-Allow-Origin: *`
4. Cache recommended: `Cache-Control: max-age=3600`

### Verification Flow

1. User sees identifier: `civicos@sanrafael.gov`
2. Nostr client fetches: `https://sanrafael.gov/.well-known/nostr.json?name=civicos`
3. Client verifies pubkey matches event signatures
4. Client displays verified badge

### Reference

- [NIP-05 Specification](https://github.com/nostr-protocol/nips/blob/master/05.md)

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Crypto (secp256k1/Schnorr) | ✅ Complete | BIP-340 compliant |
| Event Models (Voice/Entity/Sub) | ✅ Complete | Kinds 30800-30802 |
| Event Models (Provenance/Vouch) | ✅ Complete | Kinds 10800, 1800-1802 |
| Event Models (Action Primitives) | 🚧 In Progress | Kinds 30810-30812 |
| Storage Layer | ✅ Complete | PostgreSQL + indexes |
| WebSocket Relay | ✅ Complete | NIP-01 compliant |
| Key Link Attestation | ✅ Complete | Dual-sig validation |
| REST Compatibility | ✅ Complete | Deprecated endpoints |
| NIP-05 Verification | ✅ Complete | /.well-known/nostr.json endpoint |
| Action Accounting Views | 🚧 Pending | Commitment/completion aggregation |

## References

- [NIP-01: Basic protocol flow](https://github.com/nostr-protocol/nips/blob/master/01.md)
- [BIP-340: Schnorr Signatures](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki)
- [CivicOS Coordination Protocol](./COORDINATION_PROTOCOL.md)

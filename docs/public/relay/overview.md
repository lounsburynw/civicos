# CivicOS Relay

The relay is CivicOS's coordination infrastructure — it stores and serves signed civic events (voices, actions, subscriptions) and provides authenticated AI access for residents.

## Relay vs. MCP Server

CivicOS operators can run either or both of two independent services:

| Component | Direction | Purpose |
|-----------|-----------|---------|
| **MCP Server** | Read-only | Serves civic data queries — meetings, decisions, legislation, transcripts |
| **Relay** | Bidirectional | Coordinates civic participation — voices, actions, subscriptions, AI drafting |

The MCP server is a **data API**. It answers questions like "what's on the agenda?" by querying structured civic records. Any AI client (Claude, ChatGPT) or application can connect to it. No identity required.

The relay is **coordination infrastructure**. It handles the things that require identity and trust: voicing support or opposition on an agenda item, committing to civic actions, subscribing to topics, and using AI to draft testimony. All relay interactions are signed with secp256k1 Schnorr signatures (Nostr-compatible) and most require [attestation](attestation.md).

A city government might run only an MCP server to publish authoritative civic data. A neighborhood group might run only a relay to coordinate community voices. A full CivicOS operator runs both.

## What the Relay Stores

| Data | Nostr Kind | Requires Attestation |
|------|-----------|---------------------|
| **Voices** — support, oppose, or watching on a civic entity | 30800 | Yes |
| **Actions** — commitments and completions on civic actions | 30810-30812 | Yes |
| **Subscriptions** — topic and event notifications | 30820 | No |
| **Attestations** — residency proofs issued by the relay | 30850 | N/A (this IS attestation) |

All voice and action records are signed Nostr events. The relay verifies signatures on ingest and serves them to any client. Records are self-verifying — any relay, anywhere, can validate a voice by checking its signature and embedded attestation proof without contacting the original relay.

## Services

### VoiceService
Public expression of civic interest on entities (agenda items, decisions, initiatives).

- `cast_voice(voice)` — Submit a signed stance (support/oppose/watching)
- `get_counts(entity)` — Aggregate voice counts per entity
- `verify(voice)` — Verify signature and attestation proof

One key = one stance per entity. Casting a new stance revokes the previous one.

### ActionService
Track commitments and completions on civic actions.

- `record_commitment(action)` — Record a commitment to act
- `record_completion(action)` — Record completion
- `get_counts(entity)` — Action counts per entity

### RelayService
Event routing and subscription management.

- `subscribe(subscription)` — Subscribe to events by topic, geography, or event type
- `unsubscribe(id)` — Remove subscription
- `emit(event)` — Route event to subscribers

### AI Proxy
Authenticated AI access for attested residents. See [AI Proxy](ai-proxy.md).

### ProvenanceService
Trust signals for voice quality — tracks which keys have participated in which entities and jurisdictions.

### SyncService
Voice and event synchronization between peer relays. See [Federation](federation.md).

## Cryptography

All relay interactions use **secp256k1 Schnorr signatures** (Nostr-compatible, BIP-340). Not P-256 ECDSA.

- Keys are generated client-side in the browser extension
- Private keys never leave the user's device
- Signatures are verified by the relay on every write operation
- Attestation proofs are embedded on each voice/action record

## Acceptance Policy

All relay write endpoints enforce signature verification and an acceptance policy. Writes are checked against a tiered system:

1. **Attested** — present a kind-30850 attestation proof for unlimited writes (Phase 3)
2. **Paid** — include a payment proof for unlimited writes (Phase 4)
3. **Rate-limited** — per-event-type daily limits (active now)

Default rate limits:

| Event Type | Daily Limit |
|------------|-------------|
| voice | 50 |
| comment | 20 |
| initiative | 5 |
| action_create | 10 |
| action_commit | 20 |
| action_complete | 20 |

If a write exceeds the rate limit without an attestation or payment proof, the relay returns **HTTP 402** with upgrade options:

```json
{
  "accepted": false,
  "tier": "rejected",
  "reason": "Daily rate limit exceeded (50/day for voice)",
  "options": {
    "attestation": "Present a kind-30850 attestation proof for unlimited writes",
    "payment": "Include a payment proof for unlimited writes",
    "retry": "Wait until tomorrow when your rate limit resets"
  }
}
```

Write tools are not exposed in the MCP server — all writes go through the relay directly.

> **Current status:** Rate limiting (tier 3) and attestation verification (tier 1) are active. Attestation codes are issued via multi-issuer registry — organizations register their signers and the relay verifies attestation proofs against trusted issuer pubkeys. Payment proof verification (tier 2) is designed but not yet enforced. Rate limits are persistent (PostgreSQL-backed), unlike REST API rate limits which are in-memory.

## HTTP Endpoints

All endpoints are under the relay's base URL. Write endpoints require Nostr-signed request bodies; read endpoints are public.

### Voice

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/voice` | Signed + acceptance policy | Cast a stance on an entity |
| GET | `/coordination/voice/counts/{entity}` | None | Get voice counts (support/oppose/watching) |
| GET | `/coordination/voice/{entity}` | None | List all voices for an entity |

### Comments

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/comment` | Signed + acceptance policy | Submit a public comment |
| GET | `/coordination/comments/{entity}` | None | List comments for an entity |
| GET | `/coordination/comment/counts/{entity}` | None | Get comment count |

### Initiatives

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/initiative` | Signed + acceptance policy | Create a community initiative |
| GET | `/coordination/initiatives/{jurisdiction}` | None | List initiatives (optional topic/status filter) |
| GET | `/coordination/initiative/{initiative_id}` | None | Get initiative details |

### Civic Actions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/civic-action` | Signed + acceptance policy | Create a civic action (kind 30810) |
| GET | `/coordination/civic-actions/{initiative_id}` | None | List actions for an initiative |
| GET | `/coordination/civic-action/{action_id}/progress` | None | Get progress metrics |
| POST | `/coordination/civic-action/{action_id}/commit` | Signed + acceptance policy | Commit to an action (kind 30811) |
| POST | `/coordination/civic-action/{action_id}/complete` | Signed + acceptance policy | Complete an action (kind 30812) |
| POST | `/coordination/civic-action/{action_id}/withdraw` | Signed | Withdraw a commitment |

### Subscriptions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/subscribe` | None | Subscribe to event notifications |
| DELETE | `/coordination/subscribe/{subscription_id}` | None | Unsubscribe |

### Attestation

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/attest` | Signed (kind-24242) | Redeem an attestation code |
| GET | `/coordination/attestation/{public_key}` | None | Check attestation status |
| GET | `/coordination/attestation/stats/{jurisdiction}` | None | Attestation statistics |
| POST | `/coordination/codes/batch` | Admin | Upload issuer-signed code batch (kind-30851) |
| POST | `/coordination/issuers/register` | Admin | Register a trusted issuer |
| GET | `/coordination/issuers/{jurisdiction}` | None | List trusted issuers |
| POST | `/coordination/admin/issuer/{id}/verify` | Admin | Verify an issuer |
| POST | `/coordination/admin/issuer/{id}/revoke` | Admin | Revoke an issuer |

### Feedback

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/coordination/feedback` | Signed | Submit platform feedback (kind 1804) |
| GET | `/coordination/feedback` | Admin | Query feedback by type/jurisdiction |

### Federation & Sync

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/coordination/sync/voices` | None | Export voices for peer sync (paginated) |
| POST | `/coordination/sync/voices` | None | Import voices from a peer relay |
| GET | `/coordination/sync/events` | None | Export events for peer sync (paginated) |
| POST | `/coordination/sync/events` | None | Import events from a peer relay |
| POST | `/coordination/sync/trigger` | Admin | Trigger immediate sync from all peers |
| GET | `/coordination/provenance/{public_key}` | None | Get provenance data for a key |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check with relay ID |

## Storage

- **Production:** PostgreSQL (`RELAY_DATABASE_URL`), separate from the civic data database
- **Development:** In-memory storage (fallback when no database URL is set)

The relay uses its own database, separate from the MCP server's civic data store. This is a deliberate architectural boundary — coordination data (who voiced what) is isolated from civic data (what happened at the meeting).

## Attestation Signing

Trusted organizations run their own signing services via [`civicos-signer`](../packages/civicos-signer.md). When a resident redeems an attestation code, the relay calls the issuing organization's signer to produce the attestation event. This separates attestation authority from relay operation from day one — see [Attestation: Multi-Issuer](attestation.md#multi-issuer-attestation).

## Further Reading

- [Nostr Event Schemas](nostr-events.md) — Complete tag structures for building CivicOS clients
- [Attestation](attestation.md) — How gated attestation prevents spam and ensures genuine participation
- [Trust Model](trust.md) — Adversary analysis, commitment logs, operator integrity
- [Federation](federation.md) — Multi-operator peering, jurisdiction rollup, data sovereignty
- [AI Proxy](ai-proxy.md) — Privacy-preserving AI access for residents

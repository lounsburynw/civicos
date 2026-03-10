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

All relay write endpoints enforce an acceptance policy after signature verification. When enabled (`RELAY_ACCEPTANCE_POLICY=true`), writes are checked against a tiered system:

1. **Attested** — present a kind-30850 attestation proof for unlimited writes
2. **Paid** — include a payment proof for unlimited writes
3. **Rate-limited** — per-event-type daily limits (e.g., 50 voices/day, 20 comments/day)

If a write exceeds the rate limit without an attestation or payment proof, the relay returns **HTTP 402** with a body describing upgrade options:

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

The acceptance policy is disabled by default. Write tools are not exposed in the MCP server — all writes go through the relay directly.

## Storage

- **Production:** PostgreSQL (`RELAY_DATABASE_URL`), separate from the civic data database
- **Development:** In-memory storage (fallback when no database URL is set)

The relay uses its own database, separate from the MCP server's civic data store. This is a deliberate architectural boundary — coordination data (who voiced what) is isolated from civic data (what happened at the meeting).

## Attestation Signing

Trusted organizations run their own signing services via [`civicos-signer`](../packages/civicos-signer.md). When a resident redeems an attestation code, the relay calls the issuing organization's signer to produce the attestation event. This separates attestation authority from relay operation from day one — see [Attestation: Multi-Issuer](attestation.md#multi-issuer-attestation).

## Further Reading

- [Attestation](attestation.md) — How gated attestation prevents spam and ensures genuine participation
- [Trust Model](trust.md) — Adversary analysis, commitment logs, operator integrity
- [Federation](federation.md) — Multi-operator peering, jurisdiction rollup, data sovereignty
- [AI Proxy](ai-proxy.md) — Privacy-preserving AI access for residents

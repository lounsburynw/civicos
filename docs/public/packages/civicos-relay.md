# civicos-relay

Coordination relay for voice casting, subscriptions, and relay-to-relay sync.

**Location:** `packages/civicos-relay/`

## Services

### VoiceService
Public expression of civic interest on entities (agenda items, decisions, initiatives).

- `cast_voice(voice)` — Submit a signed stance (support/oppose/watching)
- `get_counts(entity)` — Aggregate voice counts per entity
- `verify(voice)` — Verify signature

One key = one stance per entity. Casting a new stance revokes the previous one.

### ActionService
Track commitments and completions on civic actions.

- `record_commitment(action)` — Record an action commitment
- `record_completion(action)` — Record completion
- `get_counts(entity)` — Action counts

### RelayService
Event routing and subscription management.

- `subscribe(subscription)` — Subscribe to events by topic, geography, or event type
- `unsubscribe(id)` — Remove subscription
- `emit(event)` — Route event to subscribers

### ProvenanceService
Trust signals for voice quality — tracks which keys have touched which entities and jurisdictions.

### SyncService
Voice and event synchronization between peer relays.

## Storage

- **`PostgresStorage`** — Production. Uses `RELAY_DATABASE_URL` (separate Supabase project).
  - Tables: `coordination_voices`, `coordination_subscriptions`, `coordination_initiatives`
- **`InMemoryStorage`** — Fallback for local dev/testing.

Selection: `RELAY_DATABASE_URL` > `DATABASE_URL` > in-memory.

## Cryptography

All voices are signed with secp256k1 Schnorr signatures (Nostr-compatible, BIP-340). Not P-256 ECDSA.

## Deployment

```bash
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py
```

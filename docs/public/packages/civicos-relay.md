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
Voice and event synchronization between peer relays. Pull-based: each relay periodically fetches new voices from configured peers via `GET /coordination/sync/voices`.

- `sync_from_peer(peer)` — Pull voices from a peer, verify signatures, import
- `export_voices(request)` — Serve voices for peer consumption
- Health checking with auto-disable of unhealthy peers

Configure peers via `RELAY_PEERS` (comma-separated URLs) and interval via `RELAY_SYNC_INTERVAL` (seconds, default 300).

### AttestationService
Orchestrates multi-issuer code redemption and attestation issuance.

- `register_issuer(registration)` — Register an issuer organization
- `accept_code_batch(signed_event)` — Accept issuer-signed code batches
- `redeem_code(code, pubkey, sig, created_at)` — Redeem code via issuer's signer

## Storage

- **`PostgresStorage`** — Production. Uses `RELAY_DATABASE_URL` (separate from the civic data database).
  - Tables: `coordination_voices`, `coordination_subscriptions`, `coordination_initiatives`, `coordination_attestation_codes`, `coordination_attestations`, `coordination_issuer_registry`, `coordination_sync_cursors`, and more
- **`InMemoryStorage`** — Fallback for local dev/testing.

Selection: `RELAY_DATABASE_URL` > `DATABASE_URL` > in-memory.

## Attestation

The relay verifies attestation proofs (kind-30850 events) embedded on voices and comments. Trusted organizations run [`civicos-signer`](civicos-signer.md) instances with their own keys, and the relay calls out to their `/sign` endpoints during code redemption. The relay maintains a registry of trusted issuer pubkeys per jurisdiction in `coordination_issuer_registry`.

## Cryptography

All voices are signed with secp256k1 Schnorr signatures (Nostr-compatible, BIP-340). Not P-256 ECDSA.

## Deployment

```bash
# Production (Modal)
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py

# Multi-platform (Modal, Fly.io, or Docker)
./scripts/deploy-relay.sh <jurisdiction> <platform>
```

Each relay instance is self-contained — a single jurisdiction can be served by one relay, or multiple relays can peer via `RELAY_PEERS` for federation.

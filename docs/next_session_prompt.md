# Recommended: Issue Test Attestations for Federation Relays

**Priority:** P0 (`issue_test_attestations`)
**Area:** federation_testbed
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session consolidated the relay coordination router into a self-contained package and deployed federation test relays for Mill Valley and San Anselmo on Fly.io with separate Neon Postgres databases. Three independent relays are now running across two platforms (Modal + Fly.io). The next step is generating issuer keypairs so the relays can verify attestations — a prerequisite for cross-relay voice and comment verification.

## What Was Completed This Session

`deploy_marin_test_relays` (P0) is done:
- **Relay consolidation**: Moved coordination router (40 endpoints, 2948 lines) from civicos_services into civicos_relay package. Relay is now fully self-contained.
- **Dockerfile + Fly.io deployment**: `apps/civicos-relay/Dockerfile` + `fly.toml` + `scripts/deploy-relay.sh`
- **Parameterized deployment**: `./scripts/deploy-relay.sh <jurisdiction> <platform>` (modal/fly/docker)
- **Test relays deployed on Fly.io**:
  - Mill Valley: `https://civicos-relay-mill-valley.fly.dev/health`
  - San Anselmo: `https://civicos-relay-san-anselmo.fly.dev/health`
- **Separate Neon Postgres databases**: Full schema (21 coordination tables each), $0/mo free tier
- **Production relay unchanged**: San Rafael still on Modal with Supabase

Also discussed but deferred:
- Multi-tenant MCP consolidation (free up Modal endpoint slots) — separate session
- Peer sync configuration (RELAY_PEERS) — after attestation setup

## Recommended Task

Generate issuer keypairs for Mill Valley and San Anselmo. Register them in each relay's issuer_registry table. Verify that attestation issuance and verification work across the three relays.

### Key Files

- `packages/civicos-relay/src/civicos_relay/attestation/service.py` — AttestationService (redeem codes, verify proofs)
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py` — `sign_attestation_event()`, `verify_attestation_proof()`
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py` — PostgresAttestationStorage, PostgresIssuerStorage
- `packages/civicos-relay/src/civicos_relay/server/coordination.py` — `/coordination/attest`, `/coordination/issuers/register`
- `scripts/sql/add_attestation_tables.sql` — Schema for attestation codes + attestations
- `scripts/sql/add_issuer_registry.sql` — Schema for trusted issuers

### Relay Deployment Info

| Relay | Platform | URL | Database |
|-------|----------|-----|----------|
| San Rafael | Modal | `civicos--civicos-relay-relayserver-relay-endpoint.modal.run` | Supabase (production) |
| Mill Valley | Fly.io | `civicos-relay-mill-valley.fly.dev` | Neon (`ep-blue-base-akoamc38-pooler`) |
| San Anselmo | Fly.io | `civicos-relay-san-anselmo.fly.dev` | Neon (`ep-old-term-akcsgm0j-pooler`) |

Deploy script: `./scripts/deploy-relay.sh <jurisdiction> <platform>`

## Suggested Approach

### Phase 1: Configure peer sync (do this first)
The relays are running independently. Configure them to sync voices/events:

1. Set `RELAY_PEERS` on each Fly.io relay so they know about each other:
   ```bash
   fly secrets set RELAY_PEERS="https://civicos-relay-san-anselmo.fly.dev" -a civicos-relay-mill-valley
   fly secrets set RELAY_PEERS="https://civicos-relay-mill-valley.fly.dev" -a civicos-relay-san-anselmo
   ```
2. Verify sync endpoints respond: `GET /coordination/sync/voices` and `GET /coordination/sync/events`
3. Key files for sync: `packages/civicos-relay/src/civicos_relay/sync/service.py`, `sync/protocol.py`

### Phase 2: Issue attestations
1. Generate secp256k1 keypairs for Mill Valley and San Anselmo issuers
2. Register issuers on each relay via `POST /coordination/issuers/register` (requires CIVICOS_RELAY_API_KEY)
3. Set `CIVICOS_ATTESTATION_PRIVATE_KEY` as Fly.io secret on each test relay
4. Generate test attestation codes via `POST /coordination/codes/batch`
5. Test attestation redemption: `POST /coordination/attest` on each relay

### Phase 3: Cross-relay verification
6. Cast a voice on Mill Valley relay with attestation from Mill Valley issuer
7. Verify the voice syncs to San Anselmo relay via peer sync
8. Verify attestation proof validates on the receiving relay

## Tests to Run

```bash
# Relay tests (should stay green)
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="

# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Health checks
curl -s https://civicos-relay-mill-valley.fly.dev/health
curl -s https://civicos-relay-san-anselmo.fly.dev/health
```

## Success Criteria

- [ ] Issuer keypairs generated for Mill Valley and San Anselmo
- [ ] Issuers registered in each relay's database
- [ ] Attestation codes issued on each test relay
- [ ] Attestation redemption works on each relay
- [ ] Cross-relay attestation proof verification works

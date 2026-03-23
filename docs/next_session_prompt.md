# Recommended: Token Issuance Service

**Priority:** P0 (token_issuance_service)
**Area:** token_issuance
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous two sessions built the full crypto + verification chain for privacy-preserving payment tokens:
- Session N-1: Schnorr blind signature primitives (`blind.py`), `SpentTokenStorage` protocol, Postgres + InMemory implementations
- Session N: Wired real token verification into `AcceptancePolicy._verify_payment()` — issuer allowlist, signature check, atomic double-spend prevention (12 new tests, all passing)

The relay can now **verify and spend** tokens. What's missing is the **issuance** side: a service that accepts payment (Stripe), runs the blind signing protocol, and returns tokens the user can spend. This is the privacy boundary — the issuer sees payment identity but not which tokens get spent; the relay sees tokens but not who paid.

## What Exists Now

- `packages/civicos-relay/src/civicos_relay/voice/blind.py` — Full protocol: `generate_nonce()`, `blind()`, `sign_blinded()`, `unblind()`, `verify_token()`, `compute_token_hash()`
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:189-200` — `AcceptancePolicy` accepts `spent_token_storage` and `known_token_issuers` params
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:371-410` — `_verify_payment()` validates tokens end-to-end
- `packages/civicos-relay/src/civicos_relay/server/app.py:148-152` — Where `AcceptancePolicy` is instantiated (needs `spent_token_storage` + `known_token_issuers` wired in)
- `docs/internal/blind-signature-spec.md` — Full design spec including issuance flow diagram

## What Needs to Be Done

1. **Create the token issuance service** — A new module (likely `packages/civicos-relay/src/civicos_relay/server/token_issuer.py` or a standalone service). This service:
   - Holds the issuer's private key (NOT the relay's key — separate identity)
   - Exposes an endpoint: user sends blinded challenges, issuer returns blind signatures
   - Must NOT see the unblinded token message (this is the privacy guarantee)

2. **Payment integration** — Accept Stripe checkout session ID (or Lightning invoice) as proof of payment before signing tokens. For MVP, a simple webhook or session verification.

3. **Issuance protocol endpoints** (2-step):
   - `POST /tokens/nonce` — Issuer generates nonce (k, R=kG), returns R to user. Requires payment proof.
   - `POST /tokens/sign` — User sends blinded challenge, issuer returns blind signature s = k + e*d mod n

4. **Wire `AcceptancePolicy` in `app.py:148-152`** — Add `spent_token_storage=storage.spent_tokens` and `known_token_issuers={ISSUER_PUBKEY_HEX}` to the constructor call.

5. **Token batch support** — Spec suggests packages of 10/50/100 tokens per purchase. Each token requires a separate nonce+sign round.

## Key Files

- `packages/civicos-relay/src/civicos_relay/voice/blind.py:98-171` — Issuer-side functions: `generate_nonce()`, `sign_blinded()`
- `packages/civicos-relay/src/civicos_relay/server/app.py:148-152` — AcceptancePolicy instantiation (needs wiring)
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:189-200` — Constructor params ready for `spent_token_storage` + `known_token_issuers`
- `docs/internal/blind-signature-spec.md:81-100` — Issuance flow diagram
- `docs/internal/blind-signature-spec.md:118-124` — Open questions (batch size, expiry, key rotation, rate limiting)

## Suggested Approach

1. Read `blind-signature-spec.md` fully — it has the design decisions and flow diagram
2. Create `packages/civicos-relay/src/civicos_relay/server/token_issuer.py` with `TokenIssuer` class
3. Implement the 2-step protocol: nonce generation + blind signing
4. Add rate limiting on signing endpoint (Wagner's attack mitigation — spec says max 5 concurrent sessions)
5. Wire `AcceptancePolicy` in `app.py` with `spent_token_storage` and `known_token_issuers`
6. Write tests using `_issue_token()` pattern from `test_blind_signatures.py:40-46`
7. Defer Stripe integration to a follow-up if needed — focus on the signing protocol first

## Tests to Run

```bash
# Blind signature tests (existing, should still pass)
pytest packages/civicos-relay/tests/test_blind_signatures.py -q --override-ini="addopts="

# Acceptance policy tests (existing, should still pass)
pytest packages/civicos-relay/tests/test_acceptance_policy.py -q --override-ini="addopts="

# All relay tests
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] `TokenIssuer` class implements nonce generation + blind signing
- [ ] Issuer holds its own keypair (separate from relay identity)
- [ ] Rate limiting on concurrent signing sessions (Wagner's attack mitigation)
- [ ] `AcceptancePolicy` in `app.py` wired with `spent_token_storage` and `known_token_issuers`
- [ ] Integration test: issue token via `TokenIssuer` -> spend via `AcceptancePolicy` -> double-spend rejected
- [ ] Existing blind signature and acceptance policy tests still pass

## Roadmap Context

- **Phase 1 (DONE):** Generalize RefreshRunner
- **Phase 2 (DONE):** Wire cron orchestrators
- **Phase 3 (DONE):** Onboarding YAML generation
- **Phase 4 (DONE):** Blind signature primitives + SpentTokenStorage
- **Phase 5 (DONE):** Token verification in acceptance policy
- **Phase 6 (P0):** Token issuance service <-- THIS SESSION
- **Phase 7 (P3):** Extension token wallet + purchase UI

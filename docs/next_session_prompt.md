# Recommended: Token Verification in Acceptance Policy

**Priority:** P0 (token_verification_in_policy)
**Area:** token_issuance
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session implemented Schnorr blind signature crypto primitives (`blind.py`) and a `SpentTokenStorage` protocol with Postgres and InMemory implementations. The acceptance policy's `_verify_payment()` at line 367 is still a stub that always returns `False`. This session wires in real token verification using the new primitives, completing the relay's payment tier.

## What Exists Now

- `packages/civicos-relay/src/civicos_relay/voice/blind.py` — `verify_token()`, `compute_token_hash()`, `SpendableToken`, `SpentTokenStorage` Protocol
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py` — `PostgresSpentTokenStorage` (atomic `INSERT ON CONFLICT DO NOTHING`)
- `packages/civicos-relay/src/civicos_relay/storage/memory.py` — `InMemorySpentTokenStorage`
- Both composites (`PostgresStorage`, `InMemoryStorage`) expose `.spent_tokens`
- `scripts/sql/add_spent_tokens.sql` — migration for `coordination_spent_tokens` table

## What Needs to Be Done

1. **Inject `SpentTokenStorage` into `AcceptancePolicy`** — Add a `spent_token_storage` parameter to `__init__` (line 180). When not provided, fall back gracefully (payment always fails, matching current behavior).

2. **Replace `_verify_payment()` stub** (line 367-369) with real verification:
   - Parse `payment_proof` dict into `SpendableToken.from_dict()`
   - Call `verify_token(token)` to check the Schnorr signature
   - Call `spent_token_storage.check_and_mark_spent(compute_token_hash(token))` for atomic double-spend prevention
   - Return `True` only if both signature is valid AND token was not already spent

3. **Add issuer pubkey validation** — The relay should only accept tokens signed by known issuer public keys. Follow the pattern from `_verify_attestation()` (line 303-306) which uses `self._issuer_lookup`. Add a `known_token_issuers` config or reuse the issuer registry.

4. **Update tests** in `packages/civicos-relay/tests/test_acceptance_policy.py`:
   - Replace `test_payment_stub_always_fails` (line 84-89) with real verification tests
   - Test: valid token accepted with tier="paid"
   - Test: invalid signature falls through to rate limit
   - Test: double-spend (same token twice) second attempt falls through
   - Test: unknown issuer pubkey rejected
   - Test: no spent_token_storage provided payment always fails (backwards compat)

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:170` — `AcceptancePolicy` class
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:236-239` — Payment tier check in `check()`
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:367-369` — `_verify_payment()` stub
- `packages/civicos-relay/src/civicos_relay/voice/blind.py:70` — `SpentTokenStorage` Protocol
- `packages/civicos-relay/src/civicos_relay/voice/blind.py:201` — `verify_token()`
- `packages/civicos-relay/src/civicos_relay/voice/blind.py:248` — `compute_token_hash()`
- `packages/civicos-relay/tests/test_acceptance_policy.py:84-89` — Current payment stub test
- `packages/civicos-relay/tests/test_blind_signatures.py` — 28 existing crypto tests

## Suggested Approach

1. Read `acceptance.py` fully to understand the `check()` flow and `_verify_attestation()` pattern
2. Add `spent_token_storage: Optional[SpentTokenStorage] = None` to `AcceptancePolicy.__init__`
3. Replace `_verify_payment()` with real verification (signature check + atomic spend)
4. Add issuer pubkey allowlist (simple list or reuse issuer registry)
5. Write tests using `InMemorySpentTokenStorage` and tokens from `_issue_token()` helper
6. Run existing acceptance tests to ensure no regressions

## Tests to Run

```bash
# Blind signature tests (should still pass)
pytest packages/civicos-relay/tests/test_blind_signatures.py -q --override-ini="addopts="

# Acceptance policy tests
pytest packages/civicos-relay/tests/test_acceptance_policy.py -q --override-ini="addopts="

# All relay tests
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] `_verify_payment()` validates `SpendableToken` signatures via `verify_token()`
- [ ] Double-spend prevented via `SpentTokenStorage.check_and_mark_spent()` (atomic)
- [ ] Only tokens from known issuer pubkeys are accepted
- [ ] Backwards compatible: no `spent_token_storage` means payment tier always fails (existing behavior)
- [ ] Existing acceptance policy tests still pass
- [ ] New tests cover: valid token, invalid sig, double-spend, unknown issuer

## Roadmap Context

- **Phase 1 (DONE):** Generalize RefreshRunner
- **Phase 2 (DONE):** Wire cron orchestrators
- **Phase 3 (DONE):** Onboarding YAML generation
- **Phase 4 (DONE):** Blind signature scheme design + SpentTokenStorage
- **Phase 5 (P0):** Token verification in acceptance policy <-- NEXT
- **Phase 6 (P3):** Token issuance service (Stripe/Lightning)
- **Phase 7 (P3):** Extension token wallet + purchase UI

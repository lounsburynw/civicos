# Recommended: Attestation Expiry

**Priority:** P0 (`attestation_expiry`)
**Area:** acceptance_policy
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session completed `multi_issuer_lookup`: `_verify_attestation()` now iterates all verified issuers for a jurisdiction instead of returning the first match. This enables cross-relay attestation verification via peer sync. The next natural step is adding expiry checking so old attestations don't verify forever.

## What Was Completed Last Session

- `IssuerLookup` type changed from `Callable[[str], Optional[str]]` to `Callable[[str], list[str]]`
- `_verify_attestation()` iterates all issuer pubkeys, accepts if any verifies
- `issuer_lookup` closure in `app.py` returns all verified, non-revoked pubkeys
- 6 new multi-issuer tests added (40 total acceptance policy tests pass)
- 391 relay tests pass
- Spec updated (`docs/internal/multi-issuer-lookup-spec.md` steps 3,4 marked done)

## Recommended Task

Add attestation expiry checking to `_verify_attestation()`. Currently, a kind-30850 attestation event is accepted regardless of age. Add a check: `proof["created_at"] + validity_period > now`. Recommend 1-year default validity (31536000 seconds).

Also design a revocation mechanism — a blocklist of revoked attestation event IDs stored in the coordination DB.

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:176-211` — `_verify_attestation()` where the expiry check should go
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:46-56` — `DEFAULT_POLICY` config dict — could add `attestation_validity_seconds` here
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py:409` — `verify_attestation_proof()` does the crypto verification
- `packages/civicos-relay/tests/test_acceptance_policy.py` — 40 existing tests including `TestMultiIssuerAttestation`
- `docs/internal/relay-acceptance-policy-spec.md` — Phase 3 spec for attestation expiry

## Suggested Approach

1. **Add expiry check in `_verify_attestation()`** — before calling `verify_attestation_proof()`, check `proof.get("created_at", 0) + validity_period > int(time.time())`. If expired, log and return False.

2. **Make validity period configurable** — add `attestation_validity_seconds` to the policy config or `AcceptancePolicy.__init__()` (default 31536000 = 1 year).

3. **Design revocation blocklist** — create `coordination_attestation_revocations` table with `event_id TEXT PRIMARY KEY, revoked_at TIMESTAMPTZ, reason TEXT`. Check blocklist in `_verify_attestation()` before crypto verification.

4. **Add tests:**
   - Attestation with `created_at` older than validity period is rejected
   - Attestation within validity period passes
   - Revoked attestation event ID is rejected
   - Custom validity period works

5. **Migration SQL** — add to `scripts/sql/` for the revocations table.

## Tests to Run

```bash
# Acceptance policy tests (primary)
pytest packages/civicos-relay/tests/test_acceptance_policy.py -q --override-ini="addopts="

# Full relay suite
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] Attestation proofs older than validity period are rejected
- [ ] Validity period is configurable (default 1 year)
- [ ] Revocation blocklist table designed and created
- [ ] Revoked attestation event IDs are rejected
- [ ] Tests cover expiry and revocation scenarios
- [ ] `launch.json` item marked done

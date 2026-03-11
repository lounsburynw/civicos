# Recommended: HTTP IP Rate Limiting

**Priority:** P0
**Area:** acceptance_policy
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed two acceptance policy items: `nip13_proof_of_work` (wired `_verify_pow` into `check()` as tier 3, valid PoW bypasses rate limit) and `wire_attestation_verification` (wired `_verify_attestation` to extract jurisdiction from j-tag, look up issuer via `issuer_lookup` callable, call `verify_attestation_proof()`). The acceptance policy now has all four tiers operational: attestation > payment (stub) > PoW > rate limit.

The next security priority is HTTP-level per-IP rate limiting — a coarse first line of defense that runs *before* any crypto verification, protecting the relay from brute-force spam.

## Recommended Task

Add per-IP rate limiting middleware to the relay's FastAPI/Starlette app. This should be a lightweight check at the HTTP layer (before request body parsing or Nostr event verification). The spec is in the relay acceptance policy doc.

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/app.py` — FastAPI app, lifespan, middleware setup
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py` — Current acceptance policy (per-pubkey rate limiting exists here, `InMemoryRateLimiter` is a useful pattern)
- `docs/internal/relay-acceptance-policy-spec.md` — Full spec, Phase 2 section covers IP rate limiting
- `packages/civicos-relay/src/civicos_relay/modal_relay.py` — Modal deployment entry point

## Suggested Approach

1. Read `docs/internal/relay-acceptance-policy-spec.md` Phase 2 section for requirements
2. Add ASGI middleware or Starlette `Middleware` to `app.py` that tracks request counts per IP
3. Use in-memory counter (similar to `InMemoryRateLimiter` in `acceptance.py`) — no DB needed
4. Apply to write endpoints only (POST routes), not reads
5. Return 429 Too Many Requests when limit exceeded
6. Make limits configurable via `RelayConfig` or policy config
7. Add tests

## Tests to Run

```bash
# Existing acceptance policy tests (should still pass)
pytest packages/civicos-relay/tests/test_acceptance_policy.py -v --override-ini="addopts="

# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Per-IP rate limiting middleware added to relay app
- [ ] Runs before crypto/Nostr verification (HTTP layer)
- [ ] Only affects write endpoints
- [ ] Returns 429 with appropriate message
- [ ] Tests cover basic rate limiting and bypass for reads
- [ ] `http_ip_rate_limiting` marked done in launch.json

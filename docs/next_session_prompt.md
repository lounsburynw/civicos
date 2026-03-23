# Recommended: Token Issuer Environment Configuration

**Priority:** P0 (token_issuer_env_config)
**Area:** token_issuance
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The token issuance pipeline is functionally complete: blind signatures, token wallet, issuer HTTP endpoints, and acceptance policy all work locally and pass tests. But the TokenIssuer is **not yet deployable** — its env vars (`TOKEN_ISSUER_SECRET`, `TOKEN_ISSUER_MAX_SESSIONS`, `TOKEN_ISSUER_SESSION_TTL`) are not in any Modal secret group, the relay Modal deployment doesn't reference them, and docs don't mention them.

## What Exists Now

- **Token issuer code** reads env vars at startup in `app.py:178-187` — already wired
- **Relay Modal deployment** (`apps/civicos-relay/modal_relay.py:49-55`) uses these secrets: `civicos-env`, `civicos-attestation`, `civic-anthropic`, `civicos-platform` — **no token issuer secret group**
- **Token endpoints** (`GET /coordination/tokens/info`, `POST /coordination/tokens/session`, `POST /coordination/tokens/sign`) are defined in `app.py:256-295`
- **Acceptance policy** (`acceptance.py:190,379-390`) validates tokens against `TOKEN_ISSUER_PUBKEYS`
- **deployment.md** has no mention of TOKEN_ISSUER_* env vars
- **relay/overview.md** doesn't document the token endpoints

## Key Files

| File | Purpose |
|------|---------|
| `packages/civicos-relay/src/civicos_relay/server/app.py:178-187` | TokenIssuer env var reading (already implemented) |
| `packages/civicos-relay/src/civicos_relay/server/app.py:154-172` | TOKEN_ISSUER_PUBKEYS + known_token_issuers wiring |
| `packages/civicos-relay/src/civicos_relay/server/app.py:256-295` | Token HTTP endpoints |
| `apps/civicos-relay/modal_relay.py:49-55` | `get_relay_secrets()` — needs token issuer secret |
| `docs/internal/deployment.md` | Needs TOKEN_ISSUER_* documentation |
| `docs/public/relay/overview.md` | Needs token endpoint documentation |

## Suggested Approach

1. **Generate a TOKEN_ISSUER_SECRET** (32-byte hex key for blind signatures)
   ```python
   import os; print(os.urandom(32).hex())
   ```

2. **Add to Modal secrets** — either create a new `civicos-token-issuer` secret or add to existing `civicos-attestation`:
   ```bash
   modal secret create civicos-token-issuer \
     TOKEN_ISSUER_SECRET=<hex_key> \
     TOKEN_ISSUER_MAX_SESSIONS=5 \
     TOKEN_ISSUER_SESSION_TTL=300
   ```

3. **Wire into relay deployment** — update `get_relay_secrets()` in `apps/civicos-relay/modal_relay.py` to include the new secret group

4. **Derive and set TOKEN_ISSUER_PUBKEYS** — the public key derived from the secret must be added to `civicos-env` (or wherever the relay reads it) so the acceptance policy can verify tokens

5. **Document in deployment.md** — add TOKEN_ISSUER_* env vars to the secrets reference table

6. **Document token endpoints in relay/overview.md** — the three `/coordination/tokens/*` endpoints

7. **Deploy and smoke test** — `modal deploy apps/civicos-relay/modal_relay.py` then hit the `/coordination/tokens/info` endpoint

## Tests to Run

```bash
# Token issuer unit tests
pytest packages/civicos-relay/tests/ -k "token_issuer" -q --override-ini="addopts="

# Acceptance policy tests (verify token verification still works)
pytest packages/civicos-relay/tests/ -k "acceptance" -q --override-ini="addopts="

# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] TOKEN_ISSUER_SECRET exists in a Modal secret group
- [ ] `get_relay_secrets()` includes the token issuer secret
- [ ] TOKEN_ISSUER_PUBKEYS is set for acceptance policy verification
- [ ] `deployment.md` documents all TOKEN_ISSUER_* env vars
- [ ] `relay/overview.md` documents `/coordination/tokens/*` endpoints
- [ ] Deployed relay responds to `GET /coordination/tokens/info` with issuer pubkey
- [ ] Existing tests pass (no regressions)

## Deferred Items

- **token_purchase_ui** (P3) — Stripe checkout flow for buying tokens (depends on issuer being deployed)
- **pagination Phase 3-4** (unscheduled) — REST API limit/offset params, X-Total-Count header

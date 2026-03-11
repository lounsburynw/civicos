# Recommended: Extension 402 Handling

**Priority:** P0
**Area:** acceptance_policy
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The relay acceptance policy is fully wired: rate limiting, PoW mining (client-side), attestation verification, and monitoring (just completed). However, when the relay rejects a write with HTTP 402, the extension silently swallows the error. Users get no feedback about why their voice/comment was rejected, nor guidance on how to resolve it (get attested, wait for rate limit reset, etc.).

## Recommended Task

Update the browser extension and `civicos-client` to handle HTTP 402 responses from the relay. Parse the `PolicyResult` response body (which includes `tier`, `reason`, and `options` for upgrade paths) and surface it to the user.

## Key Files

- `packages/civicos-client/src/api.ts:224-243` — `submitVoice()` returns `response.ok` (boolean), discards 402 body
- `packages/civicos-client/src/api.ts:627-654` — `castVoice()` calls `submitVoice()`, returns boolean
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:803` — `api.castVoice(...).catch(() => {})` — silently swallows all errors
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:30-43` — `PolicyResult.to_dict()` defines the 402 response format:
  ```json
  {"accepted": false, "tier": "rejected", "reason": "...", "options": {"attestation": "...", "payment": "...", "retry": "..."}}
  ```
- `packages/civicos-relay/src/civicos_relay/server/app.py:326` — `raise HTTPException(status_code=402, detail=result.to_dict())`

## Suggested Approach

1. **Update `civicos-client` API methods** to return richer results (not just boolean):
   - Change `submitVoice()`, `submitComment()` return type from `Promise<boolean>` to `Promise<{ok: boolean, rejection?: PolicyResult}>`
   - On 402, parse response JSON and return the `PolicyResult` body
   - Similarly update `castVoice()`, `castComment()` to propagate rejection info

2. **Update extension SidePanel** to handle rejection:
   - Replace `.catch(() => {})` with proper error handling
   - On 402 rejection, show a user-friendly message based on `reason`:
     - Rate limit: "Daily limit reached. Try again tomorrow."
     - Rejected (no proof): "Authentication required. Get verified to continue."
   - Show `options` from the response (attestation, retry guidance)

3. **Consider a toast/notification component** in the extension for transient error messages

## Tests to Run

```bash
# Client-side tests
cd packages/civicos-client && npm test

# Relay acceptance tests (should still pass)
pytest packages/civicos-relay/tests/test_acceptance_policy.py -v
```

## Success Criteria

- [ ] `submitVoice()` and `submitComment()` return structured result (not just boolean) on 402
- [ ] Extension shows user-friendly message when write is rejected (rate limit, no attestation)
- [ ] Extension shows upgrade guidance (attestation option, retry timing)
- [ ] Existing happy-path behavior unchanged (successful writes still work)
- [ ] No regression in acceptance policy tests

## Recent Completions

- **Acceptance policy monitoring** (this session) — `_log_acceptance()` logs every decision, `get_acceptance_stats()` admin endpoint, `coordination_acceptance_logs` table in relay DB
- **NIP-13 PoW mining** (prev session) — `castVoice()` and `castComment()` mine transparently when no attestation proof
- **Billing deferred** — Stripe items moved to P3, need usage data first

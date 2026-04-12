# Recommended: Token Purchase UI (`token_purchase_ui`)

**Priority:** P0
**Area:** token_issuance
**Date:** 2026-04-12

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

**Note:** This item was deprioritized per the April 2026 roadmap pivot (OAuth + free tier before billing). Only 4 items remain in launch.json (this P0 + 3 P3s). The next session has full discretion to pick a different item or re-prioritize.

## Context

Prior session completed `cross_jurisdiction_civic_api_methods` (commit `cbba504a`) — wired `funding_flow` and `intergovernmental_revenue` through `walk_scope` for cross-jurisdiction queries. The launch checklist now has 4 items remaining. The token purchase UI is the Stripe checkout -> blinded tokens flow in the extension. Backend infrastructure is ~95% ready; the missing piece is the purchase UI and Stripe-to-issuer bridge.

## What's Already Built

- **Token issuer service**: `packages/civicos-relay/src/civicos_relay/server/token_issuer.py:49-222` — Schnorr blind signature protocol, nonce sessions, Wagner attack mitigation
- **Token HTTP endpoints**: `packages/civicos-relay/src/civicos_relay/server/app.py:258-291` — `/coordination/tokens/info`, `/tokens/session`, `/tokens/sign`
- **Acceptance policy**: `packages/civicos-relay/src/civicos_relay/server/acceptance.py:373-411` — Tier 2 payment proof verification with atomic double-spend check
- **Client token wallet**: `apps/civicos-extension/src/lib/token-wallet.ts:1-137` — `requestTokens()`, `getAvailableToken()`, `storeTokens()` in Chrome storage
- **Client blind crypto**: `apps/civicos-extension/src/lib/blind.ts` — full Schnorr blind signature (noble-curves)
- **SidePanel auto-attach**: `apps/civicos-extension/src/side-panel/SidePanel.svelte:812-823` — auto-attaches payment proof to `castVoice()`
- **Stripe billing (API subs)**: `packages/civicos-services/core/stripe_billing.py:1-212` — Stripe checkout + webhooks, but NOT connected to token issuance

## What's Missing

1. **Stripe-to-issuer bridge**: No endpoint connects Stripe payment to token issuance
2. **Extension purchase UI**: No "Buy tokens" button, amount selector, or progress flow
3. **Token balance display**: No visible token count in extension UI
4. **Token pricing model**: Unresolved (flat per-token? bundles?)

## Architectural Decisions Needed

1. **Stripe flow**: Stripe webhook triggers token issuance (async) vs. redirect-based (sync)?
2. **Token pricing**: Flat rate ($0.01/token), bundles (50/$0.40), or per-jurisdiction?
3. **Bridge endpoint**: On relay (`/coordination/tokens/checkout`) or separate service?
4. **Identity**: Email-only (current Stripe) vs. anonymous vs. extension-linked?

## Suggested Approach

1. **Design the Stripe->token bridge** — Add a `/coordination/tokens/checkout` endpoint that creates a Stripe checkout session and stores the mapping to the requesting client
2. **Add Stripe webhook handler on relay** — On `checkout.session.completed`, issue N blinded tokens to the client's pending session
3. **Build extension purchase UI** — "Buy tokens" button in SidePanel, amount selector, redirect to Stripe, poll for completion
4. **Add token balance display** — Show current token count in extension sidebar
5. **Test end-to-end** — Stripe test mode -> webhook -> token issuance -> extension wallet

## Tests to Run

```bash
# Token issuer tests
civicos-env/bin/python3 -m pytest packages/civicos-relay/tests/test_token_issuer.py -v --override-ini="addopts="

# Acceptance policy tests
civicos-env/bin/python3 -m pytest packages/civicos-relay/tests/test_acceptance_policy.py -v --override-ini="addopts="

# Stripe billing tests
civicos-env/bin/python3 -m pytest packages/civicos-services/tests/test_stripe_billing.py -v --override-ini="addopts="

# Extension build
cd apps/civicos-extension && npm run build
```

## Success Criteria

- [ ] Stripe checkout session created from extension UI
- [ ] Stripe webhook triggers token issuance on relay
- [ ] Extension receives and stores blinded tokens after payment
- [ ] Token balance visible in extension UI
- [ ] End-to-end flow works in Stripe test mode
- [ ] A new P0 assigned before session end

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items — 6 pre-existing failures total, stable across sessions.

## Open PRs

None.

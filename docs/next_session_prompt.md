# Recommended: Token Purchase UI

**Priority:** P0 (token_purchase_ui)
**Area:** token_issuance
**Date:** 2026-04-03

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Launch phase is 134/138 items done. All token infrastructure is complete EXCEPT the purchase UI:
- Blind signature scheme (secp256k1 Schnorr) -- done
- Token issuance service (civicos-signer) -- done
- Token wallet in extension (chrome.storage.local) -- done
- Token spending in API (paymentProof param) -- done
- Token verification in acceptance policy -- done

Only 4 items remain: this one + 3 P3 federation/operator items.

## Goal

Build the Stripe checkout -> blinded token acquisition flow in the browser extension. User clicks "Buy Tokens", pays via Stripe, receives blinded tokens in their wallet.

## Key Files

- `apps/civicos-extension/src/lib/blind.ts` -- Schnorr blind signing primitives (blind, unblind, verify)
- `apps/civicos-extension/src/lib/token-wallet.ts` -- Wallet API (getTokens, storeTokens, requestTokens, getAvailableToken)
- `apps/civicos-extension/src/background/service-worker.ts:195` -- Token message handlers (GET_TOKEN_COUNT, REQUEST_TOKENS, SPEND_TOKEN)
- `apps/civicos-extension/src/lib/messaging.ts` -- Message protocol types
- `packages/civicos-signer/src/civicos_signer/server.py` -- Token issuer service
- `apps/civicos-extension/src/popup/Popup.svelte` -- Main popup UI (no token UI yet)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` -- Side panel (no token UI yet)
- `packages/civicos-client/src/api.ts` -- REST API with paymentProof support

### Token Discovery

The relay exposes `/coordination/tokens/info` which returns `{ enabled: boolean, issuer_pubkey: string }`. The extension's `requestTokens(config, count)` already handles the full blind signing protocol.

## Suggested Approach

1. **Add Stripe JS SDK** to `apps/civicos-extension/package.json`
2. **Create payment endpoint** on the API/relay that creates a Stripe Checkout Session, returns session URL
3. **Build UI component** in extension (Popup or SidePanel) -- "Buy Tokens" button showing wallet balance
4. **Stripe Checkout flow** -- redirect to Stripe hosted checkout, handle success callback
5. **Webhook handler** on backend -- Stripe payment confirmed -> issue tokens via blind signing
6. **Wire end-to-end** -- payment confirmed -> tokens in wallet -> balance updates in UI

### Key decisions needed
- Stripe Checkout (hosted) vs Stripe Elements (embedded) -- hosted is simpler
- Where does the payment endpoint live? Relay (`/coordination/tokens/purchase`) or API?
- Token pricing: how many tokens per dollar?
- **Check `.env` for STRIPE_PUBLIC_KEY / STRIPE_SECRET_KEY** -- may need to set up Stripe account first

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Extension build
cd apps/civicos-extension && npm run build

# Token wallet tests (if they exist)
cd apps/civicos-extension && npm test
```

## Success Criteria

- [ ] Stripe Checkout Session created from extension
- [ ] Payment confirmation webhook processes correctly
- [ ] Blinded tokens arrive in extension wallet after payment
- [ ] Wallet balance displays in extension UI
- [ ] Token can be spent on a voice/comment submission

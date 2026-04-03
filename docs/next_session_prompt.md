# Recommended: Re-onboard Marin + Token Purchase UI

**Priority:** P0 (token_purchase_ui), but re-onboard first (30 min)
**Area:** operator_readiness → token_issuance
**Date:** 2026-04-03

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session (28 commits) rebuilt the entire onboarding pipeline: 10 platforms, escalating fetch (requests→curl→Playwright stealth), LLM QC, officials from elections, web verification. All critic findings addressed. But the Marin sandboxes are stale — they need re-onboarding with the final code to get officials + enriched QC.

Launch phase: 134/138 items done. `platform_coverage_expansion` is done. `token_purchase_ui` is the P0.

## Step 1: Re-onboard Marin (30 min)

Clean re-onboard all 8 cities to get definitive QC with officials:

```bash
for city in Sausalito Tiburon Novato "Corte Madera" Larkspur Fairfax Belvedere Ross; do
  python scripts/onboard.py --cleanup "city-$(echo $city | tr '[:upper:] ' '[:lower:]-')" 2>/dev/null
  python scripts/onboard.py --city "$city" --state CA --county Marin --trial
done
```

Expected: 8/8 PASS with meetings + elections + officials + web verification. Novato may need manual view_id fix (Granicus LLM body naming requires API key).

After trials pass, run the full QC overview:
```bash
python3 scripts/qc_sandbox.py --jurisdiction city-sausalito --json  # repeat for each
```

## Step 2: Token Purchase UI (P0)

Build Stripe checkout → blinded token flow in the browser extension.

### Key Files
- `apps/civicos-extension/src/lib/blind.ts` — Schnorr blind signing
- `apps/civicos-extension/src/lib/token-wallet.ts` — Token storage
- `apps/civicos-extension/src/background/service-worker.ts:195` — Token message handlers
- `packages/civicos-signer/src/civicos_signer/server.py` — Token issuer
- `packages/civicos-client/src/api.ts` — paymentProof support

### Token infrastructure (all done)
- Blind signature scheme (secp256k1 Schnorr)
- Token issuance service (civicos-signer)
- Token wallet in extension (chrome.storage.local)
- Token spending in API (paymentProof param)
- Token verification in acceptance policy

### What's needed
1. Stripe JS SDK in extension
2. Payment endpoint on relay (`/coordination/tokens/purchase`)
3. "Buy Tokens" UI in extension showing wallet balance
4. Stripe Checkout → webhook → issue tokens via blind signing
5. End-to-end test: purchase → tokens in wallet → spend on voice

## Tests to Run
```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
cd apps/civicos-extension && npm run build
```

## Success Criteria
- [ ] All 8 Marin cities pass QC with officials populated
- [ ] Stripe Checkout Session created from extension
- [ ] Tokens arrive in wallet after payment
- [ ] Token can be spent on voice submission

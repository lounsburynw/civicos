# Recommended: Extension Token Wallet

**Priority:** P0 (extension_token_wallet)
**Area:** token_issuance
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The last three sessions built the complete server-side token pipeline: blind signature primitives (`blind.py`), token verification in `AcceptancePolicy`, spent-token tracking (`SpentTokenStorage`), and the `TokenIssuer` service. The relay can now issue, verify, and reject double-spent tokens. What's missing is the **client side**: the browser extension needs to request tokens from the issuer, store them locally, and attach them to relay writes as `payment_proof`.

## What Exists Now

**Server side (complete):**
- `packages/civicos-relay/src/civicos_relay/voice/blind.py` — Full Schnorr blind signature protocol: `generate_nonce()`, `blind()`, `sign_blinded()`, `unblind()`, `verify_token()`, `compute_token_hash()`
- `packages/civicos-relay/src/civicos_relay/server/token_issuer.py` — `TokenIssuer` class: 2-step protocol (nonce session + sign), Wagner's attack mitigation, batch issuance
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:373-411` — `_verify_payment()` validates tokens end-to-end with atomic double-spend check
- `packages/civicos-relay/src/civicos_relay/server/app.py:148-170` — `AcceptancePolicy` wired with `spent_token_storage` and `known_token_issuers`

**Extension side (infrastructure exists, tokens don't):**
- `apps/civicos-extension/src/lib/providers/local-wallet.ts:67-340` — BIP-39 wallet with AES-256-GCM encryption, uses `chrome.storage.local`
- `apps/civicos-extension/src/lib/providers/crypto.ts:79-103` — secp256k1 Schnorr signing via `@noble/curves`
- `apps/civicos-extension/src/lib/identity.ts:32-271` — `IdentityManager`, session persistence via `chrome.storage.session`
- `apps/civicos-extension/src/lib/messaging.ts:15-28` — Message types enum (has `REDEEM_ATTESTATION` placeholder, no token types yet)
- `apps/civicos-extension/src/lib/adapters/extension-signer.ts:12-36` — `ExtensionSigner` delegates to service worker
- `apps/civicos-extension/src/background/service-worker.ts:21-100` — Message handler routes to `identityManager`
- `apps/civicos-extension/src/lib/storage.ts:37-50` — `ChromeStorageWalletStorage` pattern (reuse for tokens)

**Crypto deps already in extension:** `@noble/curves@^1.4.0`, `@noble/hashes@^1.4.0` (secp256k1 Schnorr — same curve as token protocol).

## What Needs to Be Done

1. **TypeScript blind signature client** — Port the user-side of `blind()` and `unblind()` from `blind.py` using `@noble/curves/secp256k1`. The math: `R' = R + alpha*G + beta*P`, `e' = SHA256(R'||P||m) mod n`, `e = e' + beta mod n` (blind), `s' = s + alpha mod n` (unblind). All secp256k1 operations already available via `@noble/curves`.

2. **Token storage module** — New `src/lib/token-wallet.ts` that persists `SpendableToken[]` in `chrome.storage.local` (matching wallet pattern). Functions: `storeTokens()`, `getAvailableToken()`, `removeSpentToken()`, `getTokenCount()`.

3. **Token acquisition flow** — Function that talks to the issuer service: request nonce session, blind locally, send blinded challenge, unblind response, store token. For MVP, can be triggered manually.

4. **Attach tokens to relay writes** — When extension sends a voice/comment/action to the relay, auto-attach a token as `payment_proof` if available. Modify the relay write path in service worker.

5. **Message types** — Add to `messaging.ts:15-28`: token-related message types for service worker communication.

## Key Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `apps/civicos-extension/src/lib/providers/local-wallet.ts` | Storage pattern to follow | 67-340 |
| `apps/civicos-extension/src/lib/providers/crypto.ts` | Schnorr with @noble/curves | 79-103 |
| `apps/civicos-extension/src/lib/messaging.ts` | Message type enum to extend | 15-28 |
| `apps/civicos-extension/src/background/service-worker.ts` | Message handler to extend | 21-100 |
| `apps/civicos-extension/src/lib/storage.ts` | Chrome storage adapter pattern | 37-50 |
| `packages/civicos-relay/src/civicos_relay/voice/blind.py` | `blind()` to port to TS | 109-150 |
| `packages/civicos-relay/src/civicos_relay/voice/blind.py` | `unblind()` to port to TS | 174-198 |
| `packages/civicos-relay/src/civicos_relay/voice/blind.py` | `SpendableToken` (TS interface) | 41-67 |
| `docs/internal/blind-signature-spec.md` | Protocol spec + flow diagram | 83-100 |

## Suggested Approach

1. Port `blind()` and `unblind()` to TypeScript using `@noble/curves/secp256k1` — this is the critical crypto piece
2. Write tests for the TS blind client against known test vectors from `test_blind_signatures.py` (deterministic issuer key `(42).to_bytes(32, "big")`)
3. Create `token-wallet.ts` for persistent token storage in `chrome.storage.local`
4. Wire token attachment into the relay write path
5. Add minimal UI indicator (token count) — can be basic for MVP

## Tests to Run

```bash
# Server-side (should still pass — no server changes expected)
pytest packages/civicos-relay/tests/test_blind_signatures.py -q --override-ini="addopts="
pytest packages/civicos-relay/tests/test_token_issuer.py -q --override-ini="addopts="
pytest packages/civicos-relay/tests/test_acceptance_policy.py -q --override-ini="addopts="

# Extension
cd apps/civicos-extension && npm run build   # verify build succeeds
```

## Success Criteria

- [ ] TypeScript blind signature client (blind + unblind) produces tokens that pass Python `verify_token()`
- [ ] Token storage persists across browser sessions via `chrome.storage.local`
- [ ] Relay writes automatically attach a token as `payment_proof` when tokens are available
- [ ] Token count decrements after each spend
- [ ] Extension builds without errors (`npm run build`)
- [ ] Server-side tests still pass (no regressions)

## Deferred Items (tracked in launch.json)

- **token_issuer_env_config** (P2) — Env vars for issuer deployment params (TOKEN_ISSUER_SECRET, TOKEN_ISSUER_MAX_SESSIONS, TOKEN_ISSUER_SESSION_TTL). Tracked in launch.json, source: configuration critic flagged across two sessions.
- **token_purchase_ui** (P3) — Stripe checkout flow for buying tokens.

## Roadmap Context

- **Phase 4 (DONE):** Blind signature primitives + SpentTokenStorage
- **Phase 5 (DONE):** Token verification in acceptance policy
- **Phase 6 (DONE):** Token issuance service (TokenIssuer)
- **Phase 7 (P0):** Extension token wallet + spending <-- NEXT SESSION
- **Phase 8 (P3):** Token purchase UI (Stripe checkout)

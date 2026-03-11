# Blind Signature Token Scheme Spec

**Status:** Not started
**Date:** 2026-03-11
**Launch.json item:** `blind_signature_scheme_design`
**Depends on:** `token_issuance_service`, `token_verification_in_policy`, `extension_token_wallet`

## Problem

The relay acceptance policy (Phase 4) requires a privacy-preserving payment tier: users pay for write access without the relay being able to link a token to a payment session. The `payment_proof` field exists on Voice and other models but always returns `False` in verification.

We need a blind signature scheme using existing secp256k1 primitives that enables:
1. User pays (Stripe or Lightning) → receives blinded tokens
2. User submits token with relay write → relay verifies without learning payment identity
3. Spent tokens are tracked atomically (mark spent BEFORE persisting write)

## Design Principles

1. **Use secp256k1** — we already depend on coincurve. No new curve libraries.
2. **Issuer-relay separation** — the token issuer (takes payment) MUST be a separate service from the relay (verifies tokens). This is the privacy boundary.
3. **Unlinkability** — the issuer cannot link a blinded token it signed to the unblinded token the relay receives.
4. **Atomicity** — spent-token tracking must be atomic with write persistence. A token cannot be double-spent even under concurrent requests.
5. **Simplicity over generality** — we need one denomination (1 token = 1 write). No multi-denomination complexity.

## Decisions Required

### 1. Blind Signature Primitive

**Option A: Schnorr blind signatures (BIP-340 compatible)**
- Builds directly on existing `_schnorr_sign()` / `_schnorr_verify()` in crypto.py
- Well-documented in academic literature (Schnorr 1991, Wagner 2002)
- Risk: Wagner's attack on concurrent signing sessions. Mitigate by limiting concurrent blind signing requests per session.
- Implementation: ~200 lines of new crypto code

**Option B: DLEQ-based blind tokens (Privacy Pass style)**
- More modern, designed specifically for anonymous tokens
- Used by Cloudflare Privacy Pass, Apple Private Access Tokens
- More complex but better studied for exactly this use case
- Implementation: ~400 lines, may need additional dependencies

**Recommendation:** Option A. Schnorr blind signatures align with existing primitives and keep the dependency surface minimal. Wagner's attack is mitigable for our throughput (civic participation, not high-frequency trading).

### 2. Token Format

```python
@dataclass(frozen=True)
class BlindedToken:
    """Token submitted by user to issuer for signing."""
    blinded_point: str       # hex-encoded blinded message point

@dataclass(frozen=True)
class SignedBlindToken:
    """Issuer's response — blind signature."""
    blind_signature: str     # hex-encoded blind signature

@dataclass(frozen=True)
class SpendableToken:
    """Unblinded token held by user, submitted to relay."""
    message: str             # unique nonce (hex)
    signature: str           # unblinded Schnorr signature (hex)
    issuer_pubkey: str       # which issuer signed this token
```

### 3. Spent-Token Storage

**Option A: Dedicated `spent_tokens` table in relay DB**
```sql
CREATE TABLE coordination_spent_tokens (
    token_hash TEXT PRIMARY KEY,    -- SHA-256(message || signature)
    spent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    relay_write_id TEXT             -- FK to the write this token paid for
);
```

**Option B: Bloom filter with periodic DB sync**
- Faster lookups, but false positives reject valid tokens
- Requires careful sizing for expected token volume

**Recommendation:** Option A. Volume is low (civic participation writes), and atomicity with PostgreSQL transactions is straightforward. Bloom filter is premature optimization.

### 4. Issuance Flow

```
User                    Issuer Service              Relay
  |                          |                        |
  |-- Stripe checkout ------>|                        |
  |                          |-- provision N tokens   |
  |                          |                        |
  |-- send N blinded pts --->|                        |
  |<-- N blind signatures ---|                        |
  |                          |                        |
  |-- unblind locally        |                        |
  |                          |                        |
  |-- write + SpendableToken ----------------------->|
  |                          |         verify sig     |
  |                          |         check not spent|
  |                          |         mark spent     |
  |                          |         persist write  |
  |<--------------------------------------------- ok |
```

### 5. Relay Verification

In `acceptance.py`, the payment tier check becomes:

```python
def _verify_payment(self, payment_proof: dict) -> bool:
    token = SpendableToken(**payment_proof)
    # 1. Verify Schnorr signature against known issuer pubkeys
    if not verify_token_signature(token):
        return False
    # 2. Check not already spent (atomic with write)
    return True  # actual spend happens in transaction with write
```

The atomic spend-then-write must happen in the storage layer, not the acceptance policy. The policy says "this token is valid and unspent"; the write handler does `BEGIN; INSERT spent_token; INSERT voice; COMMIT;`.

## Open Questions

1. **Token batch size** — how many tokens per purchase? Suggest packages: 10, 50, 100.
2. **Token expiry** — should tokens expire? Suggest 1 year, matching attestation expiry.
3. **Issuer key rotation** — when the issuer rotates keys, old tokens must still verify. Store historical issuer pubkeys with validity windows.
4. **Rate limiting token requests** — the issuer itself needs rate limiting on the blinding endpoint to prevent Wagner's attack. Suggest max 5 concurrent signing sessions per IP.

## Implementation Order

1. Crypto primitives: `blind()`, `sign_blinded()`, `unblind()`, `verify_token()` in a new `packages/civicos-relay/src/civicos_relay/voice/blind.py`
2. Spent-token table migration
3. Token issuance service (Modal deployment, Stripe integration)
4. Acceptance policy integration (`_verify_payment()`)
5. Extension token wallet (store, auto-attach to writes)
6. Extension purchase UI (Stripe checkout flow)

## Test Strategy

- Unit tests for blind/unblind/verify roundtrip
- Unit test: double-spend rejection
- Integration test: full flow from blinding through spend
- Concurrency test: parallel spends of same token → exactly one succeeds

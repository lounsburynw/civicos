# Multi-Issuer Lookup Spec

**Status:** Not started
**Date:** 2026-03-11
**Launch.json item:** `multi_issuer_lookup`

## Problem

The current issuer lookup signature is:

```python
IssuerLookup = Callable[[str], Optional[str]]  # jurisdiction -> Optional[pubkey]
```

This assumes one trusted issuer per jurisdiction. With the federation testbed (3 jurisdictions, 3 issuers), and eventually cross-jurisdiction trust, we need:

- Multiple issuers per jurisdiction (e.g., city clerk + county registrar can both attest)
- Validity windows (issuer keys rotate; old attestations must still verify)
- Trust levels (a county attestation might carry more weight than a city one)
- Revocation (compromised issuer keys must be rejected)

## Design Principles

1. **Backward compatible** — existing single-issuer deployments must work without changes.
2. **Minimal model** — don't over-design. Start with what the testbed actually needs.
3. **Relay-local resolution** — each relay resolves issuers from its own registry. No cross-relay issuer lookup at verification time.

## TrustedIssuer Model

```python
@dataclass(frozen=True)
class TrustedIssuer:
    pubkey: str                          # hex-encoded secp256k1 pubkey
    jurisdiction_id: str                 # which jurisdiction this issuer attests for
    issuer_name: str                     # human-readable ("San Rafael City Clerk")
    valid_from: int                      # unix timestamp
    valid_until: Optional[int] = None    # None = no expiry
    trust_level: int = 1                 # 1 = standard, 2 = elevated (county/state)
    revoked: bool = False                # set True to reject without removing from registry
    revoked_at: Optional[int] = None     # when revocation occurred
```

## Updated Lookup Signature

```python
# Old
IssuerLookup = Callable[[str], Optional[str]]

# New
IssuerLookup = Callable[[str], List[TrustedIssuer]]
```

Returns all non-revoked issuers for a jurisdiction whose validity window includes `now`. Empty list = no trusted issuers (same semantics as returning None before).

## Acceptance Policy Changes

Current `_verify_attestation()` in `acceptance.py`:

```python
issuer_pubkey = self.issuer_lookup(jurisdiction)
if issuer_pubkey and verify_attestation_proof(proof, issuer_pubkey):
    return True
```

Updated:

```python
issuers = self.issuer_lookup(jurisdiction)
for issuer in issuers:
    if verify_attestation_proof(proof, issuer.pubkey):
        return True, issuer.trust_level
return False, None
```

The acceptance tier can optionally use `trust_level` to differentiate (e.g., county attestation → tier 1, city attestation → tier 1, but different metadata in `coordination_write_metadata`).

## Storage Options

### Option A: Extend `config/registry.json`

```json
{
  "city-san-rafael": {
    "attestation_issuers": [
      {
        "pubkey": "a8a87b...",
        "issuer_name": "San Rafael City Clerk",
        "valid_from": 1709251200,
        "trust_level": 1
      }
    ]
  }
}
```

- Pro: Already the source of truth for jurisdiction config. `attestation_issuer_pubkey` already lives here (singular).
- Con: Registry gets complex. Rotation history accumulates.

### Option B: Database table (`coordination_issuer_registry`)

```sql
CREATE TABLE coordination_issuer_registry (
    pubkey TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    trust_level INTEGER DEFAULT 1,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMPTZ
);
```

- Pro: Queryable, supports rotation history, revocation without config redeploy.
- Con: Requires DB access at relay startup. Current `issuer_lookup` is provided from storage in `app.py` lifespan, so this fits the existing pattern.

**Recommendation:** Option B. The relay already connects to PostgreSQL at startup. Issuer registry is coordination data — it belongs in the coordination DB alongside voices and actions.

## Migration Path

1. Create `coordination_issuer_registry` table
2. Seed from current `registry.json` `attestation_issuer_pubkey` values
3. Update `app.py` lifespan to build `IssuerLookup` from DB query
4. Update `AcceptancePolicy._verify_attestation()` to iterate issuers
5. Remove `attestation_issuer_pubkey` from `registry.json` (replaced by DB)
6. Generate issuer keypairs for Mill Valley + San Anselmo testbed cities

## Backward Compatibility

During migration, support both:
- If `coordination_issuer_registry` table exists → use it
- If not → fall back to `registry.json` `attestation_issuer_pubkey` (single issuer)

This allows self-hosted operators to use the simple config-file approach without running the migration.

## Test Strategy

- Unit test: lookup returns multiple issuers, verification tries each
- Unit test: expired issuer is excluded from lookup results
- Unit test: revoked issuer is excluded from lookup results
- Integration test: attestation from issuer A verifies on relay, attestation from revoked issuer B is rejected
- Testbed test: 3 issuers (SR, Mill Valley, San Anselmo) each attest their own users, cross-verify on shared relay

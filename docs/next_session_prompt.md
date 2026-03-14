# Recommended: Multi-Issuer Lookup

**Priority:** P0 (`multi_issuer_lookup`)
**Area:** federation_testbed
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session built the full federation attestation pipeline: issuer registry endpoints, code batch submission, attestation redemption, and peer sync — all validated on live relays (Mill Valley and San Anselmo). The one remaining gap is that `AcceptancePolicy._verify_attestation()` only checks the **first** verified issuer it finds. It should try **all** verified issuers for a jurisdiction, since a voice arriving via peer sync might carry an attestation signed by a different issuer than the one the local relay would pick first.

## What Was Completed Last Session

- Issuer registry HTTP endpoints (register, verify, revoke, list, code batch)
- `verify_code_batch()` moved to relay crypto module (no civicos_signer dependency)
- Issuer keypairs generated for Mill Valley + San Anselmo, registered on live relays
- Attestation redemption verified end-to-end on both relays
- Peer sync working: voices propagate between Mill Valley ↔ San Anselmo
- Manual sync trigger endpoint (`POST /coordination/sync/trigger`)
- Documentation updated (public + internal)

## Recommended Task

Update `_verify_attestation()` to iterate all verified issuers instead of returning only the first match. The `issuer_lookup` callable in `app.py` already queries the DB — it just needs to return all issuers instead of the first one's pubkey.

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:176-207` — `_verify_attestation()` currently calls `self._issuer_lookup(jurisdiction)` which returns `Optional[str]` (single pubkey)
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py:17` — `IssuerLookup = Callable[[str], Optional[str]]` type alias
- `packages/civicos-relay/src/civicos_relay/server/app.py:139-145` — `issuer_lookup()` closure that queries `issuer_storage.get_issuers_for_jurisdiction()` but returns only the first verified pubkey
- `packages/civicos-relay/src/civicos_relay/storage/postgres.py:2330` — `get_issuers_for_jurisdiction()` already returns all issuers
- `docs/internal/multi-issuer-lookup-spec.md` — Spec with TrustedIssuer model and updated signature
- `packages/civicos-relay/tests/test_acceptance.py` — Existing acceptance policy tests

## Suggested Approach

1. **Update the type alias** in `acceptance.py`:
   ```python
   # Old
   IssuerLookup = Callable[[str], Optional[str]]
   # New
   IssuerLookup = Callable[[str], list[str]]  # returns list of verified pubkeys
   ```

2. **Update `issuer_lookup` in `app.py:139-145`** to return all verified pubkeys:
   ```python
   def issuer_lookup(jurisdiction: str) -> list[str]:
       issuers = issuer_storage.get_issuers_for_jurisdiction(jurisdiction)
       return [i["issuer_pubkey"] for i in issuers if i.get("verified") and not i.get("revoked")]
   ```

3. **Update `_verify_attestation()` in `acceptance.py:176-207`** to iterate:
   ```python
   issuer_pubkeys = self._issuer_lookup(jurisdiction)
   if not issuer_pubkeys:
       return False
   for pubkey in issuer_pubkeys:
       if verify_attestation_proof(proof, public_key, jurisdiction, pubkey):
           return True
   return False
   ```

4. **Add a test** — cast a voice with an attestation from issuer B, verify it passes acceptance when both issuer A and B are registered.

5. **Update spec** — mark `multi-issuer-lookup-spec.md` steps 3 and 4 as done.

## Tests to Run

```bash
# Acceptance policy tests
pytest packages/civicos-relay/tests/test_acceptance.py -q --override-ini="addopts="

# Attestation multi-issuer tests
pytest packages/civicos-relay/tests/test_attestation_multi_issuer.py -q --override-ini="addopts="

# Issuer endpoint tests
pytest packages/civicos-relay/tests/test_issuer_endpoints.py -q --override-ini="addopts="

# Full relay suite
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] `IssuerLookup` returns `list[str]` instead of `Optional[str]`
- [ ] `_verify_attestation()` iterates all issuers for a jurisdiction
- [ ] Test: attestation from issuer B passes when issuers A and B are both registered
- [ ] Test: attestation from revoked issuer fails
- [ ] `multi-issuer-lookup-spec.md` updated with implementation status
- [ ] `launch.json` item marked done

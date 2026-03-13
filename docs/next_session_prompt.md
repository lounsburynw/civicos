# Recommended: Deploy Marin Test Relays

**Priority:** P0 (`deploy_marin_test_relays`)
**Area:** federation_testbed
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Mill Valley and San Anselmo have been onboarded (data extracted, configs generated). The relay is already multi-jurisdiction — it serves all cities through one endpoint and routes by `jurisdiction` field. "Deploying test relays" actually means deploying **MCP servers** for each city and configuring attestation, since the relay itself needs no changes.

Both jurisdictions are already registered in `config/registry.json` (lines 40-51) with `modal_app_name` set.

## Recommended Task

Deploy MCP server instances for Mill Valley and San Anselmo on Modal, generate attestation keypairs, and verify end-to-end relay routing.

### 1. Deploy MCP Servers (~2 commands each)
```bash
CIVICOS_JURISDICTION=city-mill-valley modal deploy apps/civicos-mcp/modal_mcp.py
CIVICOS_JURISDICTION=city-san-anselmo modal deploy apps/civicos-mcp/modal_mcp.py
```

### 2. Generate Attestation Keypairs
Generate issuer keypairs for each city and update `config/registry.json` with `attestation_issuer_pubkey`.

### 3. Redeploy Relay (picks up new MCP endpoints)
```bash
modal deploy apps/civicos-relay/modal_relay.py
```

### 4. Verify Cross-Jurisdiction Routing
Test that the relay routes AI proxy requests to the correct jurisdiction's MCP server.

## Key Files

- `apps/civicos-relay/modal_relay.py:131-153` — AI proxy jurisdiction routing (reads registry.json)
- `apps/civicos-relay/modal_relay.py:46-50` — registry.json mount into Modal image
- `apps/civicos-mcp/modal_mcp.py:36-79` — MCP per-jurisdiction deployment + secrets
- `config/registry.json:40-51` — Mill Valley & San Anselmo already registered
- `packages/civicos/src/civicos/registry.py:181-195` — Modal app name derivation
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py` — Attestation signing (secp256k1)
- `docs/internal/deployment.md` — Deployment procedures & secrets inventory

## Architecture Notes

- **Relay is single-instance, multi-jurisdiction** — jurisdiction is data, not deployment artifact
- **MCP servers are per-jurisdiction** — each gets its own Modal app
- **Shared database:** RELAY_DATABASE_URL (`lvfikysdbdkpxemssuxa` us-west-1) stores all coordination data with `jurisdiction` field
- **Existing secrets:** `civicos-marin-county-env` already exists for Marin jurisdictions
- **San Rafael attestation pubkey** already configured: `a8a87b73...` (registry.json:14)

## Suggested Approach

1. Check `modal app list` and `modal secret list` for current state
2. Deploy Mill Valley MCP: `CIVICOS_JURISDICTION=city-mill-valley modal deploy apps/civicos-mcp/modal_mcp.py`
3. Deploy San Anselmo MCP: `CIVICOS_JURISDICTION=city-san-anselmo modal deploy apps/civicos-mcp/modal_mcp.py`
4. Verify MCP endpoints respond: `curl https://civicos--civicos-mill-valley-...modal.run/api/tools`
5. Generate attestation keypairs (check `scripts/` for generation script)
6. Update `config/registry.json` with pubkeys
7. Redeploy relay: `modal deploy apps/civicos-relay/modal_relay.py`
8. Test: relay routes `/api/ai/chat` with `jurisdiction: "city-mill-valley"` correctly

## Tests to Run

```bash
# Relay tests
pytest packages/civicos-relay/tests/ -q --override-ini="addopts="

# Verify existing jurisdictions still work
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
for j in ['city-san-rafael', 'city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(j)
    print(f'{j}: {len(c.storage.get_meetings(j))} meetings')"

# Health check after deploy
/health
```

## Success Criteria

- [ ] `modal app list` shows `civicos-mill-valley` and `civicos-san-anselmo` MCP apps running
- [ ] Each MCP endpoint returns tools at `/api/tools`
- [ ] Attestation issuer pubkeys set in `config/registry.json` for both cities
- [ ] Relay routes AI requests to correct jurisdiction MCP server
- [ ] Existing San Rafael relay functionality unaffected

## Known Issues

- **Local SSL cert issue** — anaconda Python's CA bundle is outdated. External HTTPS calls to some hosts (eScribe) fail locally but work on Modal/CI. Other clients (Legistar, Granicus) work fine locally.
- **Legistar API intermittent 500s** — Berkeley/SF. Not related to relay work.

# Recommended: Deploy MCP API Key Gate + Run Platform DB Migration

**Priority:** P0 is `turnkey_city_deployment` (deferred — marked "post E2E operational"). Recommend deploying the API key gate built in Session 26, then tackling a P1+ item.
**Area:** deployment_artifacts > api_server
**Date:** 2026-03-05

> This is recommended context from Session 26. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 26 completed two things:
1. **MCP API Key Gate** — `apps/civicos-mcp/api_key_middleware.py` adds optional API key auth + rate limiting to all `/api/tools/*` REST endpoints. Committed but **not yet deployed**.
2. **Privacy-Preserving Billing ADR** — `docs/decisions/privacy_preserving_billing.md` designs the credit ledger for resident AI billing (design only, no code yet).

## Recommended Task

### Step 1: Deploy MCP with API Key Gate (~15 min)

```bash
modal deploy apps/civicos-mcp/modal_mcp.py

# Verify health shows new auth field
curl -s https://san-rafael.civicosproject.org/health | python3 -m json.tool | grep auth
# Expected: "auth": "optional_api_key"

# Test public access (no key) — should work
curl -s https://san-rafael.civicosproject.org/api/tools/ | head -c 200

# Test invalid key — should get 401
curl -s -H "Authorization: Bearer cvk_live_invalid" https://san-rafael.civicosproject.org/api/tools/
```

### Step 2: Run Platform DB Migration (if needed)

Check if `platform_api_keys` table exists:
```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.getenv('PLATFORM_DATABASE_URL') or os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute(\"SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='platform_api_keys')\")
print('platform_api_keys exists:', cur.fetchone()[0])
conn.close()
"
```

If table doesn't exist: `psql $PLATFORM_DATABASE_URL -f scripts/sql/add_platform_billing.sql`

### Step 3: Pick Next Work Item

After deploy verification, choose from remaining items. All remaining non-P0 items are P3.

## Key Files
- `apps/civicos-mcp/api_key_middleware.py` — Rate limiter + API key FastAPI dependency (NEW)
- `apps/civicos-mcp/rest_api.py:155-162` — Router wired with `Depends(require_api_key_or_rate_limit)`
- `apps/civicos-mcp/modal_mcp.py:405` — Health endpoint shows `"auth": "optional_api_key"`
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — `ApiKeyStore` (validates keys against Platform DB)
- `scripts/sql/add_platform_billing.sql` — DB migration for platform tables
- `docs/decisions/privacy_preserving_billing.md` — Billing ADR (design for future implementation)

## Important Design Notes
- MCP endpoint (`/mcp`) is NOT gated — only REST API (`/api/tools/*`) has middleware
- If `PLATFORM_DATABASE_URL` is not set, middleware passes through (all requests at public rate)
- Relay calls MCP REST endpoints server-to-server without API keys — 60 req/min per IP suffices
- API key format: `cvk_live_` + 32 hex chars, validated via SHA-256 hash lookup

## Success Criteria
- [ ] MCP deployed with API key gate active
- [ ] Health endpoint shows `"auth": "optional_api_key"`
- [ ] Public requests work (rate-limited at 60/min)
- [ ] Invalid key returns 401
- [ ] Relay -> MCP tool calls still work (no regression)

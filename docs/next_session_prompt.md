# Recommended: Address API Key Architecture Notes + Turnkey City Deployment

**Priority:** P0 is `turnkey_city_deployment`
**Area:** city_onboarding > scaling
**Date:** 2026-03-05

> This is recommended context from Session 27. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 27 deployed the full API key infrastructure:
- Platform billing tables (platform_api_keys, platform_usage_logs, platform_usage_daily)
- Self-serve key provisioning: `POST /api/keys/` (live at san-rafael.civicosproject.org)
- End-to-end verified: key creation -> authenticated tool access

Three architecture advisory notes were flagged by critics. These are quick fixes (~15 min) before moving to the P0.

## Recommended Task

### Step 1: Fix Architecture Advisory Notes (~15 min)

1. **Parameterize SQL in `get_usage_stats`/`get_all_usage_summary`** — replace f-string `since_clause` with proper parameterized queries
   - `packages/civicos-services/src/civicos_services/core/api_keys.py:297-310` and `:496-511`

2. **Optional: Add comment about DATABASE_URL fallback being intentional**
   - `packages/civicos-services/src/civicos_services/core/api_keys.py:86`

3. **In-memory rate limiter** — no action needed now, just awareness for future scaling

### Step 2: Turnkey City Deployment (P0)

The main work item. Description: "Make unified config system actually reduce new city deployment effort. Currently config is ~20% of work; extractors, HUD mapping, and elections are ~80%."

Explore what's needed:
- Check `config/registry.json` for jurisdiction config
- Check `packages/civicos-extraction/` for extractor patterns
- Check `docs/critical/EXTRACTOR_PROTOCOL.md`
- Check `docs/user_guides/CITY_ONBOARDING_GUIDE.md`

## Key Files
- `apps/civicos-mcp/rest_api.py:580-650` — Self-serve key provisioning endpoint
- `apps/civicos-mcp/api_key_middleware.py` — Rate limiter + auth dependency
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — ApiKeyStore (DB fallback + sslmode fix)
- `scripts/sql/add_platform_billing.sql` — Migration (already run)

## Important Design Notes
- MCP endpoint (`/mcp`) is NOT gated — only REST API (`/api/tools/*`) has middleware
- API key format: `cvk_live_` + 32 hex chars, validated via SHA-256 hash lookup
- `ApiKeyStore` falls back to `DATABASE_URL` when `PLATFORM_DATABASE_URL` not set (intentional for now)
- Self-serve endpoint creates free-tier keys only (5 signups/hr per IP rate limit)

## Success Criteria
- [ ] SQL injection surface removed (parameterized queries)
- [ ] Turnkey deployment scope understood and approach defined
- [ ] Progress toward reducing city onboarding effort

# Recommended: API Key Architecture Fixes + Turnkey City Deployment + Landing Page

**Priority:** P0 is `turnkey_city_deployment`
**Area:** city_onboarding > scaling
**Date:** 2026-03-06

> This is recommended context from Session 27. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 27 completed the full API key infrastructure and user-facing documentation:
- Platform billing tables live (platform_api_keys, platform_usage_logs, platform_usage_daily)
- Self-serve key provisioning: `POST /api/keys/` (deployed, verified end-to-end)
- User guides updated with REST API docs + get_started tool mentions API access
- Three architecture advisory notes flagged by critics (quick fixes)

## Recommended Task

### Step 1: Fix Architecture Advisory Notes (~15 min)

1. **Parameterize SQL in `get_usage_stats`/`get_all_usage_summary`** — replace f-string `since_clause` with proper parameterized queries
   - `packages/civicos-services/src/civicos_services/core/api_keys.py:297-310` and `:496-511`

2. **Optional: Add comment about DATABASE_URL fallback being intentional**
   - `packages/civicos-services/src/civicos_services/core/api_keys.py:86`

3. **In-memory rate limiter** — no action needed now, just awareness for future scaling

### Step 2: Turnkey City Deployment (P0)

Description: "Make unified config system actually reduce new city deployment effort. Currently config is ~20% of work; extractors, HUD mapping, and elections are ~80%."

Explore what's needed:
- `config/registry.json` — jurisdiction config
- `packages/civicos-extraction/` — extractor patterns
- `docs/critical/EXTRACTOR_PROTOCOL.md` — protocol docs
- `docs/user_guides/CITY_ONBOARDING_GUIDE.md` — onboarding guide

### Future Session: Landing Page + Read the Docs

The project needs a public-facing landing page at `san-rafael.civicosproject.org/` (currently returns health JSON). Should cover:
- What CivicOS is
- Available data and tools
- How to get an API key
- Example queries
- Link to full docs

A Read the Docs site was also discussed for comprehensive documentation (API reference, user guides, architecture). Both are separate session work.

## Key Files
- `apps/civicos-mcp/rest_api.py:557-636` — Self-serve key provisioning endpoint
- `apps/civicos-mcp/api_key_middleware.py` — Rate limiter + auth dependency
- `apps/civicos-mcp/tools/handlers.py:1086-1104` — get_started tool (now mentions API access)
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — ApiKeyStore
- `docs/user_guides/MCP_SETUP_GUIDE.md:282-335` — REST API Access section (new)

## Success Criteria
- [ ] SQL injection surface removed (parameterized queries in api_keys.py)
- [ ] Turnkey deployment scope understood and approach defined
- [ ] Progress toward reducing city onboarding effort

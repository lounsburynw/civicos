# Recommended: Federal Server Deployment

**Priority:** P0 (federal_server_deployment)
**Area:** multi_scale_participation
**Date:** 2026-03-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Federal comment tools (`draft_federal_comment`, `prepare_federal_comment`) are now implemented and wired into civic.act. The missing piece is a **dedicated federal-level Modal server** (`country-united-states`) that serves these tools alongside executive orders and rulemaking search.

Currently all federal tools are served through city-level servers (e.g., `city-san-rafael`). A dedicated federal server would:
- Serve federal data without city-level overhead
- Be reusable across all city jurisdictions
- Enable `federal.civicosproject.org/mcp` endpoint

## What Already Exists

- `FEDERAL_TOOLS` set in `apps/civicos-mcp/handlers/loader.py` — 8 tools including new comment handlers
- `TOOL_LEVELS["federal"]` computes the full tool set for federal level
- `modal_mcp.py` already supports jurisdiction-level configuration
- `jurisdictions/` directory has YAML configs for cities — needs a federal config
- `config/registry.json` already has `federal.civicosproject.org` registered

## Key Files

- `apps/civicos-mcp/modal_mcp.py` — Modal MCP server (needs federal deployment entry)
- `apps/civicos-mcp/handlers/loader.py` — Tool levels and jurisdiction config
- `apps/civicos-mcp/jurisdictions/` — YAML configs per jurisdiction
- `config/registry.json` — Endpoint registry

## Suggested Approach

1. Create `apps/civicos-mcp/jurisdictions/united-states.yaml` — Federal jurisdiction config
2. Add Modal deployment function for `country-united-states` in `modal_mcp.py`
3. Deploy and verify federal tools are served correctly
4. Update extension to route federal queries to dedicated server (optional, could be next session)

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="  # Smoke
cd apps/civicos-extension && npm run build  # Extension builds
```

## Success Criteria

- [ ] `country-united-states` Modal app deployed
- [ ] Federal tools (8) served at federal endpoint
- [ ] `draft_federal_comment` and `prepare_federal_comment` work via federal server
- [ ] Extension Federal tab can optionally route through federal server

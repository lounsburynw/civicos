# Recommended: MCP Usage Logging

**Priority:** P0
**Area:** observability
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed `http_ip_rate_limiting` — added per-IP rate limiting middleware to the relay (sliding-window in-memory counter, 100 req/hr default, POST-only on `/coordination/*`, returns 429). All 11 tests pass.

The MCP server is currently the only production service serving traffic and has **no usage logging**. The API server (`civicos-services`) already has a working `usage_logging_middleware` that can be adapted.

## Recommended Task

Wire usage logging into the MCP Modal server so we can track request volumes, latencies, and errors. The pattern already exists in the API server — it just needs to be adapted for the MCP server's deployment.

## Key Files

- `apps/civicos-mcp/modal_mcp.py` — MCP Modal deployment entry point, needs middleware
- `packages/civicos-services/src/civicos_services/servers/api.py:342` — Existing `usage_logging_middleware` (fire-and-forget to Platform DB)
- `packages/civicos-services/src/civicos_services/servers/api.py:387` — How it's wired into the middleware chain
- `scripts/sql/add_platform_billing.sql` — Platform DB schema (where usage logs go)
- `scripts/modal_usage_rollup.py` — Cron job that rolls up usage data

## Suggested Approach

1. Read the existing `usage_logging_middleware` in `api.py:342-380` to understand the pattern
2. Read `modal_mcp.py` to understand MCP server structure and current middleware setup
3. Add `civicos-platform` to the Modal secrets list in `get_secrets()` (the platform DB connection)
4. Import or adapt the usage logging middleware for MCP endpoints
5. Wire it into the MCP app's middleware chain
6. Verify the `civicos-platform` Modal secret exists: `modal secret list | grep platform`
7. Test locally if possible, otherwise verify via deployment logs

## Tests to Run

```bash
# Smoke test (should still pass)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `usage_logging_middleware` wired into MCP Modal server
- [ ] `civicos-platform` secret added to MCP Modal deployment
- [ ] Usage logs written for MCP tool calls (endpoint, latency, status code)
- [ ] Fire-and-forget pattern (logging failures never block responses)
- [ ] `mcp_usage_logging` marked done in launch.json

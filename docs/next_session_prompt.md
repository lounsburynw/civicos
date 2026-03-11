# Recommended: Relay Usage Logging

**Priority:** P0
**Area:** observability
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed `mcp_usage_logging` — added UsageLoggingMiddleware (raw ASGI) to the MCP Modal server. The middleware logs all HTTP requests (endpoint, method, status code, latency, jurisdiction, key_id) to the Platform DB via fire-and-forget `call_soon`. Also added `civicos-platform` secret and `_mcp_request_key_id` context var.

The relay server (`civicos-relay`) is the other production service and also has **no usage logging**. The same pattern can be applied.

## Recommended Task

Wire usage logging into the relay Modal server. The pattern is now proven in both the REST API server and the MCP server — adapt it for the relay's Starlette app.

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/app.py` — Relay Starlette app, needs middleware
- `apps/civicos-mcp/modal_mcp.py:396-445` — Reference: MCP UsageLoggingMiddleware (just completed)
- `packages/civicos-services/src/civicos_services/servers/api.py:342-378` — Reference: REST API middleware
- `packages/civicos-services/src/civicos_services/core/api_keys.py:324-355` — `ApiKeyStore.log_usage()`

## Suggested Approach

1. Read `app.py` to understand the relay's middleware chain and app structure
2. Check if the relay Modal deployment already has `civicos-platform` secret
3. Add UsageLoggingMiddleware (adapt from MCP pattern — may use BaseHTTPMiddleware or raw ASGI)
4. Wire into middleware chain
5. Test relay endpoints still work

## Success Criteria

- [ ] Usage logging middleware wired into relay server
- [ ] `civicos-platform` secret available in relay deployment
- [ ] Usage logs written for relay requests (coordination, AI proxy endpoints)
- [ ] Fire-and-forget pattern (logging failures never block responses)
- [ ] `relay_usage_logging` marked done in launch.json

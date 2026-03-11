# Recommended: Deploy Usage Rollup

**Priority:** P0
**Area:** observability
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Usage logging middleware is now wired into all three production services (REST API, MCP, Relay). Each logs per-request data (endpoint, method, status, latency, jurisdiction, key_id) to `platform_usage_logs` in the Platform DB via `ApiKeyStore.log_usage()`. The final piece is deploying the usage rollup cron job that aggregates raw logs into daily summaries for billing and dashboards.

## Recommended Task

Deploy `scripts/modal_usage_rollup.py` as a Modal cron job and verify the Platform DB has all required tables. The script exists but is NOT currently deployed (`modal app list` shows no rollup app). The SQL schema file also exists but may not be applied to the Platform DB yet.

## Key Files

- `scripts/modal_usage_rollup.py` -- Rollup cron job (aggregates `platform_usage_logs` into daily summaries)
- `scripts/sql/add_platform_billing.sql` -- Platform DB schema (usage_logs, rollup tables, billing tables)
- `packages/civicos-services/src/civicos_services/core/api_keys.py:324-355` -- `log_usage()` that writes raw logs
- `apps/civicos-mcp/modal_mcp.py:403-452` -- MCP UsageLoggingMiddleware (reference)
- `apps/civicos-relay/modal_relay.py:163-209` -- Relay UsageLoggingMiddleware (just added)

## Suggested Approach

1. Read `scripts/modal_usage_rollup.py` to understand the rollup logic and Modal cron schedule
2. Read `scripts/sql/add_platform_billing.sql` to understand required tables
3. Check if Platform DB tables exist: connect via `PLATFORM_DATABASE_URL` and list tables
4. If tables missing, apply the SQL schema
5. Deploy the rollup cron: `modal deploy scripts/modal_usage_rollup.py`
6. Verify deployment: `modal app list | grep rollup`
7. Optionally trigger a manual run to verify it works: `modal run scripts/modal_usage_rollup.py`
8. Mark `deploy_usage_rollup` done in `launch.json`

## Tests to Run

```bash
# No dedicated test file — verify via:
modal app list | grep rollup                    # Cron is deployed
modal run scripts/modal_usage_rollup.py         # Manual trigger works
```

## Success Criteria

- [ ] Platform DB has all required tables from `add_platform_billing.sql`
- [ ] `modal_usage_rollup.py` deployed as a Modal cron job
- [ ] Manual trigger completes without errors
- [ ] `deploy_usage_rollup` marked done in `launch.json`

## What Changed This Session (uncommitted)

1. `apps/civicos-relay/modal_relay.py` -- UsageLoggingMiddleware, api_keys.py mount, civicos-platform secret
2. `launch.json` -- `relay_usage_logging` done, `deploy_usage_rollup` set as P0

## Remaining Security Audit Warnings (informational, not blocking)

- Coordination router has no acceptance policy enforcement (relay has it, services router doesn't)
- `/coordination/attest` endpoint has its own inline clock skew check rather than using shared `_check_created_at()`
- IP rate limiting is in-memory only -- on multi-container Modal, each container has its own counter

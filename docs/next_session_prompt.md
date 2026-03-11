# Recommended: Acceptance Policy Monitoring

**Priority:** P0
**Area:** observability
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The relay acceptance policy is now fully wired: rate limiting, PoW verification (server + client), attestation verification, and write metadata tracking. However there's no observability into how it's performing. With usage logging live on all three services (API, MCP, Relay), the write-side acceptance policy is the missing piece for the "observe usage to inform pricing" strategy.

## Recommended Task

Add monitoring for relay acceptance policy: rejections by tier, rate limit hits/day, total writes by tier. This feeds into the billing model decision (deferred — needs usage data first).

## Key Files

- `packages/civicos-relay/src/civicos_relay/server/acceptance.py` — `AcceptancePolicy.check()` returns `PolicyResult` with `accepted`, `tier`, `reason`
- `packages/civicos-relay/src/civicos_relay/server/app.py:360-391` — voice endpoint calls `_check_acceptance()`
- `scripts/sql/add_platform_billing.sql` — Platform DB schema (usage_logs table already exists)
- `packages/civicos-services/src/civicos_services/core/api_keys.py` — `ApiKeyStore.log_usage()` for fire-and-forget logging pattern

## Suggested Approach

1. Add acceptance policy outcome logging to Platform DB — log tier, accepted/rejected, reason, event_type per write
2. Could reuse `platform_usage_logs` table (already has endpoint, status_code) or add a new `platform_acceptance_logs` table
3. Wire into `_check_acceptance()` in app.py — fire-and-forget pattern (same as read-side usage logging)
4. Add a rollup query or admin endpoint for: rejections/day by tier, writes/day by tier, rate limit hits/day
5. Consider adding to the daily rollup in `scripts/modal_ingest.py` (already runs usage rollup)

## Tests to Run

```bash
pytest packages/civicos-relay/tests/test_acceptance_policy.py -v
pytest packages/civicos-relay/tests/test_acceptance.py -v
```

## Success Criteria

- [ ] Acceptance policy outcomes logged to Platform DB (tier, accepted, reason, event_type)
- [ ] Fire-and-forget pattern (logging failure doesn't block writes)
- [ ] Admin can query write volume by tier and rejection reasons
- [ ] Existing acceptance tests still pass

## Recent Completions

- **NIP-13 PoW mining** (this session) — `civicos-client/src/pow.ts`, castVoice/castComment mine transparently
- **External cron triggers** (parallel session) — Modal crons migrated to GitHub Actions workflows
- **Billing deferred** — Stripe items moved to P3, need usage data for pricing model decision

## Infrastructure Notes

- **Platform DB**: Supabase project `axhmnnvefrtliyszbuou` (us-west-1), pooler URL required for Modal (IPv6 not supported)
- **Modal crons**: Now run via GitHub Actions (`.github/workflows/cron-*.yml`), not `modal.Cron()`

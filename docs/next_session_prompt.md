# Recommended: Verify Ingestion Fixes + Federation ADR (`federation_adr`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-13

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## First: Verify Ingestion Fixes

Prior session deployed 8 ingestion fixes. The next high-velocity cron (~2:20 PM UTC / 7:20 AM Pacific on Apr 13) is the first run with all fixes. **Check ntfy or cron logs before starting main work:**

```bash
# Check latest cron run
gh run list --workflow=cron-high-velocity.yml --limit 3

# Check for city-sausalito (was missing from cron)
gh run view <run_id> --log | grep -i "sausalito"

# Check school-san-rafael (93 days stale, now simbli)
gh run view <run_id> --log | grep -i "school-san-rafael"

# Check simbli routing (7 school districts, previously skipped)
gh run view <run_id> --log | grep -i "simbli"

# Check issues refresh (10 Marin cities, previously "No issues source configured")
gh run view <run_id> --log | grep "issues" | head -20
```

If anything failed, fix it before proceeding.

## Then: Federation ADR

Write an Architecture Decision Record for federation boundaries. This is a documentation/design task, not implementation. The ADR should cover:

1. **Which protocols change vs. stay** — What's shared across jurisdictions (token issuance, voice, identity) vs. what's per-jurisdiction (data, relay endpoints, sync)
2. **Execution model for cross-jurisdiction queries** — How `walk_scope` fans out to parent/sibling jurisdictions, latency implications, failure modes
3. **Trust chain design** — How relays verify each other's attestations, how token issuers from different jurisdictions interoperate
4. **Federation vs. replication** — Where data lives vs. where it's queried, caching strategy

## Existing Context to Read

- `docs/public/decisions/` — Existing ADRs (vector storage, entity IDs, federation, tool scope)
- `docs/public/relay/overview.md` — Relay architecture, trust model
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py` — Acceptance policy tiers
- `packages/civicos-relay/src/civicos_relay/voice/` — Voice + crypto modules
- `apps/civicos-mcp/tools/scope_walk.py` — `walk_scope` implementation
- `docs/public/decisions/tool_scope_and_federation.md` — Current scope/federation decision

## Success Criteria

- [ ] Ingestion cron verified: city-sausalito, school-san-rafael, simbli schools, issues all refreshing
- [ ] ADR written at `docs/public/decisions/federation_boundaries.md`
- [ ] Documents protocol boundaries (shared vs. per-jurisdiction)
- [ ] Documents cross-jurisdiction query execution model
- [ ] Documents trust chain for multi-relay federation
- [ ] A new P0 assigned before session end

## Backlog Items (not P0, but noted for context)

These were identified during the ingestion audit:
- **Municipal code** expansion: only 6/24 jurisdictions have it
- **Transcript backfill**: 10 jurisdictions at 0% coverage, free captions mode available (`--transcript-mode captions`)
- **Budget data**: San Rafael only
- **Diligent platform**: 2 school districts (school-ross-valley, school-marin-county-oe) — no extraction client

## Pre-existing Test Failures

**CI is green.** All smoke, unit (4 groups), and integration (5 groups) pass.

## Remaining Launch Items

| Priority | Item | Category |
|----------|------|----------|
| P0 | `federation_adr` | federation_testbed |
| P3 | `operator_relay_dockerfile` | operator_readiness |
| P3 | `direct_city_submission` | federation_testbed |
| P3 (deferred) | `billing_endpoint_deployment` | billing_payments |
| P3 (deferred) | `stripe_key_delivery_automation` | billing_payments |
| P3 (deferred) | `stripe_secrets_deployment` | billing_payments |

# Recommended: Query Monitoring and Docs

**Priority:** P0 (query_monitoring_and_docs)
**Area:** federation_testbed
**Date:** 2026-03-24

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed two major tracks: turnkey onboarding (12/12) and multi-scale participation (18/18). The platform now supports onboarding any US city with a supported meeting platform in one command, batch onboarding multiple cities, cost estimation before ingestion, and generalized state-level legislation syncing for all 50 states.

The remaining launch work is mostly polish and operator readiness. `query_monitoring_and_docs` is the highest-priority remaining item — it adds production observability (query latency logging, connection pool metrics) and sweeps ~10 doc files to update stale decision ID format references.

## What Was Done This Session

10 commits covering:
- `onboard_deploy_integration` — Registry update + Modal deploy + API verification (`--deploy` flag)
- `onboard_cost_estimate` — Extrapolates LLM cost from sample, prompts before full backfill (`--yes` flag)
- `onboard_configurable_defaults` — YAML `ingestion.days_past` / `sample_days` overrides
- `onboard_batch_mode` — `--cities "A,B,C"` with aggregate report
- `onboard_transcript_auto` — YouTube channel auto-detection via Data API
- `legislation_adapter_unification` — LegislationAdapter queries storage+vectors directly (no API calls on query path)
- `downward_query_scaling` — Fan-out capped at 20 jurisdictions
- `turnkey_state_onboarding` — STATE_CODE_MAP for all 50 states, dynamic legislation loop, registry-based state resolution
- Critic fixes: removed silent CA fallback, added lru_cache for registry loading, consolidated registry loading via `civicos.registry`

## Key Files

| File | Purpose |
|------|---------|
| `packages/civicos-services/src/civicos_services/query/verbs.py` | v2 query execution — add latency logging here |
| `packages/civicos-services/src/civicos_services/servers/api.py` | API server — middleware for request metrics |
| `packages/civicos/src/civicos/storage/postgres_backend.py` | Connection pool — add pool metrics here |
| `docs/public/data-dictionary.md` | Primary doc to check for stale decision ID formats |
| `docs/public/api.md` | API doc — check for stale references |

## Suggested Approach

1. **Query latency logging** — Add timing to `execute_search()` and `_execute_cross_jurisdiction_search()` in `verbs.py`. Log query time, corpus breakdown, and jurisdiction count at INFO level.
2. **Connection pool metrics** — Add pool size/available/waiters to the `/health` endpoint response in `api.py`.
3. **Alert thresholds** — Define thresholds (e.g., >5s query time) and log at WARNING level.
4. **Docs sweep** — Search for stale `decision:` ref format patterns across docs/. The old format was `decision:{jurisdiction}:{id}`, verify all examples match current `{type}:{jurisdiction}:{id}` pattern.

## Tests to Run
```bash
pytest packages/civicos-services/tests/test_query_v2.py -v --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Query latency logged at INFO level for all v2 verbs
- [ ] Connection pool metrics available via `/health` endpoint
- [ ] Warning logs for queries exceeding threshold
- [ ] No stale decision ID format references in docs/
- [ ] All existing tests pass

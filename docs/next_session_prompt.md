# Recommended: Query Engine Performance (Session B)

**Priority:** P0 (cross_marin_query_prototype) / P1 (query_engine_performance)
**Area:** federation_testbed > operator_readiness
**Date:** 2026-03-17

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session A of a 4-session game plan is complete. Cross-jurisdiction queries work end-to-end: querying `county-marin` fans out to all 3 child cities (SR, MV, SA) with semantic relevance scores. Decision IDs migrated to stable meeting-scoped ordinals. v2 mounted on REST API. **But query latency is 9.4s** — mostly from opening a new TCP connection per query (no connection pooling).

## Recommended Task

**Session B: Query Engine Performance** — make cross-jurisdiction queries fast under load.

## Key Files
- `packages/civicos/src/civicos/storage/postgres_backend.py:133` — `_get_connection()` opens fresh TCP connection every call
- `packages/civicos/src/civicos/storage/pgvector_backend.py:1384` — `SET hnsw.ef_search = 200` (overkill for 17k vectors)
- `packages/civicos-services/src/civicos_services/query/verbs.py:37` — `CORPUS_TIMEOUT_S = 20`
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py` — freshly rewritten with caching + downward resolution

## Suggested Approach
1. **Connection pooling** — Replace per-call `psycopg2.connect()` with `ThreadedConnectionPool` in PostgresBackend. Biggest single win. civicos-relay already uses `SimpleConnectionPool` (see `packages/civicos-relay/src/civicos_relay/storage/postgres.py`).
2. **Tune ef_search** — Drop from 200 to ~80. At 17k vectors, 200 is extreme overkill trading latency for marginal recall.
3. **Profile end-to-end** — Measure cross-jurisdiction query latency with 3 cities. Target: <3s for a 3-city fan-out.
4. **Deploy** — Push updated API + MCP to Modal with pooling.

## Tests to Run
```bash
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] ConnectionPool in PostgresBackend (min=2, max=10 or similar)
- [ ] ef_search tuned to 80 (or data-driven value)
- [ ] Cross-jurisdiction query (3 cities) completes in <3s
- [ ] 150 tests still passing
- [ ] Deployed to Modal

## Game Plan Context

| Session | Item | Status |
|---------|------|--------|
| **A** | Downward resolution, registry cache, v2 on REST | **Done** (this session) |
| **B** | Connection pooling, ef_search tuning, profiling | **Next** |
| **C** | Configurable refresh policies (GH Actions cron) | Planned |
| **D** | Pagination protocol, monitoring, docs sweep | Planned |

All items tracked in `launch.json` under `federation_testbed` and `operator_readiness`.

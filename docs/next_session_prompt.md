# Recommended: v2 Adapter Storage Refactor

**Priority:** P0 (`v2_adapter_storage_refactor`)
**Area:** federation_testbed > v2 query layer cleanup
**Date:** 2026-03-14

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session implemented cross-jurisdiction queries in the v2 query layer (`include_parents`/`include_siblings` on `SearchRequest`), updated 9 docs to position v2 as the primary API (removing legacy CivicOS methods from public docs), and validated with real PostgreSQL data. The validation revealed that v2 corpus adapters create CivicOS instances per jurisdiction, causing connection pool exhaustion and cold-start thundering herd (pgvector cold queries take ~15s). Workarounds were applied (shared backends, warm-then-fan-out, 20s timeout) but the root cause is that adapters shouldn't go through CivicOS at all.

## What Was Done This Session

1. **Cross-jurisdiction queries** — `jurisdictions.py` (resolution, tiers), `verbs.py` (`_execute_cross_jurisdiction_search`), `models.py` (new fields). 18 new tests, 130 total passing.
2. **Doc overhaul** — Removed legacy CivicOS methods from all public docs (api.md, quickstart, mcp/setup, building-agents, README, packages/civicos). Updated internal specs. Updated CLAUDE.md.
3. **Real data validation** — San Rafael returns 10 housing results across decisions + meetings. Sibling cities return empty (0 decisions extracted). Latency: ~52s cold, needs the refactor.
4. **Workarounds** — Shared storage/vector backends across jurisdictions, warm base first then parallel fan-out, timeout bumped to 20s.

## Recommended Task

Refactor v2 corpus adapters to call storage/vector backends directly instead of CivicOS query methods. Each adapter currently receives a `civic` (CivicOS) object and calls methods like `civic.what_happened()`, `civic.what_applies()`, etc. These are thin wrappers over `history.py` functions and `StorageBackend`/`VectorBackend`. The adapters should receive storage/vector backends directly.

## Key Files

- `packages/civicos-services/src/civicos_services/query/adapters.py` — All 10 adapters, each calls CivicOS methods
- `packages/civicos-services/src/civicos_services/query/verbs.py:76-98` — Where adapters are called (`adapter.search(civic, jid, ...)`)
- `packages/civicos-services/src/civicos_services/query/verbs.py:291-395` — Cross-jurisdiction fan-out with CivicOS workarounds
- `packages/civicos/src/civicos/history.py:1150` — `search_decisions()` that `what_happened()` wraps
- `packages/civicos/src/civicos/civicos.py:366-402` — `what_happened()` wrapper (thin delegation)
- `packages/civicos-services/tests/test_query_v2.py` — 130 tests, `make_mock_civic()` at line 124

## Suggested Approach

1. **Change adapter signature** — `search(self, civic, jurisdiction, ...)` → `search(self, storage, vectors, jurisdiction, ...)` where `storage: StorageBackend` and `vectors: Optional[VectorBackend]`
2. **Refactor each adapter** — Replace `civic.what_happened(query)` with direct calls to `search_decisions(...)` from `history.py`, or better, direct `storage.get_decisions()` + `vectors.search()` calls
3. **Update `execute_search`** in `verbs.py` — Pass `civic._storage` and `civic._vectors` to adapters instead of `civic`
4. **Simplify cross-jurisdiction** — `_execute_cross_jurisdiction_search` no longer needs to create CivicOS instances. Just pass storage/vectors with the target jurisdiction ID
5. **Update tests** — `make_mock_civic()` becomes mock storage/vector backends. The mock patterns already exist in the codebase

## Tests to Run

```bash
# v2 query tests (primary — 130 tests)
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts="

# Core smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Adapters receive storage/vector backends, not CivicOS
- [ ] Cross-jurisdiction fan-out no longer creates CivicOS instances
- [ ] Warm-then-fan-out workaround and shared backend hack removed
- [ ] All 130 v2 tests pass (updated mocks)
- [ ] Real data cross-jurisdiction query works with improved latency

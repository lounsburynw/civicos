# Recommended: Cross-Marin Query Prototype

**Priority:** P0 (cross_marin_query_prototype)
**Area:** federation_testbed
**Date:** 2026-03-27

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The v2 query layer already supports cross-jurisdiction queries with `include_parents` and `include_siblings`. Infrastructure is done: jurisdiction resolution, tier boosting (self=1.0, sibling=0.8), parallel fan-out, semantic relevance scores, noise filter (MIN_RELEVANCE=0.45), and 130+ tests. Data is ready: San Rafael 83 decisions, Mill Valley 60, San Anselmo 96.

Previous session completed `upcoming_ballot_preview` — 107 candidates across 8 contests stored for the June 2026 primary via CA SOS PDF parsing.

Three items remain per the notes in launch.json:
1. **Downward resolution** — query `county-marin` should fan out to child cities
2. **Cache registry.json in memory** — avoid re-reading on every request
3. **Mount v2 on REST API server** — expose v2 endpoints on the deployed API

## What Needs to Be Done

### 1. Downward Resolution (Primary)

Currently, querying `county-marin` with `include_siblings` only resolves *sibling* counties. It should also resolve *child* cities (San Rafael, Mill Valley, San Anselmo). The jurisdiction resolution logic needs a `include_children` or downward-expansion mode.

### 2. Cache registry.json

`registry.json` is read from disk on every query. Cache it in memory with a TTL or load once at startup.

### 3. Mount v2 on REST API Server

The v2 query verbs need to be mounted on the Modal-deployed REST API server so they're accessible externally.

## Key Files

- `packages/civicos-services/src/civicos_services/query/jurisdictions.py` — Jurisdiction resolution (parent/sibling/child expansion)
- `packages/civicos-services/src/civicos_services/query/verbs.py` — Query verb implementations (search, upcoming, context, act, explore)
- `packages/civicos-services/src/civicos_services/query/models.py` — SearchRequest, SearchResponse models
- `packages/civicos-services/tests/test_query_v2.py` — 130+ tests for v2 layer
- `docs/internal/cross-jurisdiction-query-spec.md` — Full design spec with relevance tiers
- `config/registry.json` — Jurisdiction hierarchy (parent_jurisdictions, etc.)
- `packages/civicos-services/src/civicos_services/servers/modal_api.py` — REST API server (where v2 endpoints get mounted)

## Suggested Approach

1. **Start with downward resolution** — read `jurisdictions.py` to understand current resolution logic, then add child-city expansion when querying a county
2. **Add registry caching** — simple module-level cache with lazy loading
3. **Wire v2 to REST API** — add routes in `modal_api.py` that delegate to v2 verbs
4. **Test end-to-end** — query `county-marin` for "housing" and verify results from San Rafael, Mill Valley, and San Anselmo appear

## Relevant Memories

- `memory/project_query_interface.md` — v2 query interface is primary API; CivicOS methods are internal-only
- `memory/project_adapter_refactor.md` — v2 adapters should call storage/vector backends directly

## Tests to Run

```bash
# v2 query tests (130+)
pytest packages/civicos-services/tests/test_query_v2.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Querying `county-marin` with downward expansion returns results from child cities
- [ ] registry.json is cached in memory (not re-read per request)
- [ ] v2 endpoints mounted on REST API server
- [ ] End-to-end: search "housing" on county-marin returns results from SR, MV, SA

# Recommended: Query Interface Operators

**Priority:** P0 (`query_interface_operators`)
**Area:** operator_readiness
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The v2 unified query interface was hardened this session — cursor pagination, aggregate mode, and trend mode are all implemented with 88 passing tests. The next step is set operators (`-` for diff/monitoring, `&` for intersection) and civic jargon lookup, which are the remaining deferred items from the ADR. Also carries forward: live-data integration tests and RRF ranking calibration.

## What Was Built This Session

- **Cursor pagination**: stateless base64-encoded per-corpus offsets, `SearchRequest.cursor` → planner → adapters → `ResponseMeta.cursor`
- **Aggregate mode**: `mode: "aggregate"` returns `AggregateEntry` (count, earliest, latest) per corpus
- **Trend mode**: `mode: "trend"` returns `TrendBucket` (year-month period + count per corpus)
- **All 11 adapters** accept `offset` parameter for pagination
- **MCP schema** updated with `mode` + `cursor` params

## Recommended Task

Implement query composition operators and civic jargon lookup per the ADR spec (`docs/public/decisions/query_interface.md:293-308`).

### 1. Set operators (highest priority)

The ADR defines three operators mirroring SQL composition:

| Operator | Meaning | Example |
|----------|---------|---------|
| `+` (UNION) | Combine results | Already implicit in multi-corpus |
| `-` (EXCEPT) | What's new/gone | `search(today) - search(last_week)` = diff |
| `&` (INTERSECT) | Cross-corpus match | `decisions & testimony` = decisions with testimony |

Design decision needed: should operators be expressed as a `compare` field on `SearchRequest` (e.g., `compare: {op: "-", cursor: <previous>}`) or as a separate verb (`civic.compare`)?

### 2. Civic jargon lookup

"What is a conditional use permit?" doesn't map to search — it's a definition lookup. Extend `civic.context` to accept `concept` as an alternative to `ref`, pulling from `municipal_code` corpus.

### 3. Live-data integration tests (carried forward)

Current 88 tests use mocks. Need tests against real PostgreSQL:
- `civic.search(query="housing", corpus=["decisions", "legislation"])` returns merged results
- `civic.explore(what="corpora")` counts match `/data-status`
- Pattern: `test_integration_query_v2.py` alongside existing `test_integration_rag_san_rafael.py`

### 4. RRF ranking calibration (carried forward)

Test 5-10 real queries across 3+ corpora. Check if high-relevance results from small corpora get buried. Consider corpus-specific k values or caller-supplied weights (`corpus: {"decisions": 2.0}`).

## Key Files

- `packages/civicos-services/src/civicos_services/query/models.py:40` — SearchMode enum (add operator-related types here)
- `packages/civicos-services/src/civicos_services/query/models.py:97` — SearchRequest (add compare/operator fields)
- `packages/civicos-services/src/civicos_services/query/verbs.py:37` — execute_search (add operator logic)
- `packages/civicos-services/src/civicos_services/query/verbs.py:264` — execute_context / parse_ref (extend for concept lookup)
- `packages/civicos-services/src/civicos_services/query/merger.py:18` — RRF (may need intersection logic)
- `packages/civicos-services/tests/test_query_v2.py` — 88 tests (add operator + jargon tests)
- `docs/public/decisions/query_interface.md:293-308` — ADR spec for operators and jargon

## Tests to Run

```bash
# Existing v2 tests (should stay green throughout)
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts="

# Core smoke tests (regression check)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Set operator `-` (diff) implemented and tested
- [ ] Set operator `&` (intersect) implemented and tested
- [ ] `civic.context(concept="conditional use permit")` returns definition from municipal_code
- [ ] Live-data integration tests pass against PostgreSQL
- [ ] RRF ranking verified with 5+ real queries
- [ ] All 88+ existing tests still pass

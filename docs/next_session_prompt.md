# Recommended: Query Interface Operators (continued)

**Priority:** P0 (`query_interface_operators`)
**Area:** operator_readiness
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session implemented the core operator features for the v2 query interface: diff mode (`-`), intersect mode (`&`), and civic jargon lookup via `civic.context(concept=...)`. All are working with 112 tests passing. The remaining work on this P0 item is: live-data integration tests against PostgreSQL and RRF ranking calibration with real queries.

## What Was Built This Session

- **Diff mode** (`mode: "diff"` + `snapshot_date`): filters results to items dated after the snapshot. Validated with ISO format. Handles edge cases (undated items, on-snapshot-date exclusion, datetime normalization).
- **Intersect mode** (`mode: "intersect"` + `intersect_corpus`): parallel search on secondary corpora, matches by date overlap or significant title words (>= 6 chars to avoid false positives on common civic terms).
- **Concept lookup** (`civic.context(concept="conditional use permit")`): searches municipal_code corpus, returns matching sections with excerpts. Mutually exclusive with `ref` via model_validator.
- **Hardening pass**: snapshot_date ISO validation, intersect error logging (mirrors run_corpus pattern), null guards on adapter and request.ref, async executor + timeout on concept lookup.
- **MCP schema** updated for all new fields.
- **ADR** (query_interface.md) open questions 1 & 2 marked resolved.

## Recommended Task

Complete the remaining items to close out this P0:

### 1. Live-data integration tests (highest priority)

Current 112 tests all use mocks. Need tests against real PostgreSQL to validate the full stack:

```python
# Pattern: test_integration_query_v2.py alongside test_integration_rag_san_rafael.py
# Must load .env for DATABASE_URL

# Test cases:
# - civic.search(query="housing", corpus=["decisions", "legislation"]) returns merged results
# - civic.search(query="housing", corpus=["decisions"], mode="diff", snapshot_date="2025-01-01") returns recent items
# - civic.search(query="housing", corpus=["decisions"], mode="intersect", intersect_corpus=["testimony"]) returns correlated items
# - civic.context(concept="conditional use permit") returns municipal code sections
# - civic.explore(what="corpora") counts match /data-status
# - civic.search mode="aggregate" counts are non-zero for populated corpora
```

### 2. RRF ranking calibration

Test 5-10 real queries across 3+ corpora. Check if high-relevance results from small corpora get buried by larger corpora. Current RRF uses k=60 uniformly.

Questions to answer:
- Does a highly relevant decision get outranked by mediocre legislation results?
- Should `corpus_weights` be added to SearchRequest? (ADR open question #3)
- Are there queries where the top-5 results are all from one corpus despite multi-corpus search?

### 3. Multi-jurisdiction fan-out (stretch)

Not yet implemented. Would allow `civic.search(query="housing", jurisdiction=["city-san-rafael", "county-marin"])`. Lower priority than integration tests and calibration.

## Key Files

- `packages/civicos-services/src/civicos_services/query/models.py` — SearchRequest, SearchMode, ContextRequest (all updated this session)
- `packages/civicos-services/src/civicos_services/query/verbs.py` — execute_search (diff/intersect at lines 131-232), _execute_concept_lookup (lines 530-600)
- `packages/civicos-services/src/civicos_services/query/merger.py:18` — RRF with k=60 (calibration target)
- `packages/civicos-services/tests/test_query_v2.py` — 112 tests (add integration tests here or in new file)
- `packages/civicos/tests/test_integration_rag_san_rafael.py` — existing integration test pattern to follow
- `docs/public/decisions/query_interface.md:307` — ADR open question #3 (corpus weights)

## Tests to Run

```bash
# Existing v2 tests (must stay green)
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts="

# Core smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Integration tests (once written)
pytest packages/civicos-services/tests/test_integration_query_v2.py -q --override-ini="addopts="
```

## Success Criteria

- [x] Set operator `-` (diff) implemented and tested
- [x] Set operator `&` (intersect) implemented and tested
- [x] `civic.context(concept="...")` returns definition from municipal_code
- [ ] Live-data integration tests pass against PostgreSQL
- [ ] RRF ranking verified with 5+ real queries
- [ ] All 112+ existing tests still pass
- [ ] P0 item marked done (or remaining work re-scoped)

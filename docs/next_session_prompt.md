# Recommended: cross_marin_query_prototype

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-03-16

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session closed critical Marin data gaps: Mill Valley decisions went from 2 to 60, chunk/decision vectors were indexed for both MV and SA, and MinutesViewer redirect handling was fixed. A multi-PDF chunk extraction upgrade was built and validated (6 to 106 chunks/meeting) but full re-extraction was intentionally deferred to the refresh framework -- we want the same turnkey flow for us and for any new operator.

Cross-Marin queries are now unblocked. All three jurisdictions have searchable chunks, decisions, and meetings.

## Recommended Task

Implement cross-jurisdiction queries within Marin County via the v2 query layer. `SearchRequest.include_parents`/`include_siblings` should enable queries that span San Rafael, Mill Valley, and San Anselmo with tier-based relevance boosting (local > sibling > parent).

## Current Data State

| Corpus | San Rafael | Mill Valley | San Anselmo |
|--------|-----------|-------------|-------------|
| Meetings | 96 | 113 | 171 |
| Chunks (indexed) | 7,039 | 601 | 489 |
| Decisions (indexed) | 83 | 60 | 96 |
| Transcripts | 41 | 0 | 0 |
| Issues | 2,084 | 0 | 0 |
| Municipal Code | 2,364 | 0 | 0 |

Note: MV chunks are HTML-only (avg 255 chars). Multi-PDF upgrade is committed (`chunks.py:_extract_granicus_multi_pdf`) but full re-extraction deferred to `configurable_refresh_policies`. SA chunks are proper PDF extracts (avg 1,156 chars).

## Key Files

- `packages/civicos-services/src/civicos_services/query/` -- v2 query layer
- `packages/civicos-services/src/civicos_services/query/search.py` -- SearchRequest with `include_parents`/`include_siblings`
- `packages/civicos/src/civicos/storage/pgvector_backend.py` -- vector search backend
- `data/jurisdictions/city-*.yaml` -- parent_jurisdictions: [county-marin, ...] for all three cities
- `packages/civicos-services/tests/test_query_v2.py` -- existing v2 query tests

## Suggested Approach

1. Load context on the v2 query layer (`/load_context` or Explore agent on `packages/civicos-services/src/civicos_services/query/`)
2. Understand how `SearchRequest.include_parents`/`include_siblings` are defined and whether any cross-jurisdiction logic exists
3. Implement sibling discovery: given `city-san-rafael` with `parent: county-marin`, find siblings sharing the same parent
4. Add tier-based relevance boosting: local results score higher than sibling results
5. Test with real queries across Marin County jurisdictions

## Tests to Run

```bash
pytest packages/civicos-services/tests/test_query_v2.py -v
```

## Success Criteria

- [ ] `POST /api/v2/civic/search` with `include_siblings=true` returns results from MV and SA
- [ ] Local jurisdiction results rank higher than sibling results
- [ ] Cross-jurisdiction query for "housing" returns decisions from all three cities
- [ ] Existing single-jurisdiction queries are unaffected

## Known Issues (not blocking)

- **MV duplicate meetings**: view_2 and view_3 create identical meetings per date. Fix at Granicus discovery time -- not urgent for query prototype.
- **MV chunk quality**: HTML-only, avg 255 chars. Multi-PDF code committed, re-extraction deferred to refresh framework.
- **`configurable_refresh_policies`** (P1): chunk re-extraction, Granicus dedup, and new city onboarding should all flow through this. Design principle: same turnkey process for internal use and any new operator/dev.

# Cross-County Relevance Filtering Spec

**Status:** Not started (depends on Phase A validation)
**Date:** 2026-03-11 (updated 2026-03-13)
**Launch.json item:** `cross_county_query_prototype`
**Depends on:** `cross_marin_query_prototype` (Phase A findings inform this)

## Problem

Cross-jurisdiction queries within a county (San Rafael ↔ Mill Valley) share meaningful context: same county supervisors, same regional bodies, same water district. Cross-county queries (San Rafael ↔ Berkeley) share only state-level context. Without relevance filtering, a San Rafael user querying "water policy" would get EBMUD results from Berkeley alongside MMWD results from Marin — only one is relevant.

This spec defines how the system determines when cross-county results are relevant and how to filter noise.

## Design Principles

1. **Shared parent = relevant** — jurisdictions sharing a parent in the `parent_jurisdictions` chain have shared legislative context at that level.
2. **No shared parent = explicit only** — cross-county results appear only when the user explicitly requests them or searches by jurisdiction name.
3. **State level is always shared** — state and federal legislation applies to all California jurisdictions regardless of county.
4. **Operational vs policy distinction** — a Berkeley decision about "housing policy" might be relevant as precedent. A Berkeley decision about "123 Main St variance" is not.

## Relevance Rules

### Rule 1: Parent Chain Inclusion

Given a query for jurisdiction J, automatically include results from all ancestors in `parent_jurisdictions`:

```
city-san-rafael → county-marin → state-california → country-united-states
```

These are always included, labeled by source jurisdiction. **Implemented** via `include_parents=True` on v2 `SearchRequest`.

### Rule 2: Sibling Inclusion (Opt-In)

Siblings share the same immediate parent county. For `city-san-rafael`, siblings under `county-marin` include Mill Valley, San Anselmo, etc.

Include when:
- `include_siblings=True` is passed
- Topic is policy-level (housing, zoning, transportation, climate)

Exclude when:
- Topic is operational (permits, street closures, personnel)
- Default behavior (sibling inclusion is opt-in)

**Implemented** via `include_siblings=True` on v2 `SearchRequest`.

### Rule 3: Cross-County Exclusion (Default)

Berkeley (`county-alameda`) results are NOT included in San Rafael queries by default. They share `state-california` as an ancestor, but state-level results are already included via Rule 1.

Include when:
- User explicitly names the jurisdiction ("how did Berkeley handle rent control?")
- User passes explicit `jurisdiction` parameter in v2 `SearchRequest`

**Implemented** via tier system: `get_jurisdiction_tier()` returns `"cross_county"` for Berkeley relative to San Rafael, with tier weight 0.5.

### Rule 4: Topic Classification

To distinguish policy vs operational queries (for Rule 2), use the existing topic taxonomy:

**Policy topics** (sibling-relevant):
- housing, zoning, land_use, transportation, climate, public_safety, education, water, budget

**Operational topics** (jurisdiction-specific):
- permits, personnel, maintenance, closures, events, contracts

This can be a simple lookup table, not ML classification. If the query topic matches a policy keyword, sibling results are eligible.

## API Surface (v2 Query Layer)

Cross-jurisdiction is implemented in the v2 query interface (`civicos-services/query/`), not on the CivicOS class.

```python
# v2 REST API — POST /api/v2/civic/search

# Default: local + parent chain only
{"query": "housing", "corpus": ["decisions"], "include_parents": true}

# Explicit sibling inclusion
{"query": "housing", "corpus": ["decisions"], "include_parents": true, "include_siblings": true}

# Explicit cross-county (pass jurisdiction directly)
{"query": "rent control", "corpus": ["decisions"], "jurisdiction": "city-berkeley"}
```

**Response** includes `jurisdiction_results` grouping:

```json
{
    "results": [/* flat, tier-boosted relevance */],
    "jurisdiction_results": {
        "city-san-rafael": [/* results */],
        "county-marin": [/* results */],
        "city-mill-valley": [/* results, if include_siblings */]
    }
}
```

Each `CivicResult` has a `jurisdiction` field identifying its source. See `packages/civicos-services/src/civicos_services/query/jurisdictions.py` for tier weights and resolution logic.

## Testbed Validation

### Questions to Answer with Real Data

1. **Are sibling results actually useful?** Query "housing" across 3 Marin cities. Do Mill Valley results add value to a San Rafael user, or is it noise?

2. **Is the policy/operational distinction clean?** Query "water" — does this return MMWD regional decisions (useful) mixed with "water main break on 4th St" (noise)?

3. **How does relevance score differ across jurisdictions?** When searching "housing" across SR + Mill Valley + Berkeley, are the vector similarity scores comparable, or do different corpus sizes skew ranking?

4. **What's the right default?** After testing, should sibling inclusion be opt-in or opt-out for policy topics?

5. **Do cross-county results ever surface without explicit request?** If someone searches "rent control" in San Rafael (which doesn't have rent control), should Berkeley results appear as precedent? This is a product decision informed by the testbed.

## Open Questions

1. **Regional body resolution** — TAM, MMWD, etc. are not jurisdictions in the current model. They're shared across cities but don't have a `jurisdiction_id`. Should they? Or are they discovered via topic search across siblings?

2. **Result deduplication** — if county-marin passes a housing ordinance that references state legislation, both might appear in results. Deduplicate by entity ID, or show both with different jurisdiction labels?

3. **Latency budget** — cross-county queries with 4+ jurisdictions. What's the acceptable latency ceiling?

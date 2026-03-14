# Cross-Jurisdiction Query Spec

**Status:** Phase A implemented (v2 query layer)
**Date:** 2026-03-11 (updated 2026-03-13)
**Launch.json items:** `cross_marin_query_prototype`, `cross_county_query_prototype`

## Problem

CivicOS queries operate on a single jurisdiction. When a San Rafael user asks "what happened with housing?", they get only San Rafael results. But housing policy is shaped by Marin County decisions, state legislation, and potentially by what neighboring cities have done.

We need to define what cross-jurisdiction queries return, when cross-jurisdiction results are relevant, and how the query API exposes this.

## Design Principles

1. **Explicit, not implicit** — cross-jurisdiction results are opt-in or clearly labeled. A user asking about San Rafael shouldn't get Berkeley results by surprise.
2. **Hierarchical relevance** — parent jurisdictions (county, state, federal) are almost always relevant. Sibling jurisdictions (other cities) are sometimes relevant. Cross-county jurisdictions are rarely relevant.
3. **Client-side display autonomy** — the API returns results with jurisdiction metadata. The client decides how to present (grouped, ranked, filtered).
4. **Incremental** — start with parent-chain queries (already implied by `parent_jurisdictions` in registry.json), then add sibling queries.

## Relevance Model

### Tier 1: Parent Chain (Always Relevant)
A query for `city-san-rafael` should include results from:
- `county-marin` — county ordinances, supervisor decisions
- `state-california` — state legislation
- `country-united-states` — federal legislation

This is the `parent_jurisdictions` array in `registry.json`.

### Tier 2: Sibling Cities (Sometimes Relevant)
Cities sharing a parent jurisdiction. For San Rafael: Mill Valley, San Anselmo, Larkspur, etc.

Relevant when:
- Same topic (housing, zoning) — neighboring cities face similar issues
- Shared regional bodies (TAM, MMWD) — decisions affect all member cities
- Precedent — "how did Mill Valley handle this?"

Not relevant when:
- Operational (street closures, park maintenance)
- City-specific (budget line items, personnel)

### Tier 3: Cross-County (Rarely Relevant)
Berkeley decisions about housing are relevant to San Rafael only at the policy/precedent level, not operationally. State legislation is the shared context — not county-level decisions.

Relevant when:
- Explicit comparison request ("how did Berkeley handle rent control?")
- State-level policy with local implementation variation

## Implementation (v2 Query Layer)

Cross-jurisdiction queries are implemented in the v2 query interface (`civicos-services/query/`), not on the CivicOS class. The v2 layer's planner/adapter/merger pattern naturally extends to multi-jurisdiction fan-out.

### API Surface

```python
# v2 REST API — POST /api/v2/civic/search
{
    "query": "housing",
    "corpus": ["decisions", "meetings"],
    "include_parents": true,       # expand parent chain from registry.json
    "include_siblings": false      # expand sibling cities (same county)
}
```

**Response** includes both flat ranked results and jurisdiction-grouped results:

```json
{
    "results": [/* flat, ranked by tier-boosted relevance */],
    "jurisdiction_results": {
        "city-san-rafael": [/* results */],
        "county-marin": [/* results */],
        "state-california": [/* results */]
    },
    "meta": {
        "corpus_counts": {"city-san-rafael:decisions": 5, "county-marin:decisions": 2},
        "corpus_status": {"city-san-rafael:decisions": "ok", "county-marin:decisions": "ok"}
    }
}
```

Each `CivicResult` includes a `jurisdiction` field identifying its source.

### Implementation Files

| File | Purpose |
|------|---------|
| `packages/civicos-services/src/civicos_services/query/jurisdictions.py` | Jurisdiction resolution (parents, siblings, tiers) |
| `packages/civicos-services/src/civicos_services/query/models.py` | `SearchRequest.include_parents/include_siblings`, `CivicResult.jurisdiction`, `SearchResponse.jurisdiction_results` |
| `packages/civicos-services/src/civicos_services/query/verbs.py` | `_execute_cross_jurisdiction_search()` — parallel fan-out per jurisdiction |

### How It Works

1. `SearchRequest` arrives with `include_parents=True` or `include_siblings=True`
2. `execute_search()` delegates to `_execute_cross_jurisdiction_search()`
3. `resolve_jurisdictions()` reads `config/registry.json` to expand the jurisdiction list
4. For each target jurisdiction, a CivicOS instance is created and the standard per-corpus search runs in parallel (asyncio)
5. Results are tagged with `jurisdiction` and relevance is multiplied by tier weight (self=1.0, parent=1.0, sibling=0.8, cross_county=0.5)
6. Response includes both flat ranked list and `jurisdiction_results` grouping

## Vector Search Implications

Cross-jurisdiction queries hit multiple vector namespaces. Options:

1. **Sequential fan-out** — query each jurisdiction's vectors separately, merge results. Simple but latency scales linearly with jurisdiction count.

2. **Shared vector index with jurisdiction metadata** — all embeddings in one pgvector table with `jurisdiction_id` column. Filter at query time. Fast but requires all cities in same DB.

3. **Parallel fan-out** — query jurisdictions concurrently with asyncio. Latency = max(individual queries). Better for federated deployment where jurisdictions are on different DBs.

**Current implementation:** Option 3 (parallel fan-out). Each jurisdiction gets its own CivicOS instance and adapter calls run concurrently. This works for both shared-DB (testbed) and federated (production) deployments.

## Ranking Across Jurisdictions

**Implemented:** Tier-boosted relevance. Each result's relevance score is multiplied by its tier weight:
- Self: 1.0
- Parent: 1.0
- Sibling: 0.8
- Cross-county: 0.5

Weights are defined in `packages/civicos-services/src/civicos_services/query/jurisdictions.py:TIER_WEIGHTS` and can be tuned based on testbed validation.

## Testbed Validation Plan

### Phase A (Marin): `cross_marin_query_prototype`
1. ~~Implement cross-jurisdiction search in v2 layer~~ ✅ Done
2. ~~Jurisdiction resolution (parents, siblings) from registry.json~~ ✅ Done
3. ~~Tier-based relevance boosting~~ ✅ Done
4. **TODO:** Test with real data — "housing" query across Marin cities
5. **TODO:** Validate sibling results are useful, not noise
6. **TODO:** Test shared regional body queries (TAM, MMWD)
7. **NOTE:** Mill Valley and San Anselmo have meetings but 0 decisions — may need extraction first

### Phase B (Berkeley): `cross_county_query_prototype`
1. Ingest Berkeley + county-alameda data
2. Test: "housing" query for San Rafael with Berkeley included → is this useful?
3. Test: state legislation appears for both SR and Berkeley (shared parent)
4. Test: county-alameda results do NOT appear for San Rafael queries (different parent)
5. Validate: tier-boosted ranking weights with real cross-county data
6. Answer: when should cross-county results appear? Only on explicit request?

## Open Questions

1. **Performance budget** — what's acceptable latency for cross-jurisdiction queries? Current single-jurisdiction is ~200ms. Cross-county with 4 cities might be 400-800ms.
2. **Result limits** — max results per jurisdiction? Total across all jurisdictions?
3. **Caching** — parent-chain results (state legislation) change slowly. Cache county/state results?
4. **Legacy method removal** — the CivicOS class still has `what_happened()`, `what_applies()`, etc. These are used by v2 adapters internally but should not be extended with cross-jurisdiction features. Eventually the adapters should call storage/vector backends directly, removing the CivicOS dependency.

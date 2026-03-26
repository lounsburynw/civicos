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
4. ~~Test with real data — "housing" query across Marin cities~~ ✅ Done (2026-03-17)
5. ~~Validate sibling results are useful, not noise~~ ✅ Done — see QC below
6. **TODO:** Test shared regional body queries (TAM, MMWD) — blocked on regional body data
7. ~~Mill Valley and San Anselmo have 0 decisions~~ ✅ Resolved — MV has 60, SA has 96

### Phase A QC Report (2026-03-17)

Tested cross-jurisdiction queries against PostgreSQL with real Marin data (SR 83, MV 60, SA 96 decisions).

**Functional: Working (warm backend)**
- Fan-out to 3 cities, tier boosting, result merging all work as designed
- Field completeness: all results have title, date, summary, jurisdiction, ref, details
- Parent jurisdictions correctly return 0 results (no county/state data ingested)
- Multi-corpus (decisions + meetings) works across jurisdictions

**Issue: Cold Start Timeout (P0 — FIXED 2026-03-17)**
- `_ensure_schema()` ran 137 DDL statements on first call, taking 12-21 seconds
- Fix: added fast schema probe (single `information_schema` query) + thread-safe lock
- Cold start now **805ms** (down from 12-21s), well under 20s timeout
- Thread safety prevents race condition in cross-jurisdiction parallel fan-out

**Issue: Relevance Scores Are Rank-Based, Not Semantic (P1 — FIXED 2026-03-17)**
- Was: `1.0, 0.95, 0.90, ...` (constant 0.05 decrement per rank position)
- Fix: `Decision.score` now carries cosine similarity from pgvector. DecisionsAdapter uses real scores.
- Example: "housing" returns scores 0.53-0.65 (semantically meaningful), not 1.0/0.95/0.90

**Issue: No Relevance Threshold (P1 — FIXED 2026-03-17)**
- Was: "xyzzy12345" returned 30 results (10 per jurisdiction) — all noise
- Fix: `DecisionsAdapter.MIN_RELEVANCE = 0.45` filters low-similarity results
- Nonsense queries now return ~3 results instead of 10 per jurisdiction (borderline scores just above threshold)
- Note: `min_score` parameter also plumbed through `_search_with_vector_backend` → `pgvector_backend.search()` for DB-level filtering

**Issue: Ref Format Inconsistency (P2 — PARTIALLY FIXED 2026-03-17)**
- FIXED: `_make_ref()` now detects when `item_id` already has the ref prefix and avoids doubling
- SR refs are now correct: `decision:city-san-rafael:proudcity-city-san-rafael-city-council-february-17-2026-tuesday:05` (no more doubled prefix)
- REMAINING: MV has description text leaked into decision IDs from extraction (`1- bayfront terrace/1 hamilton drive...`). This is a data quality issue that needs re-extraction to fix properly.

**Issue: Intermittent DNS Failure (P2 — FIXED 2026-03-17)**
- PostgresBackend already had retry logic catching `OperationalError` (covers DNS failures)
- Fix: Added matching retry logic to PgVectorBackend's `_get_connection()` (was missing)

**Sibling Result Quality: Acceptable for Prototype**
- 3/4 unique top results across topics (vector search differentiates by topic)
- Housing: relevant siblings (Bayfront Terrace, Housing Initiatives, Rezone Housing Site)
- Parking/police: less relevant siblings (generic zoning/planning items)
- Some overlap: "100 Evelyn Ave" appears as MV top result for both housing and parking

**Performance (warm backend)**
| Metric | Value |
|--------|-------|
| Single jurisdiction decisions | ~5-7s |
| Cross-jurisdiction (3 cities) decisions | ~7-8s |
| Multi-corpus cross-jurisdiction | ~5s |
| Cold start penalty | +12-21s |
| Vector search alone | 1.2-2.3s |
| SQL enrichment (`get_decisions`) | 0.7-0.9s (warm) |
| `_ensure_schema` (cold) | 12-21s |

**Answered Open Questions**
1. Performance: 7-8s warm is acceptable for prototype, but cold start needs fix
2. Result quality: sibling decisions add value for policy topics, less so for operational queries

### Phase B (Berkeley): `cross_county_query_prototype`
1. Ingest Berkeley + county-alameda data
2. Test: "housing" query for San Rafael with Berkeley included → is this useful?
3. Test: state legislation appears for both SR and Berkeley (shared parent)
4. Test: county-alameda results do NOT appear for San Rafael queries (different parent)
5. Validate: tier-boosted ranking weights with real cross-county data
6. Answer: when should cross-county results appear? Only on explicit request?

## Open Questions

1. ~~**Performance budget**~~ — Answered: 7-8s warm is acceptable for prototype. Cold start (12-21s) needs fix before production.
2. **Result limits** — max results per jurisdiction? Total across all jurisdictions? (Currently: 10 per jurisdiction, merged to request limit)
3. **Caching** — parent-chain results (state legislation) change slowly. Cache county/state results?
4. **Legacy method removal** — the CivicOS class still has `what_happened()`, `what_applies()`, etc. These are used by v2 adapters internally but should not be extended with cross-jurisdiction features. Eventually the adapters should call storage/vector backends directly, removing the CivicOS dependency.
5. **Relevance threshold** — should the API enforce a minimum vector distance to avoid returning noise for unrelated queries? Currently returns k nearest regardless of distance.
6. **Ref normalization** — decision refs are inconsistent across jurisdictions (doubled prefixes, description text in IDs). Needs cleanup before refs become stable client-side identifiers.

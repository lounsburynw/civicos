# Cross-Jurisdiction Query Spec

**Status:** Not started
**Date:** 2026-03-11
**Launch.json items:** `cross_marin_query_prototype`, `cross_county_query_prototype`

## Problem

CivicOS queries (`what_happened()`, `what_applies()`, `whats_next()`) operate on a single jurisdiction. When a San Rafael user asks "what happened with housing?", they get only San Rafael results. But housing policy is shaped by Marin County decisions, state legislation, and potentially by what neighboring cities have done.

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
- `state-california` — state legislation (already handled by `what_applies()`)
- `country-united-states` — federal legislation

This is the `parent_jurisdictions` array in `registry.json`. It already exists — the query layer just doesn't use it.

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

## API Design

### Option A: Expand Existing Methods

```python
# Add scope parameter to existing methods
c.what_happened("housing", scope="local")        # Current behavior (default)
c.what_happened("housing", scope="county")       # + parent chain up to county
c.what_happened("housing", scope="state")        # + parent chain up to state
c.what_happened("housing", scope="region")       # + sibling cities
```

- Pro: Backward compatible, simple
- Con: "region" is ambiguous. What about cross-county?

### Option B: Explicit Jurisdiction List

```python
c.what_happened("housing", jurisdictions=["city-san-rafael", "city-mill-valley"])
c.what_happened("housing", include_parents=True)  # auto-expand parent chain
```

- Pro: Precise control
- Con: Caller needs to know jurisdiction IDs

### Option C: Return Grouped Results

```python
results = c.what_happened("housing", scope="county")
# Returns:
{
    "city-san-rafael": [Decision, Decision, ...],
    "county-marin": [Decision, ...],
    "state-california": [Decision, ...]
}
```

- Pro: Client can display hierarchically
- Con: Different return type from current (breaking change or new method)

**Recommendation:** Option B with Option C return format, exposed as a new method:

```python
# Existing method unchanged
c.what_happened("housing")  # -> List[dict], single jurisdiction

# New method for cross-jurisdiction
c.what_happened_across("housing",
    jurisdictions=["city-san-rafael"],
    include_parents=True,
    include_siblings=False
)  # -> Dict[str, List[dict]], grouped by jurisdiction
```

This avoids breaking the existing API while providing cross-jurisdiction capabilities.

## Vector Search Implications

Cross-jurisdiction queries hit multiple vector namespaces. Options:

1. **Sequential fan-out** — query each jurisdiction's vectors separately, merge results. Simple but latency scales linearly with jurisdiction count.

2. **Shared vector index with jurisdiction metadata** — all embeddings in one pgvector table with `jurisdiction_id` column. Filter at query time. Fast but requires all cities in same DB.

3. **Parallel fan-out** — query jurisdictions concurrently with asyncio. Latency = max(individual queries). Better for federated deployment where jurisdictions are on different DBs.

**For testbed (same Supabase instance):** Option 2 is natural — all cities share the DB. Add `jurisdiction_id` filter to vector queries.

**For production federation (different DBs):** Option 3. The testbed should validate that result merging and ranking work correctly, so the transition from Option 2 → 3 is a deployment concern, not a design change.

## Ranking Across Jurisdictions

When merging results from multiple jurisdictions, how do we rank?

- **By relevance score** — vector similarity, regardless of jurisdiction. Simple, but parent-chain results may be less textually similar while being more legally relevant.
- **By tier then relevance** — Tier 1 (parent) results first, then Tier 2 (sibling), then Tier 3 (cross-county). Within each tier, by relevance score.
- **Boosted by tier** — multiply relevance score by tier weight (e.g., parent = 1.0, sibling = 0.8, cross-county = 0.5).

**Recommendation:** Tier-boosted relevance. Let the testbed validate the weights with real data before hardcoding.

## Testbed Validation Plan

### Phase A (Marin): `cross_marin_query_prototype`
1. Ingest Mill Valley + San Anselmo data
2. Implement `what_happened_across()` with `include_parents=True`
3. Test: "housing" query for San Rafael → results from SR + county-marin + state-california
4. Test: "housing" with `include_siblings=True` → adds Mill Valley, San Anselmo results
5. Validate: are sibling results actually useful, or noise?
6. Test: shared regional body queries (TAM, MMWD)

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

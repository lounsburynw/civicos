# Cross-County Relevance Filtering Spec

**Status:** Validated against real Postgres (2026-04-07)
**Date:** 2026-03-11 (updated 2026-04-07)
**Launch.json item:** `cross_county_query_prototype`
**Depends on:** `cross_marin_query_prototype` (Phase A findings inform this) — **DONE**

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

# Explicit cross-county via direct target (single-jurisdiction query)
{"query": "rent control", "corpus": ["decisions"], "jurisdiction": "city-berkeley"}

# Explicit cross-county via also_include (base + named targets, tier-boosted)
{"query": "housing", "corpus": ["decisions"], "also_include": ["city-berkeley"]}

# Comparative cross-county (every named jid guaranteed visible in flat view)
{
  "query": "housing",
  "corpus": ["decisions"],
  "also_include": ["city-berkeley", "city-san-francisco"],
  "per_jurisdiction_limit": 5
}
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

## Phase B Validation (2026-04-07)

Validated end-to-end against PostgreSQL using the live verification script
`scripts/verify_cross_county_phase_b.py`. Test data:

| Jurisdiction | County | Decisions | Vector embeddings |
|---|---|---|---|
| city-san-rafael | Marin | 111 | 111 |
| city-berkeley | Alameda | 273 | 273 |
| city-san-francisco | (consolidated) | 188 | 188 |
| county-alameda | — | **0** | **0** (data gap) |

**Verified semantics** — query "housing" from `city-san-rafael` (decisions corpus):

| Mode | Result | Berkeley present? | SF present? |
|---|---|---|---|
| `include_siblings=True` | 19 Marin jurisdictions fanned out | ❌ No | ❌ No |
| `include_parents=True` | county-marin, state-california, country-united-states | ❌ No | ❌ No |
| `also_include=[berkeley, sf]` (default cap) | 15 results, SR dominates | ✅ 5 | ❌ 0 (crowded out) |
| `also_include=[berkeley, sf], per_jurisdiction_limit=5` | 15 results, balanced | ✅ 5 | ✅ 5 |

**Tier weights confirmed**: Berkeley and SF results both capped at `0.5x` raw
cosine similarity (raw cosine 0.56-0.66 → boosted 0.28-0.33).

### Answers to Open Questions

1. **When should cross-county results appear?**
   *Answer*: **Only on explicit `also_include`. Never via implicit fan-out.**
   `include_siblings` and `include_parents` are bounded to the parent-county
   chain. Cross-county results require the caller to name the target jid.
   Validated by the `siblings_only_excludes_other_counties` and
   `parents_only_excludes_other_counties` integration tests.

2. **Visibility of named cross-county jurisdictions**
   *Problem found*: With the default global top-K cap, a cross-county jid's
   results can be silently dropped from the flat ranked stream when another
   jid's marginally higher cosine similarity wins ranking. Tested with SR +
   Berkeley + SF — Berkeley filled positions 11-15 and SF was cut entirely
   from the flat view at `limit=15`, even though SF had 188 housing-relevant
   decisions in its bucket.
   *Resolution*: Added `SearchRequest.per_jurisdiction_limit` (Phase B). When
   set, each fanned-out jid contributes up to N results to the flat view AND
   each `jurisdiction_results` bucket is capped at N. Total flat results size
   is bounded by `per_jurisdiction_limit × num_jurisdictions`. Default `None`
   preserves the global top-K behavior. Comparative cross-county queries
   should set this knob; federation discovery queries (siblings within county)
   typically should not.

3. **Result deduplication** *(still open — deferred)*
   If county-marin passes a housing ordinance that references state
   legislation, both might appear in results. Phase B does NOT deduplicate
   by entity ID — each jid's results are independent and labeled by source.
   This is acceptable for now because (a) cross-jurisdiction overlap of
   actual entity IDs is rare (each jid has its own ID-space) and (b) the
   `jurisdiction` field on `CivicResult` lets clients group/dedup as needed.
   Revisit if/when we get real entity overlap (e.g., shared regional body
   decisions).

4. **Latency budget** *(observed, within target)*
   Real-data measurements (single corpus, decisions only):
   - 1 jid (base only): ~80-300 ms
   - 3 jids (`also_include` 2 cross-county): ~900-2500 ms total
   - 19 jids (Marin sibling fan-out): ~4700 ms total
   The fan-out is parallel, so cost scales with the slowest jid, not linearly.
   Target ceiling: <8s for 5 jids, <15s for 20 jids. Currently meeting both.

5. **Regional body resolution** *(still open — out of scope for Phase B)*
   TAM, MMWD, and other regional bodies are not yet modeled as jurisdictions.
   The Phase B prototype only validates city-to-city cross-county queries.
   Regional body modeling is tracked separately under multi_scale_participation
   in `launch.json`.

## Known Data Gaps (filed for follow-up)

These were discovered during Phase B validation but are out of scope for the
query layer itself:

1. **`county-alameda` extraction never populated data** — onboarded
   2026-03-13 (commit `d6f3adc`), but Postgres has 0 meetings, 0 decisions,
   0 transcripts. The original config had 6 Granicus archive views which
   were simplified to a single `board: "1"` view in commit `ee9d584` without
   re-running extraction. Berkeley's parent-chain queries (`include_parents`
   from `city-berkeley`) currently get nothing at the county level. Refile
   `onboard_county_alameda` as `not_started`.

2. **Berkeley + SF have duplicate decisions in storage** — On the "housing"
   query, Berkeley returns 4 identical "Authorizing funding for affordable
   housing projects" entries (same title, same `0.3304` relevance) and SF
   returns 5 identical "Affordable Housing and Sustainable Communities
   Program" entries. Likely an upsert idempotency issue in the Granicus or
   Legistar extraction path. Should be a `data.critic` violation; file
   under `data_integrity`.

3. **`city-san-francisco` registry entry lacks `county-san-francisco` parent**
   — SF is a consolidated city-county, so its parent_jurisdictions is just
   `[state-california, country-united-states]`. Cross-county tier resolution
   still works coincidentally because the tier check returns `cross_county`
   when neither base nor target shares any county. But it's structurally
   wrong and should list `county-san-francisco` for federation symmetry
   (regional bodies, parent-chain queries, etc.).

## Open Questions (remaining)

1. **Topic classification for sibling relevance** (Rule 4 above) — still
   not implemented. Phase A and B both treat sibling inclusion as a binary
   opt-in via `include_siblings`. The policy/operational distinction would
   need a topic classifier or keyword table that we don't have yet. Defer.

2. **Cross-county precedent surfacing** — should there be a higher-level
   "find precedent" query that scans all populated jurisdictions for similar
   decisions? Not the same as `also_include`, which requires the caller to
   name targets. This is a product feature, not a query primitive.

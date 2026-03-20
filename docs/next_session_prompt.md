# Recommended: Vertical Query Tier Tuning

**Priority:** P0 (vertical_query_tier_tuning)
**Area:** multi_scale_participation
**Date:** 2026-03-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session completed `vector_llm_relevance_pipeline` — federal rules now have LLM-scored local relevance (149 rules with impact summaries in `local_relevance_summary` column). The multi-scale participation stack is nearly complete: city, county, state, and federal data all flow through the v2 query layer with `include_parents`/`include_siblings` cross-jurisdiction support. The remaining gap is **tier weighting**: parent jurisdictions (state, federal) currently have weight 1.0, meaning a generic CA bill competes equally with a San Rafael city council decision in search results.

## What Needs to Be Done

Tune the `TIER_WEIGHTS` system so upward queries (city→county→state→federal) return results weighted by relevance proximity. Current weights in `jurisdictions.py:24-30`:

```python
TIER_WEIGHTS = {
    "self": 1.0,     # Local results — should stay highest
    "child": 1.0,    # Downward — fine as-is
    "parent": 1.0,   # ← PROBLEM: state/federal compete equally with local
    "sibling": 0.8,  # Neighboring cities
    "cross_county": 0.5,
}
```

Options to consider:
1. **Simple weight reduction**: `parent: 0.7` or level-aware (`county: 0.9, state: 0.7, federal: 0.5`)
2. **Separate result grouping**: Return results in tiers (local first, then state, then federal)
3. **Level-aware weighting**: Differentiate county parent vs state parent vs federal parent
4. **Hybrid**: Weight within tier + group between tiers

The current `get_tier_weight()` only knows "parent" — it doesn't distinguish county from state from federal. May need `get_jurisdiction_level()` to determine depth.

## Key Files

- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:24` — `TIER_WEIGHTS` dict (the main target)
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:122` — `get_jurisdiction_tier()` returns "self"/"parent"/"sibling" etc.
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:164` — `get_tier_weight()` applies weights
- `packages/civicos-services/src/civicos_services/query/verbs.py:383-409` — Where tier boosting is applied to cross-jurisdiction results
- `packages/civicos-services/src/civicos_services/query/verbs.py:54-62` — Cross-jurisdiction search dispatch
- `packages/civicos-services/src/civicos_services/query/models.py:123` — `include_parents` field on SearchRequest
- `data/jurisdictions.yml` — Jurisdiction registry with `parent_jurisdictions` hierarchy

## What's Already Working

- `include_parents=True` on a city query fans out to county → state → federal
- Results from all levels are collected and merged
- `tier_weight` is multiplied against `relevance` score before sorting
- Federal rules now have `local_relevance_score` (0-0.8) and `local_relevance_summary` (LLM text) — these quality signals could inform weighting
- The `vector_relevance.py` pipeline (just completed) scores how relevant federal content is to San Rafael

## Suggested Approach

1. **Analyze current behavior** — Run a cross-jurisdiction search with `include_parents=True` and observe how local vs state vs federal results interleave
2. **Add level-aware tier detection** — Extend `get_jurisdiction_tier()` to return "parent_county"/"parent_state"/"parent_federal" instead of just "parent". The `parent_jurisdictions` list in `jurisdictions.yml` has the hierarchy (city→county→state→federal)
3. **Implement level-aware weights** — E.g., `parent_county: 0.9, parent_state: 0.7, parent_federal: 0.5`. Potentially boost federal results that have high `local_relevance_score`
4. **Consider result grouping** — The v2 response already has a `metadata` dict where tier/level info could be exposed for UI grouping
5. **Test with real queries** — "housing" and "water" are good test queries (strong federal relevance from LLM pipeline)

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
pytest packages/civicos-services/tests/ -q --override-ini="addopts=" -k "jurisdiction or tier or cross"
```

## Success Criteria

- [ ] Parent tier weight differentiates county vs state vs federal
- [ ] Local results rank above equivalent-quality state/federal results
- [ ] Federal rules with high `local_relevance_score` still surface prominently
- [ ] Cross-jurisdiction search returns intuitive ordering for "housing" query
- [ ] No regression in single-jurisdiction queries

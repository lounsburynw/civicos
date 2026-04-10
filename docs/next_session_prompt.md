# Recommended: Fix SF county parent (`fix_sf_county_parent`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-10

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

This session wrote the mass ingest cost ceiling document (`docs/internal/cost-ceiling.md`). The next logical work is fixing SF's missing county parent — it affects cross-jurisdiction query correctness for all SF queries.

## Problem

`city-san-francisco` has `parent_jurisdictions: [state-california, country-united-states]` — it's missing a county parent. SF is a consolidated city-county, but the registry should list `county-san-francisco` for federation symmetry. Without it:

1. **`resolve_relationship_tier()`** returns `"cross_county"` for SR→SF queries (line 177 of `jurisdictions.py`) because neither shares a county — this is technically wrong, they're both in the same state
2. **Sibling detection** fails: `base_counties & target_counties` is empty (line 174) so SR and SF are never considered siblings even though they're both Bay Area cities
3. **Tier weighting** uses `cross_county: 0.5` instead of what should be a closer relationship

## Key Files

- `data/jurisdictions/city-san-francisco.yaml:22-24` — `parent_jurisdictions` missing county
- `config/registry.json:300-306` — same data in registry format
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py:143-177` — `resolve_relationship_tier()` logic
- `data/jurisdictions/county-san-francisco.yaml` — **DOES NOT EXIST** (needs to be created)

## Suggested Approach

1. **Create `data/jurisdictions/county-san-francisco.yaml`** — SF is unique as a consolidated city-county. The county config needs to exist even if it has no separate meetings (the city IS the county).

2. **Update `city-san-francisco.yaml`** — add `county-san-francisco` to `parent_jurisdictions`:
   ```yaml
   parent_jurisdictions:
     - county-san-francisco
     - state-california
     - country-united-states
   ```

3. **Update `config/registry.json`** — same change in the registry entry for `city-san-francisco`

4. **Verify `resolve_relationship_tier()`** handles it correctly — after fix, SR→SF should return `"cross_county"` (they ARE in different counties: Marin vs SF) but for the right structural reason (both have county parents, those counties differ).

5. **Test**: Run query tests to ensure cross-jurisdiction queries still work:
   ```bash
   pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts=" -k "jurisdiction"
   pytest packages/civicos-services/tests/test_integration_query_v2.py -q --override-ini="addopts=" -k "cross" 2>/dev/null
   ```

## Design Decision

SF as consolidated city-county means `county-san-francisco` is a "virtual" jurisdiction — it has no separate meetings or data because the city government IS the county government. But the registry needs it for structural correctness. Pattern: create a minimal YAML config with `type: county`, no extraction config, pointing to `city-san-francisco` as the data source.

Check how `county-marin` is structured for reference — it has its own meetings. `county-san-francisco` won't have separate meetings but needs to exist in the hierarchy.

## Success Criteria

- [ ] `county-san-francisco.yaml` created with proper structure
- [ ] `city-san-francisco.yaml` and `config/registry.json` updated with county parent
- [ ] `resolve_relationship_tier()` returns correct tiers for SF queries
- [ ] Query tests pass
- [ ] New P0 promoted

## Open PRs

None.

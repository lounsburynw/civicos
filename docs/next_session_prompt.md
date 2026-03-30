# Recommended: All-California Election Coverage

**Priority:** P0 (all_california_coverage)
**Area:** multi_state_portability
**Date:** 2026-03-29

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed Phase 3 of the multi-state portability roadmap: `StateElectionProvider` ABC + `CaliforniaElectionProvider`. Election source detection now dispatches through a provider registry — `onboard.py:detect_election_sources()` calls `get_provider(state)` which returns the CA provider (or None for unsupported states). All 150+ tests pass.

The current CA provider only knows about 3 counties with Civera instances (Marin, Sonoma, Yolo). The remaining 55 CA counties get CA SOS statewide data but no local race results. This item expands coverage.

## What Needs to Be Done

1. **Expand Civera instance discovery** — Probe more CA county registrar sites for GraphQL endpoints matching the Civera ElectionStats pattern (`/api/graphql_pr`). Add discovered instances to `CIVERA_INSTANCES` registry.
2. **CA SOS as universal fallback** — The `CASOSResultsClient` already has `get_county_breakdown()` for county-level race results. Wire this into the CA provider as a fallback for counties without Civera.
3. **Discovery script** — Write a script to systematically probe CA county registrar websites for Civera endpoints.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/providers/california.py` — CA provider (just created). Civera + SOS fallback logic lives here.
- `packages/civicos-extraction/src/civicos_extraction/clients/civera_election_stats.py:32-49` — `CIVERA_INSTANCES` registry (currently 3 counties: marin, sonoma, yolo)
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py` — `CASOSResultsClient` with `get_county_breakdown()` (line 286). Already functional, just not wired into the provider.
- `packages/civicos-extraction/src/civicos_extraction/providers/__init__.py` — Provider ABC + registry
- `packages/civicos-extraction/tests/test_election_providers.py` — 17 provider tests
- `packages/civicos-extraction/tests/test_election_detection.py` — 61 detection tests

## Suggested Approach

1. **Research Civera adoption** — Civera ElectionStats uses a consistent URL pattern: `https://electionstats.{county-domain}/api/graphql_pr`. The 3 known instances each have different domain patterns. Write a script to probe the top 20 CA counties by population.

2. **Add discovered instances** — For each county with a working Civera endpoint, add to `CIVERA_INSTANCES` dict with `graphql_url`, `tenant`, and `county_name`.

3. **Wire CA SOS fallback** — In `CaliforniaElectionProvider.detect_election_sources()`, after the Civera check, add a fallback: if no Civera instance for this county, add a `ca_sos_county_results` source entry that tells the ingestion pipeline to use `CASOSResultsClient.get_county_breakdown()` for local races.

4. **Update tests** — Add tests for new Civera instances and the SOS fallback path.

## Tests to Run

```bash
# Provider tests (direct)
pytest packages/civicos-extraction/tests/test_election_providers.py -v --override-ini="addopts="
# Detection tests (regression)
pytest packages/civicos-extraction/tests/test_election_detection.py -v --override-ini="addopts="
# Election calendar (regression)
pytest packages/civicos/tests/test_election_calendar.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] CIVERA_INSTANCES expanded beyond 3 counties (or documented why others don't have Civera)
- [ ] CA SOS county breakdown wired as fallback for non-Civera counties
- [ ] Discovery script exists for probing county registrar sites
- [ ] All existing tests pass (zero regression)
- [ ] New tests cover expanded Civera instances and SOS fallback path

## Architecture Notes

- Providers live in `civicos-extraction/providers/` (not `civicos/_internal/elections/`) to avoid layer violations
- The `_create_provider()` factory in `providers/__init__.py` uses lazy imports
- County normalization (lowercase, strip "County" suffix) happens in `onboard.py` dispatcher before reaching the provider
- Marin uses legacy `marin_registrar_results` config key for backwards compatibility

## Multi-State Roadmap Progress

| Phase | Item | Status |
|-------|------|--------|
| 1 | state_election_config | Done |
| 2 | deadline_generalization | Done |
| 3 | state_election_provider | Done |
| **4** | **all_california_coverage** | **P0 (next)** |
| 5 | texas_election_support | P2 |
| 6 | florida_election_support | P2 |

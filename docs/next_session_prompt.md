# Recommended: Texas Election Support

**Priority:** P0 (texas_election_support)
**Area:** multi_state_portability
**Date:** 2026-03-29

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 4 (`all_california_coverage`) is done. Probed all 58 CA counties — discovered San Joaquin as 4th Civera instance. Externalized CIVERA_INSTANCES to `data/extraction/civera_instances.json` (config-driven). Added explicit `county_breakdown` flag on CA SOS source for all counties (True for 54 non-Civera, False for 4 Civera counties).

Texas is Phase 5 — the first non-CA state, validating the multi-state provider abstraction. `StateElectionConfig` for TX already exists at `state_config.py:128` (March primary, 30-day registration, 17-day early voting, no VBM). What's missing is the provider and any TX-specific election data clients.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/providers/__init__.py:80-88` — `_create_provider()` factory. Add TX branch here.
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py` — Reference implementation. TX provider follows same pattern.
- `packages/civicos/src/civicos/_internal/elections/state_config.py:128-154` — TX `StateElectionConfig` (already exists).
- `packages/civicos-extraction/tests/test_election_providers.py:54` — Test asserting `get_provider("TX")` returns None. Must change.
- `packages/civicos-extraction/tests/test_election_detection.py:120` — Test for unsupported TX returning empty. Must update.
- `data/extraction/civera_instances.json` — Config-driven Civera registry pattern to follow if TX has similar sources.

## Suggested Approach

1. **Research TX SOS data availability** — Texas SOS (sos.state.tx.us) has election results. Check if they have a usable API or scrape-only. Also check county registrar APIs (Harris, Travis, Dallas, Bexar are the big ones).

2. **Create `providers/texas.py`** — Implement `TexasElectionProvider(StateElectionProvider)` with `detect_election_sources()`. Initially can return TX SOS source if API exists, or a minimal source dict with documentation of what's available.

3. **Register in factory** — Add `"TX"` branch in `_create_provider()` at `providers/__init__.py:86`.

4. **Create TX SOS client** (if API exists) — `clients/tx_sos_results.py` following the `ca_sos_results.py` pattern.

5. **Add tests** — Provider tests for TX detection, update detection tests that currently assert TX returns empty.

6. **End-to-end test** — Test with a TX jurisdiction (e.g., `city-austin` in Travis County).

## Tests to Run

```bash
pytest packages/civicos-extraction/tests/test_election_providers.py -v --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_detection.py -v --override-ini="addopts="
pytest packages/civicos/tests/test_election_calendar.py -v --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `TexasElectionProvider` created and registered in factory
- [ ] `get_provider("TX")` returns a provider (not None)
- [ ] TX SOS data source research complete (API or scrape-only documented)
- [ ] At least TX SOS source detected for TX jurisdictions
- [ ] Provider + detection tests updated for TX
- [ ] All existing tests pass (zero regression)
- [ ] End-to-end test with a TX jurisdiction (e.g., city-austin)

## Architecture Notes

- Providers live in `civicos-extraction/providers/` (not `civicos/_internal/elections/`)
- The `_create_provider()` factory uses lazy imports — add the TX import inside the `if` branch
- County normalization (lowercase, strip "County" suffix) happens in `onboard.py` dispatcher before reaching the provider
- Config-driven pattern: if TX has county registrar sources, create `data/extraction/tx_election_instances.json` (following the CA Civera pattern)

## Multi-State Roadmap Progress

| Phase | Item | Status |
|-------|------|--------|
| 1 | state_election_config | Done |
| 2 | deadline_generalization | Done |
| 3 | state_election_provider | Done |
| 4 | all_california_coverage | Done |
| **5** | **texas_election_support** | **P0 (next)** |
| 6 | florida_election_support | P2 |

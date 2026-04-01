# Recommended: Multi-State Portability — Florida Election Support

**Priority:** P0 (florida_election_support)
**Area:** multi_state_portability
**Date:** 2026-04-01

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election pipeline is fully working for California (CA SOS, Civera, LegiScan, Congress.gov) and Texas has a skeleton provider. The multi_state_portability category is 5/9 done — the remaining 4 items are FL, NY, PA, IL election support. Florida is P0 because it uses Clarity Elections (Scytl) widely, and building that client covers many FL counties. The user explicitly asked to address multi_state_portability next.

This session also completed: cron failure triage (3 failures fixed), config-driven jurisdiction registry (auto-loads from files, 50 jurisdictions registered), LegiScan Modal secret cleaned, docs updated.

## What to Build

**FloridaElectionProvider** following the exact pattern of CA and TX:

1. **StateElectionConfig** entry for FL in `state_config.py` (deadlines, election calendar, SOS URL)
2. **FloridaElectionProvider** class in `providers/florida.py` implementing `StateElectionProvider` ABC
3. **Clarity Elections client** (or FL SOS client) for fetching election results

## Key Files (follow these patterns)

- `packages/civicos/src/civicos/_internal/elections/state_config.py:47` — `StateElectionConfig` dataclass (311 lines). Add FL config here.
- `packages/civicos-extraction/src/civicos_extraction/providers/__init__.py:26` — `StateElectionProvider` ABC (91 lines). Defines `detect_election_sources()` and `detect_districts()`.
- `packages/civicos-extraction/src/civicos_extraction/providers/texas.py` — TX provider (56 lines). **Copy this as the template for FL.**
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py` — CA provider (75 lines). More complex (Civera + CA SOS). Reference for multi-source pattern.
- `docs/internal/clarity-elections-research.md` — Research on Clarity Elections (Scytl) coverage for non-Civera CA counties. Relevant to FL since Clarity is FL's primary platform.
- `packages/civicos-extraction/tests/test_election_providers.py` — Tests for CA and TX providers. Add FL tests here.

## Suggested Approach

1. Read `docs/internal/clarity-elections-research.md` for Clarity Elections API research
2. Read the TX provider (`providers/texas.py`) as the simplest template
3. Research FL SOS election data sources (dos.myflorida.com)
4. Add `StateElectionConfig` for FL in `state_config.py` (registration deadlines, primary/general dates, SOS URL)
5. Implement `FloridaElectionProvider` in `providers/florida.py`
6. If Clarity Elections client is feasible, build it in `clients/` — this would also benefit CA counties without Civera
7. Register FL provider in `providers/__init__.py`
8. Add tests in `test_election_providers.py`
9. If time permits, continue with NY, PA, IL (same pattern, ~56 lines each)

## Tests to Run

```bash
# Provider tests
pytest packages/civicos-extraction/tests/test_election_providers.py -q --override-ini="addopts="

# Election tests
pytest packages/civicos-extraction/tests/test_election_cron_enrollment.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_coverage_monitoring.py -q --override-ini="addopts="

# State config tests
pytest packages/civicos/tests/test_election_calendar.py -q --override-ini="addopts="

# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `StateElectionConfig` for FL with correct deadlines and election calendar
- [ ] `FloridaElectionProvider` implementing `detect_election_sources()` and `detect_districts()`
- [ ] Tests for FL provider passing
- [ ] If Clarity Elections client built: reusable for CA counties too
- [ ] Bonus: NY, PA, IL providers (same pattern, lower priority)

## Notes

- The jurisdiction registry now auto-loads from config files — adding a FL city just requires creating `data/extraction/city-miami.json` (no Python code edits)
- LegiScan API key is clean (Modal secret updated this session) — FL state legislators will work via LegiScan
- Census geocoder for district detection already works for any US state
- FL uses different election infrastructure than CA — no Civera, Clarity Elections instead

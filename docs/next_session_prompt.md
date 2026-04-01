# Recommended: Election Cron Enrollment Validation

**Priority:** P0 (election_cron_enrollment_validation)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-31

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We just completed `calendar_aware_election_refresh` — the election cron now fires daily via GH Actions and uses `determine_refresh_cadence()` to gate per-jurisdiction (daily/weekly/monthly based on election proximity). We also consolidated `marin_registrar_results` into `civera_election_stats` across 15 configs.

The cron dispatches to all jurisdictions returned by `get_active_jurisdictions()`. This next item validates that ALL jurisdiction types (school-*, college-*, county-*) are properly included and that new jurisdictions auto-enroll without manual steps.

## What This Session Completed

- Calendar-aware cadence gating in `scheduled_election_refresh()` (daily ≤7d, weekly 8-90d, monthly >90d)
- Per-source gating: Civera monthly-only, CA SOS Results daily near election
- Consolidated 15 Marin configs from `marin_registrar_results` → `civera_election_stats`
- Updated provider, dispatcher, scheduler, and all tests (176 passing)
- GH Actions cron switched from monthly to daily
- 28 cadence tests, 20 smoke tests passing

## Recommended Task

Verify `get_active_jurisdictions()` includes all jurisdiction types in the election cron dispatch. Add a test confirming new jurisdictions with `election_sources` are auto-included.

Currently `get_active_jurisdictions()` at `packages/civicos-extraction/src/civicos_extraction/config.py:108` scans `data/extraction/*.json` and skips files with `-schools` or `-districts` in the name. It includes `school-*`, `college-*`, `county-*`, `state-*` correctly (27 jurisdictions total). But there's no test asserting this invariant.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/config.py:108` — `get_active_jurisdictions()` scans config dir
- `packages/civicos-extraction/src/civicos_extraction/config.py:128` — skip filter for `-schools`/`-districts` supplementary files
- `scripts/modal_ingest.py:6204` — `scheduled_election_refresh()` calls `get_active_jurisdictions()`
- `scripts/modal_ingest.py:6092-6148` — `determine_refresh_cadence()` and `should_run_today()` helpers
- `data/extraction/*.json` — 27 jurisdiction configs (10 city, 10 school, 5 county, 1 college, 1 state)
- `packages/civicos-extraction/tests/test_election_refresh_cadence.py` — cadence test patterns

## Suggested Approach

1. Write an integration test that loads `get_active_jurisdictions()` and asserts all expected prefix types are present (city, county, school, college, state)
2. Assert no jurisdiction with `election_sources` in its config is excluded
3. Assert supplementary files (`-schools`, `-districts`) are correctly excluded
4. Verify that adding a new test config file with `election_sources` auto-enrolls it
5. Check for edge cases: `civera_instances.json` and other non-jurisdiction configs that get loaded (note `city-civera_instances` appears in the scan — this is a bug)

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Cadence tests (from this session)
pytest packages/civicos-extraction/tests/test_election_refresh_cadence.py -q --override-ini="addopts="

# Election detection tests
pytest packages/civicos-extraction/tests/test_election_detection.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Test validates all jurisdiction prefix types included in `get_active_jurisdictions()`
- [ ] Test confirms auto-enrollment: new config with `election_sources` is auto-included
- [ ] Fix `civera_instances.json` being loaded as `city-civera_instances` jurisdiction
- [ ] No false exclusions from `-schools`/`-districts` skip filter
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P2 | `officials_refresh_cron` | 0.5 session |
| P3 | `election_coverage_monitoring` | 0.5 session |

## Notes

- `city-civera_instances`, `city-ghost`, `city-test`, `city-warn` appear in `get_active_jurisdictions()` — these are non-jurisdiction config files that get incorrectly loaded. Cleaning these up would be a quick win.
- The `-schools`/`-districts` skip filter is fragile — what if a real jurisdiction has those substrings? Consider a positive match (require `jurisdiction_id` field) instead.
- Estimated ~0.5 session

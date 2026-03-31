# Recommended: Wire Election Fetch Into Onboard

**Priority:** P0 (wire_election_fetch_into_onboard)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election data pipeline is fully wired: sources, officials fetch, deadlines, officials derivation, snapshot archival, and now quarterly Civera discovery. This session also completed non-Civera research (Clarity Elections covers 7 additional CA counties).

Currently, when a new city is onboarded, `detect_election_sources()` populates the extraction config with election source metadata (step 3.6), but no election data is actually fetched. The city must wait up to 30 days for the monthly `scheduled_election_refresh()` cron to run. This item wires an immediate election fetch into the onboard flow so new cities get data on day 1.

## What This Session Completed

- Created `.github/workflows/cron-civera-discovery.yml` — quarterly probe of all 58 CA counties
- Researched Clarity Elections: 9 CA counties have it (7 net-new beyond Civera). See `docs/internal/clarity-elections-research.md`
- Both items marked done in `launch.json`

## Recommended Task

After `detect_election_sources()` populates the extraction config at onboard step 3.6, trigger an immediate election data fetch. The challenge: onboard runs locally but election fetch runs on Modal.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py:2193` — where `detect_election_sources()` is called during onboard
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:687` — `detect_election_sources()` function
- `scripts/modal_ingest.py:6103` — `scheduled_election_refresh()` — the cron entry point
- `scripts/modal_ingest.py:3640` — `fetch_civera_election_results()` — Civera fetch function
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py` — `CaliforniaElectionProvider.detect_election_sources()`
- `packages/civicos-extraction/src/civicos_extraction/clients/factory.py` — provider dispatch from config

## Suggested Approach

1. Read `onboard.py:2190-2210` to understand the current onboard step 3.6 flow
2. Read `modal_ingest.py:6103-6200` to understand `scheduled_election_refresh()` dispatch logic
3. The key design decision: how to trigger Modal from a local onboard script
   - Option A: `modal run scripts/modal_ingest.py::fetch_civera_election_results --jurisdiction county-marin` (subprocess call)
   - Option B: Add a `--fetch-elections` flag to the onboard CLI that triggers Modal
   - Option C: Extract the fetch logic into a function callable both locally and on Modal
4. Implement the chosen approach — ensure it works for both Civera and CA SOS sources
5. Test with a jurisdiction that has election sources configured

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election-related tests
pytest packages/civicos-extraction/tests/test_marin_registrar.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Onboarding a new city triggers immediate election data fetch
- [ ] Works for both Civera and CA SOS election sources
- [ ] Graceful failure if Modal is unavailable (onboard shouldn't fail)
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P2 | `ballot_preview_smart_scheduling` | 0.5 session |
| P2 | `calendar_aware_election_refresh` | 1 session |
| P2 | `election_cron_enrollment_validation` | 0.5 session |
| P2 | `officials_refresh_cron` | 0.5 session |

## Notes

- Cron jobs run via GitHub Actions, NOT `modal.Cron()` (Modal starter plan limits crons)
- Onboard currently runs locally via CLI (`python -m civicos_extraction.onboard`)
- The `factory.py` dispatch logic already routes election sources to the right client
- 2 pre-existing test failures in `test_integration_election_dispatch.py` — unrelated
- Estimated ~1 session

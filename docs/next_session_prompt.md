# Recommended: Calendar-Aware Election Refresh

**Priority:** P0 (calendar_aware_election_refresh)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-31

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We just completed `ballot_preview_smart_scheduling` — added a 90-day window guard for `ca_sos_ballot_preview` in `scheduled_election_refresh()`. This next item generalizes that idea: vary the *entire* election refresh cadence based on proximity to known election dates. Currently the GH Actions cron fires monthly; the idea is to make it fire daily and let the Modal function itself decide what to do based on election proximity.

## What This Session Completed

- Added date guard to ballot preview fetch (`scripts/modal_ingest.py:6231-6275`)
- 12 new tests in `test_ballot_preview_scheduling.py`, all passing
- Smoke tests 20/20

## Recommended Task

Make `scheduled_election_refresh()` calendar-aware so different source types run at different cadences depending on election proximity:
- **Daily** within 7 days of election (capture election-night SOS results)
- **Weekly** within 90 days (ballot previews, candidate updates)
- **Monthly** otherwise (officials, general maintenance)

The GH Actions cron should switch from monthly to daily, but the Modal function gates work internally so most daily runs are no-ops.

## Key Files

- `scripts/modal_ingest.py:6103-6352` — `scheduled_election_refresh()` full function
- `.github/workflows/cron-election-refresh.yml` — currently monthly (`0 3 1 * *`), needs to become daily
- `packages/civicos/src/civicos/_internal/elections/cycles.py:142` — `get_next_election_date()` returns next election date for an office type
- `packages/civicos/src/civicos/_internal/elections/cycles.py:330` — `get_upcoming_races()` returns all upcoming races for a jurisdiction's config
- `data/extraction/city-san-rafael.json` — sample config with `election_sources` and `ca_sos_ballot_preview.election_date`
- `packages/civicos-extraction/tests/test_ballot_preview_scheduling.py` — pattern for date-window tests

## Architecture Insight

The function has 5 source blocks that run per-jurisdiction:
1. **Civera ElectionStats** — historical election results (monthly is fine)
2. **Marin Registrar** — legacy alias (monthly is fine)
3. **CA SOS Results** — election results (daily near election day)
4. **CA SOS Ballot Preview** — already has 90-day guard (done this session)
5. **Elected Officials** — changes after elections (weekly near election, monthly otherwise)

Plus 2 always-run blocks: deadline generation and officials derivation.

## Suggested Approach

1. Add a `determine_refresh_cadence()` helper that reads election dates from configs and returns a cadence level (`"daily"`, `"weekly"`, `"monthly"`, `"skip"`) based on proximity to the nearest election
2. At the top of `scheduled_election_refresh()`, compute cadence. If cadence is `"skip"` (no elections within 90 days for a jurisdiction), skip everything except officials derivation
3. Gate each source block: Civera/Marin/SOS results run daily near election, otherwise monthly. Officials run weekly near election, monthly otherwise. Ballot preview already has its own guard.
4. Update GH Actions cron from monthly to daily: `0 3 * * *`
5. Update the docstring and log messages to reflect new behavior
6. **Simplest approach**: scan `election_date` fields in `election_sources` configs for the nearest one, similar to what ballot preview does — rather than computing from office-type cycles

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Ballot preview scheduling tests (from this session)
pytest packages/civicos-extraction/tests/test_ballot_preview_scheduling.py -q --override-ini="addopts="

# Election calendar tests (cycles.py)
pytest packages/civicos/tests/test_election_calendar.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `scheduled_election_refresh()` determines cadence from election proximity
- [ ] Daily runs within 7 days of election date (results sources fire)
- [ ] Weekly runs within 90 days (ballot preview, officials)
- [ ] Monthly runs otherwise (general maintenance)
- [ ] GH Actions cron updated to daily
- [ ] No-op runs log clearly why they skipped
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P2 | `election_cron_enrollment_validation` | 0.5 session |
| P2 | `officials_refresh_cron` | 0.5 session |
| P3 | `election_coverage_monitoring` | 0.5 session |

## Notes

- Cron jobs run via GitHub Actions, NOT `modal.Cron()` (Modal starter plan limits crons)
- Today is 2026-03-31; the 2026-06-02 primary is 63 days away — within the 90-day "weekly" window
- The `ca_sos_snapshot_archival` dependency mentioned in launch.json notes may not actually block this — the ballot preview guard already prevents overwrites for that source
- 2 pre-existing failures in `test_integration_election_dispatch.py` (division_filter string mismatch) — unrelated
- Estimated ~1 session

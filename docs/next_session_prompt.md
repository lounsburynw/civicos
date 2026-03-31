# Recommended: Ballot Preview Smart Scheduling

**Priority:** P0 (ballot_preview_smart_scheduling)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-31

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election pipeline is now fully wired end-to-end: source detection, onboard-time fetch (just completed), officials derivation, deadline generation, snapshot archival, and quarterly Civera discovery. The remaining election_coverage_lifecycle items are scheduling refinements.

Currently, `scheduled_election_refresh()` fetches ballot preview data monthly regardless of election timing. This wastes API calls and processing outside the relevant window. The config already includes `election_date` — the fix is a date comparison guard.

## What This Session Completed

- Created `election_fetch.py` — shared fetch logic callable from onboard (no Modal dependency)
- Wired immediate election fetch into onboard step 3.6.1
- 10 new tests, all passing. Smoke tests 20/20.

## Recommended Task

Add a date-based guard in `scheduled_election_refresh()` that skips `ca_sos_ballot_preview` fetch unless today is within ~90 days before the election date. This is a ~0.5 session task.

## Key Files

- `scripts/modal_ingest.py:6232` — where ballot preview fetch is triggered in the cron
- `scripts/modal_ingest.py:6238` — `election_date` is already read from config
- 3 jurisdictions have ballot preview configs: city-san-rafael, city-mill-valley, city-san-anselmo
- All 3 target the 2026-06-02 primary (election_date is in the config)

## Sample Config (from data/extraction/city-san-rafael.json)

```json
"ca_sos_ballot_preview": {
  "election_slug": "2026-primary",
  "election_date": "2026-06-02",
  "election_type": "primary",
  "races": { "congress": [2], "state-senate": [2], "assembly": [12] }
}
```

## Suggested Approach

1. Read `modal_ingest.py:6230-6260` — the ballot preview block in `scheduled_election_refresh()`
2. Add a date guard before the fetch call:
   - Parse `election_date` from config
   - If today is more than 90 days before election_date, skip with a log message
   - If election_date is in the past, also skip (data already archived)
3. Consider adding a second fetch window ~30 days before for updated candidate lists
4. Add a unit test verifying the window logic

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election dispatch tests (2 pre-existing failures — unrelated)
pytest packages/civicos/tests/test_integration_election_dispatch.py -q --override-ini="addopts="

# Election fetch tests (from this session)
pytest packages/civicos-extraction/tests/test_election_fetch.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Ballot preview fetch only runs within 90 days of election_date
- [ ] Past elections are skipped
- [ ] Log message explains why fetch was skipped
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P2 | `calendar_aware_election_refresh` | 1 session |
| P2 | `election_cron_enrollment_validation` | 0.5 session |
| P2 | `officials_refresh_cron` | 0.5 session |
| P3 | `election_coverage_monitoring` | 0.5 session |

## Notes

- Cron jobs run via GitHub Actions, NOT `modal.Cron()` (Modal starter plan limits crons)
- Today is 2026-03-31; the 2026-06-02 primary is 63 days away — within the 90-day window
- The `calendar_aware_election_refresh` item (P2) is a broader version of this same idea but for all election source types, not just ballot preview
- 2 pre-existing failures in `test_integration_election_dispatch.py` (division_filter string mismatch)
- Estimated ~0.5 session

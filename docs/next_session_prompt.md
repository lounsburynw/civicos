# Recommended: Officials Refresh Cron

**Priority:** P0 (officials_refresh_cron)
**Area:** representative_lookup
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed Texas election support (multi-state Phase 5) and then conducted a strategic review of election/officials coverage across California. We documented findings in `docs/internal/election-coverage-assessment.md` and added a new `election_coverage_lifecycle` category to launch.json with 11 items across three priorities (CA depth, automation, ingestion strategy). The `officials_refresh_cron` is the existing P0 that bridges two new items: it establishes the Congress.gov/LegiScan refresh baseline, and the new `officials_derivation_in_cron` (P1) will add contest-winner derivation to the same cron.

## Key Files

- `scripts/modal_ingest.py:5989` — `scheduled_election_refresh()` — monthly cron that fetches election data. Officials refresh should be wired here or as a companion function.
- `scripts/modal_ingest.py:3973` — `derive_elected_officials()` — existing Modal function, NOT called by cron today.
- `scripts/modal_ingest.py:4317` — `fetch_elected_officials()` — fetches from Congress.gov + LegiScan + curated.
- `packages/civicos/src/civicos/_internal/elections/derive.py` — `derive_officials_from_contests()` — derives officials from contest winners.
- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py` — `CongressGovClient`, `RepresentativesClient`, `extract_elected_officials_to_storage()`.
- `.github/workflows/cron-election-refresh.yml` — existing monthly cron workflow pattern to follow.
- `.github/workflows/cron-high-velocity-refresh.yml` — alternative cron pattern for reference.

## Suggested Approach

1. **Create `.github/workflows/cron-officials-refresh.yml`** — GitHub Actions workflow following the existing cron pattern. Monthly schedule (e.g., 8th at 2 AM UTC, offset from election refresh on 1st). Calls `modal run scripts/modal_ingest.py::scheduled_officials_refresh`.

2. **Create `scheduled_officials_refresh()` in modal_ingest.py** — New Modal function that iterates active jurisdictions and for each: (a) calls `fetch_elected_officials.local()` to refresh Congress.gov + LegiScan data, (b) calls `derive_elected_officials.local()` to re-derive from contest winners. Include failure notification (same pattern as other crons).

3. **Consider combining with `officials_derivation_in_cron`** (P1 in election_coverage_lifecycle) — Since both items touch the same cron, they could be done together. The derivation step adds ~5 lines to call `derive_elected_officials.local()` after contest data is stored in `scheduled_election_refresh()`.

4. **Add tests** — Validate that the Modal function runs without error for a pilot jurisdiction. Integration test pattern: mock external APIs, verify storage calls.

## Tests to Run

```bash
pytest packages/civicos/tests/test_election_calendar.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_providers.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `scheduled_officials_refresh()` Modal function created
- [ ] GitHub Actions workflow created with monthly cron schedule
- [ ] Congress.gov + LegiScan officials refresh for all configured jurisdictions
- [ ] Officials derived from contest winners after refresh
- [ ] Failure notification via GitHub issue (matching existing cron pattern)
- [ ] All existing tests pass (zero regression)

## Strategic Context

The new `election_coverage_lifecycle` category in launch.json has 11 items with this priority ordering:
1. **CA depth** (P1): SOS snapshot archival, backfill 24 configs, wire deadlines, Civera re-probing, non-Civera research
2. **Automation** (P1-P2): election fetch on onboard, officials derivation in cron, enrollment validation
3. **Ingestion strategy** (P2-P3): calendar-aware scheduling, smart ballot preview, coverage monitoring

After `officials_refresh_cron`, the highest-impact next items are `backfill_election_sources` (quick win: 24 configs get coverage) and `populate_deadlines_in_cron` (3 lines to wire existing generator). See `docs/internal/election-coverage-assessment.md` for the full analysis.

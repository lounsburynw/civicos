# Recommended: Populate Deadlines in Cron

**Priority:** P0 (populate_deadlines_in_cron)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Cron infrastructure is now healthy (previous session fixed `IndexError` crashes from `Path(__file__).parents[N]` on Modal). The `scheduled_election_refresh()` function in `modal_ingest.py` fetches election data and officials for all jurisdictions, but never generates or stores election deadlines. The `generate_deadlines()` function and `store_election_deadlines()` storage method already exist — they just need to be wired into the cron.

## What This Session Completed

- Fixed all cron jobs (root cause: `origin/main` was 189 commits behind local HEAD)
- Fixed 4 `Path(__file__).parents[N]` crashes on Modal containers
- Manually verified meetings-poll cron works (San Anselmo: 2 new meetings found, vectors indexed)
- Closed 4 cron-failure GitHub issues (#18, #19, #20, #22)

## Recommended Task

Wire `generate_deadlines()` into `scheduled_election_refresh()` so that after election data is stored for each jurisdiction, deadlines are automatically generated from `StateElectionConfig` offsets and stored via `store_election_deadlines()`. Currently only 3 pilot jurisdictions have deadlines (from a manual seed script).

## Key Files

- `scripts/modal_ingest.py:6001` — `scheduled_election_refresh()` — loop over jurisdictions, fetch elections + officials. **Add deadline generation after officials fetch.**
- `packages/civicos/src/civicos/_internal/elections/deadlines.py:19` — `generate_deadlines()` — takes election config + dates, returns deadline objects
- `packages/civicos/src/civicos/storage/postgres_backend.py:8828` — `store_election_deadlines()` — persists deadlines to Postgres
- `packages/civicos/src/civicos/storage/protocols/elections.py:56` — `store_election_deadlines()` protocol definition
- `data/extraction/*.json` — Per-jurisdiction configs with `election_sources`

## Suggested Approach

1. Read `generate_deadlines()` in `deadlines.py` to understand its inputs/outputs
2. Read the `StateElectionConfig` and how offsets work
3. In `scheduled_election_refresh()` (~line 6160, after the officials fetch block), add a new block that:
   - Loads the jurisdiction's `StateElectionConfig` (from extraction config or election_sources)
   - Calls `generate_deadlines()` with the relevant election dates
   - Calls `store_election_deadlines()` to persist
4. Handle errors gracefully (try/except, log warnings, don't break the loop)
5. Test by manually triggering: `gh workflow run cron-election-refresh.yml`

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election-specific tests
pytest packages/civicos/tests/ -q --override-ini="addopts=" -k "election or deadline"

# If cron wiring is modified, integration tests
pytest packages/civicos-extraction/tests/ -q --override-ini="addopts=" -k "cron"
```

## Success Criteria

- [ ] `scheduled_election_refresh()` calls `generate_deadlines()` after storing election data
- [ ] Deadlines are stored via `store_election_deadlines()` for each jurisdiction with election_sources
- [ ] Error handling: deadline generation failure doesn't block the rest of the cron
- [ ] Manually triggered election-refresh completes without error
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `officials_derivation_in_cron` | 0.5 session |
| P1 | `ca_sos_snapshot_archival` | 1 session |
| P1 | `civera_periodic_discovery` | 0.5 session |

## Important: CI Tests Failing

The full CI test suite (`Tests` workflow) is currently failing. This is unrelated to cron work — it's likely because 189 previously-unpushed commits hit CI for the first time. You may want to investigate briefly or ignore if it's pre-existing flakiness.

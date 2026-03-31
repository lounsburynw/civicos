# Recommended: Officials Derivation in Cron

**Priority:** P0 (officials_derivation_in_cron)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The `scheduled_election_refresh()` cron now stores election data from all configured sources AND generates deadlines for elections that lack them (just completed). However, it does NOT derive elected officials from contest winners. The `derive_elected_officials()` Modal function exists (`modal_ingest.py:3973`) and calls `derive_officials_from_contests(backend, jurisdiction)`, but it's never called from the cron loop.

Note: the cron already has an "Elected Officials" block (lines 6155-6166) that calls `fetch_elected_officials.local()` — this fetches officials from external APIs (Congress.gov, LegiScan, curated). The derivation task is different: it creates officials records from election contest *winners* stored in our DB.

## What This Session Completed

- Wired `generate_deadlines()` into `scheduled_election_refresh()` (P0 done)
- After all election sources are processed per jurisdiction, upcoming elections without deadlines get state-aware deadlines generated and stored
- Idempotent (skips elections with existing deadlines), error-tolerant (try/except per jurisdiction)
- Created a shared `PostgresBackend` instance at line 6039 (reusable by next task)
- All critics pass, tests pass

## Recommended Task

Call `derive_officials_from_contests()` in `scheduled_election_refresh()` after contest data is stored. The function at `modal_ingest.py:3973` shows the pattern — it calls `derive_officials_from_contests(backend, jurisdiction)` which scans `election_contests` for `is_winner=True` candidates and creates `elected_officials` records.

## Key Files

- `scripts/modal_ingest.py:6155` — `scheduled_election_refresh()` — the officials fetch block. Add derivation after it.
- `scripts/modal_ingest.py:3973` — `derive_elected_officials()` — standalone Modal function showing the pattern
- `packages/civicos/src/civicos/_internal/elections/derive.py` — `derive_officials_from_contests()` — the core logic
- `scripts/modal_ingest.py:6168` — deadline generation block (just added) — follow this pattern for error handling

## Suggested Approach

1. Read `derive_officials_from_contests()` in `derive.py` to understand inputs/outputs
2. In `scheduled_election_refresh()`, after the deadline generation block (~line 6209), add a new block:
   - Import `derive_officials_from_contests` at the top of the function (alongside existing imports at line 6033)
   - Call `derive_officials_from_contests(backend, jid)`
   - Only run if any contest data was stored (check results from civera/ca_sos sources)
   - Log results, store in `results[jid]["officials_derived"]`
3. Error handling: wrap in try/except like the deadline block
4. The `backend` PostgresBackend instance is already created at line 6039

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election-specific tests
pytest packages/civicos/tests/ -q --override-ini="addopts=" -k "election or official or derive"
```

## Success Criteria

- [ ] `scheduled_election_refresh()` calls `derive_officials_from_contests()` after contest data is stored
- [ ] Only runs for jurisdictions where contests were actually stored (check result counts)
- [ ] Error handling: derivation failure doesn't block the rest of the cron
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `ca_sos_snapshot_archival` | 1 session |
| P1 | `civera_periodic_discovery` | 0.5 session |
| P1 | `election_onboarding_integration` | 1 session |

## Notes

- The `backend` PostgresBackend instance created at line 6039 can be reused (added this session for deadline generation)
- 2 pre-existing test failures in `test_integration_election_dispatch.py` (config value `'San Rafael'` vs `'City of San Rafael'`) — unrelated

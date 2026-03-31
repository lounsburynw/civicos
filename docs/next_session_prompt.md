# Recommended: CA SOS Snapshot Archival

**Priority:** P0 (ca_sos_snapshot_archival)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The `scheduled_election_refresh()` cron now fetches election data from all configured sources, fetches elected officials from APIs, derives officials from contest winners, and generates deadlines. This was the last three sessions of work.

The CA Secretary of State API (`api.sos.ca.gov`) is **ephemeral** — it only serves the current/most-recent election. When the SOS switches from one election cycle to another (e.g., 2024 general to 2026 primary), the old data disappears from the API. Without archival, we lose historical results.

The `store_elections()` method (`postgres_backend.py:8663`) does temporal versioning at the row level (closes old versions with `valid_to`, inserts new), so we don't lose data on re-fetch of the **same** election. But when the API flips to a **different** election entirely, we need to detect this and log the transition.

## What This Session Completed

- Wired `derive_officials_from_contests()` into `scheduled_election_refresh()` (P0 done)
- After deadline generation block, derives elected officials from contest winners for each jurisdiction
- Idempotent, error-tolerant — follows same pattern as other cron blocks
- The cron now has a complete pipeline: sources → officials fetch → deadlines → officials derivation

## Recommended Task

Add snapshot archival to the CA SOS fetch path in `scheduled_election_refresh()`. On each run:
1. Before fetching new data, query existing election IDs for the jurisdiction
2. After fetch, compare new election IDs against previous
3. If the election ID changed (SOS switched cycles), log the transition
4. The temporal versioning in `store_elections` already preserves old rows — this task is about **detecting** and **logging** the transition, not about data preservation (that's already handled)

A fingerprint mechanism already exists at `modal_ingest.py:3791-3803` — it computes a hash of counts and stores it via `update_refresh_metadata()`. This could be extended to also track the election ID itself.

## Key Files

- `scripts/modal_ingest.py:6106` — CA SOS block in `scheduled_election_refresh()`. This is where archival logic goes.
- `scripts/modal_ingest.py:3705` — `fetch_ca_sos_election_results()` — standalone Modal function. Lines 3791-3803 show the fingerprint pattern.
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py:725` — `extract_ca_sos_results_to_storage()` — the extraction function. Lines 754-774 have a partial-fetch guard (abort if zero data).
- `packages/civicos/src/civicos/storage/postgres_backend.py:8663` — `store_elections()` — temporal versioning (closes old, inserts new).
- `packages/civicos/src/civicos/storage/postgres_backend.py:8747` — `get_elections()` — for querying existing elections before fetch.

## Suggested Approach

1. Read the existing CA SOS block in `scheduled_election_refresh()` (~line 6106-6127)
2. Before the `fetch_ca_sos_election_results.local()` call, query existing election IDs:
   ```python
   existing_elections = backend.get_elections(jid, include_past=False)
   existing_ids = {e["id"] for e in existing_elections}
   ```
3. After the fetch, check if the returned election IDs differ from existing:
   ```python
   new_result = results[jid].get("ca_sos_results", {})
   # The fetch function returns election info — check if the election_id changed
   ```
4. If different, log the transition and store a snapshot record (could be in `refresh_metadata` or a new field)
5. Consider: the `extract_ca_sos_results_to_storage()` function generates the election ID from `ca_sos_race_to_election()` — you may need to read this to understand ID format

Alternative simpler approach: extend the fingerprint in `fetch_ca_sos_election_results` (line 3791) to include the election ID, and compare against `last_fetch_hash` from `refresh_metadata` before fetching. If hash differs, log the change.

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election-specific tests
pytest packages/civicos/tests/ -q --override-ini="addopts=" -k "election or ca_sos"
```

## Success Criteria

- [ ] Before CA SOS fetch, existing election data is queried
- [ ] Election cycle transitions are detected (new election ID vs previous)
- [ ] Transitions are logged clearly (old ID, new ID, timestamp)
- [ ] No data loss — temporal versioning already preserves old rows, this adds detection/logging
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `civera_periodic_discovery` | 0.5 session |
| P1 | `non_civera_local_race_research` | 1 session |
| P1 | `wire_election_fetch_into_onboard` | 1 session |

## Notes

- The shared `PostgresBackend` instance at line 6040 is available for pre-fetch queries
- The CA SOS API docstring at line 3718 confirms: "the API only serves the current/most-recent election — no historical data"
- 2 pre-existing test failures in `test_integration_election_dispatch.py` (config value mismatch) — unrelated
- The cron runs monthly via GitHub Actions (`.github/workflows/cron-*.yml`), not Modal crons

# Recommended: Election Source Auto-Detection (Session 3)

**Priority:** P0 (election_source_auto_detection)
**Area:** multi_state_portability
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Sessions 1-2 (2026-04-02) built the ClarityElectionsClient, validated it against live endpoints, and fixed a critical format mismatch. The live Clarity ENR uses **parallel arrays** (`CH`, `V`, `PCT` at contest level) not nested objects. Session 2 fixed the parser, discovered 42 election IDs across 7 CA counties, implemented archive-on-fetch to R2, added ballot measure auto-detection from YES/NO candidates, and integrated the `electionsettings.json` endpoint for authoritative election metadata.

**What's done:** Parser handles both formats. Discovery uses static registry + scrape fallback. Archive-on-fetch wired. 80 Clarity tests, 299 election tests, 20 smoke tests all pass.

**What still needs work:** End-to-end extraction against live data (contests into Postgres), extending to non-CA states, and marking the item done.

## What to Build

### 1. End-to-End Live Extraction (highest priority)
Run the full Clarity pipeline against a live county (e.g., Contra Costa with 12 elections, or Ventura with 99 contests). Verify contests are stored correctly in Postgres. This is the final validation step.

### 2. Extend to Non-CA States
Clarity covers 30+ states. Add entries to `clarity_instances.json` for non-CA states and wire Clarity detection into `DefaultElectionProvider` (currently only `CaliforniaElectionProvider` checks for Clarity). This completes the "auto-detect election platforms" goal.

### 3. Mark Item Done
Once live extraction works and non-CA detection is wired, update `launch.json` status from `not_started` to `done`.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/clarity_elections.py` — Full client. Key functions:
  - `_is_parallel_array_format()` (line ~417) — format detection
  - `clarity_contest_to_storage()` (line ~436) — handles both formats
  - `discover_elections()` (line ~234) — two-tier: registry + scrape
  - `get_election_settings()` (line ~308) — fetches authoritative name/date
  - `extract_clarity_results_to_storage()` (line ~731) — pipeline orchestrator with archive
- `data/extraction/clarity_instances.json` — 42 election IDs across 9 CA counties (7 net-new)
- `packages/civicos-extraction/src/civicos_extraction/election_fetch.py:280` — `_fetch_clarity` handler with R2 archive wiring
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py:65` — Clarity detection in CA provider
- `packages/civicos-extraction/src/civicos_extraction/providers/__init__.py` — DefaultElectionProvider (needs Clarity detection)
- `docs/internal/clarity-elections-research.md` — Platform research, URL patterns, ephemerality notes
- `packages/civicos-extraction/tests/test_clarity_elections.py` — 80 tests

## Live Data Reference (Verified 2026-04-02)

| County | Elections | Sample ID | Version | Contests |
|--------|-----------|-----------|---------|----------|
| Contra Costa | 12 | 122765 | 355929 | Many (incl. President, Senate, local) |
| Ventura | 7 | 122837 | 356562 | 99 (incl. state props, local measures) |
| Santa Clara | 1 | 125819 | 367736 | 1 (Assessor runoff) |

JSON format: parallel arrays. Example field mapping:
- `C` = contest name, `CH` = candidate names array, `V` = votes array
- `PCT` = percentages array, `P` = party array, `W` = winner flags array
- No `IQ` flag for ballot measures — detected via YES/NO candidate names

## Suggested Approach

1. **Run live extraction** against Contra Costa (richest data): instantiate client, call `extract_clarity_results_to_storage()` with real Postgres backend
2. **Verify stored data** — query `store_elections` and `store_election_contests` results from Postgres
3. **Add Clarity detection to DefaultElectionProvider** — check `has_clarity_instance()` during onboarding for any state
4. **Probe non-CA states** — Clarity covers counties in FL, OH, TX, etc. Add a few to `clarity_instances.json`
5. **Update launch.json** — mark `election_source_auto_detection` as `done`

## Tests to Run

```bash
pytest packages/civicos-extraction/tests/test_clarity_elections.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_fetch.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/ -k election -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] End-to-end extraction works for at least 1 Clarity county (contests in Postgres)
- [ ] Clarity detection wired into DefaultElectionProvider for non-CA states
- [ ] At least 1 non-CA state added to clarity_instances.json
- [ ] launch.json item marked done
- [ ] All existing tests pass (no regressions)

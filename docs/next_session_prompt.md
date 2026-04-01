# Recommended: Cron Failure Triage + Data Coverage Audit

**Priority:** P0 (cron_failure_triage_2026_04)
**Area:** observability
**Date:** 2026-04-01

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election_coverage_lifecycle category is fully complete (11/11 items). We built the election cron pipeline (calendar-aware cadence, enrollment validation, officials refresh, coverage monitoring) over several sessions. However, 3 cron jobs failed on 2026-04-01, and a data audit reveals that only 6 of 22 configured jurisdictions actually have election data in Postgres. The user wants to both fix the immediate failures AND gauge how well our data serves what real users would typically ask.

## What This Session Completed

- Added `check_election_coverage()` to `scripts/modal_ingest.py:6164` (monthly completeness report)
- election_coverage_lifecycle: ALL 11 ITEMS COMPLETE
- Audited election data in Postgres — see "Data Coverage" below
- Identified 3 cron failures from today's runs

## Part 1: Fix 3 Cron Failures

### Failure 1: Election Refresh (GH Actions run 23831258244)

Three distinct errors in a single run:

**a) LegiScan API key quoting** — Key is URL-encoded with literal quotes: `key=%27456ec...%27`. The `%27` is a URL-encoded single quote wrapping the key value. Likely the Modal secret `civic-legiscan` has the key stored with surrounding quotes.
- Fix: Check `modal secret list` / update the secret value to strip quotes
- File: `scripts/modal_ingest.py` — search for `fetch_state_legislators` or `LEGISCAN_API_KEY`

**b) `city-national-city` unknown jurisdiction** — The extraction config `data/extraction/city-national-city.json` exists with `election_sources`, but `city-national-city` is not in the jurisdiction registry. `normalize_jurisdiction()` throws `JurisdictionError`.
- Fix: Either add `city-national-city` to the jurisdiction registry, or remove `election_sources` from the config until it's properly onboarded
- File: `packages/civicos/src/civicos/_internal/jurisdiction.py` — jurisdiction registry
- File: `data/extraction/city-national-city.json` — extraction config

**c) `county-marin` officials fetch — NoneType.upper()** — Congress.gov returns 404 ("No MemberTerm matches the given query"), then code calls `.upper()` on a None value. Likely a `state_code` that's None for county-level jurisdictions.
- File: `scripts/modal_ingest.py` — search for `fetch_elected_officials` near line 6362
- The function expects `state_code` but county configs may not have it populated

### Failure 2: Vector Refresh (GH Actions run 23835606851)

Chunk indexing jobs killed by runner (SIGTERM, exit 143). Jobs ran 10-20 minutes. The GH Actions workflow likely has a timeout that's too short for the full chunk corpus (5000+ chunks).
- File: `.github/workflows/cron-vector-refresh.yml` — check `timeout-minutes`
- May need to increase timeout or reduce batch sizes

### Failure 3: Meetings Poll (GH Actions run 23773890264, Mar 31)

`IndexError(5)` from Modal container runtime — opaque error. Needs investigation via `modal app logs` or re-running manually.
- File: `.github/workflows/cron-meetings-poll.yml`
- File: `scripts/modal_ingest.py` — search for `scheduled_meetings_poll`

## Part 2: Data Coverage Audit — User Experience Perspective

Beyond fixing failures, gauge how well the current data serves **what a typical panel of users would probably request**. Think about the most common civic questions:

- "What's happening at the next city council meeting?" — **meetings** corpus
- "What did they decide about housing?" — **decisions** corpus
- "Who represents me?" — **officials** data
- "What's on the ballot?" — **elections/contests** data
- "When are the registration deadlines?" — **deadlines** data
- "What does the municipal code say about ADUs?" — **municipal_code** corpus
- "Are there open issues on my street?" — **issues** (SeeClickFix) corpus

For each question type, evaluate: which jurisdictions can answer it today vs. which should be able to? Where are the biggest gaps relative to likely user demand?

### Current Election Data in Postgres

| Jurisdiction | Elections | Contests | Deadlines | Officials |
|---|---|---|---|---|
| county-sonoma | 44 | 987 | 0 | 4 |
| city-san-rafael | 24 | 29 | yes | 14 |
| city-san-anselmo | 18 | 53 | yes | 13 |
| city-mill-valley | 14 | 35 | yes | 12 |
| state-california | 1 | 5 | 0 | 1 |
| city-berkeley | 1 | 5 | 0 | 0 |
| **16 other jurisdictions** | **0** | **0** | **0** | **0** |

22 jurisdictions configured with `election_sources`. Only 6 have data. The 16 with zero data are mostly Marin school districts + newer additions (Berkeley, Sacramento, Alameda, Yolo, National City).

### Full Data Inventory Commands

```bash
# Election data per jurisdiction
/data-status city-san-rafael

# Quick Postgres query for all corpus counts
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status
c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c.vectors, 'city-san-rafael')
print(format_data_status(status.summary()))
"
```

## Key Files

- `scripts/modal_ingest.py:6164` — `check_election_coverage()` (just added)
- `scripts/modal_ingest.py:6259` — `scheduled_election_refresh()` main loop
- `scripts/modal_ingest.py` — search `fetch_elected_officials` (~line 6362)
- `scripts/modal_ingest.py` — search `scheduled_meetings_poll`
- `.github/workflows/cron-election-refresh.yml` — daily election cron
- `.github/workflows/cron-vector-refresh.yml` — vector indexing cron
- `.github/workflows/cron-meetings-poll.yml` — meetings poll cron
- `packages/civicos/src/civicos/_internal/jurisdiction.py` — jurisdiction registry
- `data/extraction/city-national-city.json` — problematic config

## Suggested Approach

1. Fix the 3 cron failures (highest priority — these block daily pipeline)
2. Run `/data-status` across pilot jurisdictions to build a complete picture
3. Map data coverage against likely user queries (meetings, decisions, officials, elections, code, issues)
4. Identify the biggest UX-impacting gaps and propose backfill priorities
5. Write tests for any code fixes

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election tests (should still pass)
pytest packages/civicos-extraction/tests/test_election_coverage_monitoring.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_cron_enrollment.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] All 3 cron failures diagnosed with root cause
- [ ] At least the election refresh failure fixed (highest impact)
- [ ] Data coverage matrix: which jurisdictions can answer which user questions
- [ ] Gap analysis: biggest UX-impacting data holes identified
- [ ] Prioritized backfill recommendations (what to ingest next for maximum user value)
- [ ] Smoke tests pass

## Notes

- Use `gh run view <id> --log` to get full failure logs
- LegiScan key fix is likely just removing quotes from the Modal secret — verify with `modal secret list`
- `city-national-city` is in San Diego County — may not be a priority jurisdiction. Consider removing election_sources rather than adding to registry.
- Estimated ~1-1.5 sessions (triage + audit)

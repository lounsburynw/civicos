# Recommended: CA Secretary of State Results API Client

**Priority:** P0 (ca_sos_results_client)
**Area:** election_integration
**Date:** 2026-03-26

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed BoardDocsClient — a locale-agnostic school board meeting extraction client with full onboarding integration (platform detection, committee auto-discovery, standard pipeline dispatch). 43 tests passing, 5 Marin district extraction configs created (1,162 meetings ready to ingest).

The election integration category now has: Marin Registrar GraphQL (county-level results, complete but not yet ingested) and BoardDocs (school board meetings, complete). The remaining gap is **state-level election results** — CA SOS covers governor, legislature, US Congress, and ballot propositions with county-level breakdowns.

## Pre-P0: Still-pending Marin Election Ingestion

The Marin Registrar results client was built 2 sessions ago but never run against Postgres. Consider running before or after CA SOS work:

```bash
# Dry run
modal run scripts/modal_ingest.py::fetch_marin_election_results --dry-run
# San Rafael only
modal run scripts/modal_ingest.py::fetch_marin_election_results --division-filter "City of San Rafael"
```

Schema decision still open: `election_candidates` table vs JSONB-only. See `claude-progress.txt` for details.

## P0: CA SOS Results Client

Build `CASOSResultsClient` for the CA Secretary of State election results API. Free, no auth, JSON responses.

### API Reference

Full reference in `docs/internal/election-data-research.md` (line ~473). Key points:

- **Base URL:** `https://api.sos.ca.gov`
- **Auth:** None required
- **Key limitation:** Only serves current/most-recent election. No historical access.
- **Endpoints:**
  - `GET /returns/president` — statewide results
  - `GET /returns/us-rep/district/{N}` — US House (Marin = district 2)
  - `GET /returns/state-assembly/district/{N}` — state assembly (Marin = district 12)
  - `GET /returns/ballot-measures` — all ballot measures
  - County breakdowns: append `/county/{slug}` (e.g., `/county/marin`)
  - `GET /returns/status` — county reporting status
- **Data gotcha:** All values are strings. Candidate votes are comma-formatted (`"2,909,979"`), ballot measure votes are not (`"7453339"`).
- **Marin specifics:** county code 21, slug `marin`, US House district 2, Assembly district 12, Senate district 2

### Key Files
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos.py` — create new
- `packages/civicos-extraction/tests/test_ca_sos.py` — create new
- `scripts/modal_ingest.py` — add `fetch_ca_sos_results()` function
- `packages/civicos/src/civicos/_internal/elections/__init__.py` — existing election data models
- `packages/civicos-extraction/src/civicos_extraction/clients/marin_registrar.py` — reference client pattern

### Suggested Approach
1. Read CA SOS API Reference in `docs/internal/election-data-research.md:473`
2. Build `CASOSResultsClient` with methods for statewide races, district races, ballot measures, and county breakdowns
3. Map to existing election storage models (Election, ElectionContest, Candidate, BallotMeasure)
4. Handle string-to-number parsing (comma-formatted vote counts)
5. Wire Modal ingestion function
6. Test against live endpoints (free, no auth)

### Storage Consideration
CA SOS only has the current election — no history. This means:
- Refreshing overwrites previous data (unlike Marin Registrar with 46 elections)
- Store `reportType` (`"R"` = preliminary, `"U"` = certified) to track result finality
- Results map to `state-california` jurisdiction with county breakdowns in `raw_data`

## Tests to Run

```bash
# BoardDocs tests (verify still passing)
pytest packages/civicos-extraction/tests/test_boarddocs.py -v --override-ini="addopts="
# Marin Registrar tests
pytest packages/civicos-extraction/tests/test_marin_registrar.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] CASOSResultsClient fetches statewide race results
- [ ] County breakdown queries work (Marin results for US House district 2)
- [ ] Ballot measure results with yes/no vote parsing
- [ ] String vote counts correctly parsed to integers
- [ ] Results map to existing election storage models
- [ ] Modal ingestion function wired
- [ ] Unit + integration tests passing
- [ ] No regressions in smoke tests

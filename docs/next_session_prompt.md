# Recommended: Build Marin Registrar Election Results Client

**Priority:** P0
**Area:** election_integration
**Date:** 2026-03-25

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed a deep research pass on election data sources and school board platforms for Bay Area / Marin County. Key findings: Google Civic Representatives API is dead (April 2025), civic data aggregator APIs (Democracy Works, Ballotpedia, BallotReady) all have opaque sales-gated pricing. The best path is building against primary government sources.

The Marin County past elections database (`pastelections.marincounty.gov`) turned out to be powered by a **GraphQL API** (ElectionStats by Civera) — not CSV downloads as initially assumed. It's unauthenticated, structured, and has 15+ years of data. A new `election_integration` category was added to `launch.json` with 6 implementation items.

## Recommended Task

Build a GraphQL client for the Marin County Registrar's ElectionStats platform. Three-query pattern:
1. List elections (46 elections, June 2010 – May 2025)
2. List contests per election (521 candidate contests, 380 ballot questions)
3. Get precinct-level data per contest (146 precincts, vote channel breakdowns)

Map results to existing election data models (Election, Contest, Candidate, BallotMeasure). The storage protocol and Postgres schema are already complete.

## Key Files

- `docs/internal/election-data-research.md` — **Full technical reference** including GraphQL queries, field schemas, response formats. Read the "Marin Registrar GraphQL Reference" section.
- `packages/civicos-extraction/src/civicos_extraction/clients/marin_registrar.py` — Existing Playwright-based election schedule scraper. Extend or companion with GraphQL client.
- `packages/civicos/src/civicos/_internal/elections/__init__.py` — Election, Contest, Candidate, BallotMeasure data models
- `packages/civicos/src/civicos/storage/protocols/elections.py` — ElectionStorage protocol (store_elections, store_election_contests, etc.)
- `packages/civicos/src/civicos/storage/postgres_backend.py:8663` — Postgres implementation of election storage
- `scripts/modal_ingest.py:3393` — `fetch_elections()` Modal function
- `packages/civicos-extraction/src/civicos_extraction/clients/google_civic.py` — Reference for how election data maps to storage models

## Suggested Approach

1. Read `docs/internal/election-data-research.md` (Marin Registrar GraphQL Reference section) for the full API spec
2. Build `MarinRegistrarElectionStatsClient` (or extend existing `marin_registrar.py`) with three methods:
   - `list_elections(from_year, to_year)` — GraphQL `searchSuggestions` query
   - `list_contests(event_id)` — GraphQL `search` query with pagination
   - `get_precinct_data(contest_id)` — GraphQL `contestGranularData` query
3. Map to existing data models. May need to add `votes_received: Optional[int]` to the `Candidate` dataclass.
4. Write storage mapping functions (similar to `google_civic_to_election()` pattern)
5. Wire into `fetch_elections()` in `modal_ingest.py` as a source alongside Google Civic
6. Test against live API (no auth needed)

## GraphQL Endpoint

```
POST https://pastelections.marincounty.gov/api/graphql_pr
Content-Type: application/json
# No auth required
```

The ElectionStats platform (by Civera) is also used by Sonoma County and Yolo County in CA — same API patterns with different tenant URLs. Building this client generalizes to those counties too.

## Tests to Run

```bash
# Existing election tests
pytest packages/civicos-extraction/tests/test_marin_registrar.py -v
# Smoke tests (verify no regressions)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] GraphQL client fetches elections, contests, and candidates from live API
- [ ] Data maps to existing Election/Contest/Candidate models
- [ ] Results stored to Postgres via existing ElectionStorage protocol
- [ ] Precinct-level data available for San Rafael contests
- [ ] No regressions in smoke tests

## Important Notes

- The existing `marin_registrar.py` is a Playwright scraper for election *schedules* (upcoming dates). The new client is for election *results* (historical). These are complementary, not overlapping.
- The `Candidate` dataclass may need `votes_received: Optional[int]` and `vote_percentage: Optional[float]` fields added.
- Ballot measures appear as contests with candidates named "Yes"/"No" — the `pseudocandidate` field distinguishes real candidates from summary rows (TOTAL_VOTES, TOTAL_BALLOTS, etc.).
- Pagination on the `search` query is 1-indexed.

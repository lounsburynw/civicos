# Recommended: election_integration (Phase 2)

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 460. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 460 completed **Phase 1: Foundation** of election_integration:
- Election data models (`Election`, `Contest`, `Candidate`, `BallotMeasure`, `ElectedOfficial`, `VotingRecord`)
- `ELECTIONS` CorpusType with registry entry
- StorageBackend protocol extended with 10 election methods
- Both SQLite and Postgres backends implemented (4 tables each + indexes)

All 39 smoke tests passing. Commit: `efe845b`

## Recommended Task

Continue to **Phase 2: Google Civic API Client** - create the data source client to fetch election data.

## Key Files

- `docs/critical/ELECTION_INTEGRATION.md` - Full implementation reference
- `packages/civic/src/civic/_internal/elections/__init__.py` - Data models (created)
- `packages/civic/src/civic/storage/backend.py:1448-1670` - Election protocol methods
- `packages/civic-extraction/src/civic_extraction/clients/` - Where Google Civic client goes

## Suggested Approach (Phase 2)

1. Create `packages/civic-extraction/src/civic_extraction/clients/google_civic.py`:
   - `GoogleCivicClient` class
   - Methods: `get_elections()`, `get_voter_info()`, `get_representatives()`
   - Handle API key from environment (`GOOGLE_CIVIC_API_KEY`)
   - Free tier: 25k requests/day

2. Reference the Google Civic API docs:
   - Elections: `https://civicinfo.googleapis.com/civicinfo/v2/elections`
   - Voter Info: `https://civicinfo.googleapis.com/civicinfo/v2/voterinfo`
   - Representatives: `https://civicinfo.googleapis.com/civicinfo/v2/representatives`

3. Map API responses to our data models:
   - `election` → `Election`
   - `contest` → `Contest`
   - `candidate` → `Candidate`
   - `official` → `ElectedOfficial`

4. Add tests with mocked responses

## Tests to Run

```bash
# After creating client
pytest packages/civic-extraction/tests/ -v -q -k "google_civic" --override-ini="addopts="

# Smoke test
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `GoogleCivicClient` class created with API key handling
- [ ] `get_elections()` returns list of elections
- [ ] `get_voter_info(address)` returns ballot info for an address
- [ ] `get_representatives(address)` returns elected officials
- [ ] Response mapping to our data models
- [ ] Tests with mocked API responses
- [ ] Integration test with real API (optional, requires key)

## Alternative: roll_call_extraction

If Google Civic API work is blocked (no API key), consider `roll_call_extraction` (priority 1) instead - extracting AYES/NOES patterns from meeting minutes to populate vote results in decisions. This enables voting record queries.

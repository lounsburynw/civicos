# Recommended: What's On My Ballot

**Priority:** P0 (whats_on_my_ballot)
**Area:** representative_lookup
**Date:** 2026-03-28

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `election_calendar` — built a deterministic cycle resolver (`get_next_election_date()`) and CA deadline generator (`generate_ca_deadlines()`). All 3 pilot jurisdictions now have the June 2 primary and Nov 3 general elections stored with 8 contests and 5 deadlines each. `whats_next(include_elections=True)` returns elections with deadlines.

This is the capstone query: combine election calendar + contests + candidates + deadlines into one "what's on my ballot?" answer. The data layer is ready; this session wires it into the API.

## What Needs to Be Done

Add `explore what='my_ballot'` to the v2 query layer. Given a jurisdiction, return:
1. Next upcoming election (date, type, name)
2. Every contest on the ballot (federal → state → local)
3. Candidates per contest (from CA SOS ballot preview data)
4. Key deadlines (registration, VBM, early voting, election day)
5. Which deadlines have passed vs upcoming

## Key Files

- `packages/civicos-services/src/civicos_services/query/verbs.py:1264` — existing `explore what='representatives'` handler (pattern to follow)
- `packages/civicos-services/src/civicos_services/query/verbs.py:1298` — dispatch switch where new `what='my_ballot'` goes
- `packages/civicos/src/civicos/_internal/elections/cycles.py:1` — cycle resolver with `get_contests_for_jurisdiction()`, `get_next_election_date()`
- `packages/civicos/src/civicos/_internal/elections/deadlines.py:1` — `generate_ca_deadlines()`
- `packages/civicos/src/civicos/storage/postgres_backend.py:8747` — `get_elections()`, `get_election_contests()`, `get_election_deadlines()`
- `data/extraction/city-san-rafael.json:26` — election_sources with district config
- `apps/civicos-mcp/server.py` — MCP server, add `whats_on_my_ballot` tool

## Data Already Available (Postgres)

Per jurisdiction (San Rafael, Mill Valley, San Anselmo):
- **Elections**: June 2 primary + Nov 3 general stored with source="election_cycle" or "ca_sos_ballot_preview"
- **Contests**: 8 per election (US House D2, Assembly D12, State Senate D2, Governor, Lt Gov, AG, Controller, Treasurer)
- **Candidates**: 3 candidates for State Senate D2 (from CA SOS), others have contest shells without candidate data yet
- **Deadlines**: 5 per election (VBM mailed May 4, registration May 18, early voting May 23, conditional reg June 2, election day June 2)
- **Elected Officials**: Federal (Schiff, Padilla, Huffman) + local council members stored

## Suggested Approach

1. **Add `explore what='my_ballot'` handler** in `verbs.py` — follow the `representatives` pattern. Fetch upcoming elections via `storage.get_elections(jid, include_past=False)`, then for each election get contests and deadlines.

2. **Enrich contests with candidates** — `storage.get_election_contests(election_id)` returns contests with `raw_data` containing parsed candidates (see CA SOS ballot preview data). Surface candidate name, party, incumbent status.

3. **Compute deadline status** — mark each deadline as passed/upcoming relative to today. Highlight the next actionable deadline.

4. **Structure the response** — nested: election → contests (grouped by level: federal/state/local) → candidates, plus deadlines array.

5. **Add MCP tool** — `whats_on_my_ballot(jurisdiction)` in `apps/civicos-mcp/server.py` that calls the explore endpoint.

6. **Write tests** — test the explore handler with mock storage, verify contest grouping, deadline ordering.

## Example Response Shape

```json
{
  "jurisdiction": "city-san-rafael",
  "next_election": {
    "name": "2026 California Primary Election",
    "date": "2026-06-02",
    "type": "primary",
    "days_until": 66
  },
  "contests": [
    {
      "level": "federal",
      "races": [
        {"title": "US House District 2", "candidates": [{"name": "...", "party": "..."}]}
      ]
    },
    {
      "level": "state",
      "races": [
        {"title": "Governor", "candidates": [...]},
        {"title": "State Senate District 2", "candidates": ["Damon Connolly (D)", "Tief Gibbs (R)", "Aaron Smith (R)"]}
      ]
    }
  ],
  "deadlines": [
    {"type": "voter_registration", "date": "2026-05-18", "passed": false, "description": "Last day to register..."}
  ],
  "next_deadline": {"type": "vbm_ballots_mailed", "date": "2026-05-04", "days_until": 37}
}
```

## Tests to Run

```bash
# Election calendar tests (should still pass)
pytest packages/civicos/tests/test_election_calendar.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
# Elected officials tests
pytest packages/civicos/tests/test_elected_officials.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `POST /api/v2/civic/explore` with `what='my_ballot'` returns structured ballot data
- [ ] Response includes contests grouped by level (federal, state, local)
- [ ] Candidates from CA SOS data appear on contests that have them
- [ ] Deadlines sorted with next actionable deadline highlighted
- [ ] MCP tool `whats_on_my_ballot` works for all 3 pilot jurisdictions
- [ ] Graceful handling when no elections exist for a jurisdiction

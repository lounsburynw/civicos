# Recommended: Derive Elected Officials from Election Winners

**Priority:** P0 (derive_officials_from_winners)
**Area:** representative_lookup
**Date:** 2026-03-28

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session built the foundation for "who represents me?" — the most common citizen query. District detection now works automatically during onboarding (Census Bureau API → congressional/state districts). The `representative_lookup` category in launch.json has 7 items; this is the critical data step that turns election results we already have into a usable officials roster.

The election_contests table already stores `is_winner` flags in raw_data for candidates from both Civera ElectionStats (Marin County 2010-2025, 521 contests) and CA SOS results. The `elected_officials` storage protocol is already defined with `store_elected_officials()` / `get_elected_officials()` / `get_official_by_name()`. This item connects those two pieces.

## What Needs to Be Done

Build a function that:
1. For a given jurisdiction, queries election_contests (most recent election per seat type)
2. Extracts candidates with `is_winner=true` from raw_data
3. Maps them to the elected_officials storage format (id, name, seat, jurisdiction_id, term_start, term_end, candidate_id)
4. Stores via `store_elected_officials()` with temporal versioning

This covers: federal congress, state legislature, county supervisors — all from data we already have.

## Key Files

- `packages/civicos/src/civicos/storage/protocols/elections.py` — Storage protocol with `store_elected_officials()`, `get_elected_officials()`, `get_official_by_name()`
- `packages/civicos/src/civicos/storage/sqlite_backend.py:507-624` — SQLite implementation (elected_officials table schema)
- `packages/civicos/src/civicos/_internal/elections/__init__.py` — Elections module (derivation logic goes here)
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_results.py:615-624` — Winner detection in CA SOS mapper
- `packages/civicos-extraction/src/civicos_extraction/clients/civera_election_stats.py` — Civera contest mapper with is_winner
- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py` — Representative dataclass (reference for official fields)
- `scripts/modal_ingest.py` — Where the Modal function to run derivation would go

## Elected Officials Table Schema

```sql
CREATE TABLE elected_officials (
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  seat TEXT NOT NULL,           -- e.g. "US House District 2", "State Assembly 12"
  jurisdiction_id TEXT NOT NULL,
  term_start TEXT NOT NULL,
  term_end TEXT,                -- NULL = currently serving
  name_variations TEXT,
  candidate_id TEXT,            -- Links to election_contests for voting record
  valid_from TIMESTAMP,
  valid_to TIMESTAMP,
  PRIMARY KEY (id, jurisdiction_id, valid_from)
)
```

## Contest raw_data Structure (what you're parsing)

```json
{
  "candidates": [
    {
      "id": "ca-sos-cand-...",
      "name": "Jared Huffman",
      "party": "Dem",
      "votes_received": 23772,
      "vote_percentage": 52.5,
      "is_winner": true,
      "source": "ca_sos_results"
    }
  ]
}
```

## Suggested Approach

1. Read the elections storage protocol to understand the exact method signatures
2. Read the election_contests data (via `storage.get_election_contests()`) to understand what's stored
3. Build `derive_officials_from_contests(storage, jurisdiction_id)` in `_internal/elections/`
4. For each contest type, find the most recent election, extract winners
5. Map winner → elected_official dict with proper seat naming
6. Call `storage.store_elected_officials()` with temporal versioning
7. Add a Modal function in `modal_ingest.py` (`derive_elected_officials`) for remote execution
8. Write tests validating the derivation against known San Rafael data

## Broader Context: 2026 Election Sprint

All election-related items were elevated to P1 this session. The CA primary is June 2 (66 days), general November 3. Two new launch.json categories track the work:

- **representative_lookup** (8 items) — "who represents me?" chain. This P0 is the critical data step.
- **ballot_awareness** (4 items) — election calendar, local candidates, ballot measures, deadlines. Feeds "what's on my ballot?"

See `memory/project_election_cycle_gaps.md` for the full gap analysis.

## Relevant Memories

- `memory/project_representative_lookup.md` — Full design for "who represents me?" feature chain
- `memory/project_election_cycle_gaps.md` — What citizens need vs what we have for Nov 2026
- `memory/feedback_no_openstates.md` — Open States unreliable; use our own election data for state legislators

## Tests to Run

```bash
# Election detection tests (should still pass)
pytest packages/civicos-extraction/tests/test_election_detection.py -v --override-ini="addopts="
# New tests for this item
pytest packages/civicos/tests/test_elected_officials.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Function derives current officials from election_contests for San Rafael
- [ ] Officials stored via store_elected_officials() with temporal versioning
- [ ] Covers federal (congress), state (assembly/senate), county (supervisors)
- [ ] candidate_id links officials to their contest data for voting record joins
- [ ] Modal function wired for remote execution
- [ ] Tests validate derivation against known Marin County election data

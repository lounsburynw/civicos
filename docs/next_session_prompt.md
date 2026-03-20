# Recommended: Congressional Hearings — Query + UX (Session 2 of 2)

**Priority:** P0 (congressional_hearings)
**Area:** multi_scale_participation
**Date:** 2026-03-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 1 (ingest) is complete. 421 congressional hearings are stored in the `congressional_hearings` table — 274 House, 147 Senate. Types: 215 Hearings, 170 Meetings, 36 Markups. The data is refreshed weekly via `scheduled_low_velocity_refresh()`. Session 2 is wiring this data into the query and UX layers so users can see upcoming federal hearings.

## What Already Exists

- `congressional_hearings` table in Postgres with 421 rows, temporal versioning, 4 indexes
- `StorageBackend.get_congressional_hearings(committee_code, chamber, hearing_date_start, hearing_date_end, hearing_type, ...)` — filtering works
- `StorageBackend.get_congressional_hearings_count(chamber)` — counts work
- `CorpusType.CONGRESSIONAL_HEARINGS` registered in corpus_types.py (SQL-only, no vectors)
- `CongressGovClient.get_committee_hearings()` and `get_committee_hearing_detail()` methods
- `fetch_congressional_hearings()` Modal function in modal_ingest.py, added to weekly refresh

## What Needs to Be Done (Session 2)

### 1. Wire into `civic.upcoming(types=["hearings"])`

**File:** `packages/civicos-services/src/civicos_services/query/verbs.py` (~line 562)

Currently, the "hearings" event type in `execute_upcoming()` only looks at local meetings that have hearing agenda items. Extend to also query `backend.get_congressional_hearings()` with `hearing_date_start=now, hearing_date_end=now+days`. Return as `CivicResult(type="hearing", ref="hearing:federal-us:{event_id}")`.

### 2. v2 Search Adapter

**File:** `packages/civicos-services/src/civicos_services/query/adapters.py`

Add `CongressionalHearingsAdapter` to search for hearings by topic (title match) or committee. Follow the pattern of `CongressionalVotesAdapter`.

### 3. MCP Tool

**File:** `apps/civicos-mcp/tools/handlers.py`, `apps/civicos-mcp/tools/registry.py`

Add `get_upcoming_hearings` tool. Parameters: chamber, committee, days_ahead, topic keyword. Returns formatted hearing list with date, committee, title, location, related bills.

### 4. Extension UX

**File:** `apps/civicos-extension/` (Svelte components)

Add "Congressional Hearings" section on Federal tab showing upcoming hearings with date, committee, title. Group by date. Link to hearing URL.

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py` — `get_congressional_hearings()` at ~line 7630, `store_congressional_hearings()` at ~line 7570
- `packages/civicos/src/civicos/storage/protocols/legislation.py` — protocol at ~line 351
- `packages/civicos-services/src/civicos_services/query/verbs.py` — `execute_upcoming()` at ~line 562
- `packages/civicos-services/src/civicos_services/query/adapters.py` — v2 search adapters
- `apps/civicos-mcp/tools/handlers.py` — MCP tools
- `apps/civicos-extension/` — browser extension

## Data Shape

```python
backend.get_congressional_hearings(hearing_date_start="2026-03-20", limit=5)
# Returns: [{
#   "event_id": "119107", "chamber": "House", "congress": 119,
#   "hearing_date": "2026-03-26T18:00:00Z",
#   "title": "Policies to Protect Our Communities From Illicit Drug Threats",
#   "hearing_type": "Hearing", "meeting_status": "Scheduled",
#   "committee_name": "House Energy and Commerce Subcommittee on Health",
#   "committee_code": "hsif14",
#   "location_building": "Rayburn House Office Building", "location_room": "2123",
#   "related_bills": [{"name": "H.R. 1266, Combatting Illicit Xylazine Act", "url": "..."}],
#   "hearing_url": "https://www.congress.gov/event/119th-congress/house/119107",
# }]
```

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `civic.upcoming(types=["hearings"])` returns federal hearings alongside local
- [ ] v2 search finds hearings by topic keyword
- [ ] MCP `get_upcoming_hearings` tool works
- [ ] Extension shows "Congressional Hearings" on Federal tab
- [ ] Can answer: "What hearings are coming up about housing?" through all three surfaces

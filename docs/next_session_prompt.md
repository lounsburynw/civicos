# Recommended: MCP who_represents_me Tool

**Priority:** P0 (mcp_who_represents_me)
**Area:** representative_lookup
**Date:** 2026-03-29

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `whats_on_my_ballot` — the capstone ballot query is now live as `explore what='my_ballot'`. Returns elections sorted by date, contests grouped by government level (federal/state/local/judicial), candidates from CA SOS, and deadlines with next_deadline computation. 16 integration tests passing.

The data infrastructure is solid: elected officials, elections, contests, candidates, and deadlines all queryable through the v2 explore verb. Now we need to expose this as a dedicated MCP tool — the flagship citizen query: "Who represents me?"

## What Needs to Be Done

Add a `who_represents_me` tool to the MCP server that geocodes an address, resolves jurisdictions, and returns elected officials at every level. This combines the existing `explore what='representatives'` infrastructure with geocoding.

## Key Files

- `apps/civicos-mcp/server.py:410-528` — existing v2 tool definitions and routing (pattern to follow)
- `packages/civicos-services/src/civicos_services/query/verbs.py:1264` — `explore what='representatives'` handler (walks jurisdiction hierarchy, returns officials per level)
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py` — `resolve_jurisdictions()` for hierarchy resolution
- `packages/civicos/src/civicos/storage/postgres_backend.py:9103` — `get_elected_officials(jurisdiction_id, current_only=True)`

## Data Already Available (Postgres)

- **Federal officials**: Schiff (Senate), Padilla (Senate), Huffman (House D2) for San Rafael
- **Local officials**: San Rafael city council members stored
- **Geocoding**: `GOOGLE_MAPS_API_KEY` available in env, used by existing geocoding_service

## Suggested Approach

1. **Add tool definition** in `server.py` — `who_represents_me(address, jurisdiction?)`. Address is primary; jurisdiction is fallback when no address provided.

2. **Implement handler** — Geocode address → resolve jurisdiction from coordinates → call `explore what='representatives'` logic (or call it directly via the verb) → return officials grouped by level.

3. **Fallback behavior** — If no address, use the server's default jurisdiction. If geocoding fails, return error with suggestion to provide jurisdiction directly.

4. **Consider combining with ballot** — Could optionally include `my_ballot` summary (next election date, total contests) alongside officials for a comprehensive civic profile.

5. **Write tests** — Test MCP tool registration, mock geocoding, verify response shape.

## Tests to Run

```bash
# Ballot tests (verify nothing regressed)
pytest packages/civicos/tests/test_explore_ballot.py -v --override-ini="addopts="
# Election calendar tests
pytest packages/civicos/tests/test_election_calendar.py -v --override-ini="addopts="
# Elected officials tests
pytest packages/civicos/tests/test_elected_officials.py -q --override-ini="addopts="
# MCP sequences (existing)
pytest packages/civicos/tests/test_integration_mcp_sequences.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] MCP tool `who_represents_me` registered and callable
- [ ] Address input geocodes to jurisdiction and returns officials
- [ ] Officials grouped by level (federal → state → local)
- [ ] Fallback to default jurisdiction when no address provided
- [ ] Works for all 3 pilot jurisdictions (San Rafael, Mill Valley, San Anselmo)
- [ ] Graceful error when geocoding fails or address is outside service area

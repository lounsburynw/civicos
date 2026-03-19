# Recommended: Congressional Votes Query + UX

**Priority:** P0 (congressional_votes_query)
**Area:** multi_scale_participation
**Date:** 2026-03-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 3 of the federal data plan (ingest) is complete. 1,491 congressional votes are stored in the `congressional_votes` table — 173 House votes for Huffman (CA-02) and 1,318 Senate votes for Schiff and Padilla. The data is refreshed weekly via `scheduled_low_velocity_refresh()`. Session 4 is wiring this data into the query and UX layers so users can actually ask "How did my representative vote on [bill]?"

## What Already Exists

- `congressional_votes` table in Postgres with 1,491 rows, temporal versioning, 5 indexes
- `StorageBackend.get_congressional_votes(bioguide_id, bill_id, chamber, congress, ...)` — filtering works
- `StorageBackend.get_congressional_votes_count(bioguide_id, chamber)` — counts work
- `CorpusType.CONGRESSIONAL_VOTES` registered in corpus_types.py (SQL-only, no vectors)
- `CongressGovClient` with `get_house_member_votes()`, `get_senate_member_votes()`, `get_house_roll_calls()`
- Vote positions normalized to: Yea, Nay, Not Voting, Present

## Suggested Approach

1. **v2 search adapter** — `civic.search("housing votes")` should return how local reps voted on housing-related bills. Add congressional vote results to search responses when query matches legislation topics. Key decision: match votes to search queries by joining `congressional_votes.bill_id` against `legislation.bill_id` where legislation matches the search term.
2. **MCP tool** — `get_congressional_votes` tool in `apps/civicos-mcp/tools/handlers.py`. Parameters: member name or bioguide_id, bill keyword, date range. Parallels existing `get_voting_record` for city council.
3. **Extension UX** — "How They Voted" view on the Federal tab. Show recent votes for the user's representatives, grouped by bill. Link from legislation items to vote positions.

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py` — `get_congressional_votes()` at ~line 7380, `store_congressional_votes()` at ~line 7280
- `packages/civicos/src/civicos/storage/backend.py` — protocol definition at ~line 1555
- `packages/civicos-services/src/civicos_services/query/` — v2 query adapters (search, context)
- `apps/civicos-mcp/tools/handlers.py` — MCP tool definitions
- `apps/civicos-extension/` — browser extension (Svelte)
- `packages/civicos/src/civicos/storage/corpus_types.py` — CONGRESSIONAL_VOTES corpus type

## Data Shape

```sql
-- Sample: How did Huffman vote recently?
SELECT vote_date, vote_position, bill_id, bill_title, vote_question
FROM congressional_votes
WHERE bioguide_id = 'H001068' AND valid_to IS NULL
ORDER BY vote_date DESC LIMIT 10;

-- Linking to legislation table
SELECT cv.vote_position, cv.vote_date, l.title, l.summary
FROM congressional_votes cv
JOIN legislation l ON cv.bill_id = l.bill_id
WHERE cv.bioguide_id = 'H001068' AND cv.valid_to IS NULL;
```

Note: `bill_id` format in congressional_votes is like "HR3424", "HRES682". Check if this matches the `legislation.bill_id` format or if normalization is needed.

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] v2 search returns vote positions when query matches legislation topics
- [ ] MCP `get_congressional_votes` tool works (by member, by bill, by keyword)
- [ ] Extension shows "How They Voted" on Federal tab
- [ ] Can answer: "How did Huffman vote on HR3424?" through all three surfaces

# Recommended: election_whats_next_integration

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-08

> Data Readiness is top priority for pilot. Election data integration enables whats_next() to surface upcoming elections alongside meetings.

## Context

The `whats_next()` method currently returns only meetings. For pilot readiness, it should also surface:
- Upcoming elections
- Registration deadlines
- Early voting start dates
- Ballot measure summaries

This enables notifications like "Registration deadline in 5 days" alongside meeting notifications.

## Dependencies

This item depends on `election_ingestion_pipeline` which is already **ready** (completed 2026-01-05). Elections table is populated in Supabase.

## Key Files

- `packages/civic/src/civic/civic.py` - whats_next() method to modify
- Election data already in Supabase `elections` table

## Suggested Approach

1. **Explore current whats_next() implementation**
   - How does it query meetings?
   - What's the return structure?

2. **Check election data schema**
   - What fields are in the elections table?
   - How to identify "upcoming" elections?

3. **Extend whats_next() to include elections**
   - Query elections with date > now
   - Include registration deadlines, early voting dates
   - Merge with meeting results

4. **Add tests**
   - Verify elections appear in whats_next() results
   - Test deadline proximity logic

## Related Items (same cluster)

After this P0, consider these related P1 items:
- `election_api_endpoints` - REST endpoints for election data
- `election_vector_embeddings` - Vector embeddings for election RAG

## Session Context

Previous session completed:
- `incremental_vector_indexing` - Fixed critical vector deletion bug
- Added --force flag and safety checks to vectors CLI
- 8 unit tests added

Priority re-evaluation: User directed focus on Data Readiness before other categories (eval_framework demoted to P1).

# Recommended: election_integration

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 459. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 459 completed `data_completeness_audit` - verified all 37 claimed-ready data items are actually complete. The audit script (`scripts/audit_data_completeness.py`) confirms:
- 31,951 vector embeddings in pgvector
- All storage tables populated (meetings, decisions, issues, budget, funding)
- All API methods exist (what_applies, budget, funding_flow, etc.)

With core data verified, the next priority is election integration for the `whats_next()` feature.

## Recommended Task

Implement election data integration following the phased approach in the reference doc. Start with **Phase 1: Foundation** - data models and storage.

## Key Files

- `docs/critical/ELECTION_INTEGRATION.md` - Full implementation reference (read first!)
- `packages/civic/src/civic/storage/corpus_types.py:44` - Add ELECTIONS to CorpusType enum
- `packages/civic/src/civic/storage/backend.py:727` - Add election storage methods
- `packages/civic/src/civic/storage/sqlite_backend.py` - Implement SQLite storage
- `packages/civic/src/civic/storage/postgres_backend.py` - Implement Postgres storage

## Suggested Approach (Phase 1 Only)

1. Create `packages/civic/src/civic/_internal/elections/__init__.py` with data models:
   - `ElectionType`, `ContestType` enums
   - `Election`, `Contest`, `Candidate`, `BallotMeasure` dataclasses
   - `ElectedOfficial`, `VotingRecord` for future linkage

2. Add `ELECTIONS` to `CorpusType` in `corpus_types.py`:
   - Set `jurisdiction_type="both"` (elections span federal/state/local)

3. Add election methods to `StorageBackend` protocol:
   - `store_elections()`, `get_elections()`, `get_election_count()`
   - `store_elected_officials()`, `get_elected_officials()`

4. Implement in SQLiteBackend (Postgres can follow same pattern)

## Tests to Run

```bash
# After adding models
pytest packages/civic/tests/test_storage_protocols.py -v -q --override-ini="addopts="

# Smoke test
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `Election`, `Contest`, `Candidate`, `BallotMeasure` models created
- [ ] `ElectedOfficial`, `VotingRecord` models created
- [ ] `ELECTIONS` added to CorpusType with jurisdiction_type="both"
- [ ] Election storage methods added to StorageBackend protocol
- [ ] SQLite implementation with elections/election_deadlines/election_contests tables
- [ ] Tests pass

## Dependencies

Note from reference doc: Roll call extraction (`roll_call_extraction` item) is needed to populate `vote_results` in decisions, which enables voting record queries. Consider tackling that as a follow-up.

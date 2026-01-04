# Recommended: corpus_type_registry

**Priority:** P0
**Area:** data_architecture > vector_sql_linkage
**Date:** 2026-01-04

> This is recommended context from Session 467. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 467 completed `scheduled_data_tests` - the weekly CI workflow for slow/heavy tests. The test infrastructure is now complete with both main CI (push/PR) and scheduled data tests (weekly).

**Current state:**
- Main CI (`tests.yml`) runs smoke + full suite on push/PR (~15 min)
- Data tests (`data-tests.yml`) runs `@pytest.mark.slow` weekly (Sundays 6am UTC)
- 285 slow tests: load testing, e2e verification, rollback, extraction failures, seed ops

## Recommended Task

Create a CorpusType registry with metadata for each corpus type:

1. **Current state in `packages/civic/src/civic/rag/search.py`:**
   ```python
   CORPUS_TYPES = frozenset({"decision", "issue", "chunk", "transcript", "municipal_code", "meeting"})
   ```
   This is just a set of strings with no metadata.

2. **Goal: Add CorpusTypeRegistry with metadata:**
   ```python
   @dataclass
   class CorpusTypeInfo:
       name: str
       source_table: str | None  # SQL table name, e.g., "decisions"
       vector_collection: str  # pgvector collection name
       has_sql_source: bool  # True if backed by SQL table
       description: str
       icon: str | None = None  # For UI (optional)

   CORPUS_REGISTRY = {
       "decision": CorpusTypeInfo(
           name="decision",
           source_table="decisions",
           vector_collection="decisions",
           has_sql_source=True,
           description="City council decisions and votes"
       ),
       "issue": CorpusTypeInfo(...),
       # etc.
   }
   ```

3. **Benefits:**
   - ERD diagram can dynamically show which corpora have SQL backing
   - Unified search knows which corpora support SQL joins
   - Admin API can list all corpus types with metadata
   - Adding new corpus types is self-documenting

## Key Files

- `packages/civic/src/civic/rag/search.py:42` - Current CORPUS_TYPES frozenset
- `packages/civic/src/civic/rag/unified_search.py` - Uses CORPUS_TYPES
- `apps/civic-workspace/src/components/ERDDiagram.vue` - Renders corpus types
- `packages/civic/src/civic/storage/postgres_backend.py` - SQL tables for corpora

## Tests to Run

```bash
# Check current CORPUS_TYPES usage
grep -r "CORPUS_TYPES" packages/civic/src/

# Run RAG tests after changes
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] CorpusTypeInfo dataclass defined with metadata fields
- [ ] CORPUS_REGISTRY dict mapping corpus name to CorpusTypeInfo
- [ ] Backward-compatible: CORPUS_TYPES frozenset still works
- [ ] API endpoint to list corpus types (if time permits)
- [ ] Tests verify registry metadata is correct

## Dependencies

- No external dependencies
- Should be a self-contained refactor

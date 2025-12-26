# Session 368: Vector Rebuild from SQL (P0)

**Priority:** P0
**Area:** data_architecture > vector_sql_linkage
**Date:** 2025-12-26

> This is recommended context from Session 367. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 367 completed **chunks_from_sql**:
- Added `chunks` table to SQLiteBackend with temporal versioning
- Methods: `store_chunks()`, `get_chunks()`, `get_chunk_count()`
- Added `build_chunks_index_from_sql()` to CivicEmbeddings

## Current P0: vector_rebuild_from_sql

Make the INDEX stage of the ETL pipeline use SQL as the source of truth for all vector collections, not JSON files.

**Current state:**
- `build_chunks_index()` reads from JSON files
- `build_chunks_index_from_sql()` reads from SQL (new in Session 367)
- `build_decisions_index()` reads from JSON files
- Similar pattern for issues, transcripts

**Goal:**
- Pipeline INDEX stage should read from SQL (via storage backend)
- Vector collections derived from SQL = source of truth
- Enables accurate linkage_status tracking in ERD

## Key Files

- `packages/civic-extraction/src/civic_extraction/pipeline.py` - Pipeline class with INDEX stage
- `packages/civic/src/civic/_internal/meetings/embeddings.py:755-833` - `build_chunks_index_from_sql()` (pattern to follow)
- `packages/civic/src/civic/storage/sqlite_backend.py` - SQL methods for chunks, decisions, meetings

## Suggested Approach

1. **Add `_from_sql` variants for all index builders**
   - `build_decisions_index_from_sql()` - use `get_decisions()` from storage backend
   - `build_issues_index_from_sql()` - similar pattern
   - Transcripts may need different handling

2. **Update Pipeline.index_target**
   - IndexTarget protocol should pass storage_backend to embeddings
   - Or: embeddings should have storage_backend reference

3. **Update INDEX stage in Pipeline._run_index**
   - Call `_from_sql` variants instead of file-based variants
   - Log source as "sql" in stage metadata

4. **Preserve backward compatibility**
   - Keep file-based methods for corpus building/testing
   - Use SQL methods when storage_backend is available

## Success Criteria

- [ ] `build_decisions_index_from_sql()` implemented
- [ ] Pipeline INDEX stage uses SQL methods when storage_backend available
- [ ] Vector stats endpoint shows "sql" as source
- [ ] Existing file-based workflows still work

## Data Architecture Note

The 4-stage pattern is:
1. **DISCOVER** - Check what's available
2. **INGEST** - Fetch and normalize
3. **STORE** - Persist to SQL (source of truth)
4. **INDEX** - Build vectors from SQL (derived data)

This session completes the INDEX stage's SQL integration.

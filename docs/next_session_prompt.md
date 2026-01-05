# Recommended: automated_chunk_extraction

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-04

> This is recommended context from Session 469. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 469 completed the pipeline diagnosis. Key findings:
- Meeting "duplicates" were actually temporal versioning (not a bug)
- **Chunk extraction is NOT automated** - `civic-extract chunks --cloud` is not in `modal_ingest.py`
- Decision extraction is also manual (`batch_extract_decisions.py`)

This session should add chunk extraction to the Modal automated pipeline.

## Recommended Task

Add chunk extraction to `scheduled_high_velocity_refresh` in `scripts/modal_ingest.py`.

### Current Pipeline Flow
```
scheduled_high_velocity_refresh()  # Daily at 2 PM UTC
  ├── fetch_meetings()     → Scrapes meetings from ProudCity
  ├── fetch_issues()       → Scrapes issues from SeeClickFix
  └── index_vectors()      → Indexes meetings, issues to pgvector
```

### Target Pipeline Flow
```
scheduled_high_velocity_refresh()
  ├── fetch_meetings()
  ├── fetch_issues()
  ├── extract_chunks()     → NEW: Download PDFs, chunk, store
  └── index_vectors()      → Indexes all including new chunks
```

## Key Files

- `scripts/modal_ingest.py:764-832` - `scheduled_high_velocity_refresh()` function
- `packages/civic-extraction/src/civic_extraction/cli/chunks.py` - Chunk extraction CLI
- `packages/civic-extraction/src/civic_extraction/cli/chunks.py:897-916` - `store_chunks_to_cloud()`
- `packages/civic/src/civic/storage/postgres_backend.py:2159-2250` - `store_chunks()` method

## Suggested Approach

1. **Review existing chunk extraction CLI:**
   ```bash
   grep -n "def.*extract\|def.*store" packages/civic-extraction/src/civic_extraction/cli/chunks.py | head -20
   ```

2. **Create new Modal function `extract_chunks()`:**
   - Read meetings from Postgres (with agenda_url)
   - Download PDFs that haven't been chunked yet
   - Parse PDFs and extract chunks
   - Store chunks via `store_chunks()`

3. **Add to scheduled_high_velocity_refresh:**
   - Call after `fetch_meetings()`, before `index_vectors()`
   - Handle errors gracefully (chunk extraction failures shouldn't block other tasks)

4. **Test locally:**
   ```bash
   modal run scripts/modal_ingest.py::extract_chunks --dry-run
   ```

## Implementation Notes

- The CLI already has cloud support (`--cloud` flag reads from Postgres)
- May need to refactor CLI functions to be importable (not just CLI entry points)
- Consider incremental extraction (skip meetings already chunked)
- PDF parsing can be slow - may need timeout handling

## Tests to Run

```bash
# Targeted test for RAG/chunking
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v

# Full test suite before commit
pytest packages/civic/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] New `extract_chunks()` function in modal_ingest.py
- [ ] Function added to `scheduled_high_velocity_refresh()`
- [ ] Incremental extraction (skip already-chunked meetings)
- [ ] Error handling (failures don't crash pipeline)
- [ ] Local test passes with `--dry-run`
- [ ] pilot.json updated: `automated_chunk_extraction` → ready

## Scope Boundaries

**This session:** Implement chunk extraction automation only.

**Future P1 items (don't tackle yet):**
- `automated_decision_extraction` - Separate weekly schedule (minutes lag)
- `vector_sql_sync_verification` - Issues mismatch investigation

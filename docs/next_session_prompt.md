# Recommended: automated_incremental_pipeline

**Priority:** P0
**Area:** pipeline_automation > modal_remote_compute
**Date:** 2025-12-31

> This is recommended context from Session 422. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 422 fixed the Municode API content fetch issue (22% → 99.9% coverage). The fix is committed and ingestion is running in a separate process. The user emphasized the need for automated, incremental data ingestion to reduce operational burden as a solo developer preparing for pilot scaling.

## Why This Matters

Change velocity by corpus:
- **Low velocity** (monthly): Federal, State, Municipal law → scheduled full refresh is fine
- **High velocity** (weekly+): Meetings, Issues → **need incremental detection**

Without automation, every data refresh requires manual intervention. Critical for pilot success.

## Sub-Tasks

1. Add `modal.Cron` decorators for scheduled functions
2. Create `refresh_metadata` table (jurisdiction, corpus, last_fetch, last_hash)
3. Implement date-based incremental for meetings fetch
4. Implement date-based incremental for issues fetch
5. Add `--incremental` flag to `modal_ingest.py`
6. Deploy and validate with vector indexing

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_ingest.py` | Unified ingestion script - add cron + incremental logic here |
| `packages/civic/src/civic/storage/postgres_backend.py` | Add refresh_metadata table schema |
| `scripts/modal_vectors.py` | Vector indexing - validation after pipeline runs |

## Suggested Approach

1. **Start with refresh_metadata table** - Foundation for tracking
   ```sql
   CREATE TABLE refresh_metadata (
       id SERIAL PRIMARY KEY,
       jurisdiction_id TEXT NOT NULL,
       corpus_type TEXT NOT NULL,
       last_fetch TIMESTAMPTZ,
       last_hash TEXT,
       UNIQUE(jurisdiction_id, corpus_type)
   );
   ```

2. **Add Modal cron scheduling** - Low-velocity corpora first
   ```python
   @app.function(schedule=modal.Cron("0 3 * * 0"))  # Weekly Sunday 3am
   def scheduled_refresh():
       fetch_municipal_code.remote(...)
       fetch_legislation.remote(...)
       index_vectors.remote(...)
   ```

3. **Implement incremental for meetings/issues** - High-velocity corpora
   - Query `refresh_metadata` for last fetch timestamp
   - Fetch only records after that timestamp
   - Update `refresh_metadata` on success

4. **Validate with vector indexing** - Confirm pipeline works end-to-end

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# After implementation, test the pipeline
modal run scripts/modal_ingest.py --stats-only
modal run scripts/modal_ingest.py --municipal --vectors --dry-run
```

## Success Criteria

- [ ] `refresh_metadata` table exists and tracks fetch timestamps
- [ ] Modal cron scheduling deployed (`modal deploy scripts/modal_ingest.py`)
- [ ] Meetings fetch uses date filtering (only new meetings)
- [ ] Issues fetch uses date filtering (only new issues)
- [ ] Vector indexing runs automatically after data fetch
- [ ] `modal run scripts/modal_ingest.py --stats-only` shows current state

## Session 422 Stats

- Completed: `municipal_code_content_investigation` (22% → 99.9% coverage)
- Fix: Added `_find_chapter_nodes()` for recursive TOC traversal
- Municipal code ingestion running in separate process
- Pilot: 221/244 items (91%)

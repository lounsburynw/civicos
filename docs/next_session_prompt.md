# Recommended: seeclickfix_cloud_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 384. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 384 completed `vector_indexing_cloud` - created `vectors.py` CLI for indexing chunks/decisions into pgvector. The cloud ETL pipeline now has: meetings, chunks, decisions, transcripts, videos, audio, and vectors. The next step is storing SeeClickFix issues in Postgres.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | Done | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | Done | Agendas -> Decisions |
| 7 | `chunks_cloud_storage` | Done | PDF chunks -> Postgres |
| 8 | **`seeclickfix_cloud_storage`** | **P0** | Issues -> Postgres |
| 9 | `vector_indexing_cloud` | Done | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**SeeClickFix CLI exists but stores locally:**
- `seeclickfix.py` stores to local JSON checkpoint in `data/pilot/`
- 1,340 issues currently in local SQLite
- Uses SeeClickFix API to fetch operational issues (potholes, stormwater, etc.)

**PostgresBackend needs issues table:**
- No `store_issues()` or `get_issues()` methods exist yet
- Need to add issues table schema with temporal versioning (like other tables)

## Recommended Task

Add issues table to PostgresBackend and wire seeclickfix CLI:
1. Add `store_issues()` method to PostgresBackend (follow chunks pattern)
2. Add `get_issues()` method for retrieval
3. Add `--cloud` flag to seeclickfix.py CLI
4. Store issues in Postgres when DATABASE_URL set

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/seeclickfix.py` - Current CLI
- `packages/civic/src/civic/storage/postgres_backend.py:1225-1380` - Chunks pattern to follow
- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol

## Suggested Approach

1. **Add issues table schema** (similar to chunks):
   ```sql
   CREATE TABLE IF NOT EXISTS issues (
       id TEXT PRIMARY KEY,
       jurisdiction_id TEXT NOT NULL,
       external_id TEXT,              -- SeeClickFix issue ID
       title TEXT,
       description TEXT,
       status TEXT,                   -- open, closed, acknowledged
       category TEXT,                 -- pothole, graffiti, etc.
       location_lat REAL,
       location_lng REAL,
       address TEXT,
       created_at TIMESTAMP,
       updated_at TIMESTAMP,
       closed_at TIMESTAMP,
       reporter_name TEXT,
       valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       valid_to TIMESTAMP
   );
   ```

2. **Add PostgresBackend methods:**
   - `store_issues(jurisdiction_id, issues, as_of=None)` - with temporal versioning
   - `get_issues(jurisdiction_id, status=None, category=None, since=None)` - with filtering

3. **Update seeclickfix.py CLI:**
   - Add `--cloud` flag
   - Check `DATABASE_URL` for cloud mode
   - Call `backend.store_issues()` instead of local JSON

## Tests to Run

```bash
# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v

# Smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] issues table created in PostgresBackend
- [ ] store_issues() and get_issues() methods implemented
- [ ] seeclickfix.py supports --cloud flag
- [ ] Issues stored in Postgres when DATABASE_URL set
- [ ] Existing tests pass

## Why This Next?

- Bridges 311 operations to policy engagement (core Civic value prop)
- Completes the cloud data types (meetings + issues = full picture)
- 1,340 existing issues ready to migrate
- Last data type before e2e_fresh_ingestion verification

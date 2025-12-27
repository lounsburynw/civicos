# Recommended: youtube_cloud_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 378. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 378 completed `r2_source_caching` (SourceCache class for caching HTTP responses). The next item is `youtube_cloud_storage` - wire youtube.py CLI to store video metadata in Postgres instead of local JSON.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | ✅ Done | Meetings → Postgres |
| 2 | `r2_source_caching` | ✅ Done | Cache HTML/PDFs in R2 |
| 3 | **`youtube_cloud_storage`** | **P0** | Video metadata → Postgres |
| 4 | `audio_cloud_storage` | P1 | Audio files → R2 |
| 5 | `assemblyai_transcript_storage` | P1 | Transcripts → Postgres |
| 6 | `decision_extraction_pipeline` | P1 | Minutes PDF → Decisions |
| 7 | `chunks_cloud_storage` | P1 | PDF chunks → Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues → Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data → pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**youtube.py CLI** (`packages/civic-extraction/src/civic_extraction/cli/youtube.py`):
- Scrapes meeting pages for YouTube video IDs
- Stores results to local JSON: `data/{jurisdiction}_videos.json`
- Uses `VideoResult` dataclass: video_id, meeting_url, title, date, youtube_url
- Uses `YouTubeCheckpoint` for progress tracking

**PostgresBackend** already has:
- `meetings` table with `video_url` column
- No dedicated `videos` table yet

## Recommended Task

Wire youtube.py to store video metadata in Postgres:

1. **Add `videos` table to PostgresBackend**:
   ```python
   # In _ensure_tables()
   CREATE TABLE IF NOT EXISTS videos (
       id TEXT PRIMARY KEY,  -- video_id
       jurisdiction_id TEXT NOT NULL,
       meeting_url TEXT,
       title TEXT,
       date TEXT,
       youtube_url TEXT,
       discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       metadata JSONB DEFAULT '{}'
   )
   ```

2. **Add storage methods**:
   ```python
   def store_videos(self, jurisdiction_id: str, videos: List[Dict]) -> int:
       """Store video records, upsert on video_id."""

   def get_videos(self, jurisdiction_id: str, limit: int = 100) -> List[Dict]:
       """Get videos for jurisdiction."""
   ```

3. **Update youtube.py CLI**:
   - Import `get_storage_backend`
   - Replace JSON file operations with `storage.store_videos()`
   - Add `--cloud` flag (or auto-detect from DATABASE_URL)
   - Keep JSON fallback for local development

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/youtube.py` - CLI to update
- `packages/civic/src/civic/storage/postgres_backend.py` - Add videos table/methods
- `packages/civic/src/civic/storage/backend.py` - Add protocol methods if needed

## Tests to Run

```bash
# Storage protocol tests (add video tests)
pytest packages/civic/tests/test_storage_protocols.py -v -k video

# YouTube CLI tests (if any exist)
pytest packages/civic-extraction/tests/ -v -k youtube

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `videos` table created in PostgresBackend
- [ ] `store_videos()` and `get_videos()` methods work
- [ ] youtube.py CLI uses `get_storage_backend()` when DATABASE_URL set
- [ ] Video discovery writes to Supabase in cloud mode
- [ ] Local JSON fallback still works
- [ ] Existing tests pass

## Why This Next?

Continuing the cloud storage integration path:
- Videos are discovered from meeting pages (already scraped)
- Audio extraction (`audio_cloud_storage`) depends on video metadata
- Transcription (`assemblyai_transcript_storage`) depends on audio
- This unblocks the audio → transcribe pipeline

# Recommended: audio_cloud_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 379. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 379 completed `youtube_cloud_storage` (videos table + store_videos/get_videos methods in PostgresBackend, youtube.py CLI wired to cloud). The next item is `audio_cloud_storage` - wire audio.py CLI to store audio files in R2 with metadata in Postgres.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | **`audio_cloud_storage`** | **P0** | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | P1 | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | P1 | Minutes PDF -> Decisions |
| 7 | `chunks_cloud_storage` | P1 | PDF chunks -> Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues -> Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**audio.py CLI** (`packages/civic-extraction/src/civic_extraction/cli/audio.py`):
- Downloads audio from YouTube videos using yt-dlp
- Stores to local files: `data/youtube_audio/{video_id}.mp3`
- Uses `DownloadResult` dataclass: video_id, status, file_path, file_size_mb, duration_minutes
- Uses `AudioCheckpoint` for progress tracking
- Reads video list from local JSON (now also available from Postgres via `get_videos()`)

**R2Backend** (`packages/civic/src/civic/storage/r2_backend.py`):
- Already implemented with upload(), download(), exists(), delete(), list_keys()
- Used by SourceCache for HTTP response caching
- Ready for audio file storage

## Recommended Task

Wire audio.py to store audio files in R2:

1. **Add `--cloud` flag to audio.py CLI** (like youtube.py):
   ```python
   parser.add_argument(
       "--cloud",
       action="store_true",
       help="Store audio in cloud storage (requires BLOB_STORAGE_URL)",
   )
   ```

2. **Update download logic to use R2**:
   ```python
   if cloud or os.environ.get("BLOB_STORAGE_URL"):
       from civic.storage import get_blob_storage
       blob = get_blob_storage()
       # Upload to R2: audio/{jurisdiction_id}/{video_id}.mp3
       key = f"audio/{jurisdiction_id}/{video_id}.mp3"
       blob.upload(key, audio_bytes, content_type="audio/mpeg")
   ```

3. **Optional: Add audio metadata table to Postgres**:
   - Could track: video_id, jurisdiction_id, r2_key, file_size, duration, downloaded_at
   - Or just use R2 key convention and list_keys() for discovery

4. **Read videos from cloud if available**:
   - Use `get_storage_backend().get_videos()` instead of local JSON when DATABASE_URL set

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/audio.py` - CLI to update
- `packages/civic/src/civic/storage/r2_backend.py` - R2 upload/download (already implemented)
- `packages/civic/src/civic/storage/postgres_backend.py:1352-1513` - Video methods pattern to follow

## Pattern from youtube.py (Session 379)

```python
# Try cloud storage first if enabled
if cloud or os.environ.get("BLOB_STORAGE_URL"):
    try:
        from civic.storage import get_blob_storage
        blob = get_blob_storage()
        key = f"audio/{jurisdiction_id}/{video_id}.mp3"
        blob.upload(key, audio_data, content_type="audio/mpeg")
        logger.info(f"Uploaded {key} to cloud storage")
    except ImportError:
        logger.warning("civic.storage not available, using local fallback")
    except Exception as e:
        logger.warning(f"Cloud storage failed: {e}, using local fallback")
```

## Tests to Run

```bash
# R2 backend tests (verify upload/download works)
pytest packages/civic/tests/test_storage_protocols.py -v -k r2

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `--cloud` flag added to audio.py CLI
- [ ] Audio files upload to R2 when BLOB_STORAGE_URL set
- [ ] R2 key convention: `audio/{jurisdiction_id}/{video_id}.mp3`
- [ ] Local file fallback still works
- [ ] Reads videos from Postgres when DATABASE_URL set (optional enhancement)
- [ ] Existing tests pass

## Why This Next?

Continuing the cloud storage integration path:
- Audio files are large (50-200MB each) - R2 is ideal for blob storage
- Transcription (`assemblyai_transcript_storage`) depends on audio being accessible
- Having audio in R2 enables serverless transcription workflows
- Follows same pattern established in youtube.py (Session 379)

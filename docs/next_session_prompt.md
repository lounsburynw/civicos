# Recommended: assemblyai_transcript_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 380. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 380 completed `audio_cloud_storage` (audio.py CLI now uploads audio files to R2, reads videos from Postgres). The next item is `assemblyai_transcript_storage` - store AssemblyAI transcripts in Postgres with R2 audio backup.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | **`assemblyai_transcript_storage`** | **P0** | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | P1 | Minutes PDF -> Decisions |
| 7 | `chunks_cloud_storage` | P1 | PDF chunks -> Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues -> Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**transcribe.py CLI** (`packages/civic-extraction/src/civic_extraction/cli/transcribe.py`):
- Transcribes audio files using AssemblyAI
- Stores transcripts to local JSON files
- Uses `TranscriptionResult` dataclass
- Tracks progress with checkpoints

**Audio is now in R2:**
- Key convention: `audio/{jurisdiction_id}/{video_id}.mp3`
- audio.py with `--cloud` flag uploads to R2

## Recommended Task

Wire transcribe.py to store transcripts in Postgres and read audio from R2:

1. **Add transcripts table to PostgresBackend**:
   ```python
   # Similar pattern to videos table
   def store_transcripts(self, jurisdiction_id: str, transcripts: List[dict]) -> int:
       """Store transcripts with upsert semantics."""

   def get_transcripts(self, jurisdiction_id: str) -> List[dict]:
       """Get all transcripts for jurisdiction."""

   def get_transcript(self, video_id: str) -> Optional[dict]:
       """Get specific transcript by video_id."""
   ```

2. **Add `--cloud` flag to transcribe.py CLI**:
   ```python
   parser.add_argument(
       "--cloud",
       action="store_true",
       help="Store transcripts in cloud storage (requires DATABASE_URL)",
   )
   ```

3. **Update transcription logic**:
   - Read audio from R2 when `--cloud` enabled
   - Store transcript JSON in Postgres after successful transcription
   - Keep local file fallback

4. **Table schema suggestion**:
   ```sql
   CREATE TABLE transcripts (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       jurisdiction_id TEXT NOT NULL,
       video_id TEXT NOT NULL UNIQUE,
       transcript JSONB NOT NULL,  -- Full AssemblyAI response
       text TEXT,  -- Plain text for search
       duration_seconds INTEGER,
       word_count INTEGER,
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
   );
   ```

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - CLI to update
- `packages/civic/src/civic/storage/postgres_backend.py:1352-1513` - Videos pattern to follow
- `packages/civic/src/civic/storage/blob.py` - R2 download for audio

## Pattern from audio.py (Session 380)

```python
# Read audio from R2 when cloud enabled
if cloud or os.environ.get("BLOB_STORAGE_URL"):
    try:
        from civic.storage import get_blob_storage
        blob = get_blob_storage()
        r2_key = f"audio/{jurisdiction_id}/{video_id}.mp3"
        audio_data = blob.download(r2_key)
        # Use audio_data for transcription...
    except Exception as e:
        logger.warning(f"Cloud read failed: {e}, using local fallback")
```

## Tests to Run

```bash
# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `transcripts` table added to PostgresBackend
- [ ] `store_transcripts()`, `get_transcripts()`, `get_transcript()` methods
- [ ] `--cloud` flag added to transcribe.py CLI
- [ ] Transcripts stored in Postgres when DATABASE_URL set
- [ ] Audio read from R2 when BLOB_STORAGE_URL set
- [ ] Local file fallback still works
- [ ] Existing tests pass

## Why This Next?

Continuing the cloud storage integration path:
- Transcripts are needed for decision extraction and semantic search
- Having transcripts in Postgres enables SQL queries and full-text search
- Audio in R2 + transcripts in Postgres = complete meeting content in cloud
- This is the 5th of 10 items in the E2E cloud ETL roadmap

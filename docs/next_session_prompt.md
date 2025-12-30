# Session 410 Context

**Priority:** Fix StorageBackend protocol gaps
**Date:** 2025-12-30

## Session 409 Completed

1. **Content hashing for data integrity** - Created `integrity.py` with SHA-256 hashing
2. **PostgresBackend updates** - `store_transcripts()`, `store_chunks()`, `store_decisions()` now compute content_hash
3. **32 new tests** for integrity module
4. **Pilot progress** - 209/230 items ready (90%)

## Urgent: StorageBackend Protocol Fix

The protocol critic identified gaps between `StorageBackend` protocol and implementations:

### Issue 1: `store_chunks()` signature mismatch
**File:** `packages/civic/src/civic/storage/backend.py` (line 396-415)
- Protocol: `store_chunks(jurisdiction_id, chunks, as_of=None)`
- PostgresBackend: `store_chunks(jurisdiction_id, chunks, as_of=None, meeting_id=None)`
- **Fix:** Add `meeting_id: Optional[str] = None` to protocol

### Issue 2: Transcript methods missing from protocol
**File:** `packages/civic/src/civic/storage/backend.py`
- PostgresBackend has: `store_transcripts()`, `get_transcripts()`, `get_transcript()`, `get_transcript_count()`
- Protocol has: NONE
- `corpus_types.py` references `get_transcripts` - so protocol needs these
- **Fix:** Add transcript methods section to protocol (similar to Chunks/Decisions sections)

### Issue 3: Video methods missing from protocol
- PostgresBackend has: `store_videos()`, `get_videos()`, `get_video_count()`
- Protocol has: NONE
- Videos are source data for transcripts
- **Fix:** Add video methods section to protocol

### Implementation Steps

1. Read `packages/civic/src/civic/storage/backend.py` (the protocol)
2. Read PostgresBackend methods for transcripts (lines 1949-2165) and videos (lines 1786-1924)
3. Add to protocol:
   - `meeting_id` param to `store_chunks()`
   - Video methods section (store_videos, get_videos, get_video_count)
   - Transcript methods section (store_transcripts, get_transcripts, get_transcript, get_transcript_count)
4. Update SQLiteBackend with stubs if needed (or raise NotImplementedError)
5. Run protocol tests: `pytest packages/civic/tests/test_storage_protocols.py -v`

## After Protocol Fix

**P0:** `cost_dashboard` - Admin dashboard showing cumulative ETL costs

## Transcript Status

We have transcript infrastructure but NO transcript data yet:
- `transcribe.py` CLI exists but hasn't been run
- No videos discovered/transcribed for San Rafael yet
- This is a future pipeline run, not blocking

## Key Files

- `packages/civic/src/civic/storage/backend.py` - Protocol definition
- `packages/civic/src/civic/storage/postgres_backend.py` - Reference implementation
- `packages/civic/src/civic/storage/sqlite_backend.py` - Dev implementation (needs stubs)
- `packages/civic/tests/test_storage_protocols.py` - Protocol tests

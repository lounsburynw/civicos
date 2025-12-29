# Recommended: transcripts_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 394. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 394 completed chunks_extraction_reliability by adding timeout protection to PDF parsing. The chunks pipeline now completes in ~2 minutes (was 2+ hours). 34/46 meetings have chunks in cloud. The next step is transcripts - currently 0 transcripts in cloud storage.

## Current Cloud Data Status

| Data Type | Cloud Count | Status |
|-----------|-------------|--------|
| Meetings | 46 | ready |
| Issues | 1,330 | ready |
| Agenda Items | 44 | ready |
| Decisions | 44 | ready |
| Chunks | ~4,800 (34/46 meetings) | ready |
| **Transcripts** | **0** | **not_ready** |

## Recommended Task

Run the transcript extraction pipeline using AssemblyAI to populate cloud storage with meeting transcripts. Audio files are in R2 blob storage.

**Cost Warning:** AssemblyAI costs $0.02/minute (~$2.40 per 2-hour meeting). Check how many audio files exist before running full extraction.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - Transcript CLI
- `packages/civic/src/civic/storage/postgres_backend.py` - store_transcripts()

## Suggested Approach

1. **Check audio file count and estimate cost:**
```bash
source civic-env/bin/activate
civic-extract transcribe --jurisdiction city-san-rafael --cloud --dry-run
```

2. **Run small batch first to verify pipeline:**
```bash
civic-extract transcribe --jurisdiction city-san-rafael --cloud --limit 3
```

3. **If pipeline works, run full extraction:**
```bash
civic-extract transcribe --jurisdiction city-san-rafael --cloud
```

## Environment Requirements

- `ASSEMBLYAI_API_KEY` - Required for transcription
- `DATABASE_URL` - For cloud storage
- `R2_*` credentials - For audio file access

## Success Criteria

- [ ] Dry-run shows audio files available in R2
- [ ] Small batch (3 videos) transcribes successfully
- [ ] Transcripts stored in cloud (verify with SQL count)
- [ ] Cost is reasonable (<$50 for pilot data)

## Notes

- Audio is stored in R2 blob storage (DO NOT use local files)
- The transcribe CLI has `--cloud` flag similar to chunks
- Consider timeout handling if large audio files cause issues (apply same pattern as chunks)
- Check if ASSEMBLYAI_API_KEY is set before running

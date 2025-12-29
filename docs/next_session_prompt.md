# Recommended: transcripts_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 396. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 396 completed `audio_e2e_cloud` - all 19 audio files are now in R2 blob storage. This unblocks `transcripts_e2e_cloud`, which can now run.

Also fixed a critical bug: the civic-extraction CLI was not loading `.env` for R2 credentials. Added `load_dotenv()` to `packages/civic-extraction/src/civic_extraction/cli/__init__.py`.

## Current Data Status

| Data Type | Cloud Count | Status |
|-----------|-------------|--------|
| Audio files | **19/19** | **ready** |
| Transcripts | 1/19 | **not_ready** (P0) |

## Recommended Task

Run transcription for all 19 meeting audio files via AssemblyAI to Postgres.

**Cost Warning:** Transcription costs ~$2.40 per video. Total: ~$46 for remaining 18 videos.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - Transcription CLI
- `packages/civic-extraction/src/civic_extraction/cli/__init__.py:74-79` - Fixed dotenv loading
- R2 path: `audio/city-san-rafael/*.mp3` (19 files)

## Suggested Approach

1. **Dry-run to verify:**
```bash
source civic-env/bin/activate
civic-extract transcribe --jurisdiction city-san-rafael --cloud --dry-run
```

2. **Run transcription (background recommended - takes 2-3 hours):**
```bash
civic-extract transcribe --jurisdiction city-san-rafael --cloud
```

3. **Verify transcripts in Postgres:**
```sql
SELECT COUNT(*) FROM transcripts WHERE jurisdiction_id = 'city-san-rafael';
-- Should return 19
```

## Success Criteria

- [ ] All 19 transcripts in Postgres
- [ ] Mark `transcripts_e2e_cloud` as ready
- [ ] Set next P0 (likely `decisions_e2e_cloud` or `municipal_code_e2e_cloud`)

## Notes

- AssemblyAI API key is in `.env` (ASSEMBLYAI_API_KEY)
- Transcription is rate-limited by AssemblyAI's queue
- Session 395 fixed `find_audio_files()` to detect R2 audio directly
- Run during off-peak hours if possible to minimize queue time

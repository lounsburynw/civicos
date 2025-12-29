# Recommended: audio_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 395. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 395 discovered that audio files were NOT in R2 (handoff from Session 394 was incorrect). Fixed `transcribe.py` to detect R2 audio directly. Validated the full pipeline by downloading 3 audio files to R2 and transcribing 1 meeting successfully. The next step is uploading the remaining 14 audio files to R2, then running full transcription.

## Current Data Status

| Data Type | Cloud Count | Status |
|-----------|-------------|--------|
| Audio files | **3/19** | **not_ready** |
| Transcripts | 1/19 | blocked on audio |

## Recommended Task

Upload remaining 14 audio files from YouTube to R2 blob storage. This unblocks `transcripts_e2e_cloud`.

**Time Warning:** Audio download takes ~3 min per video. 14 videos = ~45 minutes.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/audio.py` - Audio download CLI
- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py:221-270` - Fixed find_audio_files()
- `data/city_san_rafael_videos.json` - Source video list (19 videos)

## Prerequisites

- YouTube cookies at `~/Downloads/www.youtube.com_cookies.txt` (required for downloads)
- Verify cookies exist before running

## Suggested Approach

1. **Verify cookies and dry-run:**
```bash
source civic-env/bin/activate
ls -la ~/Downloads/www.youtube.com_cookies.txt
civic-extract audio --jurisdiction city-san-rafael --cloud --dry-run
```

2. **Run full audio download (background recommended):**
```bash
civic-extract audio --jurisdiction city-san-rafael --cloud
```
This will resume from checkpoint (already have 3/19).

3. **Verify audio in R2:**
```bash
python3 -c "
from civic.storage import get_blob_storage
blob = get_blob_storage()
print(len(blob.list_keys('audio/city-san-rafael/')), 'audio files in R2')
"
```

4. **Once audio complete, run transcription (P1 next):**
```bash
civic-extract transcribe --jurisdiction city-san-rafael --cloud --dry-run
civic-extract transcribe --jurisdiction city-san-rafael --cloud
```
Estimated cost: ~$46 total (19 videos × ~$2.40 avg)

## Success Criteria

- [ ] All 19 audio files in R2
- [ ] Mark `audio_e2e_cloud` as ready
- [ ] Set `transcripts_e2e_cloud` as next P0

## Notes

- Session 395 fixed transcribe.py to detect R2 audio directly (line 250-264)
- Audio downloads can be rate-limited by YouTube - run during off-peak if issues
- Checkpoint file tracks progress: `data/checkpoints/audio_city-san-rafael.json`

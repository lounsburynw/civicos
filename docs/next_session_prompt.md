# Recommended: fix_corrupted_city_council_transcripts

**Priority:** P0
**Area:** data_integrity > source_provenance
**Date:** 2026-01-10

> This is recommended context from Session 499. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 499 added automated transcript ingestion to the Modal pipeline (`extract_transcripts()` in `scripts/modal_ingest.py`). The pipeline now runs: meetings -> issues -> transcripts -> chunks -> vectors. However, 9 of 19 existing city-san-rafael transcripts have corrupted audio from a playlist concatenation bug. These need to be fixed before the automated pipeline will produce valid data.

## Recommended Task

Re-download and re-transcribe 9 corrupted city council meeting transcripts. The audio files were originally downloaded from YouTube playlists instead of individual videos, causing concatenation/corruption.

**Corrupted video IDs:**
- IdgRa0uEywo, 1u4NX88tsCI, nSCoylgGf9M, k5ZUhxHn5pE, iYeihDimgxE
- dnzo2fEXiO0, ZP7fkN8cBK4, SFsaaL51urs, QLDoO6OvMSA

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py:2770-2850` - `store_transcripts()` and transcript storage
- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py:486-768` - Transcription with AssemblyAI
- `packages/civic-extraction/src/civic_extraction/cli/audio.py:241-375` - Audio download from YouTube
- `scripts/modal_ingest.py:1127-1279` - New `extract_transcripts()` Modal function

## Suggested Approach

1. **Soft-delete invalid transcripts** - Use `PostgresBackend.soft_delete()` on the 9 corrupted video IDs
2. **Delete corrupted audio from R2** - Remove the concatenated audio files from blob storage
3. **Re-download audio** - Use `civic-extract audio --jurisdiction city-san-rafael --cloud` to download individual videos (not playlists)
4. **Re-transcribe** - Use `civic-extract transcribe --jurisdiction city-san-rafael --cloud` (~$20 AssemblyAI cost for 9 meetings)
5. **Validate** - Run `civic-extract validate-transcripts --jurisdiction city-san-rafael` to confirm duration matches YouTube

## Tests to Run

```bash
# Validate transcripts after fix
civic-extract validate-transcripts --jurisdiction city-san-rafael

# Verify transcript count
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic.storage import get_storage_backend
b = get_storage_backend()
t = b.get_transcripts('city-san-rafael')
valid = [x for x in t if x.get('duration_valid') is True]
print(f'Valid transcripts: {len(valid)}/{len(t)}')
"
```

## Success Criteria

- [ ] 9 corrupted transcripts soft-deleted
- [ ] 9 audio files re-downloaded (single video, not playlist)
- [ ] 9 transcripts re-created with AssemblyAI
- [ ] All 19 city-san-rafael transcripts pass duration validation
- [ ] pilot.json status updated to "ready"

## Cost Estimate

- AssemblyAI: ~$0.02/minute x ~120 min x 9 meetings = ~$20

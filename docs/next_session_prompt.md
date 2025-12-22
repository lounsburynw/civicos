# Recommended: Transcription Cron

**Priority:** P0 (IMMEDIATE)
**Area:** pipeline_automation > scheduling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 323 completed `audio_download_cron` as `civic-extract audio` CLI. The pipeline automation sequence continues (discover -> youtube -> audio -> transcribe). Audio files are now being downloaded to `data/youtube_audio/`. Next is transcription.

## Recommended Task

Add `civic-extract transcribe` command to transcribe audio files using Modal's GPU infrastructure (WhisperX + PyAnnote diarization).

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/audio.py` - **Pattern to follow**
- `scripts/modal_process_audio.py` - **Existing Modal transcription logic** (core processing)
- `data/youtube_audio/` - Input audio files (from audio command)
- `data/testimony/` - Output transcripts (JSON format)

## What Needs to Happen

1. **Create transcribe.py CLI module** - `packages/civic-extraction/src/civic_extraction/cli/transcribe.py`:
   - Follow audio.py pattern for CLI structure
   - Wrap `scripts/modal_process_audio.py` logic as CLI command
   - Read audio files from `data/youtube_audio/{video_id}.mp3`
   - Output transcripts to `data/transcripts/{video_id}.json`
   - Skip already-transcribed files
   - Checkpoint save/resume
   - Support --dry-run, --limit, --schedule flags

2. **Register in CLI** - Update `cli/__init__.py` to add transcribe subcommand

3. **Handle Modal setup** - The command should:
   - Check Modal is installed and authenticated
   - Provide helpful error message if not configured
   - Support --skip-diarization flag for faster testing

## Existing Modal Infrastructure

From `scripts/modal_process_audio.py`:
- Uses Modal A10G GPU ($0.22/12min meeting)
- WhisperX large-v3 for transcription
- PyAnnote speaker diarization
- Parallel processing support (up to 10 GPUs)
- Requires HuggingFace token for diarization model

## Suggested Approach

1. Read `scripts/modal_process_audio.py` to understand Modal setup
2. Create `cli/transcribe.py` wrapping that logic
3. Read audio files from `data/youtube_audio/`
4. Output to `data/transcripts/` (or testimony as in existing script)
5. Register in `cli/__init__.py`
6. Test with --dry-run first, then single file

## Tests to Run
```bash
# After creating the command
civic-extract transcribe --help
civic-extract transcribe --jurisdiction city-san-rafael --dry-run
civic-extract transcribe --jurisdiction city-san-rafael --limit 1
```

## Success Criteria
- [ ] `civic-extract transcribe` command works
- [ ] Reads audio from `data/youtube_audio/`
- [ ] Uses Modal for GPU transcription
- [ ] Supports --schedule, --dry-run, --limit flags
- [ ] Skips already-transcribed files
- [ ] Checkpoint save/resume works
- [ ] pilot.json updated to mark transcription_cron as ready

## Notes

- Modal requires setup: `pip install modal && modal token new`
- HuggingFace token needed for diarization: `modal secret create huggingface HF_TOKEN=...`
- Can use --skip-diarization for testing without HF token
- Cost estimate: ~$0.22 per 12-minute meeting

## Pilot Progress

- 123/161 items ready (76%)
- 38 items remaining

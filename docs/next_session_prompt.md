# Recommended: Audio Download Cron

**Priority:** P0 (IMMEDIATE)
**Area:** pipeline_automation > scheduling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 322 completed `youtube_discovery_cron` as `civic-extract youtube` CLI command. The pattern continues as package CLI (discover -> youtube -> audio). Next is audio download from discovered YouTube videos.

## Recommended Task

Add `civic-extract audio` command to download audio from YouTube videos discovered by the `youtube` command.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/__init__.py` - CLI entry point (add audio subcommand)
- `packages/civic-extraction/src/civic_extraction/cli/youtube.py` - **Pattern to follow**
- `packages/civic-extraction/src/civic_extraction/cli/discover.py` - **Also a pattern**
- `scripts/download_youtube_audio.py` - **Existing audio download logic**

## What Needs to Happen

1. **Create audio.py CLI module** - `packages/civic-extraction/src/civic_extraction/cli/audio.py`:
   - Follow youtube.py and discover.py patterns
   - Read from `data/{jurisdiction}_videos.json` (output of youtube command)
   - Use yt-dlp to download audio (see scripts/download_youtube_audio.py)
   - Skip already-downloaded files
   - Checkpoint save/resume
   - Output to `data/youtube_audio/{video_id}.mp3`

2. **Register in CLI** - Update `cli/__init__.py` to add audio subcommand

3. **Handle cookies** - YouTube requires cookies for some downloads
   - Support --cookies flag (default: `~/Downloads/www.youtube.com_cookies.txt`)
   - Warn if cookies file not found

4. **Test** - `civic-extract audio --jurisdiction city-san-rafael --dry-run`

## Suggested Approach

1. Read `scripts/download_youtube_audio.py` for existing yt-dlp usage
2. Create `cli/audio.py` following youtube.py pattern
3. Read videos from `data/{jurisdiction}_videos.json`
4. Register in `cli/__init__.py`
5. Reinstall package: `pip install -e packages/civic-extraction/`
6. Test with --dry-run first

## Tests to Run
```bash
# After creating the command
civic-extract audio --help
civic-extract audio --jurisdiction city-san-rafael --dry-run
civic-extract audio --jurisdiction city-san-rafael --limit 1  # Download just 1 video for testing
```

## Success Criteria
- [ ] `civic-extract audio` command works
- [ ] Reads from `{jurisdiction}_videos.json`
- [ ] Supports --schedule, --dry-run, --cookies, --jurisdiction flags
- [ ] Skips already-downloaded files
- [ ] Checkpoint save/resume works
- [ ] pilot.json updated to mark audio_download_cron as ready

## Related Pipeline Automation Items

After audio_download_cron:
- `transcription_cron` (P2) - `civic-extract transcribe` command
- `seeclickfix_cron` (P2) - `civic-extract seeclickfix` command

## Pilot Progress

- 122/161 items ready (76%)
- 39 items remaining

# Recommended: YouTube Discovery Cron

**Priority:** P0 (IMMEDIATE)
**Area:** pipeline_automation > scheduling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 321 completed `meeting_discovery_cron` - the first pipeline automation cron job. The pattern is now established. Next is YouTube video discovery to find recordings of meetings.

## Recommended Task

Create a cron job that discovers YouTube videos for San Rafael meetings, similar to meeting_discovery_cron.py.

## Key Files

- `scripts/meeting_discovery_cron.py` - **Pattern to follow** - one-time and --schedule modes, checkpoint support, logging
- `packages/civic-extraction/src/civic_extraction/clients/youtube.py` - YouTube client (if exists)
- `packages/civic-extraction/src/civic_extraction/sources/` - Data source implementations
- `data/extraction/san-rafael.json` - Jurisdiction config

## What Needs to Happen

1. **Investigate YouTube extraction** - Find or create YouTube discovery client
   - Search for existing YouTube-related code in civic-extraction
   - Understand how videos are linked to meetings

2. **Create cron script** - `scripts/youtube_discovery_cron.py` following the pattern:
   - One-time and scheduled (--schedule) modes
   - Checkpoint save/resume capability
   - Dry-run validation mode
   - Structured logging

3. **Test with san-rafael** - Run discovery and verify output

## Suggested Approach

1. Grep for "youtube" in packages/civic-extraction to find existing code
2. Check if there's a YouTubeSource or similar client
3. Create youtube_discovery_cron.py mirroring meeting_discovery_cron.py
4. Test with --dry-run first, then full run

## Tests to Run
```bash
# After creating the script
python scripts/youtube_discovery_cron.py --jurisdiction city-san-rafael --dry-run
```

## Success Criteria
- [ ] Script created at scripts/youtube_discovery_cron.py
- [ ] Supports --schedule, --dry-run, --jurisdiction flags
- [ ] Checkpoint save/resume works
- [ ] Successfully discovers YouTube videos for san-rafael
- [ ] pilot.json updated to mark youtube_discovery_cron as ready

## Related Pipeline Automation Items

After youtube_discovery_cron:
- `audio_download_cron` (P2) - Download audio from YouTube
- `transcription_cron` (P2) - Batch transcription via AssemblyAI
- `seeclickfix_cron` (P2) - Refresh SeeClickFix data

## Pilot Progress

- 122/161 items ready (76%)
- 39 items remaining

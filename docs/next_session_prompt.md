# Recommended: YouTube Discovery Cron

**Priority:** P0 (IMMEDIATE)
**Area:** pipeline_automation > scheduling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 321 completed `meeting_discovery_cron` as `civic-extract discover` CLI command. The pattern is established as a package CLI, not standalone scripts. Next is YouTube video discovery.

## Recommended Task

Add `civic-extract youtube` command to discover YouTube videos for meetings.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/__init__.py` - CLI entry point (add youtube subcommand)
- `packages/civic-extraction/src/civic_extraction/cli/discover.py` - **Pattern to follow**
- `packages/civic-extraction/pyproject.toml` - Entry point defined here

## What Needs to Happen

1. **Investigate YouTube extraction** - Find or create YouTube discovery client
   - Grep for "youtube" in packages/civic-extraction
   - Check how videos are linked to meetings

2. **Create youtube.py CLI module** - `packages/civic-extraction/src/civic_extraction/cli/youtube.py`:
   - Follow discover.py pattern
   - One-time and --schedule modes
   - Checkpoint save/resume
   - Dry-run validation

3. **Register in CLI** - Update `cli/__init__.py` to add youtube subcommand

4. **Test** - `civic-extract youtube --jurisdiction city-san-rafael --dry-run`

## Suggested Approach

1. Grep for "youtube" in packages/civic-extraction to find existing code
2. Create `cli/youtube.py` following `cli/discover.py` pattern
3. Register in `cli/__init__.py`
4. Reinstall package: `pip install -e packages/civic-extraction/`
5. Test with --dry-run first, then full run

## Tests to Run
```bash
# After creating the command
civic-extract youtube --help
civic-extract youtube --jurisdiction city-san-rafael --dry-run
```

## Success Criteria
- [ ] `civic-extract youtube` command works
- [ ] Supports --schedule, --dry-run, --jurisdiction flags
- [ ] Checkpoint save/resume works
- [ ] Successfully discovers YouTube videos for san-rafael
- [ ] pilot.json updated to mark youtube_discovery_cron as ready

## Related Pipeline Automation Items

After youtube_discovery_cron:
- `audio_download_cron` (P2) - `civic-extract audio` command
- `transcription_cron` (P2) - `civic-extract transcribe` command
- `seeclickfix_cron` (P2) - `civic-extract seeclickfix` command

## Pilot Progress

- 122/161 items ready (76%)
- 39 items remaining

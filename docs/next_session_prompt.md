# Recommended: Meeting Discovery Cron

**Priority:** P0 (IMMEDIATE)
**Area:** pipeline_automation > scheduling
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 320 completed the codebase critics infrastructure. The P0 now moves to pipeline automation - specifically setting up cron jobs for automated data refresh.

## Recommended Task

Create a cron job that runs meeting discovery daily at 6am for San Rafael.

## Key Files

- `packages/civic-extraction/src/civic_extraction/pipeline.py` - Pipeline class with discover/ingest/store/index stages
- `packages/civic-extraction/src/civic_extraction/sources/` - Data sources (Legistar, CivicClerk, Granicus)
- `scripts/` - Existing scripts to reference for patterns

## What Needs to Happen

1. **Cron script** - Python script that:
   - Initializes Pipeline for san-rafael
   - Runs discover stage (find new meetings)
   - Runs ingest stage (fetch meeting details)
   - Stores to SQLite via StorageBackend
   - Indexes for RAG via VectorBackend

2. **Scheduling** - Either:
   - System crontab entry (simple)
   - Or lightweight scheduler in Python (more portable)

3. **Logging/monitoring** - Basic output for debugging:
   - Meetings discovered count
   - Meetings ingested count
   - Any errors encountered

## Related Items

After this, the next pipeline automation items are:
- `youtube_discovery_cron` - Discover YouTube recordings
- `transcript_processing_cron` - Process transcripts via AssemblyAI

## Pilot Progress

- 121/161 items ready (75%)
- 40 items remaining

## Recent Session Summary

Session 320 completed:
- `.critics/` directory with 4 critics (pipeline, protocol, architecture, session)
- `/critic` command for running critics on staged changes
- P0 enforcement in `/nextsesh`
- Handoff context check in `/start` (Step 1.5)
- Added `data_critic` as blocked P3 item

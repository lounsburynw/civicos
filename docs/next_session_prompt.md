# Recommended: automated_transcript_ingestion

**Priority:** P0
**Area:** data_integrity > source_provenance
**Date:** 2026-01-09

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 497 completed `data_freshness_alerting` - a daily GitHub Action that monitors data pipeline health. During testing, we discovered:
- **Decisions are 30 days stale** (latest meeting: 2026-01-14, latest decision from: 2025-12-15)
- Root cause: Transcript ingestion is manual while other pipeline steps are automated

The pipeline gap:
```
meeting ingestion → audio download → [MANUAL: transcription] → vector indexing
                                            ↑
                                    This step is not automated
```

## Recommended Task

Add transcript ingestion to the Modal automated pipeline. This should run BEFORE vector indexing since transcript text is indexed for semantic search.

## Key Files

- `scripts/modal_ingest.py:1121-1220` - Scheduled refresh functions (low/high velocity)
- `scripts/modal_ingest.py:1218-1303` - `scheduled_high_velocity_refresh()` - daily at 6 AM Pacific
- `packages/civic-extraction/src/civic_extraction/transcribe.py` - AssemblyAI transcription
- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - CLI entry point

## Current Scheduled Functions

```python
# Daily (High Velocity) - 6 AM Pacific
scheduled_high_velocity_refresh()  # meetings, issues, chunks, vectors

# Weekly (Low Velocity) - 7 PM Pacific Saturday
scheduled_low_velocity_refresh()   # municipal_code, legislation, decisions
```

Transcription should be added to daily refresh, after audio download but before vector indexing.

## Suggested Approach

1. **Understand current transcription flow:**
   ```bash
   # Check existing CLI
   civic-extract transcribe --help
   ```

2. **Add transcription step to `scheduled_high_velocity_refresh()`:**
   - After meetings are ingested (which includes video_url)
   - Before vector indexing
   - Include duration validation from Session 496

3. **Handle both jurisdictions:**
   - city-san-rafael (City Council, commissions)
   - school-san-rafael (School Board)

4. **Cost awareness:**
   - AssemblyAI charges per audio minute
   - Only transcribe new meetings (check if transcript exists)

## Tests to Run

```bash
# Transcription tests
pytest packages/civic-extraction/tests/test_transcribe.py -v

# Duration validation tests (from Session 496)
pytest packages/civic-extraction/tests/test_transcribe.py::test_duration_validation -v
```

## Success Criteria

- [ ] Transcription step added to Modal scheduled pipeline
- [ ] Runs after audio download, before vector indexing
- [ ] Includes duration validation to catch corrupted transcripts
- [ ] Handles both city-san-rafael and school-san-rafael
- [ ] Update pilot.json: `automated_transcript_ingestion` status -> ready

## Related Items

- `fix_corrupted_city_council_transcripts` (P1) - 9 transcripts need re-download/re-transcribe
- `transcript_duration_validation` (ready) - Validation logic already implemented

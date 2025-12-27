# Recommended: e2e_fresh_ingestion

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 385. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 385 completed `issues_cloud_storage` - the 9th of 10 cloud ETL items. All data types now have cloud storage paths. The final step is to verify the complete E2E pipeline works from scratch.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | Done | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | Done | Agendas -> Decisions |
| 7 | `chunks_cloud_storage` | Done | PDF chunks -> Postgres |
| 8 | `issues_cloud_storage` | Done | 311 Issues -> Postgres |
| 9 | `vector_indexing_cloud` | Done | All data -> pgvector |
| 10 | **`e2e_fresh_ingestion`** | **P0** | Full verification |

## Recommended Task

Run the complete pipeline from scratch to verify all data flows correctly through cloud storage:

1. **discover** - Fetch meeting metadata, store to Postgres
2. **youtube** - Discover video URLs, store to Postgres
3. **audio** - Download audio files, store to R2
4. **transcribe** - Process audio with AssemblyAI, store to Postgres
5. **decisions** - Extract decisions from agendas, store to Postgres
6. **chunks** - Extract PDF chunks, store to Postgres
7. **issues** - Fetch 311 issues, store to Postgres
8. **vectors** - Index all data to pgvector

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/__init__.py` - All CLI commands
- `packages/civic/src/civic/storage/postgres_backend.py` - Cloud storage methods
- `scripts/dev.sh` - Development server launcher

## Suggested Approach

### Step 1: Clear existing data (optional - for true fresh start)
```bash
# Check current counts
civic-extract vectors --jurisdiction city-san-rafael --stats --cloud
```

### Step 2: Run pipeline stages in order
```bash
# Each stage with --cloud flag for cloud storage
civic-extract discover --jurisdiction city-san-rafael --cloud
civic-extract youtube --jurisdiction city-san-rafael --cloud
civic-extract audio --jurisdiction city-san-rafael --cloud
civic-extract transcribe --jurisdiction city-san-rafael --cloud
civic-extract decisions --jurisdiction city-san-rafael --cloud
civic-extract chunks --jurisdiction city-san-rafael --cloud
civic-extract issues --jurisdiction city-san-rafael --cloud
civic-extract vectors --jurisdiction city-san-rafael --cloud
```

### Step 3: Verify data counts
```bash
civic-extract vectors --jurisdiction city-san-rafael --stats --cloud
```

### Step 4: Test search functionality
```bash
civic-extract vectors --jurisdiction city-san-rafael --test-search --cloud
```

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v
```

## Success Criteria

- [ ] All 8 pipeline stages run successfully with --cloud flag
- [ ] Data counts verified in Postgres (meetings, decisions, chunks, issues)
- [ ] Vector search returns relevant results
- [ ] No data loss between stages
- [ ] Existing tests pass

## Notes

- This is a verification step, not a feature implementation
- Focus on running commands and verifying output
- Document any failures or issues for follow-up
- May require running individual stages with --dry-run first

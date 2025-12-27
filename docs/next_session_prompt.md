# Recommended: decision_extraction_pipeline

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 381. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 381 completed `assemblyai_transcript_storage` (transcribe.py CLI now reads audio from R2 and stores transcripts in Postgres). The next item is `decision_extraction_pipeline` - automate decision extraction from minutes PDFs in the ETL pipeline.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | Done | Transcripts -> Postgres |
| 6 | **`decision_extraction_pipeline`** | **P0** | Minutes PDF -> Decisions |
| 7 | `chunks_cloud_storage` | P1 | PDF chunks -> Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues -> Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**Decision storage already exists:**
- `PostgresBackend.store_decisions()` at `postgres_backend.py:1042-1130`
- `PostgresBackend.get_decisions()` at `postgres_backend.py:1131-1180`
- `PostgresBackend.get_decision_count()` at `postgres_backend.py:1181-1200`
- 186 decisions already in local SQLite from manual batch extraction

**Decision extraction logic exists in:**
- `retrospective_analyzer.py` - Full extraction with LLM (Gemini 2.5 Pro)
- `docling_retrospective_analyzer.py` - PDF parsing with docling
- `fast_retrospective_analyzer.py` - Lighter-weight extraction

**Missing pieces:**
- No CLI command to trigger decision extraction
- No integration with cloud storage pipeline
- Minutes PDFs need to be downloaded, parsed, and decisions stored to Postgres

## Recommended Task

Create a `decisions.py` CLI command that:
1. Finds meeting minutes PDFs (from meetings in Postgres or local data)
2. Downloads/parses the PDF content
3. Extracts decisions using existing RetrospectiveAnalyzer
4. Stores decisions in Postgres via `store_decisions()`
5. Supports `--cloud` flag for cloud storage integration

## Key Files

- `packages/civic-services/src/civic_services/processing/retrospective_analyzer.py:100-200` - Decision extraction logic
- `packages/civic/src/civic/storage/postgres_backend.py:1042-1200` - Decision storage methods
- `packages/civic-extraction/src/civic_extraction/cli/audio.py` - Pattern for `--cloud` flag
- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - Recent cloud integration pattern

## Suggested Approach

1. **Create `decisions.py` CLI** in `packages/civic-extraction/src/civic_extraction/cli/`:
   ```python
   # civic-extract decisions --jurisdiction city-san-rafael --cloud
   parser.add_argument("--cloud", action="store_true",
       help="Store decisions in cloud storage")
   ```

2. **Integrate with existing extractors:**
   - Use `RetrospectiveAnalyzer.extract_high_stakes_decisions()` for LLM extraction
   - Or use simpler pattern-based extraction for cost efficiency

3. **Wire to PostgresBackend:**
   ```python
   from civic.storage import get_storage_backend
   backend = get_storage_backend()
   backend.store_decisions(jurisdiction_id, decisions)
   ```

4. **Add checkpoint support** (same pattern as audio.py, transcribe.py)

## Tests to Run

```bash
# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `decisions.py` CLI command created
- [ ] Minutes PDFs can be parsed for decisions
- [ ] Decisions stored in Postgres with `--cloud` flag
- [ ] Checkpoint/resume support for large batches
- [ ] Local fallback still works
- [ ] Existing tests pass

## Why This Next?

- Decisions are the core civic data - what got approved, rejected, voted on
- Having decisions in Postgres enables SQL queries for "what_happened" API
- This completes the meeting content pipeline: transcripts + decisions
- The 186 existing decisions prove the extraction logic works, just needs CLI automation

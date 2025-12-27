# Recommended: chunks_cloud_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 382. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 382 completed `decision_extraction_pipeline` - created `decisions.py` CLI command for automated decision extraction from meeting agendas. The next item is `chunks_cloud_storage` - wire PDF chunk extraction to use Postgres instead of local ChromaDB.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | Done | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | Done | Agendas -> Decisions |
| 7 | **`chunks_cloud_storage`** | **P0** | PDF chunks -> Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues -> Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**Chunk storage already exists:**
- `PostgresBackend.store_chunks()` at `postgres_backend.py:1219`
- `PostgresBackend.get_chunks()` at `postgres_backend.py:1295`
- `PostgresBackend.get_chunk_count()` at `postgres_backend.py:1350`

**Chunk extraction currently uses local storage:**
- `CivicEmbeddings.build_chunks_index_from_sql()` reads from SQLite at `embeddings.py:766-800`
- Vector indexing with pgvector at `pgvector_backend.py:373`
- No CLI command for cloud chunk extraction

**Missing pieces:**
- No `chunks.py` CLI command (like decisions.py, transcribe.py)
- PDF parsing and chunk extraction not wired to Postgres
- Need to extract chunks from agenda PDFs and store via `store_chunks()`

## Recommended Task

Create a `chunks.py` CLI command that:
1. Finds meeting agendas with PDF URLs (from meetings in Postgres)
2. Downloads and parses PDF content
3. Chunks the text (similar to existing docling parsing)
4. Stores chunks in Postgres via `store_chunks()`
5. Supports `--cloud` flag for cloud storage integration

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py:1219-1380` - Chunk storage methods
- `packages/civic/src/civic/_internal/meetings/embeddings.py:766-800` - Current chunk indexing from SQL
- `packages/civic-extraction/src/civic_extraction/cli/decisions.py` - Pattern for new CLI (just created)
- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py` - Cloud integration pattern

## Suggested Approach

1. **Create `chunks.py` CLI** in `packages/civic-extraction/src/civic_extraction/cli/`:
   ```python
   # civic-extract chunks --jurisdiction city-san-rafael --cloud
   parser.add_argument("--cloud", action="store_true",
       help="Store chunks in cloud storage")
   ```

2. **PDF chunk extraction:**
   - Use docling or pypdf2 to parse PDFs
   - Chunk into ~500 token segments with overlap
   - Include metadata: meeting_id, agenda_item, page_num, chunk_index

3. **Wire to PostgresBackend:**
   ```python
   from civic.storage import get_storage_backend
   backend = get_storage_backend()
   backend.store_chunks(jurisdiction_id, chunks)
   ```

4. **Add checkpoint support** (same pattern as decisions.py, transcribe.py)

## Tests to Run

```bash
# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `chunks.py` CLI command created
- [ ] Agenda PDFs can be parsed and chunked
- [ ] Chunks stored in Postgres with `--cloud` flag
- [ ] Checkpoint/resume support for large batches
- [ ] Local fallback still works
- [ ] Existing tests pass

## Why This Next?

- Chunks are needed for RAG/vector search on meeting content
- Having chunks in Postgres enables SQL-first vector indexing via pgvector
- This enables `vector_indexing_cloud` (next item in pipeline)
- Pattern is identical to decisions.py - fast to implement

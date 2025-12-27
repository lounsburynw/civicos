# Recommended: vector_indexing_cloud

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 383. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 383 completed `chunks_cloud_storage` - created `chunks.py` CLI command for extracting PDF chunks from meeting agendas and storing them in Postgres. Now all major data types are in cloud storage. The next critical step is enabling vector search on this cloud data.

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
| 8 | `seeclickfix_cloud_storage` | P1 | Issues -> Postgres |
| 9 | **`vector_indexing_cloud`** | **P0** | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**PgVectorBackend already exists:**
- `PgVectorBackend.index_from_storage()` at `pgvector_backend.py:373`
- `PgVectorBackend.search()` at `pgvector_backend.py:283`
- Implements `VectorBackend` protocol

**Pipeline currently uses ChromaDB:**
- `Pipeline.run_index()` at `pipeline.py:287` uses local ChromaDB
- `CivicEmbeddings.build_index_from_sql()` at `embeddings.py:686` builds ChromaDB index
- Need to add cloud vector indexing path

**Chunks now in Postgres:**
- `PostgresBackend.get_chunks()` returns chunks with text, meeting_id, agenda_item
- Ready for vector embedding

## Recommended Task

Wire the INDEX stage to use PgVectorBackend when DATABASE_URL is set:
1. Add a vector indexing CLI command or extend existing pipeline
2. Read chunks from Postgres via `get_chunks()`
3. Embed and store in pgvector via `PgVectorBackend.index_from_storage()`
4. Enable semantic search on cloud-stored chunks

## Key Files

- `packages/civic/src/civic/storage/pgvector_backend.py:283-400` - PgVector index/search methods
- `packages/civic/src/civic/_internal/meetings/embeddings.py:686-760` - Current index building
- `packages/civic-extraction/src/civic_extraction/pipeline.py:287` - Pipeline INDEX stage
- `packages/civic/src/civic/storage/postgres_backend.py:1295-1365` - get_chunks() method

## Suggested Approach

1. **Create `vectors.py` CLI** or extend pipeline with `--cloud-vectors` flag:
   ```python
   # civic-extract vectors --jurisdiction city-san-rafael --cloud
   ```

2. **Vector index from SQL:**
   ```python
   from civic.storage import get_storage_backend
   from civic.storage.pgvector_backend import PgVectorBackend

   backend = get_storage_backend()
   chunks = backend.get_chunks(jurisdiction_id)

   pgvector = PgVectorBackend()
   pgvector.index_from_storage(backend, jurisdiction_id)
   ```

3. **Update search to use pgvector:**
   - When DATABASE_URL set, use PgVectorBackend for semantic search
   - Local fallback to ChromaDB still works

## Tests to Run

```bash
# Storage protocol tests (includes PgVectorBackend)
pytest packages/civic/tests/test_storage_protocols.py -v

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] Vector indexing CLI or pipeline stage created
- [ ] Chunks from Postgres embedded into pgvector
- [ ] Semantic search works on cloud-stored vectors
- [ ] Local ChromaDB fallback still works
- [ ] Existing tests pass

## Why This Next?

- Completes the cloud data pipeline (store + index + search)
- Enables RAG queries on cloud-stored meeting content
- Required before `e2e_fresh_ingestion` can fully verify the pipeline
- PgVectorBackend already implemented and tested - just needs wiring

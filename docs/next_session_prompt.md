# Recommended: vector_storage_decision

**Priority:** P0
**Area:** deployment_artifacts > cloud_storage
**Date:** 2025-12-26

> This is recommended context from Session 370. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 370 completed **blob_storage_abstraction** - BlobStorage protocol with LocalBlobBackend (development) and R2Backend (production) for large files (PDFs, audio, transcripts). This completes the storage abstraction layer:
- StorageBackend: Structured data (SQLite/Postgres)
- BlobStorage: Binary files (local/R2)
- VectorBackend: Embeddings (ChromaDB/pgvector - needs production decision)

**Next step:** Document the vector storage strategy for production deployment.

## Recommended Task: vector_storage_decision

Document the vector storage strategy for production. This is a **decision document**, not code implementation.

**Options to evaluate:**
1. **ChromaDB on Fly.io volume** (~$0.45/mo for 3GB)
   - Already implemented and working
   - Self-hosted, full control
   - Requires volume management

2. **Qdrant Cloud free tier** (1GB)
   - Managed service, no ops
   - Free tier may be sufficient
   - Would need new backend implementation

3. **pgvector in Postgres** (shared with StorageBackend)
   - Single database for everything
   - Already have PostgresBackend
   - PgVectorBackend is a stub (needs implementation)

**Current state:** 880MB vector index fits all options.

## Key Files

- `packages/civic/src/civic/storage/vector.py` - VectorBackend protocol
- `packages/civic/src/civic/storage/pgvector_backend.py` - PgVectorBackend stub (NotImplementedError)
- `packages/civic/src/civic/_internal/meetings/chroma_backend.py` - Working ChromaDB implementation
- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - Architecture context

## Suggested Approach

1. **Research current ChromaDB usage**:
   - How is it deployed locally?
   - What's the index size and query patterns?
   - What would Fly.io volume setup look like?

2. **Evaluate Qdrant Cloud**:
   - Check free tier limits
   - API compatibility with current VectorBackend protocol
   - Migration complexity

3. **Evaluate pgvector**:
   - Would consolidate to single Postgres database
   - PgVectorBackend needs implementation (currently stub)
   - Check Supabase/Neon pgvector support

4. **Write decision document**:
   - Create `docs/decisions/vector_storage.md`
   - Document pros/cons of each option
   - Make a recommendation with rationale

## Success Criteria

- [ ] Decision document created in `docs/decisions/`
- [ ] All three options evaluated with pros/cons
- [ ] Clear recommendation with rationale
- [ ] Cost analysis (must stay under $7/month total)
- [ ] Migration path documented if changing from ChromaDB

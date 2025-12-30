# Session 412 Context

**Priority:** VectorBackend Unification
**Date:** 2025-12-30

## Session 411 Completed

1. **All 19 San Rafael transcripts complete** - $40.20 total transcription cost
2. **Transcripts indexed in pgvector** - Using nomic-embed-text-v1.5 (768 dims)
3. **Fixed `_transcript_to_text()`** - Now reads top-level `text` field from transcript documents
4. **Fixed timezone issue** - Manually-inserted transcripts had UTC timestamps; re-stored through proper `store_transcripts()` pipeline
5. **Added `content_hash` column** to transcripts table

## P0: VectorBackend Unification

**Problem:** Transcripts are indexed in pgvector, but the Civic API (`what_was_said()`) uses ChromaDB via `CivicEmbeddings`. They're not connected.

**Current Architecture (broken):**
```
Civic.what_was_said()
  -> history._search_transcripts()
    -> CivicEmbeddings.search_transcripts()  # Uses ChromaDB!

civic-extract vectors
  -> PgVectorBackend.index_from_storage()  # Uses pgvector
```

**Target Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│  Civic API (what_was_said, what_happened, etc.)         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  CivicEmbeddings (facade)                               │
│  - Jurisdiction-specific config                         │
│  - Collection naming conventions                        │
│  - Delegates to VectorBackend                           │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  VectorBackend (protocol) - already exists!             │
│  ├── PgVectorBackend  (when DATABASE_URL set)           │
│  └── ChromaDBBackend  (local development fallback)      │
└─────────────────────────────────────────────────────────┘
```

### Implementation Steps

1. **Read existing code:**
   - `packages/civic/src/civic/storage/vector.py` - VectorBackend protocol (lines 131-280)
   - `packages/civic/src/civic/storage/pgvector_backend.py` - PgVectorBackend implementation
   - `packages/civic/src/civic/_internal/meetings/embeddings.py` - CivicEmbeddings (ChromaDB)
   - `packages/civic/src/civic/history.py` - `_search_transcripts()` (lines 467-577)

2. **Create factory function** in `storage/vector.py`:
   ```python
   def get_vector_backend(jurisdiction_id: str) -> VectorBackend:
       """Return PgVectorBackend if DATABASE_URL set, else ChromaDBBackend."""
   ```

3. **Update CivicEmbeddings** to delegate to VectorBackend:
   - `search_transcripts()` -> `vector_backend.search(corpus_type="transcripts")`
   - Keep jurisdiction-specific config logic

4. **Update history._search_transcripts()** to use the factory or updated CivicEmbeddings

5. **Run tests:**
   ```bash
   pytest packages/civic/tests/test_integration_rag_san_rafael.py -v --override-ini="addopts="
   ```

### Key Files

| File | Purpose |
|------|---------|
| `storage/vector.py` | VectorBackend protocol - add factory function here |
| `storage/pgvector_backend.py` | Production implementation (already works) |
| `_internal/meetings/embeddings.py` | CivicEmbeddings - needs to delegate |
| `history.py` | API layer - uses CivicEmbeddings |

### Verification

After refactor, this should work:
```python
from civic import Civic
c = Civic("san-rafael")
excerpts = c.what_was_said("homeless shelter")
assert len(excerpts) > 0  # Currently fails, should pass
```

## Session 411 Stats

- Pilot: 210/231 items ready (91%)
- Transcription cost: $40.20 (19 videos, ~7337 utterances, 287k words)
- Vector index: 19 transcripts in pgvector

## Data State

| Data Type | Count | Location |
|-----------|-------|----------|
| Audio files | 19/19 | R2 cloud storage |
| Transcripts | 19/19 | Postgres `transcripts` table |
| Transcript vectors | 19/19 | Postgres `pgvector_embeddings` table |

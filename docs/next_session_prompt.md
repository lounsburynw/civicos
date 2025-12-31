# Session 413 Context

**Priority:** chunker_layer_separation
**Date:** 2025-12-30

## Session 413 Completed

1. **Fixed transcript chunked indexing** - `what_was_said()` now returns results
   - Added `_expand_transcripts_to_chunks()` to PgVectorBackend
   - Uses TranscriptChunker to create ~1500 char semantic chunks
   - 19 transcripts -> 4296 chunks indexed in pgvector
   - Full metadata preserved: speaker, timestamps, roles, video_id

## P0: chunker_layer_separation

**Problem:** Architecture critic flagged that `pgvector_backend.py` (storage layer) imports from `civic._internal.meetings.transcript` (domain-specific module). This violates layer separation - storage backends should be domain-agnostic.

**Current Code:**
```python
# packages/civic/src/civic/storage/pgvector_backend.py:465
def _expand_transcripts_to_chunks(self, transcripts, ...):
    from civic._internal.meetings.transcript import TranscriptChunker  # <-- violation
    chunker = TranscriptChunker(...)
```

**Options:**

1. **Move TranscriptChunker to shared module** (recommended)
   - Create `civic.storage.transformers.transcript_chunker`
   - Both `pgvector_backend` and `CivicEmbeddings` can import from there
   - Clean layer separation

2. **Inject chunker as dependency**
   - Pass chunker instance to `index_from_storage()` or `_expand_transcripts_to_chunks()`
   - More flexible but requires API changes

3. **Pre-chunk in calling code**
   - Caller chunks transcripts before passing to `index_from_storage()`
   - Add new corpus_type="transcript_chunks" that expects pre-chunked data
   - Keeps storage layer clean but pushes complexity to callers

### Implementation Steps (Option 1)

1. Create `packages/civic/src/civic/storage/transformers/__init__.py`
2. Move chunking logic to `packages/civic/src/civic/storage/transformers/transcript.py`
3. Update imports in:
   - `pgvector_backend.py`
   - `_internal/meetings/embeddings.py` (CivicEmbeddings)
4. Run architecture critic to verify fix
5. Run tests to verify functionality

### Key Files

| File | Purpose |
|------|---------|
| `storage/pgvector_backend.py:440-538` | `_expand_transcripts_to_chunks()` with problematic import |
| `_internal/meetings/transcript.py:976-1175` | TranscriptChunker class to move |
| `_internal/meetings/embeddings.py:953` | CivicEmbeddings also uses TranscriptChunker |

### Verification

After refactor:
1. `/critic architecture` should pass
2. `what_was_said("homeless shelter")` should still return 10 results
3. All tests should pass

## Session 413 Stats

- Pilot: 212/233 items ready (91%)
- Transcript chunks indexed: 4296 (from 19 transcripts)

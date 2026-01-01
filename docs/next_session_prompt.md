# Recommended: full_reindex_with_chunking

**Priority:** P0
**Area:** pipeline_automation > modal_remote_compute
**Date:** 2026-01-01

> This is recommended context from Session 424. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 424 attempted to speed up vector indexing to <10 minutes for 5857 municipal_code chunks. Added GPU support, bulk inserts, and parallel worker infrastructure. **Bottleneck is database writes** (~140 vectors/min = ~42 min total). GPU is NOT the bottleneck.

## Current State

```
Municipal code vectors: ~2400/5857 (partial - job was killed)
Target: 5857 vectors in <10 minutes
Current rate: ~140 vectors/min (need ~600/min for 10 min target)
```

## What Session 424 Did

1. **GPU support** - T4 GPU added (not the bottleneck)
2. **Bulk inserts** - `execute_values()` in `pgvector_backend.py:749-777`
3. **Deduplication** - Fixed ON CONFLICT errors
4. **Model pre-caching** - Baked into Docker image
5. **Parallel infrastructure** - `index_batch` function exists but has issues

## Key Files

| File | Line | Purpose |
|------|------|---------|
| `scripts/modal_vectors.py` | 57-72 | index_corpus with GPU config |
| `scripts/modal_vectors.py` | 319-338 | delete_vectors function |
| `scripts/modal_vectors.py` | 341-393 | index_batch for parallelism |
| `packages/civic/src/civic/storage/pgvector_backend.py` | 721-777 | Bulk insert logic |

## Root Cause

**DB round trips dominate:**
- batch_size=100 (CLI default) = 59 transactions for 5857 chunks
- Each transaction = network latency to Neon
- Embeddings are fast (~1s for 100 vectors), DB writes are slow (~10s)

## Options for <10 min Target

### Option A: Add --batch-size CLI flag (Quick)
Add to `main()` in modal_vectors.py, then run with `--batch-size 1000`

### Option B: Use COPY instead of INSERT (10x faster)
Replace `execute_values()` with `copy_from()` using StringIO buffer

### Option C: Fix parallel workers (Needs work)
Issue: Each worker expands ALL 5857 chunks then slices
Fix: Pre-expand once, distribute chunks via `.starmap()`

## Quick Test

```bash
# Check current vectors
source civic-env/bin/activate
python3 -c "
import os, psycopg2
exec(open('.env').read().replace('export ',''))
c = psycopg2.connect(os.environ['DATABASE_URL']).cursor()
c.execute(\"SELECT COUNT(*) FROM vector_embeddings WHERE jurisdiction_id='city-san-rafael' AND corpus_type='municipal_code'\")
print(f'Vectors: {c.fetchone()[0]}/5857')
"

# Run indexing (detached - survives laptop close)
modal run --detach scripts/modal_vectors.py --corpus municipal_code --reindex
```

## Success Criteria

- [ ] Municipal code: 5857/5857 vectors indexed
- [ ] Total indexing time: <10 minutes
- [ ] `modal run scripts/modal_ingest.py --stats-only` shows municipal_code green

## Session 424 Commit

- `0f21202` Session 424: Add GPU + bulk insert optimizations for vector indexing

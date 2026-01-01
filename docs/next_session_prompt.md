# Recommended: full_reindex_with_chunking

**Priority:** P0
**Area:** pipeline_automation > modal_remote_compute
**Date:** 2026-01-01

> This is recommended context from Session 425. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 425 fixed the chunk ID uniqueness bug (duplicate section_numbers across chapters). All 5857 municipal_code chunks are now indexed. However, indexing time is ~20 min, still above the <10 min target.

## Current State

```
Municipal code vectors: 5857/5857 (complete)
Target: <10 min indexing time
Current time: ~20 min (1214s)
Bottleneck: DB write latency to Neon (~10s per transaction)
```

## What Session 425 Did

1. **Fixed chunk ID uniqueness** - Use db_id (UUID) instead of section_number
2. **Increased batch_size** - CLI default 100→1000 (reduces DB round-trips 10x)
3. **Fixed _cost bug** - Skip metadata keys in result iteration
4. **Removed civic_extraction from Modal** - Not needed for vector indexing

## Key Files

| File | Line | Purpose |
|------|------|---------|
| `packages/civic/src/civic/_internal/legal/embeddings/chunker.py` | 278-284 | db_id for unique chunk IDs |
| `scripts/modal_vectors.py` | 424 | batch_size default |
| `packages/civic/src/civic/storage/pgvector_backend.py` | 749-777 | Bulk insert logic |

## Root Cause for Slow Indexing

With batch_size=1000, we have 6 batches for 5857 chunks. Each batch:
1. Embed 1000 docs (~2s with GPU)
2. Close connection
3. Reconnect
4. Bulk INSERT with execute_values (~3min per batch due to network latency)
5. Commit

## Options for <10 min Target

### Option A: Use COPY instead of INSERT (Recommended - 10x faster)
Replace `execute_values()` with `copy_from()` using StringIO buffer:
```python
from io import StringIO
import csv

buffer = StringIO()
writer = csv.writer(buffer, delimiter='\t')
for row in insert_values:
    writer.writerow(row)
buffer.seek(0)
cursor.copy_from(buffer, 'vector_embeddings', columns=(...))
```

### Option B: Parallel Workers with Pre-chunked Distribution
Current issue: Each worker expands ALL chunks then slices. Fix:
1. Pre-expand chunks once on local machine
2. Distribute chunks via `.starmap()` with pre-assigned ranges
3. Each worker only embeds its assigned slice

### Option C: Connection pooling
Keep connection alive between batches instead of close/reconnect cycle.

## Data Quality Issue (Separate Task)

The municipal_code table has 12,364 rows but only 2,364 unique section_numbers. Multiple ingestion runs created duplicates. Consider:
1. DELETE duplicate rows keeping latest per section
2. Add deduplication to `get_municipal_code()` query

## Quick Test

```bash
source civic-env/bin/activate

# Check vector counts
modal run scripts/modal_vectors.py --stats-only

# Time a reindex (GPU + bulk inserts)
time modal run scripts/modal_vectors.py --corpus municipal_code --reindex
```

## Success Criteria

- [ ] Municipal code indexing time: <10 minutes
- [ ] All 5857 chunks indexed
- [ ] No errors in Modal logs

## Session 425 Commit

- `8480c25` Session 425: Fix chunk ID uniqueness for municipal code indexing

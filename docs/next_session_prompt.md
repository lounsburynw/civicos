# Recommended: full_reindex_with_chunking

**Priority:** P0
**Area:** pipeline_automation > modal_remote_compute
**Date:** 2025-12-31

> This is recommended context from Session 423. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 423 completed `automated_incremental_pipeline` and deployed Modal schedules. However, municipal_code vectors are stale (2366/3811 indexed) - the Session 422 fix (22% → 99.9% content coverage) hasn't been vectorized yet. A reindex attempt failed with a RemoteError that needs investigation.

## Current State

```
Vector Indices:
  + chunks           5084/5084  ✅
  + decisions          44/44    ✅
  o meetings           46/12    ⚠️ stale
  o transcripts      4296/19    ⚠️ stale
  o municipal_code   2366/3811  ❌ NEEDS REINDEX
  + issues           1330/1330  ✅
  + legislation_CA   2839/2839  ✅
  + legislation_US  12355/12355 ✅
```

## What Failed

```bash
modal run scripts/modal_ingest.py --municipal --vectors --reindex
```

Got `RemoteError` from `index_vectors.remote()`. The error output was truncated - need to investigate the actual cause on Modal dashboard or run with more verbose logging.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_vectors.py` | Vector indexing script - try running directly |
| `scripts/modal_ingest.py` | Unified ingestion - calls index_vectors |
| `packages/civic/src/civic/_internal/legal/embeddings/chunker.py` | expand_municipal_code_to_chunks() |

## Suggested Approach

1. **Check Modal dashboard** for error details:
   https://modal.com/apps/lounsburynw/main/deployed/civic-ingest

2. **Run vector indexing directly** to see full error:
   ```bash
   modal run scripts/modal_vectors.py --corpus municipal_code --reindex
   ```

3. **If memory issue** - try with smaller batch:
   ```bash
   modal run scripts/modal_vectors.py --corpus municipal_code --reindex --batch-size 50
   ```

4. **Verify after success**:
   ```bash
   modal run scripts/modal_ingest.py --stats-only
   ```

## Success Criteria

- [ ] Municipal code vectors: 3807+/3811 indexed (was 2366)
- [ ] All corpora show green in stats
- [ ] `modal run scripts/modal_ingest.py --stats-only` shows all ✅

## Session 423 Accomplishments

- ✅ Deployed Modal schedules (daily + weekly cron jobs active)
- ✅ Added refresh_metadata table for incremental fetch tracking
- ✅ Added fetch_meetings/fetch_issues with incremental support
- ✅ Fixed stats to show legislation vectors for city jurisdictions
- ❌ Vector reindex failed - needs investigation

## Commits Made

- `aea7882` Session 423: Add automated incremental pipeline with Modal scheduling
- `189217d` Session 423: Show legislation vectors in city stats

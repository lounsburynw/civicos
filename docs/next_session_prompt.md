# Recommended: modal_unified_ingestion

**Priority:** P0
**Area:** pipeline_automation > modal_remote_compute
**Date:** 2025-12-31

> This is recommended context from Session 420. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 420 completed both Modal fetch scripts:
- `modal_municipal_code_fetch` - Fetch municipal code from Municode API
- `modal_legislation_text_fetch` - Fetch bill text from LegiScan API

Now we need a unified script to run all ingestion in parallel.

## Current State

| Script | Status | Purpose |
|--------|--------|---------|
| `scripts/modal_municipal_code.py` | Ready | Fetch municipal code (Municode API) |
| `scripts/modal_legislation.py` | Ready | Fetch bill text (LegiScan API) |
| `scripts/modal_vectors.py` | Ready | Generate embeddings (fastembed) |
| `scripts/modal_ingest.py` | Not created | Unified parallel ingestion |

## The Goal

Create `scripts/modal_ingest.py` that:
1. Spawns fetch functions in parallel (Modal's `.spawn()`)
2. Allows single command: `modal run scripts/modal_ingest.py --all`
3. Enables laptop-closed operation for full data refresh

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_municipal_code.py` | Template for fetch pattern |
| `scripts/modal_legislation.py` | Template for LegiScan fetch |
| `scripts/modal_vectors.py` | Template for vector indexing |

## Suggested Approach

```python
# scripts/modal_ingest.py
import modal

app = modal.App("civic-ingest")

@app.local_entrypoint()
def main(all: bool = False, municipal: bool = False, legislation: bool = False, vectors: bool = False):
    """Unified ingestion entrypoint."""
    handles = []

    if all or municipal:
        from scripts.modal_municipal_code import fetch_municipal_code
        handles.append(("municipal_code", fetch_municipal_code.spawn()))

    if all or legislation:
        from scripts.modal_legislation import fetch_legislation_text
        handles.append(("legislation_CA", fetch_legislation_text.spawn("state-CA")))
        # Note: US legislation shares quota with CA - may need to serialize

    # Wait for fetches to complete before vectorizing
    for name, handle in handles:
        result = handle.get()
        print(f"{name}: {result}")

    if all or vectors:
        from scripts.modal_vectors import index_corpus
        # Reindex all corpora with new data
        index_corpus.remote(corpus="all", reindex=True)
```

## API Quota Considerations

- **Municode API**: No quota, 2 req/s rate limit
- **LegiScan API**: 30,000 queries/month free tier
  - CA: ~5,700 calls (2,839 bills × 2)
  - US: ~24,700 calls (12,355 bills × 2)
  - Running both exceeds monthly quota - may need to serialize

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `scripts/modal_ingest.py` created
- [ ] Supports `--all`, `--municipal`, `--legislation`, `--vectors` flags
- [ ] Parallel execution via Modal `.spawn()`
- [ ] Single command runs full pipeline: `modal run scripts/modal_ingest.py --all`
- [ ] `pilot.json` updated: `modal_unified_ingestion` → `ready`

## Session 420 Stats

- Completed: `modal_municipal_code_fetch`, `modal_legislation_text_fetch`
- Added: `update_legislation_text()` method to PostgresBackend
- Pilot: 219/243 items (90%)

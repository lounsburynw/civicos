# Recommended: data_refresh_strategy (Modal Vector Indexing)

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-30

## Context

Session 407 set up Modal for high-memory vector indexing (16GB RAM) to solve GitHub Actions memory limits.

**Completed:**
- Created `scripts/modal_vectors.py` with proper Modal functions
- Created Modal secrets: `civic-db` (DATABASE_URL) and `civic-github` (GITHUB_TOKEN)
- Added `--offset` and `--limit` flags to CLI for splitting jobs

**Left to do:**
1. Update `scripts/modal_vectors.py` to use GitHub token for private repo access
2. Run `modal run scripts/modal_vectors.py --stats-only` to test
3. Run `modal run scripts/modal_vectors.py` to index all 8,839 docs
4. Verify search works
5. Mark `data_refresh_strategy` as ready

## Code Change Needed

Update `scripts/modal_vectors.py` to use GitHub token:

```python
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc", "git")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "fastembed>=0.3.0",
        "numpy<2",
    )
    .run_commands(
        "pip install git+https://${GITHUB_TOKEN}@github.com/lounsburynw/civic.git#subdirectory=packages/civic",
        "pip install git+https://${GITHUB_TOKEN}@github.com/lounsburynw/civic.git#subdirectory=packages/civic-extraction",
        secrets=[modal.Secret.from_name("civic-github")],
    )
)
```

## Commands to Run

```bash
# Test Modal setup
modal run scripts/modal_vectors.py --stats-only

# Run full indexing (all corpus types)
modal run scripts/modal_vectors.py

# Or just chunks (the large one that failed on GitHub Actions)
modal run scripts/modal_vectors.py --corpus chunks
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_vectors.py` | Modal function for vector indexing |
| `packages/civic/src/civic/storage/pgvector_backend.py` | PgVectorBackend with offset/limit |
| `packages/civic-extraction/src/civic_extraction/cli/vectors.py` | CLI with --offset/--limit |
| `.github/workflows/vector-refresh.yml` | GitHub Actions (fallback for small corpus) |

## Vector Stats (Current)

| Corpus | Total | Indexed | Status |
|--------|-------|---------|--------|
| chunks | 5,084 | ~0 | Needs indexing |
| municipal_code | 2,366 | 2,366 | Done |
| issues | 1,330 | ~630 | Partial |
| meetings | 46 | 46 | Done |
| decisions | 44 | 44 | Done |
| transcripts | 13 | 0 | No text |

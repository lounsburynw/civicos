# Recommended: data_refresh_strategy (Full Vector Indexing)

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 406. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 406 completed `vectors_e2e_cloud` - added configurable embedding providers (`--provider` flag) with model tracking and validation. The infrastructure is ready for portable vector ETL.

**Now we need to actually run the full indexing remotely with parallelization.**

## Task: Run Full Vector Indexing (8,839 docs)

### Vector Stats (San Rafael)
| Corpus | Documents | Status |
|--------|-----------|--------|
| chunks | 5,084 | ~1% indexed |
| municipal_code | 2,366 | 0% |
| issues | 1,330 | 0% |
| meetings | 46 | 0% |
| decisions | 44 | 100% (test) |
| transcripts | 13 | 0% |
| **Total** | **8,839** | |

### Approach: Parallel Remote Execution

Run corpus types in parallel using `--provider fastembed` (portable ONNX, no PyTorch):

```bash
# Option 1: Parallel local execution (if you have resources)
civic-extract vectors --jurisdiction city-san-rafael --corpus chunks --provider fastembed &
civic-extract vectors --jurisdiction city-san-rafael --corpus municipal_code --provider fastembed &
civic-extract vectors --jurisdiction city-san-rafael --corpus issues --provider fastembed &
civic-extract vectors --jurisdiction city-san-rafael --corpus meetings --provider fastembed &
civic-extract vectors --jurisdiction city-san-rafael --corpus transcripts --provider fastembed &
wait

# Option 2: GitHub Actions workflow
# Create .github/workflows/vector-refresh.yml
```

### GitHub Actions Approach (Recommended)

Create a workflow that:
1. Runs on schedule (weekly) or manual dispatch
2. Parallelizes corpus types across jobs
3. Uses `fastembed` provider (lightweight, no GPU needed)
4. Reports success/failure

```yaml
# .github/workflows/vector-refresh.yml
name: Vector Refresh
on:
  schedule:
    - cron: '0 6 * * 0'  # Weekly Sunday 6am UTC
  workflow_dispatch:

jobs:
  index:
    strategy:
      matrix:
        corpus: [chunks, municipal_code, issues, meetings, transcripts, decisions]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e packages/civic-extraction[embeddings]
      - run: |
          civic-extract vectors \
            --jurisdiction city-san-rafael \
            --corpus ${{ matrix.corpus }} \
            --provider fastembed
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Deliverables

1. [ ] GitHub Actions workflow for parallel vector refresh
2. [ ] Document refresh cadence in `docs/operations/DATA_REFRESH.md`
3. [ ] Run initial full indexing (all 8,839 docs)
4. [ ] Verify search works across all corpus types
5. [ ] Mark `data_refresh_strategy` as ready

### Success Criteria

```bash
civic-extract vectors --jurisdiction city-san-rafael --corpus all --stats
# Should show 100% coverage for all corpus types
```

## Key Files

| File | Purpose |
|------|---------|
| `packages/civic-extraction/src/civic_extraction/cli/vectors.py` | CLI with --provider flag |
| `packages/civic/src/civic/storage/pgvector_backend.py` | PgVectorBackend with provider support |
| `.github/workflows/vector-refresh.yml` | New workflow to create |
| `docs/operations/DATA_REFRESH.md` | New doc to create |

## Estimated Time

- GitHub Actions setup: 15-20 min
- Full indexing run: Depends on runner (est. 10-30 min parallelized)
- Documentation: 10 min

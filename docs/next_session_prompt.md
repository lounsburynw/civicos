# Recommended: ab_test_retrieval_quality

**Priority:** P0
**Area:** data_architecture > embedding_infrastructure
**Date:** 2026-01-08

> This is recommended context from Session 493. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 493 completed `full_corpus_pgvector_integration` - UnifiedSearch now uses pgvector for all corpus types (decisions, chunks, transcripts, issues, municipal_code) with ChromaDB fallback. All 39 smoke tests and 10 pgvector integration tests pass. Now we need to validate that pgvector retrieval quality matches or exceeds the ChromaDB baseline.

## Recommended Task

Create an A/B test framework to compare retrieval quality between pgvector and ChromaDB across a set of benchmark queries. This validates the migration doesn't degrade search quality.

## Key Files

- `packages/civic/src/civic/_internal/search/unified.py` - UnifiedSearch class with pgvector integration
- `packages/civic/src/civic/_internal/search/unified.py:106-141` - `_search_with_pgvector()` helper method
- `packages/civic/src/civic/storage/pgvector_backend.py:868-982` - PgVectorBackend.search() method
- `packages/civic/tests/test_integration_pgvector.py` - Existing pgvector tests as examples

## Current pgvector Corpus Coverage

San Rafael embeddings in pgvector (verified):
- municipal_code: 5,857 embeddings
- chunks: 5,084 embeddings
- transcripts: 4,296 embeddings
- issues: 1,500 embeddings
- meetings: 46 embeddings
- decisions: 44 embeddings

## Suggested Approach

1. **Create benchmark query set** - Define 10-20 representative queries across corpus types:
   - Issues: "pothole", "graffiti", "parking violation"
   - Chunks: "housing development", "budget", "climate"
   - Transcripts: "public comment", "council discussion"
   - Municipal code: "ADU", "zoning residential", "building permit"

2. **Build comparison framework** - For each query:
   - Run search via pgvector path (force `_vector_backend`)
   - Run search via ChromaDB path (set `_vector_backend = None`)
   - Compare: score distribution, result overlap, top-k agreement

3. **Define quality metrics**:
   - Precision@K overlap (e.g., how many of top-5 results match?)
   - Mean score comparison (pgvector vs ChromaDB scores)
   - Latency comparison

4. **Create test file** `test_retrieval_quality.py` with:
   - Parameterized tests over query set
   - Assert minimum quality thresholds
   - Generate comparison report

## Tests to Run

```bash
# Smoke tests (verify nothing broken)
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# pgvector tests (baseline)
pytest packages/civic/tests/test_integration_pgvector.py -v --override-ini="addopts="

# New quality tests (once created)
pytest packages/civic/tests/test_retrieval_quality.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] Benchmark query set defined (10+ queries across corpus types)
- [ ] Comparison framework implemented
- [ ] Top-5 overlap >= 60% for matching corpus types
- [ ] No significant score degradation (pgvector scores within 0.1 of ChromaDB)
- [ ] Test file created with quality assertions
- [ ] pilot.json: ab_test_retrieval_quality -> ready

## Session 493 Changes Reference

Key changes from full_corpus_pgvector_integration:
- `UnifiedSearch.__init__` now initializes `_vector_backend` via `get_vector_backend()`
- `_search_with_pgvector()` helper returns `None` to signal fallback needed
- `get_available_corpora()` uses `_get_pgvector_count()` before ChromaDB
- `VectorBackend` protocol has new `count()` method

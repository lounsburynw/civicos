# Recommended: full_corpus_pgvector_integration

**Priority:** P0
**Area:** data_architecture > embedding_infrastructure
**Date:** 2026-01-08

> This is recommended context from Session 492. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 492 completed `pgvector_integration_tests` - we now have CI coverage for pgvector searches with 10 tests in `test_integration_pgvector.py`. The API is connected to production pgvector for municipal_code and codified_law. However, several corpus types still use ChromaDB (`CivicEmbeddings`) instead of pgvector:
- **issues** - `whos_with_me()` semantic search
- **chunks** - `prepare()` document retrieval
- **decisions** - `what_happened()` semantic path

## Recommended Task

Complete pgvector integration for ALL corpus types by replacing `CivicEmbeddings` usages with `get_vector_backend()` factory pattern (already implemented for transcripts in `history.py:545-558`).

## Key Files

- `packages/civic/src/civic/civic.py:1035` - `_find_semantic_issue_types()` uses CivicEmbeddings for issues
- `packages/civic/src/civic/civic.py` - `prepare()` uses CivicEmbeddings for chunks
- `packages/civic/src/civic/history.py:545-558` - **PATTERN**: `_search_transcripts()` uses `get_vector_backend()` with ChromaDB fallback
- `packages/civic/src/civic/storage/__init__.py` - `get_vector_backend()` factory function
- `packages/civic/src/civic/storage/corpus_types.py` - CorpusType enum and CORPUS_REGISTRY

## Current Status (from pilot.json)

```
pgvector_connected:
  - codified_law via PostgresBackend.search_codified_law()
  - municipal_code via PgVectorBackend.search() [Session 491]
  - transcripts via get_vector_backend() with fallback

needs_pgvector_wiring:
  - issues - whos_with_me() uses CivicEmbeddings (civic.py:1035)
  - chunks - prepare() uses CivicEmbeddings
  - decisions - what_happened() semantic path uses CivicEmbeddings
```

## Suggested Approach

1. **Study the pattern** in `history.py:545-558` - see how `_search_transcripts()` uses `get_vector_backend()`:
```python
backend = get_vector_backend(jurisdiction_id)
if backend:
    results = backend.search(query, jurisdiction_id, "transcripts", top_k)
else:
    # fallback to ChromaDB
```

2. **Update `_find_semantic_issue_types()`** in `civic.py:1035` to use pgvector for issues

3. **Update `prepare()`** to use pgvector for chunks

4. **Update `what_happened()`** semantic search to use pgvector for decisions

5. **Verify** with existing integration tests plus new pgvector tests

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# pgvector integration tests (need DATABASE_URL)
pytest packages/civic/tests/test_integration_pgvector.py -v --override-ini="addopts="

# Verify whos_with_me still works after changes
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('city-san-rafael')
result = c.whos_with_me('pothole')
print(f'Community members: {len(result.community)}')
"
```

## Success Criteria

- [ ] `_find_semantic_issue_types()` uses `get_vector_backend()` for issues corpus
- [ ] `prepare()` uses `get_vector_backend()` for chunks corpus
- [ ] `what_happened()` semantic path uses `get_vector_backend()` for decisions
- [ ] All 39 smoke tests pass
- [ ] All 10 pgvector integration tests pass
- [ ] pilot.json: full_corpus_pgvector_integration -> ready

## Session 492 Insights

- `conftest.py` now loads dotenv early for DATABASE_URL availability during test collection
- `@pytest.mark.requires_pgvector` marker auto-skips when DATABASE_URL not set
- CI workflow has dedicated `pgvector` job that runs on main branch with secrets
- Pattern is well-established: use `get_vector_backend()` with ChromaDB fallback

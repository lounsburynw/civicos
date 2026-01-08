# Recommended: pgvector_cross_corpus_search

**Priority:** P0
**Area:** data_architecture > embedding_infrastructure
**Date:** 2026-01-08

> This is recommended context from Session 490. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 490 completed municipal_code vector indexing (5,857 vectors from 3,811 current sections). However, we discovered a critical integration gap: `what_applies()` uses `CivicEmbeddings` (ChromaDB) which doesn't see the PgVector embeddings. The 500k+ vectors in pgvector (municipal code, codified law, CFR) are unreachable from the API.

## The Problem

```python
# In context.py lines 217-246:
from civic._internal.meetings.embeddings import CivicEmbeddings
embedder = CivicEmbeddings(jurisdiction)
if embedder.has_municipal_code():  # Returns False - ChromaDB has no vectors
    results = embedder.search_municipal_code(topic, top_k=5)
```

But the vectors exist in PgVector and search works:
```python
# This WORKS - direct PgVectorBackend search
from civic.storage.pgvector_backend import PgVectorBackend
pgvector = PgVectorBackend(os.getenv('DATABASE_URL'), provider_type='fastembed')
results = pgvector.search('ADU zoning', 'city-san-rafael', 'municipal_code', top_k=3)
# Returns: Score 0.748, Section 14.16.285 (ADU regulations)
```

## Recommended Task

Create a unified query interface that enables `what_applies()` to search across all corpus types in pgvector. Two approaches:

1. **Modify `context.py`** to use PgVectorBackend directly when DATABASE_URL is set (quick fix)
2. **Create PgUnifiedSearch** abstraction that mirrors UnifiedSearch API but uses pgvector (proper solution)

## Key Files

- `packages/civic/src/civic/context.py:217-246` - Municipal code search in what_applies()
- `packages/civic/src/civic/_internal/search/unified.py` - Existing ChromaDB UnifiedSearch
- `packages/civic/src/civic/storage/pgvector_backend.py:869` - PgVectorBackend.search()
- `pilot.json:878` - pgvector_cross_corpus_search item

## Suggested Approach

1. **Quick win**: Update `context.py` to use PgVectorBackend.search() instead of CivicEmbeddings for municipal code (similar to how codified_law search works at lines 153-183)

2. **Pattern exists**: Lines 153-183 already use `PostgresBackend.search_codified_law()` directly. Apply same pattern for municipal_code:
```python
# Add after codified_law search block (~line 215)
try:
    import os
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from civic.storage.pgvector_backend import PgVectorBackend
        pgvector = PgVectorBackend(database_url, provider_type="fastembed")
        results = pgvector.search(
            query=topic,
            jurisdiction_id=jurisdiction,
            corpus_type="municipal_code",
            top_k=5,
        )
        for r in results:
            local.append({
                "type": "ordinance",
                "id": r.id,
                "section_number": r.metadata.get("section_number"),
                "text_preview": r.content[:300] if r.content else "",
                "relevance_score": round(r.score, 3),
            })
except Exception:
    pass  # Municipal code search not available
```

3. **Run tests** to verify what_applies() returns municipal code results
4. **Update pilot.json** status

## Tests to Run

```bash
# Test what_applies() returns municipal code
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v -k "what_applies"

# Quick manual test
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('city-san-rafael')
result = c.what_applies('accessory dwelling unit')
print(f'Local results: {len(result.local)}')
for loc in result.local[:3]:
    print(f'  {loc}')
"
```

## Success Criteria

- [ ] `what_applies()` returns municipal_code results from pgvector
- [ ] Scores are reasonable (0.6-0.8 range for relevant queries)
- [ ] Test "ADU zoning" returns Section 14.16.285
- [ ] pilot.json: pgvector_cross_corpus_search -> ready

## Session 490 Insights

- Municipal code vectors: 5,857 embeddings from 3,811 current sections (1.54 chunks/doc)
- 16,175 total DB records include historical versions; temporal filter `valid_to IS NULL` gives current
- PgVectorBackend.search() works perfectly - just need to wire it into context.py
- `codified_law` search already uses Postgres directly (lines 153-183) - same pattern needed

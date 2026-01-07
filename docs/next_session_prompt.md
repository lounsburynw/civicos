# Recommended: codified_law_vectors

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-07

> This is recommended context from Session 487. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 487 built the vector embedding infrastructure for codified law (U.S. Code, CA Codes, CFR). The chunkers, pgvector backend extensions, and Modal script are complete. A federal-CFR embedding job (~98k chunks, 4 parallel workers) was started and may have completed.

**Remaining work:** Run embedding jobs for federal-US and state-CA, then verify semantic search works.

## Recommended Task

Complete the codified law vector embeddings and verify semantic search integration.

## Key Files

- `packages/civic/src/civic/_internal/legal/embeddings/chunker.py:463-704` - Chunker functions
- `packages/civic/src/civic/storage/pgvector_backend.py:615-634` - Corpus type handling
- `scripts/modal_vectors.py:144-154` - Jurisdiction routing
- `packages/civic/src/civic/context.py:156-207` - what_applies() integration (keyword search)

## Steps

1. **Check federal-CFR status (may have completed):**
```bash
modal run scripts/modal_vectors.py --jurisdiction federal-CFR --stats-only
```

2. **Run federal-US embedding (~219k chunks, ~30-60 min):**
```bash
modal run scripts/modal_vectors.py --jurisdiction federal-US --corpus codified_law --reindex --parallel 4
```

3. **Run state-CA embedding (~193k chunks, ~30-60 min):**
```bash
modal run scripts/modal_vectors.py --jurisdiction state-CA --corpus codified_law --reindex --parallel 4
```

4. **Verify semantic search:**
```bash
source civic-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
from civic.storage.pgvector_backend import PgVectorBackend

pgvector = PgVectorBackend(os.environ['DATABASE_URL'], provider_type='fastembed')
results = pgvector.search('housing discrimination', 'federal-US', 'codified_law', top_k=5)
for r in results:
    print(f'{r.score:.3f}: {r.metadata.get(\"citation\", r.id)[:60]}')
"
```

5. **Update pilot.json status to ready**

## Data Inventory

| Jurisdiction | Sections | Est. Chunks | Status |
|--------------|----------|-------------|--------|
| federal-CFR  | 36,608   | ~98,000     | Check (job started Session 487) |
| federal-US   | 50,809   | ~219,000    | Pending |
| state-CA     | 161,219  | ~193,000    | Pending |

## Success Criteria

- [ ] federal-CFR: 98k+ vectors in database (check with --stats-only)
- [ ] federal-US: 219k+ vectors in database
- [ ] state-CA: 193k+ vectors in database
- [ ] Semantic search returns relevant results for "housing", "environment", "transportation"
- [ ] pilot.json: codified_law_vectors -> ready

## Optional Enhancement

After embeddings complete, consider adding semantic search to `what_applies()` in addition to existing keyword search:
- File: `packages/civic/src/civic/context.py`
- Currently uses `db.search_codified_law()` (PostgreSQL full-text search)
- Could add `pgvector.search(corpus_type="codified_law")` for semantic results

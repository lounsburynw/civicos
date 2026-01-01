# Recommended: Codified Law Ingestion (U.S. Code + CA Codes)

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-01

> This is recommended context from Session 427. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 427 discovered that LegiScan bills are mostly proposals (only 0.6% of federal bills enacted). For `what_applies()` to answer "what law applies to my ADU project?", we need **codified law** (U.S. Code, CA Codes), not pending bills. The session created a U.S. Code XML parser prototype and added the `CODIFIED_LAW` corpus type.

## Key Insight

| Corpus | Content | Purpose |
|--------|---------|---------|
| `legislation` | Bills (pending + enacted) | `whats_next()` - what's being proposed |
| `codified_law` | Compiled statutes | `what_applies()` - what law applies now |

## What's Already Done

1. ✅ USCodeParser in `packages/civic-extraction/src/civic_extraction/uscode.py`
2. ✅ Title 42 downloaded to `data/uscode/usc42.xml` (17MB, 7,029 sections)
3. ✅ CODIFIED_LAW corpus type in `packages/civic/src/civic/storage/corpus_types.py:47`
4. ✅ Federal legislation ingested (12,355 bills in legislation table)

## Recommended Task

Complete the codified law ingestion pipeline:

1. **Add storage backend methods** for `codified_law` corpus
2. **Create CLI command** for U.S. Code ingestion (similar to `civic-extract legislative`)
3. **Index to pgvector** using COPY optimization from Session 426
4. **Test `what_applies()`** with real codified law queries

## Key Files

- `packages/civic-extraction/src/civic_extraction/uscode.py` - Parser prototype
- `packages/civic/src/civic/storage/corpus_types.py:154` - CODIFIED_LAW config
- `packages/civic/src/civic/storage/pgvector_backend.py` - Need to add methods
- `data/uscode/usc42.xml` - Downloaded Title 42 (housing, public welfare)

## Suggested Approach

```bash
# 1. Test the parser works
python -m civic_extraction.uscode data/uscode/usc42.xml --stats

# 2. Add storage methods (model after legislation or municipal_code)
# Look at get_legislation(), store_legislation() in postgres_backend.py

# 3. Create CLI
# Add to packages/civic-extraction/src/civic_extraction/cli/

# 4. Index with COPY optimization
# Use pattern from modal_vectors.py --use-copy
```

## Database State

```sql
-- Current legislation counts
SELECT state, COUNT(*) FROM legislation GROUP BY state;
-- US: 12,355, CA: 2,839

-- Will need codified_law table (similar schema to legislation)
```

## Success Criteria

- [ ] `get_codified_law()` and `store_codified_law()` methods in postgres_backend.py
- [ ] CLI: `civic-extract uscode --title 42 --cloud` ingests to Postgres
- [ ] Sections indexed to pgvector with CODIFIED_LAW corpus type
- [ ] `c.what_applies("public housing")` returns U.S. Code sections

## Session 427 Commits

- `5e5edf9` - Federal legislation + U.S. Code parser prototype
- `97f91e8` - Update pilot.json with P0 for codified_law_ingestion

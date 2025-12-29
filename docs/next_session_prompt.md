# Recommended: vectors_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 400. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 400 completed `municipal_code_e2e_cloud` - 2,366 municipal code sections are now in Postgres. With SQL data ingestion complete for most data types, the next step is building vector indexes in pgvector from the cloud SQL data.

## Task

Build vector indexes in pgvector FROM cloud SQL data (not migrated from ChromaDB):

| Data Type | SQL Source | Vector Status |
|-----------|------------|---------------|
| chunks | `chunks` table | TODO |
| decisions | `decisions` table | TODO |
| issues | `issues` table | TODO |
| municipal_code | `municipal_code` table (2,366 rows) | TODO |
| transcripts | `transcripts` table (13 rows) | TODO |

## Key Files

- `packages/civic/src/civic/storage/pgvector_backend.py` - PgVectorBackend class
- `packages/civic-extraction/src/civic_extraction/cli/vectors.py` - CLI for vector operations
- `packages/civic/src/civic/storage/postgres_backend.py:527-563` - new municipal_code table schema

## Suggested Approach

1. Check if `PgVectorBackend.index_from_storage()` method exists or needs creation
2. Verify vectors CLI has `--cloud` mode that uses PgVectorBackend
3. Run `civic-extract vectors --jurisdiction city-san-rafael --cloud` for each data type
4. Verify indexes with `civic-extract vectors --stats --cloud`

## Pattern Reference

The note says: "Uses PgVectorBackend.index_from_storage() to embed from Postgres"

This suggests reading from SQL tables and embedding text content into pgvector collections.

## Tests to Run

```bash
# Verify vectors CLI exists
civic-extract vectors --help

# Check stats (may need --cloud flag)
civic-extract vectors --stats --cloud
```

## Success Criteria

- [ ] Vector indexes exist for all data types in pgvector
- [ ] `civic-extract vectors --stats --cloud` shows counts for each collection
- [ ] Semantic search works against cloud vectors
- [ ] Mark `vectors_e2e_cloud` as ready in pilot.json

# Recommended: deprecate_chromadb_legal_indexer

**Priority:** P0
**Area:** data_architecture > embedding_infrastructure
**Date:** 2026-01-03

> This is recommended context from Session 456. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 456 completed `shared_config_package` - created `packages/civic-config/` with jurisdiction configuration, fixing the cross-layer import violation where civic-services imported from civic.jurisdiction.

## Problem

After legislation uses pgvector like other corpus types (completed in `legislation_full_text_chunking`), the separate ChromaDB path via `LegalIndexer` is redundant:
- `civic/_internal/legal/embeddings/indexer.py` - ChromaDB-specific indexer
- This creates two vector store paths: pgvector (primary) and ChromaDB (legacy)

## Recommended Task

Remove the `LegalIndexer` → ChromaDB path to simplify architecture:
- One vector store (pgvector)
- One search path
- `LegalChunker` remains (it's the chunking logic, not storage)

## Key Files

- `packages/civic/src/civic/_internal/legal/embeddings/indexer.py` - LegalIndexer to remove
- `packages/civic/src/civic/_internal/legal/embeddings/__init__.py` - Update exports
- Check for imports of LegalIndexer across codebase

## Suggested Approach

1. Search for all usages of `LegalIndexer` and `legal_indexer`
2. Verify all legal corpus indexing now goes through pgvector path
3. Remove `indexer.py` and update `__init__.py` exports
4. Update any imports that reference the removed code
5. Run tests to verify nothing breaks

## Tests to Run

```bash
pytest packages/civic/tests/test_storage_protocols.py -v -q --override-ini="addopts="
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v -q --override-ini="addopts="
```

## Success Criteria

- [ ] `civic/_internal/legal/embeddings/indexer.py` deleted
- [ ] No remaining imports of LegalIndexer
- [ ] All tests pass
- [ ] Legal corpus search still works via pgvector

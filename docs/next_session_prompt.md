# Recommended: Marin County Code

**Priority:** P0 (IMMEDIATE)
**Area:** data_readiness > county_context
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 353 completed `data_dictionary` - updated docs/DATA_DICTIONARY.md with all core models. (160/174 items ready, 92.0%)

**The opportunity:** Index Marin County code sections relevant to San Rafael pilot (housing, land use). County regulations often supersede or complement city code.

## Existing Municode Infrastructure

The codebase already has `MunicipalCodeCorpus` that fetches from Municode's public API:

```
packages/civic/src/civic/_internal/legal/corpus/municipal.py
```

Key features:
- `JURISDICTION_MAP` - Add `"county-marin": {"state": "CA", "name": "Marin County"}`
- `stream_sections()` - Fetches structured code via API
- `to_documents()` - Converts to ChromaDB-ready format
- Rate limiting and caching built-in

## Recommended Task

1. **Check Municode** - Verify Marin County is available: https://www.municode.com/library/ca
2. **Extend JURISDICTION_MAP** - Add county-marin entry
3. **Create indexing script** - Similar to San Rafael municipal code
4. **Filter relevant titles** - Housing (Title 22?), Land Use, Health & Safety
5. **Index to ChromaDB** - `county-marin_municipal_code` collection
6. **Wire into what_applies()** - Include county results in regulatory stack

## Key Files

```
packages/civic/src/civic/_internal/legal/corpus/municipal.py  # MunicipalCodeCorpus class
packages/civic/src/civic/storage/embeddings.py               # CivicEmbeddings.build_municipal_code_index()
packages/civic/tests/test_integration_rag_san_rafael.py      # Test patterns
```

## Success Criteria

- [ ] Marin County code sections indexed in ChromaDB
- [ ] Relevant sections appear in `what_applies()` queries
- [ ] pilot.json `marin_county_code` marked as ready

## Upcoming P1 Items

1. **san_rafael_municipal_funding** - City funding programs (housing trust, inclusionary housing)
2. **feedback_channel** - User feedback mechanism (P2)

## Pilot Progress

- 160/174 items ready (92.0%)
- 14 items remaining
- P0: marin_county_code (this item)

# Recommended: San Rafael Municipal Funding

**Priority:** P0 (IMMEDIATE)
**Area:** data_readiness > municipal_context
**Date:** 2025-12-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 354 completed `marin_county_code` - indexed 776 Marin County code sections and integrated county ordinances into `what_applies()`. Also added configurable parsing patterns for municipality extensibility. (161/174 items ready, 92.5%)

**The opportunity:** Research and index San Rafael municipal funding programs (housing trust fund, inclusionary housing, general fund allocations, local tax measures) to complete the local funding picture.

## Existing Infrastructure

The codebase has patterns for funding program indexing:

```
data/funding/county/marin/housing_programs.json     # County housing programs (existing)
data/funding/county/marin/homelessness_programs.json # County homelessness (existing)
packages/civic/src/civic/_internal/meetings/embeddings.py:1701-1835  # build_county_programs_index()
```

## Recommended Task

1. **Research** - Find San Rafael municipal funding programs:
   - Housing trust fund
   - Inclusionary housing requirements/in-lieu fees
   - General fund housing allocations
   - Local tax measures (Measure A, etc.)

2. **Create data file** - `data/funding/municipal/san-rafael/housing_programs.json`

3. **Index to ChromaDB** - Adapt `build_county_programs_index()` pattern or create `build_municipal_programs_index()`

4. **Integrate into what_applies()** - Add municipal funding to regulatory stack

## Key Files

```
data/funding/county/marin/housing_programs.json              # Pattern to follow
packages/civic/src/civic/_internal/meetings/embeddings.py    # Indexing infrastructure
packages/civic/src/civic/context.py:177-213                  # County code integration (pattern)
pilot.json:918-924                                           # Item definition
```

## Suggested Approach

1. Search San Rafael city website for housing programs, budget documents
2. Check city council meeting minutes for funding allocations
3. Structure as JSON following county programs pattern
4. Create indexing method for municipal programs
5. Test integration with `what_applies("housing")`

## Success Criteria

- [ ] `data/funding/municipal/san-rafael/housing_programs.json` created with program data
- [ ] Municipal programs indexed in ChromaDB
- [ ] Programs appear in `what_applies()` results
- [ ] pilot.json `san_rafael_municipal_funding` marked as ready

## Pilot Progress

- 161/174 items ready (92.5%)
- 13 items remaining
- P0: san_rafael_municipal_funding (this item)

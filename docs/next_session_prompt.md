# Recommended: Legislation Ingestion and Data Quality Validation

**Priority:** P0 (User-mandated)
**Area:** Data ingestion + Quality assurance
**Date:** 2026-01-01

> This session should be entirely dedicated to legislation and data quality. No other work.

## Session Goals

1. **Finish legislation ingestion** - Complete CA bills, add federal legislation
2. **Legislation indexing** - Ensure all legislation chunks are indexed with COPY optimization
3. **Interactive stress testing** - Validate data quality and query capabilities

## Current State

```
CA legislation: 2,839 chunks indexed
Federal legislation: Not yet ingested
Previous issue: LegiScan API query limit exceeded
```

## Task 1: Finish Legislation Ingestion

```bash
# Check LegiScan API status
grep LEGISCAN .env

# Explore legislation extraction code
ls packages/civic-extraction/src/civic_extraction/legislation/
```

Key files:
- `packages/civic-extraction/src/civic_extraction/legislation/` - LegiScan client
- API limit issue needs investigation - may need pagination or rate limiting

## Task 2: Legislation Indexing

```bash
# Current CA legislation stats
modal run scripts/modal_vectors.py --stats-only --jurisdiction state-CA

# Reindex with COPY optimization (if needed)
modal run scripts/modal_vectors.py --corpus legislation --reindex --parallel 4 --jurisdiction state-CA
```

Session 426 added COPY optimization - use it for fast indexing.

## Task 3: Interactive Stress Testing

Test queries against indexed data:

```python
from civic import Civic
c = Civic("san-rafael")

# Test municipal code
c.what_applies("accessory dwelling unit")
c.what_applies("parking requirements")

# Test legislation (once indexed)
c.what_applies("housing legislation")  # Should include state bills
```

Validate:
- Query relevance (do results match intent?)
- Score thresholds (are scores reasonable?)
- Cross-corpus results (municipal + legislation together?)

## Session 426 Context

- Implemented PostgreSQL COPY for 6x faster vector indexing
- All San Rafael corpora indexed (municipal_code, transcripts, chunks)
- Commit: `7a88bf0`

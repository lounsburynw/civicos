# Pagination Protocol Update Spec

**Status:** Done (Phases 1-2 complete: protocol + both backends)
**Date:** 2026-03-11
**Launch.json item:** `pagination_protocol_update`

## Problem

`StorageBackend.get_*()` methods return `List[dict]` with no pagination. This works for single-jurisdiction queries but breaks down for:

1. **Cross-jurisdiction fan-out** — `FederatedDataSource` would call `get_decisions()` across N backends and merge. Without pagination, every backend returns its full dataset.
2. **Large corpora** — San Rafael has 16,175 municipal code entries and 17,719 legislation records. Returning all of them in a single call is wasteful for paginated UIs.
3. **API responses** — the REST API currently returns unbounded lists. Adding pagination at the API layer without storage-level support means loading everything into memory first.

## Design Principles

1. **Backward compatible** — existing callers that don't pass pagination params get current behavior (all results).
2. **Simple** — offset/limit, not cursor-based. Civic data is append-mostly and doesn't have the consistency requirements that need cursors.
3. **Uniform** — same pagination interface on every `get_*()` method.
4. **Optional** — pagination params have defaults that preserve current behavior.

## Decisions Required

### 1. Offset/Limit vs Cursor

**Offset/limit:**
- Simple, stateless, well-understood
- Can skip pages, jump to arbitrary offset
- Performance degrades at high offsets on large tables (`OFFSET 10000` still scans rows)
- Good enough for our data sizes (max ~18K rows in any table)

**Cursor-based:**
- Consistent under concurrent writes
- Performs well at any depth
- More complex API (opaque cursor token)
- Overkill for our access patterns

**Decision:** Offset/limit. Our largest table is ~18K rows. Offset performance is fine up to ~100K.

### 2. Protocol Change

Current (example from `StorageBackend`):

```python
def get_decisions(self, jurisdiction_id: str) -> List[dict]: ...
def get_meetings(self, jurisdiction_id: str) -> List[dict]: ...
def get_municipal_code(self, jurisdiction_id: str) -> List[dict]: ...
```

Proposed:

```python
def get_decisions(
    self,
    jurisdiction_id: str,
    limit: Optional[int] = None,      # None = all results (backward compat)
    offset: int = 0
) -> List[dict]: ...
```

**Return type stays `List[dict]`** — no wrapper object. Total count is available via existing `get_decision_count()` methods. Callers that need total + page can call both.

### 3. Which Methods Get Pagination

All `get_*()` methods that return lists:

| Method | Current Max Rows | Paginate? |
|--------|-----------------|-----------|
| `get_meetings()` | ~100 | Yes |
| `get_decisions()` | ~50 | Yes |
| `get_transcripts()` | ~20 | Yes |
| `get_chunks()` | ~5,000 | Yes |
| `get_issues()` | ~1,700 | Yes |
| `get_budget_items()` | ~60 | Yes |
| `get_municipal_code()` | ~16,000 | Yes |
| `get_legislation()` | ~17,000 | Yes |
| `get_videos()` | ~20 | Yes |
| `get_agenda_items()` | ~200 | Yes |

Apply uniformly. Even small tables get the parameter for protocol consistency.

### 4. Sub-Protocol Updates

The 6 sub-protocols (`ContentStorage`, `LegislationStorage`, etc.) must all be updated. Each `get_*()` method gains the same `limit`/`offset` signature.

## Implementation

### Phase 1: Protocol + PostgresBackend
1. Update all sub-protocol definitions in `storage/protocols/`
2. Update `StorageBackend` composite protocol in `storage/backend.py`
3. Update `PostgresBackend` — add `LIMIT` and `OFFSET` clauses to SQL queries
4. Existing callers unchanged (default `limit=None` returns all)

### Phase 2: SQLiteBackend
5. Update `SQLiteBackend` with same changes

### Phase 3: API Layer
6. Add `limit` and `offset` query params to REST API endpoints
7. Add `X-Total-Count` response header for paginated responses
8. Default API page size: 50

### Phase 4: Cross-Jurisdiction (depends on testbed)
9. `what_happened_across()` uses pagination internally to limit per-jurisdiction results
10. Default: 10 results per jurisdiction in cross-jurisdiction queries

## SQL Pattern

```sql
-- Current
SELECT * FROM meetings WHERE jurisdiction_id = %s ORDER BY meeting_datetime DESC;

-- With pagination
SELECT * FROM meetings WHERE jurisdiction_id = %s ORDER BY meeting_datetime DESC
LIMIT %s OFFSET %s;

-- limit=None → omit LIMIT clause entirely (backward compat)
```

## Test Strategy

- Unit test: `limit=10` returns exactly 10 results
- Unit test: `offset=5, limit=5` returns results 6-10
- Unit test: `limit=None` returns all results (backward compat)
- Unit test: `offset` beyond result count returns empty list
- Integration test: paginated API endpoint returns correct `X-Total-Count`
- Both backends: identical behavior for PostgresBackend and SQLiteBackend

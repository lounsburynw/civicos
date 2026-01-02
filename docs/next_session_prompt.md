# Recommended: Budget Schema

**Priority:** P0
**Area:** data_readiness > budget
**Date:** 2026-01-02

> This is recommended context from Session 433. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 433 completed corpus protocol conformance - added 17 corpus methods to StorageBackend protocol. The codebase is now architecturally clean with all storage methods properly declared.

Next up: **Budget data pipeline** - enabling queries like "How much does San Rafael spend on Police?" The first step is creating the budget schema (budget_items table) in both SQLite and Postgres backends.

## Recommended Task

Create the `budget_items` table schema following the established pattern for corpus types (legislation, codified_law, etc.).

## Key Files

- `packages/civic/src/civic/storage/backend.py` - Add budget methods to StorageBackend protocol
- `packages/civic/src/civic/storage/postgres_backend.py` - Implement budget methods
- `packages/civic/src/civic/storage/sqlite_backend.py` - Add budget stubs
- `docs/BUDGET_EXTRACTION.md` - Schema design docs (if exists, reference it)

## Suggested Schema (budget_items)

Based on the artifact description ("amounts in cents for precision"):

```sql
CREATE TABLE budget_items (
    id SERIAL PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    fiscal_year TEXT NOT NULL,           -- e.g., "FY2025-26"
    department TEXT,                      -- e.g., "Police", "Fire", "Parks"
    fund TEXT,                            -- e.g., "General Fund", "Enterprise"
    category TEXT,                        -- e.g., "Personnel", "Operating", "Capital"
    line_item TEXT NOT NULL,              -- Budget line description
    amount_cents BIGINT NOT NULL,         -- Amount in cents for precision
    currency TEXT DEFAULT 'USD',
    budget_type TEXT,                     -- "adopted", "revised", "actual"
    source_document TEXT,                 -- URL or filename of source PDF
    source_page INTEGER,                  -- Page number in source
    metadata JSONB,                       -- Extra fields
    created_at TIMESTAMP DEFAULT NOW(),
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP                    -- Temporal versioning
);

CREATE INDEX idx_budget_items_jurisdiction ON budget_items(jurisdiction_id);
CREATE INDEX idx_budget_items_fiscal_year ON budget_items(jurisdiction_id, fiscal_year);
CREATE INDEX idx_budget_items_department ON budget_items(jurisdiction_id, department);
```

## Suggested Approach

1. **Add budget methods to StorageBackend protocol** (`backend.py`):
   - `store_budget_items(jurisdiction_id, items, as_of) -> int`
   - `get_budget_items(jurisdiction_id, fiscal_year, department, fund, limit) -> List[Dict]`
   - `get_budget_items_count(jurisdiction_id, fiscal_year) -> int`
   - `get_budget_summary(jurisdiction_id, fiscal_year) -> Dict` (aggregates by department/fund)

2. **Implement in PostgresBackend** with temporal versioning (follow codified_law pattern)

3. **Add SQLiteBackend stubs** (return empty/0 like other corpus methods)

4. **Add test mocks** in test_storage_protocols.py

## Tests to Run

```bash
# Protocol compliance
pytest packages/civic/tests/test_storage_protocols.py -v

# Smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] StorageBackend protocol declares budget methods
- [ ] PostgresBackend implements budget_items table + methods
- [ ] SQLiteBackend has stub implementations
- [ ] Protocol tests pass (69+ tests)
- [ ] Smoke tests pass

## Related Items (not in scope this session)

The budget pipeline has 5 items total:
1. **budget_schema** (THIS SESSION - P0)
2. budget_etl_template - AI extraction prompt
3. san_rafael_fy2526_budget - Extract actual budget data
4. budget_query_api - Civic.budget() method
5. decision_financial_extraction - Link decisions to budget impact

## Notes

- Use BIGINT cents instead of DECIMAL to avoid floating-point issues
- San Rafael FY2025-26 budget is ~$192M with ~50-100 line items
- Source: https://www.cityofsanrafael.org/city-budget/

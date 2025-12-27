# Recommended: api_cloud_storage_backend

**Priority:** P0
**Area:** data_architecture > data_source_unification
**Date:** 2025-12-27

> This is recommended context from Session 386. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 386 completed `e2e_fresh_ingestion` - the final cloud ETL item. All 10 cloud ETL items are now done. However, we discovered that the **Data Browser UI shows local SQLite data instead of cloud Postgres data**.

**The Problem:**
- CLI tools with `--cloud` flag correctly read from Postgres (46 meetings, 1,330 issues)
- API server reads from local SQLite (`data/civic_participation.db`) showing only 17 meetings
- Data Browser ERD diagram shows stale/incomplete data

## Cloud Storage Stats (Verified)

| Data Type | Cloud (Postgres) | Local (SQLite) |
|-----------|------------------|----------------|
| Meetings | 46 | 17 |
| Chunks | 44 | ? |
| Issues | 1,330 | 1,340 |
| Decisions | 0 | 186 |

## Recommended Task

Wire the API server to use `get_storage_backend()` factory, which automatically picks `PostgresBackend` when `DATABASE_URL` environment variable is set.

## Key Files to Modify

1. **`packages/civic-services/src/civic_services/servers/civic_api_integrated.py`**
   - ERD/Data Browser endpoints (lines ~7800-8000)
   - Admin status endpoints
   - Currently imports SQLite directly, should use `get_storage_backend()`

2. **`packages/civic/src/civic/storage/__init__.py`**
   - `get_storage_backend(connection_string)` factory function
   - Returns `PostgresBackend` for postgres:// URLs, `SQLiteBackend` for file paths

## Suggested Approach

### Step 1: Find all SQLite imports in API server
```bash
grep -n "SQLiteBackend\|civic_state.db\|civic_participation.db" packages/civic-services/src/civic_services/servers/civic_api_integrated.py
```

### Step 2: Replace with storage factory
```python
# Before
from civic.storage.sqlite_backend import SQLiteBackend
backend = SQLiteBackend("data/civic_participation.db")

# After
from civic.storage import get_storage_backend
import os
db_url = os.environ.get("DATABASE_URL", "data/civic_participation.db")
backend = get_storage_backend(db_url)
```

### Step 3: Test with dev servers
```bash
# Ensure DATABASE_URL is in .env
./scripts/dev.sh
# Check Data Browser - should show 46 meetings
```

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q

# Storage protocol tests (both backends)
pytest packages/civic/tests/test_storage_protocols.py -v
```

## Success Criteria

- [ ] Data Browser shows 46 meetings (from Postgres) when DATABASE_URL is set
- [ ] Data Browser still works with local SQLite when DATABASE_URL is not set
- [ ] Admin status endpoints reflect cloud data
- [ ] All existing tests pass

## Notes

- This completes the cloud migration - CLI and API will both use Postgres
- Backward compatible - falls back to SQLite if no DATABASE_URL
- May need to update multiple endpoints in civic_api_integrated.py

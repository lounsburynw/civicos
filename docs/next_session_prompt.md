# Recommended: Storage Stats Abstraction

**Priority:** P0 (IMMEDIATE)
**Area:** data_architecture > modular_etl
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 338 added storage stats to the admin dashboard, but introduced a **layer boundary violation**: the API server (`civic-services`) imports `SQLiteBackend` directly from `civic.storage`. This breaks the abstraction that enables backend swapping.

**Why this matters:**
1. **Open-source adoption**: Other municipalities copying this pattern will hard-code SQLite
2. **PostgreSQL migration**: Current code will break when switching backends
3. **Architecture**: Coordination layer shouldn't import Core layer internals

## Recommended Task

Fix the layer violation by exposing storage stats via the public `Civic` API:

1. Add `Civic.get_storage_stats(jurisdiction_id)` method to core API
2. Update `civic_api_integrated.py` to call `Civic.get_storage_stats()` instead of importing `SQLiteBackend` directly
3. Keep the same API response structure (no frontend changes needed)

## Key Files

**Core API (add method):**
- `packages/civic/src/civic/civic.py` - Main Civic class, add `get_storage_stats()`

**Storage backend (reference):**
- `packages/civic/src/civic/storage/backend.py:14-53` - `StorageStats` dataclass
- `packages/civic/src/civic/storage/sqlite_backend.py:408-481` - `SQLiteBackend.get_stats()`

**API server (update import):**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py:7456-7481` - Current direct import to replace

## Suggested Approach

1. **Add method to Civic class:**
   ```python
   def get_storage_stats(self, jurisdiction_id: str = None) -> StorageStats:
       """Get storage statistics for dashboard display."""
       jurisdiction_id = jurisdiction_id or self.jurisdiction_id
       return self._storage_backend.get_stats(jurisdiction_id)
   ```

2. **Update API server:**
   ```python
   # Before (layer violation)
   from civic.storage.sqlite_backend import SQLiteBackend
   storage_backend = SQLiteBackend(str(state_db_path))

   # After (clean abstraction)
   civic = Civic(jurisdiction_id)
   storage_stats = civic.get_storage_stats()
   ```

3. **Verify existing tests still pass**

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Storage tests
pytest packages/civic/tests/ -k "storage" -q --override-ini="addopts="
```

## Success Criteria

- [ ] `Civic.get_storage_stats()` method exists and returns `StorageStats`
- [ ] `civic_api_integrated.py` no longer imports from `civic.storage`
- [ ] Admin dashboard still shows storage stats (no regression)
- [ ] All existing tests pass
- [ ] pilot.json `storage_stats_abstraction` marked as ready

## Next Up: PostgreSQL Backend (P1)

After this abstraction is clean, the next step is `postgres_backend_implementation`:
- Create `PostgresBackend` implementing `StorageBackend` protocol
- Proves the modularity for open-source adopters
- Both backends pass the same test suite

## Pilot Progress

- 141/166 items ready (84.9%)
- 27 items remaining (added 2 new items)
- P0: storage_stats_abstraction (this item)

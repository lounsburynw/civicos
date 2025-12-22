# Recommended: PostgreSQL Backend Implementation

**Priority:** P0 (IMMEDIATE)
**Area:** city_onboarding > orchestration
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 339 completed `storage_stats_abstraction`, fixing a layer boundary violation. The storage abstraction is now clean - the API server uses `Civic.get_storage_stats()` instead of importing `SQLiteBackend` directly.

**Why PostgresBackend is next:**
1. **Prove modularity**: Validates the StorageBackend protocol works for multiple implementations
2. **Open-source adoption**: Municipalities with existing Postgres infrastructure get a clear path
3. **Production readiness**: Postgres is better suited for multi-user production deployments

## Recommended Task

Create `PostgresBackend` class implementing the `StorageBackend` protocol:

1. Create `packages/civic/src/civic/storage/postgres_backend.py`
2. Implement all 5 protocol methods (validate, store_meetings, get_meetings, get_stats, delete_meetings)
3. Both SQLite and Postgres backends should pass the same test suite

## Key Files

**Protocol definition (implement this):**
- `packages/civic/src/civic/storage/backend.py:86-217` - `StorageBackend` protocol with 5 methods

**Reference implementation (follow patterns):**
- `packages/civic/src/civic/storage/sqlite_backend.py` - SQLiteBackend (549 lines)
- `packages/civic/src/civic/storage/sqlite_backend.py:62-65` - `backend_type` property
- `packages/civic/src/civic/storage/sqlite_backend.py:67-136` - `validate()` method
- `packages/civic/src/civic/storage/sqlite_backend.py:138-260` - `store_meetings()` method
- `packages/civic/src/civic/storage/sqlite_backend.py:262-405` - `get_meetings()` method
- `packages/civic/src/civic/storage/sqlite_backend.py:408-492` - `get_stats()` method

**Existing tests (adapt for Postgres):**
- `packages/civic/tests/test_sqlite_backend.py` - 26 tests to replicate
- `packages/civic/tests/test_storage_protocols.py` - Protocol conformance tests

## Suggested Approach

1. **Create postgres_backend.py** with class structure:
   ```python
   class PostgresBackend:
       def __init__(self, connection_string: str):
           self._conn_string = connection_string

       @property
       def backend_type(self) -> str:
           return "postgres"

       def validate(self) -> StorageValidationResult: ...
       def store_meetings(self, ...) -> int: ...
       def get_meetings(self, ...) -> List[Dict]: ...
       def get_stats(self, jurisdiction_id: str) -> StorageStats: ...
       def delete_meetings(self, ...) -> int: ...
   ```

2. **Use psycopg2 or asyncpg** for Postgres connectivity

3. **Mirror SQLite schema** - same tables (meetings, agenda_items) with temporal versioning (valid_from, valid_to)

4. **Add protocol compliance check** at module end (like sqlite_backend.py:538-543)

5. **Export from __init__.py** - add PostgresBackend to `civic.storage`

## Tests to Run

```bash
# Existing SQLite tests (should still pass)
pytest packages/civic/tests/test_sqlite_backend.py -q --override-ini="addopts="

# Protocol conformance
pytest packages/civic/tests/test_storage_protocols.py -q --override-ini="addopts="

# New Postgres tests (create these)
pytest packages/civic/tests/test_postgres_backend.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `PostgresBackend` class exists in `civic/storage/postgres_backend.py`
- [ ] Implements all 5 `StorageBackend` protocol methods
- [ ] Protocol compliance check passes (`isinstance(backend, StorageBackend)`)
- [ ] Test suite mirrors `test_sqlite_backend.py` structure
- [ ] `get_stats()` returns `metadata={"backend_type": "postgres"}`
- [ ] pilot.json `postgres_backend_implementation` marked as ready

## Configuration

Postgres connection should use environment variable:
```python
CIVIC_POSTGRES_URL = "postgresql://user:pass@localhost:5432/civic"
```

For testing, use pytest fixture with temp database or mock.

## Pilot Progress

- 142/168 items ready (84.5%)
- 26 items remaining
- P0: postgres_backend_implementation (this item)

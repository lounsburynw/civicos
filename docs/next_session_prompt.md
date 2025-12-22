# Recommended: Operations Backend Protocol

**Priority:** P0 (IMMEDIATE)
**Area:** admin_operations > operation_status
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 341 added operation tracking (create, update, complete, get operations) directly to StateManager, which is SQLite-only. For production Postgres deployment, these methods need to go through the StorageBackend protocol like other persistence operations.

**Current state:**
- `StateManager` has operations table + methods (SQLite)
- `StorageBackend` protocol in `backend.py` has no operation methods
- `PostgresBackend` implements StorageBackend but can't do operation tracking

**The problem:** Operation tracking won't work in production until this is fixed.

## Recommended Task

Add operation tracking to the StorageBackend protocol and implement in PostgresBackend:

1. Add protocol methods to `StorageBackend` in `backend.py`
2. Implement in `PostgresBackend`
3. Either refactor StateManager to use protocol, or create SQLiteBackend wrapper

## Key Files

**Protocol definition:**
- `packages/civic-services/src/civic_services/storage/backend.py` - StorageBackend protocol (add methods here)

**Existing SQLite implementation (reference):**
- `packages/civic-services/src/civic_services/storage/state_manager.py:751-1030` - Operations methods to port:
  - `create_operation()` (line 751)
  - `update_operation_status()` (line 791)
  - `complete_operation()` (line 851)
  - `get_operation()` (line 897)
  - `get_operations()` (line 938)

**Postgres implementation:**
- `packages/civic-services/src/civic_services/storage/postgres_backend.py` - Add implementations here

**Tests:**
- `packages/civic-services/tests/storage/test_postgres_backend.py` - Add operation tests

## Suggested Approach

1. **Add to StorageBackend protocol** (`backend.py`):
   ```python
   def create_operation(self, operation_id: str, name: str, jurisdiction_id: str) -> bool: ...
   def update_operation_status(self, operation_id: str, status: str, ...) -> bool: ...
   def complete_operation(self, operation_id: str, result: Dict, error: Optional[str]) -> bool: ...
   def get_operation(self, operation_id: str) -> Optional[Dict]: ...
   def get_operations(self, jurisdiction_id: Optional[str], status: Optional[str], limit: int) -> List[Dict]: ...
   ```

2. **Implement in PostgresBackend** - follow existing patterns (use `self.pool`, async queries)

3. **Add tests** - similar to existing StorageBackend tests

4. **Decide StateManager approach:**
   - Option A: StateManager delegates to StorageBackend (if injected)
   - Option B: Create SQLiteBackend that wraps StateManager operations
   - Option C: Leave StateManager for dev, use PostgresBackend for prod (current pattern)

## Tests to Run

```bash
# Storage backend tests
pytest packages/civic-services/tests/storage/ -v --override-ini="addopts="

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] StorageBackend protocol has operation tracking methods
- [ ] PostgresBackend implements all operation methods
- [ ] Tests pass for Postgres operation tracking
- [ ] Existing SQLite flow still works (StateManager)
- [ ] pilot.json `operations_backend_protocol` marked as ready

## Pilot Progress

- 147/169 items ready (87.0%)
- 22 items remaining
- P0: operations_backend_protocol (this item)

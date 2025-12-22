# Recommended: Storage Backend Protocol Implementation

**Priority:** P0 (IMMEDIATE)
**Area:** city_onboarding > orchestration
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 336 conducted an ETL production audit that identified a **critical architectural gap**:

**Storage backend protocols are defined but NOT implemented.** The documented 4-stage pattern (discover → ingest → store → index) is broken - pipeline goes directly from ingest to index, reading from memory instead of persistent storage.

This creates data loss risk: if indexing fails, ingested data is lost.

## Audit Findings

1. **StorageBackend protocol** defined at `packages/civic/src/civic/storage/backend.py:85-218` - no implementation exists
2. **VectorBackend protocol** defined at `packages/civic/src/civic/storage/vector.py:132-278` - no implementation exists
3. **Pipeline.py:552-554** passes in-memory `_ingested_meetings` to index stage instead of reading from storage
4. **StateManager** exists but doesn't implement StorageBackend protocol

## Recommended Task

Implement the storage layer integration in 3 sequential steps:

### Step 1: SQLiteBackend Implementation
Create `packages/civic/src/civic/storage/sqlite_backend.py`:
```python
class SQLiteBackend:
    """Implements StorageBackend protocol, wrapping StateManager."""

    @property
    def backend_type(self) -> str: ...
    def validate(self) -> StorageValidationResult: ...
    def store_meetings(self, meetings: List[Meeting]) -> int: ...
    def get_meetings(self, jurisdiction_id: str, ...) -> List[Dict]: ...
    def get_stats(self) -> StorageStats: ...
    def delete_meetings(self, ...) -> int: ...
```

### Step 2: Pipeline Store Stage
Update `packages/civic-extraction/src/civic_extraction/pipeline.py`:
- Add `store` stage between `ingest` and `index`
- Store stage calls `storage_backend.store_meetings()`
- Update `StageState` enum and stage list

### Step 3: Index Reads From Storage
Update pipeline `_run_index()` to:
- Call `storage_backend.get_meetings()`
- Pass retrieved meetings to index target
- Remove direct use of `_ingested_meetings`

## Key Files

- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol definition
- `packages/civic/src/civic/storage/vector.py` - VectorBackend protocol definition
- `packages/civic/tests/test_storage_protocols.py` - Existing protocol tests (18 passing)
- `packages/civic-extraction/src/civic_extraction/pipeline.py` - Pipeline class to update
- `packages/civic-services/src/civic_services/storage/state_manager.py` - Existing SQLite storage to wrap

## Success Criteria

- [ ] SQLiteBackend class implements StorageBackend protocol
- [ ] Pipeline has 4 stages: discover → ingest → store → index
- [ ] Index stage reads from storage, not memory
- [ ] Existing tests pass + new tests for SQLiteBackend
- [ ] pilot.json items updated: sqlite_backend_implementation, pipeline_store_stage, index_reads_from_storage

## Dependencies

Once storage backend is complete, these items can proceed:
- `status_page` - Dashboard aligned with 4-stage pipeline
- `pipeline_flow_visualization` - Show Available → Ingested → Stored → Indexed
- `operation_progress_panel` - Server-side progress tracking
- `operation_history_table` - Operation history display

## Pilot Progress

- 135/166 items ready (81.3%)
- 31 items remaining
- P0: storage_backend_protocol (this item)

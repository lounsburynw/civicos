# Recommended: Running Operations - Server-Side Progress Tracking

**Priority:** P0 (IMMEDIATE)
**Area:** admin_operations > operation_status
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 338 completed the **status_page** P0 - aligning the admin dashboard with the 4-stage pipeline (Coverage → Ingested → Stored → Indexed). The dashboard now shows storage stats from `SQLiteBackend.get_stats()`.

**The current operation tracking is client-side only.** When a user triggers an operation (fetch meetings, transcribe videos), the timer runs in the browser. If they refresh or close the tab, they lose visibility into the running operation. This is the #1 audit finding blocking dashboard completion.

## Recommended Task

Implement server-side operation state tracking:
1. Create operations table in SQLite to persist running/completed operations
2. Add `GET /api/admin/operations/current` endpoint to check running operation
3. Add `GET /api/admin/operations` endpoint for operation history
4. Update frontend to poll for operation status instead of client-side timer

## Key Files

**Backend (main work):**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py:7588-7831` - Existing trigger handlers (`handle_admin_trigger`, `_trigger_fetch_meetings`, etc.)
- `packages/civic-services/src/civic_services/core/config.py` - `get_user_path()` for database paths

**Frontend (will consume new endpoints):**
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue:508-527` - Current client-side timer logic

**Reference:**
- `packages/civic/src/civic/storage/sqlite_backend.py` - Pattern for SQLite table creation

## Suggested Approach

1. **Create operations table schema:**
   ```sql
   CREATE TABLE operations (
       id TEXT PRIMARY KEY,
       operation TEXT NOT NULL,
       jurisdiction_id TEXT NOT NULL,
       status TEXT NOT NULL,  -- 'running', 'completed', 'failed'
       started_at TIMESTAMP NOT NULL,
       completed_at TIMESTAMP,
       result_json TEXT,
       error TEXT
   )
   ```

2. **Add operation tracking helpers:**
   - `start_operation(op_name, jurisdiction)` → returns operation_id
   - `complete_operation(op_id, result)` → marks complete
   - `fail_operation(op_id, error)` → marks failed
   - `get_current_operation(jurisdiction)` → returns running op or None

3. **Add API endpoints:**
   - `GET /api/admin/operations/current?jurisdiction=san-rafael` → current running operation
   - `GET /api/admin/operations?jurisdiction=san-rafael&limit=10` → recent operations

4. **Update triggers to use tracking:**
   - Wrap existing `_trigger_*` methods to start/complete operations
   - Store result counts in `result_json`

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# After implementation, test the new endpoints manually
curl "http://localhost:8001/api/admin/operations/current?jurisdiction=san-rafael"
```

## Success Criteria

- [ ] Operations table created in civic_state.db
- [ ] Running operations persist across browser refresh
- [ ] `GET /api/admin/operations/current` returns running operation or null
- [ ] `GET /api/admin/operations` returns last N operations with results
- [ ] pilot.json `running_operations` marked as ready

## Dependencies

This item unblocks:
- `operation_progress_panel` - Real-time progress in dashboard
- `operation_history_table` - Table showing past operations

## Pilot Progress

- 141/166 items ready (84.9%)
- 25 items remaining
- P0: running_operations (this item)

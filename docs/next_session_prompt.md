# Recommended: Status Page - 4-Stage Pipeline Alignment

**Priority:** P0 (IMMEDIATE)
**Area:** ingestion_visibility > frontend_dashboard
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 337 completed the **storage_backend_protocol** P0 - the critical foundation that enables this work:
- Created `SQLiteBackend` implementing `StorageBackend` protocol
- Pipeline now has 4 stages: discover → ingest → **store** → index
- Index stage reads from storage backend when configured

**The admin dashboard is now out of sync.** It shows 3 stages (Available → Ingested → Indexed) but the actual pipeline has 4 stages. This causes confusion and doesn't show the "Stored" count which indicates data persistence before indexing.

## Recommended Task

Update `AdminStatusPage.vue` to display the 4-stage pipeline pattern:
- **Available** (from source inventory)
- **Ingested** (fetched and normalized)
- **Stored** (persisted to SQLite - NEW!)
- **Indexed** (in vector store)

## Key Files

**Frontend (main work):**
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue:77-145` - Pipeline stages UI

**API Endpoints (may need updates):**
- `packages/civic-services/src/civic_services/api/admin.py` - Admin status endpoint
- `packages/civic-services/src/civic_services/routes/admin_routes.py` - Admin routes

**Storage backend (for reference):**
- `packages/civic/src/civic/storage/sqlite_backend.py` - SQLiteBackend.get_stats()
- `packages/civic/src/civic/storage/backend.py` - StorageStats dataclass

## Suggested Approach

1. **Update API response** - Add "stored" count from SQLiteBackend.get_stats()
2. **Update frontend** - Add "Stored" stage between "Ingested" and "Indexed"
3. **Wire up storage stats** - Admin endpoint should call storage backend
4. **Test visually** - Run `/launch` and verify dashboard shows 4 stages

## Success Criteria

- [ ] Dashboard shows 4 stages: Available → Ingested → Stored → Indexed
- [ ] "Stored" count reflects SQLiteBackend.get_stats().meeting_count
- [ ] Visual freshness indicators work for Stored stage
- [ ] pilot.json status_page marked as ready

## Dependencies

This item was blocked by `storage_backend_protocol` which is now complete.

Once complete, these items become unblocked:
- `pipeline_flow_visualization` - Pipeline visual view
- Other dashboard improvements that depend on 4-stage pattern

## Pilot Progress

- 139/166 items ready (83.7%)
- 27 items remaining
- P0: status_page (this item)

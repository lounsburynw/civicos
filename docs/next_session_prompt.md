# Recommended: Operation History Table

**Priority:** P0 (IMMEDIATE)
**Area:** ingestion_visibility > frontend_dashboard
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 341 completed server-side operation tracking (running_operations, operation_history, operation_progress_panel). The backend now stores operation history in the `operations` table and exposes it via `GET /api/admin/operations`. The frontend already has the API methods (`getOperations()`) but lacks a UI table to display operation history.

**Why operation_history_table is next:**
1. **Builds on Session 341**: Backend + API + types are ready, just need the table component
2. **Admin visibility**: Operators need to see what ran, when, and whether it succeeded
3. **Quick win**: Most plumbing exists, primarily a Vue template addition

## Recommended Task

Add an operation history table to AdminStatusPage.vue showing the last 10 operations with expandable details.

## Key Files

**Frontend (add table here):**
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue:410-460` - Operation result display area
- `apps/civic-workspace/src/services/api.ts:1358-1382` - `getOperations()` method (already exists)
- `apps/civic-workspace/src/types/civic.ts:899-922` - `OperationsListResponse`, `OperationListItem` types

**Backend (already implemented in Session 341):**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py:7677-7743` - `serve_operations_list()`
- `packages/civic-services/src/civic_services/storage/state_manager.py:938-990` - `get_operations()`

## Suggested Approach

1. **Add state for operation history:**
   ```typescript
   const operationHistory = ref<OperationListItem[]>([]);
   ```

2. **Load history on mount and after operations complete:**
   ```typescript
   async function loadOperationHistory() {
     const response = await api.getOperations({
       jurisdiction: props.jurisdiction || 'san-rafael',
       limit: 10
     });
     operationHistory.value = response.operations;
   }
   ```

3. **Add table UI below the running operation banner:**
   - Show: operation name, started_at (formatted), duration, status badge
   - Status badges: green for completed, red for failed, yellow for running
   - Expandable row showing result counts (count_fetched, count_new, etc.)
   - Error message in expandable area if failed

4. **Style consistently** with existing AdminStatusPage patterns

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# TypeScript compilation
cd apps/civic-workspace && npm run type-check
```

## Success Criteria

- [ ] Operation history table displays in AdminStatusPage
- [ ] Shows last 10 operations with name, time, duration, status
- [ ] Status badges indicate success/failure/running
- [ ] Expandable rows show result details (counts, errors)
- [ ] History refreshes after each operation completes
- [ ] TypeScript compiles without errors
- [ ] pilot.json `operation_history_table` marked as ready

## Pilot Progress

- 146/168 items ready (86.9%)
- 22 items remaining
- P0: operation_history_table (this item)

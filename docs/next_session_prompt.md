# Recommended: Error Logs Display

**Priority:** P0 (IMMEDIATE)
**Area:** admin_operations > operation_status
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 342 added the operation history table to AdminStatusPage.vue. The table shows operation name, started time, duration, and status with expandable rows. Currently, errors are shown as a single line in expanded rows (`op.error`). The `error_logs` item asks for enhanced error display with log output.

**Current state:**
- Operations table stores: id, name, status, started_at, completed_at, result_json, error
- Frontend displays error in expandable row (line 511-514)
- Error field is a simple string from `complete_operation(error=...)`

**What's missing:**
- Multi-line error formatting (stack traces get truncated)
- Error filtering (show only failed operations)
- Richer error details from result_json (not just error string)

## Recommended Task

Enhance error display in the operation history table:
1. Format multi-line errors (stack traces) with proper whitespace
2. Add "Show errors only" filter toggle
3. Display additional error context from result_json if available

## Key Files

**Frontend (enhance display):**
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue:498-515` - Expandable detail row with error display
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue:461-517` - History table section
- `apps/civic-workspace/src/types/civic.ts:912-922` - OperationListItem type

**Backend (error storage):**
- `packages/civic-services/src/civic_services/storage/state_manager.py:851-895` - `complete_operation()` stores error string
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py:7677-7743` - `serve_operations_list()` returns operations

**API endpoint:**
- `GET /api/admin/operations?status=failed` - Filter by status (already supported)

## Suggested Approach

1. **Add error filter toggle:**
   ```typescript
   const showErrorsOnly = ref(false);
   const filteredHistory = computed(() =>
     showErrorsOnly.value
       ? operationHistory.value.filter(op => op.status === 'failed')
       : operationHistory.value
   );
   ```

2. **Enhance error display with pre-wrap:**
   ```vue
   <div v-if="op.error" class="detail-row error">
     <span class="detail-label">Error:</span>
     <pre class="error-log">{{ op.error }}</pre>
   </div>
   ```

3. **Add CSS for log display:**
   ```css
   .error-log {
     font-family: monospace;
     font-size: 11px;
     white-space: pre-wrap;
     background: rgba(239, 68, 68, 0.05);
     padding: 8px;
     border-radius: 4px;
     max-height: 200px;
     overflow-y: auto;
   }
   ```

4. **Update filter toggle UI** (add checkbox/toggle near section title)

## Tests to Run

```bash
# TypeScript compilation
cd apps/civic-workspace && npm run type-check

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Multi-line errors display with preserved formatting
- [ ] "Show errors only" toggle filters to failed operations
- [ ] Error log styling matches design system
- [ ] Stack traces readable with scroll for long content
- [ ] TypeScript compiles without errors
- [ ] pilot.json `error_logs` marked as ready

## Pilot Progress

- 147/168 items ready (87.5%)
- 21 items remaining
- P0: error_logs (this item)

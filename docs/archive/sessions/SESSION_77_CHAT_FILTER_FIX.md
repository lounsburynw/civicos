# Session 77: Fix Chat Navigation Filter Accumulation

**Issue**: Left sidebar filters were accumulating across separate chat queries instead of replacing them.

## Problem Analysis

### Original Behavior (Broken)
1. User: "show housing meetings" → Sidebar filters: `[housing]`
2. User: "show transportation meetings" → Sidebar filters: `[housing, transportation]` ❌

The sidebar accumulated topics instead of replacing them, making it confusing when navigating via chat.

### Root Cause
In `EventsPanel.vue:applyFilters()` (line 517-522), the topic filter used toggle logic without clearing previous filters:

```javascript
if (filters.topic) {
    if (!activeTopicFilters.value.has(filters.topic)) {
        toggleTopicFilter(filters.topic)  // ADDS to Set, never clears!
    }
}
```

## Solution: Context-Aware Filter Replacement

Added a `replace` parameter to distinguish between:
1. **Independent queries** (replace mode): Clear previous filters
2. **Complex queries** (accumulate mode): Add to existing filters

### Implementation

**1. EventsPanel.vue** - Added `replace` parameter:
```javascript
function applyFilters(filters: {
  topic?: ProjectType
  replace?: boolean  // NEW: Control accumulation (default: true)
}) {
  const shouldReplace = filters.replace !== false

  if (filters.topic) {
    if (shouldReplace) {
      activeTopicFilters.value.clear()  // Clear for independent queries
    }
    if (!activeTopicFilters.value.has(filters.topic)) {
      toggleTopicFilter(filters.topic)
    }
  }
}
```

**2. ChatPanel.vue** - Smart replacement logic:
```javascript
const shouldReplace = !options?.isMultiOp || options?.isFirstInMultiOp
```

**Logic**:
- Single operation: `replace: true` (clear previous filters)
- Multi-operation, first: `replace: true` (clear previous unrelated filters)
- Multi-operation, subsequent: `replace: false` (accumulate within query)

### Use Cases Now Supported

**✅ Independent queries** (replace):
```
User: "show housing meetings"      → [housing]
User: "show transportation meetings" → [transportation]  // Cleared housing
```

**✅ Complex AND queries** (accumulate):
```
User: "show housing AND transportation meetings"
→ Operation 1: housing (clears previous)
→ Operation 2: transportation (adds to housing)
→ Result: [housing, transportation]
```

**✅ Complex OR queries** (accumulate):
```
User: "show Berkeley OR Oakland meetings"
→ Operation 1: Berkeley (clears previous)
→ Operation 2: Oakland (adds to Berkeley)
→ Result: Both cities visible
```

## Technical Details

### Files Modified
1. `frontend/civic-workspace/src/components/sidebar/EventsPanel.vue`
   - Line 494: Added `replace?: boolean` parameter to `applyFilters()`
   - Line 523-525: Clear topic filters when `shouldReplace === true`
   - Line 549: Log replace mode for debugging

2. `frontend/civic-workspace/src/components/chat/ChatPanel.vue`
   - Line 578: Added `options` parameter to `handleSearchEvents()`
   - Line 614: Calculate `shouldReplace` based on multi-op context
   - Line 627, 655: Pass `replace` flag to `applyFilters()`
   - Line 526-529: Pass multi-op flags in `handleMultiOperation()`

### Backward Compatibility
- Default behavior: `replace: true` (safe for all existing code)
- Optional parameter: Existing calls without `replace` work correctly
- No changes required to backend or other components

## Testing Scenarios

**Test 1: Sequential independent queries**
```
1. "show housing meetings"     → Expect: [housing]
2. "show transportation"       → Expect: [transportation] only
```

**Test 2: Complex AND query**
```
"show housing AND transportation meetings"
→ Expect: [housing, transportation]
```

**Test 3: Mixed scenario**
```
1. "show budget meetings"      → Expect: [budget]
2. "show housing AND environment" → Expect: [housing, environment] only
```

## Benefits
1. **Predictable UX**: Sidebar always reflects current chat query intent
2. **Supports complex queries**: AND/OR logic works correctly
3. **Teaching moment**: Users see "AI uses same UI" when filters update
4. **No breaking changes**: Default behavior matches user expectations

---
**Session**: 77
**Date**: 2025-01-07
**Commit message**: "Fix: Prevent filter accumulation in chat navigation (Session 77)"

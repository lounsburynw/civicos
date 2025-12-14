# Two-Path Search Architecture

**Status**: ✅ Implemented
**Date**: 2025-10-27

## Overview

The Civic Conversational OS implements a **two-path search architecture** that distinguishes between simple UI-mappable queries and complex backend searches. This design ensures the AI assistant interacts with filters exactly as a user would, while still handling sophisticated queries that exceed UI capabilities.

## Philosophy: AI as First-Class User

**Core Principle**: The AI should use the same logic and methods that users do when interacting with the UI, not parallel/duplicate logic.

### Benefits:
1. **No logic duplication** - Single source of truth for filter behavior
2. **Filters remain interactive** - Users can adjust AI-applied filters naturally
3. **Consistent UX** - AI and manual filtering produce identical results
4. **Easy maintenance** - Changes to filter logic automatically apply to AI
5. **Future-proof** - New filter types automatically work with AI

## Architecture

### Path Classification

Queries are classified into two types based on complexity:

```typescript
// Simple Query (UI-mappable)
{
  type: 'simple',
  topic?: 'housing' | 'transportation' | ...,
  dateRange?: 'past' | 'upcoming' | 'all',
  searchQuery?: string
}

// Complex Query (Backend search)
{
  type: 'complex',
  topics?: ProjectType[],           // Multiple topics (OR condition)
  specificDateRange?: {              // Custom date ranges
    start?: string,
    end?: string
  },
  itemCountMin?: number,             // Agenda item count filters
  searchQuery?: string,
  customConditions?: Record<string, any>  // Extensible
}
```

### Classification Logic

**Simple queries** have:
- Single topic OR no topic
- Basic date range (past/upcoming/all) OR no date filter
- Optional text search

**Complex queries** have:
- Multiple topics (e.g., "housing OR transportation")
- Specific date ranges (e.g., "next 2 weeks")
- Item count filters (e.g., "meetings with 5+ items")
- Jurisdiction filters (when different from user location)
- Any custom conditions

## Implementation

### 1. Query Classifier (`services/queryClassifier.ts`)

Determines query complexity and formats user-facing descriptions:

```typescript
import { classifySearchQuery, formatQueryDescription } from '@/services/queryClassifier'

const query = classifySearchQuery({
  topic: 'housing',
  date_range: 'upcoming'
})
// → { type: 'simple', topic: 'housing', dateRange: 'upcoming' }

const description = formatQueryDescription(query)
// → "housing upcoming"
```

**Extensibility**: Add new classification rules by modifying `classifySearchQuery()`. The function checks for known simple parameters and treats unknowns as complex.

### 2. EventsPanel API (`components/sidebar/EventsPanel.vue`)

Exposes filter methods via `defineExpose()`:

```typescript
// Exposed methods
{
  applyFilters(filters: {
    topic?: ProjectType
    dateRange?: 'past' | 'upcoming' | 'all'
    searchQuery?: string
  }): void

  clearAllFilters(): void

  loadEvents(): Promise<void>

  loadFollows(): Promise<void>
}
```

**Key Design**: `applyFilters()` calls the same `toggleTopicFilter()` method that users trigger by clicking topic buttons. This ensures identical behavior.

### 3. ChatPanel Routing (`components/chat/ChatPanel.vue`)

Uses dependency injection to access EventsPanel:

```typescript
// Inject EventsPanel ref
const eventsPanelRef = inject<typeof EventsPanel | null>('eventsPanelRef', null)

// Path 1: Simple query
if (classifiedQuery.type === 'simple') {
  const eventsPanel = eventsPanelRef?.value
  if (eventsPanel && 'applyFilters' in eventsPanel) {
    // AI "clicks" the same filters users do
    eventsPanel.applyFilters({
      topic: classifiedQuery.topic,
      dateRange: classifiedQuery.dateRange,
      searchQuery: classifiedQuery.searchQuery
    })
  }
}

// Path 2: Complex query
else {
  const results = await api.searchEvents({
    jurisdiction: userStore.jurisdictionId,
    topics: classifiedQuery.topics,
    query: classifiedQuery.searchQuery,
    itemCountMin: classifiedQuery.itemCountMin,
    specificDateRange: classifiedQuery.specificDateRange
  })
  // ... handle results
}
```

### 4. Dependency Injection Setup (`App.vue`)

```typescript
// Create ref
const eventsPanelRef = ref<InstanceType<typeof EventsPanel> | null>(null)

// Provide to descendants
provide('eventsPanelRef', eventsPanelRef)

// Template
<EventsPanel ref="eventsPanelRef" />
```

## User Experience

### Simple Query Flow

1. User types: "show housing meetings"
2. AI classifies as simple (single topic)
3. AI calls `EventsPanel.applyFilters({ topic: 'housing' })`
4. Housing filter button becomes active (same as if user clicked it)
5. User can click other filters, toggle housing off, etc. - all works naturally

**AI Message**: "I've applied filters to show housing. You can adjust these filters in the sidebar, or ask me to refine your search."

### Complex Query Flow

1. User types: "show housing or transportation meetings in next 2 weeks with 5+ agenda items"
2. AI classifies as complex (multiple topics + custom date + item count)
3. AI calls backend search API with all parameters
4. Results displayed with special messaging

**AI Message**: "Found 12 housing or transportation meetings in Berkeley. _Note: This is a complex search. The filters in the sidebar show a simplified view. Ask me if you'd like to refine your search._"

## Future Extensions

### Adding New Simple Filter Types

To add a new UI filter (e.g., "following" vs "all"):

1. Add filter to EventsPanel UI
2. Expose filter method via `defineExpose()`
3. Update `SimpleQuery` interface in `queryClassifier.ts`
4. Add classification logic if needed
5. Pass parameter in ChatPanel's `applyFilters()` call

**No changes needed** to query routing or complex search path.

### Adding New Complex Filter Types

To add a new complex condition (e.g., "meetings with public comment"):

1. Update `ComplexQuery` interface in `queryClassifier.ts`
2. Add detection logic in `classifySearchQuery()`
3. Update backend search API to handle new parameter
4. Pass parameter in ChatPanel's complex search call

**No changes needed** to simple query path or EventsPanel.

### Supporting Mixed Complexity

For queries that are partially complex (e.g., "housing meetings in next 2 weeks"):

**Option 1**: Classify as complex, use backend search
**Option 2**: Add "approximate simple" path that applies closest UI filters + shows disclaimer

Current implementation uses Option 1 for safety.

## Performance Considerations

### Simple Path
- **Latency**: 0ms (instant filter application)
- **Cost**: $0 (no API calls)
- **Scalability**: Unlimited (client-side only)

### Complex Path
- **Latency**: ~200-500ms (API roundtrip)
- **Cost**: Depends on backend search implementation
- **Scalability**: Depends on backend capacity

**Recommendation**: Maximize simple path coverage by expanding UI filter capabilities over time.

## Testing

### Manual Testing

**Simple Queries**:
- ✅ "show housing meetings" → Housing filter active
- ✅ "show upcoming events" → Upcoming filter active
- ✅ "search for zoning" → Search box filled with "zoning"
- ✅ User can click other filters after AI applies them

**Complex Queries**:
- ✅ "housing or transportation" → Backend search
- ✅ "meetings in next 2 weeks" → Backend search
- ✅ "meetings with 5+ items" → Backend search

**Edge Cases**:
- ✅ EventsPanel not mounted → Graceful error message
- ✅ Empty results → Helpful suggestions
- ✅ Multiple rapid queries → Filters update correctly

### Automated Testing (Future)

```typescript
// Example test
it('should classify simple housing query correctly', () => {
  const query = classifySearchQuery({ topic: 'housing' })
  expect(query.type).toBe('simple')
  expect(query.topic).toBe('housing')
})

it('should classify multi-topic query as complex', () => {
  const query = classifySearchQuery({ topic: ['housing', 'transportation'] })
  expect(query.type).toBe('complex')
  expect(query.topics).toEqual(['housing', 'transportation'])
})
```

## Migration Notes

### From Previous Architecture

**Old approach** (deprecated):
- ChatPanel used `workspaceStore.setEventFilters()`
- EventsPanel watched for changes via `watch()`
- Separate logic paths for user and AI

**Problems with old approach**:
- Filter behavior could diverge between user and AI
- Users couldn't adjust AI-applied filters naturally
- Watcher pattern created timing issues

**New approach**:
- ChatPanel calls `EventsPanel.applyFilters()` directly
- Same methods for user clicks and AI actions
- No watchers, no separate logic paths

### Backward Compatibility

The old `workspaceStore.eventFilters` state is retained for complex searches but no longer used for simple queries. Can be safely removed if complex search path is refactored.

## Related Documentation

- `/docs/FRONTEND_TECHNICAL_ARCHITECTURE.md` - Overall frontend architecture
- `/docs/CHAT_ROUTING_ARCHITECTURE.md` - Chat routing with OpenAI function calling
- `src/services/queryClassifier.ts` - Query classification implementation
- `src/components/sidebar/EventsPanel.vue` - Filter UI implementation

## Questions & Discussion

**Q: Why not always use backend search?**
A: Simple queries benefit from instant client-side filtering with zero cost. Backend search adds latency and operational costs.

**Q: Can we add more simple query types?**
A: Yes! Expand EventsPanel UI filters and update classification logic. The architecture scales naturally.

**Q: What if EventsPanel changes its filter implementation?**
A: ChatPanel automatically gets the update since it calls EventsPanel methods. This is the key benefit of the architecture.

**Q: How do we handle query ambiguity?**
A: The classifier errs on the side of simplicity. Ambiguous queries default to simple path, and users can refine via chat if needed.

# Session 59: Workspace Tabs + Visual Enhancements for Multi-Operation Queries

**Status**: 📋 Ready to implement
**Estimated Time**: 4-5 hours
**Priority**: MEDIUM - Enhances multi-operation UX

---

## 🎯 Goal

Create workspace tabs for each multi-operation search result + add visual enhancements (pulse animations, filter highlights) to reinforce the "AI uses same UI" teaching moment.

---

## 📐 Architecture Decisions

Based on user discussion (2025-11-03):

### 1. Tab Location
**Decision**: Workspace area (Option 3)
**Why**: Follows existing workspace tab pattern, more screen space for results

### 2. Tab Content
**Decision**: EventList-style search results view
**Why**: Consistency with sidebar, familiar pattern

### 3. Sidebar Behavior
**Decision**: Independent after initial teaching moment
**Why**: Less coupling, simpler state management

### 4. Tab Naming
**Format**: `"Berkeley Housing"` (concise, jurisdiction + topic)

### 5. Visual Enhancements
- **Pulse animation**: Section header when expanding (600ms, scale 1.0 → 1.02 → 1.0)
- **Filter highlighting**: Active filters get temporary border/background (800ms fade)
- **Pause duration**: Increased from 500ms → 800ms for better visibility

---

## 🔨 Implementation Plan

### Task 1: Create SearchResultArtifact Component (90 min)

**New Component**: `frontend/civic-workspace/src/components/workspace/SearchResultArtifact.vue`

**Purpose**: Shows filtered EventList for a specific search operation

**Props**:
```typescript
interface SearchResultArtifactProps {
  searchId: string  // Unique ID for this search
  title: string  // "Berkeley Housing"
  filters: {
    jurisdiction?: string
    topic?: string
    dateRange?: string
    searchQuery?: string
  }
  events: Event[]  // Pre-fetched events for this search
}
```

**Template Structure**:
```vue
<template>
  <div class="search-result-artifact">
    <!-- Header with search metadata -->
    <div class="search-header">
      <h2>{{ title }}</h2>
      <div class="filter-summary">
        <span v-if="filters.jurisdiction">📍 {{ filters.jurisdiction }}</span>
        <span v-if="filters.topic">🏷️ {{ filters.topic }}</span>
      </div>
    </div>

    <!-- EventList-style results -->
    <div class="event-list">
      <EventCard
        v-for="event in events"
        :key="event.id"
        :event="event"
        @click="openEventArtifact(event)"
      />
    </div>

    <!-- Empty state -->
    <div v-if="events.length === 0" class="empty-state">
      No events found for this search
    </div>
  </div>
</template>
```

**Reuse**: EventCard component from EventsPanel

---

### Task 2: Update Workspace Store for Search Tabs (60 min)

**File**: `frontend/civic-workspace/src/stores/workspace.ts`

**Add State**:
```typescript
interface SearchTab {
  id: string  // Unique search ID
  title: string  // "Berkeley Housing"
  filters: SearchFilters
  events: Event[]
  createdAt: number
}

// Add to WorkspaceState
searchTabs: SearchTab[]
```

**Add Actions**:
```typescript
// Create new search result tab
createSearchTab(operation: ChatAction): string {
  const searchId = `search-${Date.now()}-${Math.random().toString(36).substring(7)}`
  const title = formatSearchTitle(operation.parameters)

  const tab: SearchTab = {
    id: searchId,
    title,
    filters: operation.parameters,
    events: [],  // Will be populated by API call
    createdAt: Date.now()
  }

  this.searchTabs.push(tab)

  // Open as workspace artifact
  this.openArtifact({
    id: searchId,
    type: 'search-result',
    title,
    data: { searchId }
  })

  return searchId
}

// Update search tab with fetched events
updateSearchTabEvents(searchId: string, events: Event[]) {
  const tab = this.searchTabs.find(t => t.id === searchId)
  if (tab) {
    tab.events = events
  }
}

// Format search title from parameters
formatSearchTitle(params: any): string {
  const topic = params.topic || 'All topics'
  const jurisdiction = params.jurisdiction || 'All cities'
  return `${capitalize(topic)} in ${capitalize(jurisdiction)}`
}
```

---

### Task 3: Update ChatPanel for Workspace Tabs (45 min)

**File**: `frontend/civic-workspace/src/components/chat/ChatPanel.vue`

**Update handleMultiOperation()**:
```typescript
async function handleMultiOperation(action: ChatAction) {
  console.log('[ChatPanel] Multi-operation query:', {
    count: action.operation_count,
    operations: action.all_operations
  })

  // Show visual indicator
  const operationSummary = action.all_operations!
    .map((op, i) => {
      if (op.action === 'search_events') {
        const params = op.parameters || {}
        const jurisdiction = params.jurisdiction || 'unknown'
        const topic = params.topic || 'all topics'
        return `${i + 1}. ${topic} in ${jurisdiction}`
      } else if (op.action === 'view_legislative_context') {
        const params = op.parameters || {}
        const topic = params.topic || 'all topics'
        const level = params.level || 'both'
        return `${i + 1}. ${level} ${topic} legislation`
      } else {
        return `${i + 1}. ${op.action}`
      }
    })
    .join('\n')

  chatStore.addMessage({
    role: 'assistant',
    content: `I found **${action.operation_count} searches** for your query:\n\n${operationSummary}\n\nProcessing each search now...`
  })

  // Process each operation sequentially
  for (let i = 0; i < action.all_operations!.length; i++) {
    const op = action.all_operations![i]

    console.log(`[ChatPanel] Processing operation ${i + 1}/${action.operation_count}:`, op.action)

    // SESSION 59: Create workspace tab for search operations
    if (op.action === 'search_events') {
      await handleSearchEventsAsTab(op)
    } else {
      // Fallback to original handlers
      switch (op.action) {
        case 'view_legislative_context':
          await handleLegislativeContext(op.parameters)
          break
        case 'explain_event':
          await handleExplainEvent(op.parameters)
          break
        case 'respond':
          // Skip respond actions in multi-op
          break
        default:
          console.warn('[ChatPanel] Unknown multi-op action:', op.action)
      }
    }

    // Add pause between operations
    if (i < action.all_operations!.length - 1) {
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 800)) // SESSION 59: Increased from 500ms
    }
  }

  // Summary message
  chatStore.addMessage({
    role: 'assistant',
    content: `Finished processing all **${action.operation_count} searches**. Results are shown in workspace tabs.`
  })
}

// NEW: Handle search as workspace tab
async function handleSearchEventsAsTab(operation: ChatAction) {
  // Check if user has set their location
  if (!userStore.hasLocation) {
    chatStore.addMessage({
      role: 'assistant',
      content: `📍 **Location Required**\n\nTo show you civic meetings, I need to know where you're located.`
    })
    return
  }

  // SESSION 59: Trigger pulse animation on Events section
  triggerSectionPulse('events')

  // Expand Events section
  sidebarStore.expandSectionExclusive('events')

  // Create search tab in workspace
  const searchId = workspaceStore.createSearchTab(operation)

  // Fetch events for this search
  try {
    const classifiedQuery = classifySearchQuery(operation.parameters)

    const searchParams = {
      jurisdiction: classifiedQuery.jurisdiction || userStore.jurisdictionId,
      topic: classifiedQuery.topics && classifiedQuery.topics.length > 0
        ? classifiedQuery.topics[0]
        : undefined,
      query: classifiedQuery.searchQuery,
      dateRange: classifiedQuery.specificDateRange?.start
    }

    const results = await api.searchEvents(searchParams)

    // Update search tab with results
    workspaceStore.updateSearchTabEvents(searchId, results.events || [])

    // SESSION 59: Trigger filter highlight animation
    triggerFilterHighlight(classifiedQuery)

    // Compact success message
    const topic = operation.parameters.topic || 'events'
    const jurisdiction = operation.parameters.jurisdiction || userStore.cityName
    chatStore.addMessage({
      role: 'assistant',
      content: `✓ Found **${results.count}** ${topic} in ${jurisdiction}.`
    })
  } catch (error) {
    console.error('Search tab error:', error)
    chatStore.addMessage({
      role: 'assistant',
      content: `Sorry, I encountered an error creating this search.`
    })
  }
}
```

---

### Task 4: Implement Visual Enhancements (75 min)

#### 4.1: Pulse Animation on Section Headers

**File**: `frontend/civic-workspace/src/composables/useVisualEnhancements.ts` (NEW)

```typescript
import { ref } from 'vue'

const pulsingSections = ref<Set<string>>(new Set())

export function useVisualEnhancements() {
  function triggerSectionPulse(sectionId: string) {
    pulsingSections.value.add(sectionId)

    setTimeout(() => {
      pulsingSections.value.delete(sectionId)
    }, 600)
  }

  function isSectionPulsing(sectionId: string): boolean {
    return pulsingSections.value.has(sectionId)
  }

  function triggerFilterHighlight(filters: any) {
    // Emit event for sidebar to highlight active filters
    window.dispatchEvent(new CustomEvent('highlight-filters', {
      detail: filters
    }))
  }

  return {
    triggerSectionPulse,
    isSectionPulsing,
    triggerFilterHighlight
  }
}
```

#### 4.2: Update Sidebar Section Headers

**File**: `frontend/civic-workspace/src/components/sidebar/*` (EventsPanel, LegislativePanel, etc.)

Add pulse animation CSS:
```vue
<template>
  <div
    class="section-header"
    :class="{ 'pulsing': isPulsing }"
  >
    <!-- Header content -->
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useVisualEnhancements } from '@/composables/useVisualEnhancements'

const { isSectionPulsing } = useVisualEnhancements()
const isPulsing = computed(() => isSectionPulsing('events'))
</script>

<style scoped>
.section-header.pulsing {
  animation: pulse 600ms cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 var(--primary-color);
  }
  50% {
    transform: scale(1.02);
    box-shadow: 0 0 0 4px rgba(var(--primary-rgb), 0.3);
  }
}
</style>
```

#### 4.3: Filter Highlight Animation

**File**: EventsPanel.vue, LegislativePanel.vue

Add listener for filter highlight events:
```vue
<script setup>
import { onMounted, onUnmounted } from 'vue'

const highlightedFilters = ref<Set<string>>(new Set())

function handleFilterHighlight(event: CustomEvent) {
  const filters = event.detail

  // Add highlights
  if (filters.topic) highlightedFilters.value.add('topic')
  if (filters.jurisdiction) highlightedFilters.value.add('jurisdiction')

  // Remove after 800ms
  setTimeout(() => {
    highlightedFilters.value.clear()
  }, 800)
}

onMounted(() => {
  window.addEventListener('highlight-filters', handleFilterHighlight as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('highlight-filters', handleFilterHighlight as EventListener)
})
</script>

<style scoped>
.filter-button.highlighted {
  animation: filter-highlight 800ms ease-out;
}

@keyframes filter-highlight {
  0% {
    background-color: var(--primary-color);
    border-color: var(--primary-color);
    transform: scale(1.05);
  }
  100% {
    background-color: initial;
    border-color: initial;
    transform: scale(1);
  }
}
</style>
```

---

### Task 5: Update Artifact Rendering (30 min)

**File**: `frontend/civic-workspace/src/components/workspace/TabBar.vue` or artifact router

**Add search-result artifact type**:
```vue
<template>
  <div class="workspace-content">
    <!-- Existing artifact types -->
    <EventArtifact v-if="artifact.type === 'event'" ... />
    <BillArtifact v-if="artifact.type === 'bill'" ... />

    <!-- SESSION 59: New search result artifact -->
    <SearchResultArtifact
      v-if="artifact.type === 'search-result'"
      :search-id="artifact.data.searchId"
      :title="artifact.title"
      :filters="getSearchFilters(artifact.data.searchId)"
      :events="getSearchEvents(artifact.data.searchId)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import SearchResultArtifact from './SearchResultArtifact.vue'

const workspaceStore = useWorkspaceStore()

function getSearchFilters(searchId: string) {
  const tab = workspaceStore.searchTabs.find(t => t.id === searchId)
  return tab?.filters || {}
}

function getSearchEvents(searchId: string) {
  const tab = workspaceStore.searchTabs.find(t => t.id === searchId)
  return tab?.events || []
}
</script>
```

---

## 📋 Testing Checklist

### Manual Test Cases

**Test 1: Single Operation (No Regression)**
```
Input: "Show housing meetings in Berkeley"
Expected:
- No workspace tab created (uses sidebar as before)
- Events section expands normally
- No pulse animation (single op)
```

**Test 2: Double Operation - Workspace Tabs**
```
Input: "Show housing in Berkeley OR transportation in Concord"
Expected:
1. Chat: "I found 2 searches..."
2. Events section expands with PULSE animation
3. Workspace tab created: "Housing in Berkeley"
4. Events fetched and displayed in tab
5. 800ms pause
6. Events section stays expanded (or pulses again)
7. Workspace tab created: "Transportation in Concord"
8. Events fetched and displayed in tab
9. Chat: "Finished processing all 2 searches"
10. User can click tabs to switch between results
```

**Test 3: Triple Operation**
```
Input: "Show housing in Berkeley OR Oakland OR San Francisco"
Expected:
- 3 workspace tabs created
- Each tab shows filtered results
- All tabs persist in TabBar
- Switching tabs shows correct filtered events
```

**Test 4: Visual Enhancements**
```
Input: "Show housing in Berkeley OR transportation in Concord"
Expected:
- Section header pulses (600ms animation)
- Filter buttons highlight briefly (800ms fade)
- 800ms pause between operations (longer than Session 58's 500ms)
```

**Test 5: Mixed Operations**
```
Input: "Show housing events in Berkeley OR housing bills statewide"
Expected:
- First operation: Workspace tab "Housing in Berkeley" (events)
- Second operation: Legislative tab switch (not search result tab)
- No errors, clean UX
```

---

## 🎨 Design Specifications

### Pulse Animation
- **Duration**: 600ms
- **Easing**: cubic-bezier(0.4, 0, 0.2, 1)
- **Scale**: 1.0 → 1.02 → 1.0
- **Shadow**: 0 → 4px rgba(primary, 0.3) → 0
- **Color**: Primary color from design system

### Filter Highlight
- **Duration**: 800ms
- **Easing**: ease-out
- **Background**: Primary color → fade to default
- **Scale**: 1.05 → 1.0
- **Border**: Primary color → default

### Pause Duration
- **Between operations**: 800ms (increased from 500ms)
- **Purpose**: Give users time to see animations and understand flow

---

## 📊 Success Metrics

- ✅ Workspace tabs created for each search operation
- ✅ Each tab shows correct filtered EventList
- ✅ Pulse animation visible on section headers
- ✅ Filter highlight animation visible
- ✅ 800ms pause between operations
- ✅ User can switch between tabs
- ✅ Results persist in tabs
- ✅ No regressions for single operations
- ✅ Teaching moment preserved (sidebar expansion)

---

## 📁 Files to Create/Modify

**New Files** (1):
1. `frontend/civic-workspace/src/components/workspace/SearchResultArtifact.vue`
2. `frontend/civic-workspace/src/composables/useVisualEnhancements.ts`

**Modified Files** (4):
1. `frontend/civic-workspace/src/stores/workspace.ts` - Add search tabs state
2. `frontend/civic-workspace/src/components/chat/ChatPanel.vue` - Update multi-op handler
3. `frontend/civic-workspace/src/components/sidebar/EventsPanel.vue` - Add pulse/highlight
4. `frontend/civic-workspace/src/components/workspace/TabBar.vue` - Render search artifacts

---

## 🚀 Next Sessions

**Session 60** (3-4 hours): AND operations (result intersection)
**Session 61** (3-4 hours): Result deduplication + merged view option
**Session 62** (2-3 hours): Performance optimization (parallel processing)

---

## 💡 Implementation Notes

### Tab Limit
- No hard limit for Session 59
- Future: Consider max 10 tabs with "Show more" overflow

### Sidebar Sync
- **Not implemented** in Session 59 (independent after creation)
- Future: Could add option to sync sidebar with active tab

### Click Event Behavior
- Clicking event in SearchResultArtifact → Opens EventArtifact (new tab)
- Similar to current EventsPanel behavior

### Mobile Considerations
- Workspace tabs may need horizontal scroll on mobile
- Pulse animations should work but may be less noticeable
- Filter highlights still visible

---

## ✅ Ready to Implement

All architectural decisions finalized. Estimated 4-5 hours for complete implementation with testing.

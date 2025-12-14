# Phase 3: UX Refinement for Pilot Launch

**Date**: 2025-10-22
**Status**: ✅ **SCOPED AND APPROVED**
**Goal**: Prepare platform for real-world pilot deployment with polished, production-ready UX
**Timeline**: 3-5 sessions (Sessions 21-25), ~10.5 hours total

---

## Strategic Context

### Current State
- ✅ **Phase 2 Complete**: Full complaint→civic PMF loop operational
- ✅ **Backend Complete**: All data available (events, agenda items, complaints, following, messaging)
- ✅ **Core Features Working**: Filing, matching, coordination, response tracking

### Gap Analysis

Through strategic discussion (Session 20+), identified **4 CRITICAL GAPS** blocking pilot launch:

1. **Agenda items not displayed** - Core value prop missing (users can't see specific actionable items)
2. **UI overwhelming** - All features exposed at once (confusing to new users)
3. **No location scoping** - Multi-city tree confusing (users see irrelevant jurisdictions)
4. **Chat experience restrictive** - Locked to comment drafting (doesn't feel conversational)

**Assessment**: ALL 4 gaps are **MUST-HAVES** for pilot launch (not nice-to-haves)

---

## Phase 3 Implementation Tasks

### Task 1: Address-Based Location Entry
**Session**: 21
**Duration**: ~3 hours
**Backend Required**: ✅ YES

#### Backend Work (~1.5 hours)
**New Files**:
- `src/geocoding_service.py` - Google Maps API wrapper
- `src/location_validator.py` - IP geolocation anti-bot protection

**Implementation**:
```python
# geocoding_service.py
class GeocodingService:
    def geocode_address(address: str) -> dict:
        """
        Returns: {
            "lat": 37.8044,
            "lng": -122.2712,
            "city": "Oakland",
            "county": "Alameda County",
            "state": "California",
            "jurisdictions": {
                "city": "city-oakland",
                "county": "alameda-county",
                "state_assembly": "district-18",
                "state_senate": "district-9",
                "congressional": "district-12"
            }
        }
        """

# location_validator.py
class LocationValidator:
    def validate_location(user_ip: str, claimed_lat: float, claimed_lng: float) -> bool:
        """
        Returns True if user's IP is within ~50 miles of claimed address
        Prevents astroturfing from out-of-area actors
        """
```

**API Endpoints**:
- `POST /api/user/location` - Store user's location (lat/lng only, privacy-preserving)
- `GET /api/user/location` - Retrieve user's jurisdiction scope

#### Frontend Work (~1.5 hours)
**New Components**:
- `src/components/LocationEntry.vue` - Modal shown on first visit

**Updated Components**:
- `src/App.vue` - Show LocationEntry modal if no location set
- `src/services/api.ts` - Add location endpoints
- `src/stores/user.ts` - Store user's jurisdiction scope

**User Flow**:
1. First visit → LocationEntry modal appears
2. User enters "123 Oak St, Oakland, CA"
3. Google autocomplete suggests full address
4. Backend geocodes → determines jurisdictions
5. IP validation confirms user is in Oakland area
6. App header changes to "Oakland Civic OS"
7. All data filtered to Oakland + Alameda County only

#### Success Criteria
- [ ] User enters address → sees only Oakland/Alameda data
- [ ] IP validation prevents out-of-area signups
- [ ] Jurisdiction tree shows ONLY relevant cities/county
- [ ] Legislative context filtered to Oakland-specific bills
- [ ] Privacy: Only lat/lng stored, not full address

---

### Task 2: Side-by-Side Layout Redesign
**Session**: 22
**Duration**: ~2.5 hours
**Backend Required**: ❌ NO (frontend-only)

#### Implementation (~2.5 hours)
**Files to Modify**:
- `src/App.vue` - Remove bottom chat panel, implement split pane
- `src/components/chat/ChatPanel.vue` - Add context bar
- `src/design-system.css` - Add split-pane styles

**Layout Structure**:
```vue
<div class="app-container">
  <!-- Optional sidebars (hidden by default) -->
  <sidebar v-if="showSidebars" />

  <!-- Main content: side-by-side chat + artifact -->
  <div class="main-content split-pane">
    <!-- Left: Chat (45%) -->
    <div class="chat-pane resizable">
      <ChatContextBar :context="activeArtifact" />
      <ChatMessages />
      <ChatInput />
    </div>

    <!-- Resizable divider -->
    <div class="pane-divider" @mousedown="startResize" />

    <!-- Right: Artifact (55%) -->
    <div class="artifact-pane">
      <EventArtifact v-if="activeTab?.type === 'event'" />
      <ComplaintArtifact v-if="activeTab?.type === 'complaint'" />
    </div>
  </div>
</div>
```

**Chat Context Bar**:
```vue
<div class="chat-context-bar">
  <span class="context-icon">📄</span>
  <span class="context-label">
    Discussing: Item 7.2 - Use Permit
  </span>
  <span class="context-event">
    Event: Planning Commission - Jan 15
  </span>
  <button @click="clearContext">×</button>
</div>
```

#### Success Criteria
- [ ] Chat and artifact always visible side-by-side
- [ ] Resizable divider works smoothly
- [ ] Context bar shows "Discussing: Item 7.2"
- [ ] Mobile stacks correctly (chat top, artifact bottom)
- [ ] Divider width persists in localStorage

---

### Task 3: Agenda Items Display
**Session**: 23
**Duration**: ~2 hours
**Backend Required**: ❌ NO (data already available)

#### Implementation (~2 hours)
**File to Modify**:
- `src/components/workspace/EventArtifact.vue`

**Data Already Available**:
Backend API returns `agenda_expansion.actionable_items[]` with:
- `item_ref` (e.g., "7.2")
- `title`, `description`
- `actionable`, `actionable_because`
- `project_types[]`
- `legislative_context` (when enriched)

**New EventArtifact Structure**:
```vue
<div class="event-artifact">
  <!-- Meeting Overview Section -->
  <section class="meeting-overview">
    <h1>{{ event.title }}</h1>
    <p>{{ formattedDate }}</p>
    <p>{{ event.location }}</p>
  </section>

  <!-- Agenda Items Section (PROMINENT) -->
  <section class="agenda-items">
    <h2>📋 Agenda Items ({{ totalItems }}, {{ actionableCount }} actionable)</h2>

    <div
      v-for="item in agendaItems"
      :key="item.item_ref"
      class="agenda-item"
      :class="{ actionable: item.actionable, expanded: item.actionable }"
    >
      <!-- Item Header (clickable to expand/collapse) -->
      <div class="item-header" @click="toggleItem(item.item_ref)">
        <span class="item-icon">{{ item.actionable ? '⭐' : '📄' }}</span>
        <span class="item-number">{{ item.item_ref }}</span>
        <span class="item-title">{{ item.title }}</span>
      </div>

      <!-- Item Body (expanded for actionable items) -->
      <div v-if="isExpanded(item.item_ref)" class="item-body">
        <p class="item-description">{{ item.description }}</p>

        <!-- Project Types -->
        <div class="project-types">
          <span v-for="type in item.project_types" class="type-tag">
            {{ type }}
          </span>
        </div>

        <!-- Legislative Context (if enriched) -->
        <div v-if="item.legislative_context" class="legislative-links">
          🏛️ Related:
          <a v-for="bill in item.legislative_context.state_legislation_refs">
            {{ bill }}
          </a>
        </div>

        <!-- Actions -->
        <button class="action-chip" @click="draftComment(item)">
          💬 Draft Comment
        </button>
      </div>
    </div>
  </section>

  <!-- Legislative Context Section (existing) -->
  <section class="legislative-context">
    <h2>🏛️ Legislative Context</h2>
    <!-- Detailed bill/program information -->
  </section>
</div>
```

**Behavior**:
- Actionable items expanded by default
- Non-actionable items collapsed by default
- Click header to toggle expand/collapse
- "Draft Comment" button focuses chat on that specific item

#### Success Criteria
- [ ] Agenda items displayed prominently in EventArtifact
- [ ] Actionable items expanded by default (⭐ icon)
- [ ] Non-actionable items collapsed (📄 icon)
- [ ] "Draft Comment" focuses chat on specific item
- [ ] Legislative context links work
- [ ] Expandable/collapsible behavior smooth

---

### Task 4: Progressive Sidebar Disclosure
**Session**: 24
**Duration**: ~1.5 hours
**Backend Required**: ❌ NO (frontend state management)

#### Implementation (~1.5 hours)
**Files to Modify**:
- `src/App.vue` - Sidebar visibility logic
- `src/stores/user.ts` - Track user engagement level

**Disclosure Rules**:
```javascript
const sidebarVisibility = computed(() => {
  const user = useUserStore();

  return {
    jurisdictionTree: user.hasQueriedEvents || user.hasFiledComplaint,
    myIssuesPanel: user.hasFiledComplaint,
    legislativePanel: user.hasExploredHousingEvents >= 3
  };
});
```

**User Experience**:
```
First visit:
┌─────────────────────────────────────┐
│  💬 Large centered chat input       │
│  "What's happening in your city?"   │
└─────────────────────────────────────┘

After "What housing meetings?":
┌────┬────────────────────────────────┐
│Tree│ 💬 Chat  │ 📄 Event List        │
│    │          │                      │
└────┴──────────┴──────────────────────┘

After filing complaint:
┌────┬──────────┬────────────────┬────┐
│Tree│ 💬 Chat  │ 📄 Complaint   │Issu│
│    │          │                │es  │
└────┴──────────┴────────────────┴────┘
```

**Hint System**:
- After 3 housing events: "💡 Want to understand state/federal context? [Show Legislative Panel]"
- After viewing event: "💡 Have a neighborhood issue? [File Complaint]"

#### Success Criteria
- [ ] First visit: only chat visible (centered, welcoming)
- [ ] After first query: JurisdictionTree appears
- [ ] After first complaint: MyIssuesPanel appears
- [ ] Legislative panel appears after 3+ housing events
- [ ] Never show all 3 sidebars at once on first visit
- [ ] Hints appear at appropriate times

---

### Task 5: Context-Aware Chat Enhancements
**Session**: 25
**Duration**: ~1.5 hours
**Backend Required**: ❌ NO (frontend state management)

#### Implementation (~1.5 hours)
**Files to Modify**:
- `src/components/chat/ChatPanel.vue` - Add context bar
- `src/components/chat/ChatInput.vue` - Update placeholder
- `src/stores/workspace.ts` - Track active context

**Context Tracking**:
```javascript
// stores/workspace.ts
const chatContext = computed(() => {
  const activeTab = workspaceStore.activeTab;

  if (!activeTab) return null;

  return {
    type: activeTab.type,      // 'event' | 'complaint' | 'bill'
    id: activeTab.id,
    title: activeTab.title,

    // For events with agenda items
    focusedItem: activeTab.type === 'event'
      ? activeTab.focusedAgendaItem
      : null
  };
});
```

**Chat Placeholder Updates**:
```javascript
const placeholder = computed(() => {
  if (!chatContext.value) {
    return "What's happening in your city?";
  }

  if (chatContext.value.focusedItem) {
    return `Ask about ${chatContext.value.focusedItem}...`;
  }

  if (chatContext.value.type === 'event') {
    return "Ask about this meeting...";
  }

  if (chatContext.value.type === 'complaint') {
    return "Ask about this issue...";
  }

  return "Ask me anything...";
});
```

**API Integration**:
```javascript
// When user sends message
async function sendMessage(message: string) {
  const response = await api.sendMessage({
    message,
    context: {
      type: chatContext.value?.type,
      id: chatContext.value?.id,
      focused_item: chatContext.value?.focusedItem
    }
  });
}
```

#### Success Criteria
- [ ] Context bar shows "Discussing: Item 7.2 - Use Permit"
- [ ] Placeholder updates based on context
- [ ] Tab switching updates context automatically
- [ ] General chat available when no artifact open
- [ ] Clear context button returns to general chat

---

## Phase 3 Success Metrics

**Completion Criteria** (ALL must pass):
- [ ] User can enter address → sees only Oakland data
- [ ] Agenda items displayed prominently in EventArtifact
- [ ] Side-by-side layout working (chat + artifact visible)
- [ ] Progressive disclosure: first visit shows only chat
- [ ] Context-aware chat indicates current artifact
- [ ] TypeScript type checking passes (`npm run type-check`)
- [ ] All Phase 2 features still working (no regressions)
- [ ] E2E test: address entry → file complaint → see agenda items → coordinate
- [ ] **Pilot-ready UX** validated by user

**Phase 3 Complete = Ready for Pilot Deployment**

---

## Timeline Estimate

| Session | Task | Hours | Cumulative |
|---------|------|-------|------------|
| 21 | Address-based location entry | 3.0 | 3.0h |
| 22 | Side-by-side layout redesign | 2.5 | 5.5h |
| 23 | Agenda items display | 2.0 | 7.5h |
| 24 | Progressive sidebar disclosure | 1.5 | 9.0h |
| 25 | Context-aware chat enhancements | 1.5 | 10.5h |
| **TOTAL** | **Phase 3 Complete** | **10.5h** | **~5 sessions** |

**Confidence Level**: ⭐⭐⭐⭐⭐ **VERY HIGH**
- All tasks are standard frontend development
- Backend changes minimal (geocoding only)
- Data already available from Phase 2
- No complex state management required

---

## Technical Readiness Assessment

### Backend Status

| Requirement | Status | Notes |
|-------------|--------|-------|
| Agenda items in API | ✅ READY | `/api/events` returns `agenda_expansion.actionable_items[]` |
| Geocoding service | 🔄 NEEDED | Google Maps API integration (Session 21) |
| IP geolocation | 🔄 NEEDED | Anti-bot protection (Session 21) |
| Jurisdiction filtering | ✅ READY | `/api/events?jurisdiction_id=city-oakland` works |
| Legislative context | ✅ READY | Already enriched per-jurisdiction |

**Backend Tasks** (Session 21 only):
1. `src/geocoding_service.py` - Google Maps API wrapper
2. `src/location_validator.py` - IP geolocation validation
3. `POST /api/user/location` endpoint
4. `GET /api/user/location` endpoint

**Sessions 22-25**: ✅ **Frontend-only** (no backend blockers)

### Frontend Complexity

| Task | Complexity | Risk | Dependencies |
|------|------------|------|--------------|
| Location entry | MEDIUM | LOW | Google Maps API setup |
| Side-by-side layout | MEDIUM | LOW | Vue layout refactor |
| Agenda items display | LOW | LOW | Data already available |
| Progressive disclosure | LOW | LOW | UI state management |
| Context-aware chat | LOW | LOW | Props passing |

**Overall Risk**: ⭐⭐⭐⭐⭐ **VERY LOW** - All standard Vue development patterns

---

## Documentation Updates

**Architecture**:
- ✅ `docs/FRONTEND_TECHNICAL_ARCHITECTURE.md` - Part 8 added (Phase 3 UX Refinement Decisions)
  - Section 8.1: Location-Based Multi-Jurisdiction Architecture
  - Section 8.2: Side-by-Side Layout Architecture
  - Section 8.3: Agenda Items Display Pattern
  - Section 8.4: Progressive Disclosure Strategy
  - Section 8.5: Context-Aware Chat Architecture

**Strategy**:
- 🔄 `docs/COMMUNITY_CIVIC_PMF_STRATEGY.md` - Update with location scoping strategy

**Implementation**:
- ✅ `docs/FRONTEND_IMPLEMENTATION_ROADMAP.md` - Already has EventArtifact pattern (Layer 2.2)

---

## Session 21 Kickoff

**Ready to start**: ✅ **YES**

**Goal**: Implement address-based location entry with Google Maps geocoding

**Context Files**:
- `docs/FRONTEND_TECHNICAL_ARCHITECTURE.md` (Part 8.1)
- `docs/PHASE3_UX_REFINEMENT_PLAN.md` (this file)
- `frontend/civic-workspace/src/types/civic.ts`
- `frontend/civic-workspace/src/services/api.ts`

**Deliverables**:
1. Backend: `src/geocoding_service.py`
2. Backend: `src/location_validator.py`
3. Backend: Location API endpoints
4. Frontend: `src/components/LocationEntry.vue`
5. Frontend: Update App.vue to show LocationEntry on first visit
6. Frontend: Filter all API calls by user's jurisdiction

**Acceptance Criteria**:
- User enters "123 Oak St, Oakland, CA" → sees only Oakland + Alameda County data
- IP validation prevents out-of-area signups (>50 miles away)
- Location stored as lat/lng (privacy-preserving)
- Jurisdiction tree filtered to relevant cities

---

**Phase 3 Status**: 📋 **READY TO START** | All tasks scoped and approved

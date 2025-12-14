# Social Focal Points Strategy
## Making Discussions First-Class Citizens

**Date**: 2025-10-23
**Status**: ✅ **Foundation Complete** - ThreadArtifact implemented (commit 4cc6447)
**Session**: Pre-Session 32 Planning → Session 32+ Refinement

---

## 🆕 UPDATE (2025-10-23): Refinement Strategy Available

**Foundation complete!** ThreadArtifact now opens in tabs. Next phase focuses on UX refinement:

**See**: `docs/SOCIAL_COORDINATION_REFINEMENT_STRATEGY.md` for:
- ✅ Message aesthetics (icons, avatars, activity indicators)
- ✅ Nested threading vs. semantic clustering decision (nested wins!)
- ✅ Startup discovery (make social features visible)
- ✅ Phase 1-3 implementation roadmap

**This document** remains the architectural foundation. **Refinement strategy** adds UX polish.

---

## Problem Statement

**Current Implementation** (Session 27):
- ✅ Coordination chat exists (`CoordinationChat.vue`)
- ✅ Socket.io real-time messaging working
- ✅ Backend storage (`civic_participation.db` - threads, messages tables)
- ❌ **Discussions hidden** - nested inside ComplaintArtifact component
- ❌ **Limited scope** - only Complaints can have discussions
- ❌ **No discovery** - users can't browse active conversations

**The Missing Social Layer**:
Users can't see:
- "15 people discussing the housing meeting on Oct 20"
- "3 active threads about Main St traffic"
- Which events have community coordination happening
- Who else cares about the same issues

**Schema Already Supports This!** (`civic-app-schema.json:599-615`):
```json
"DiscussionGroup": {
  "focal_point_type": {
    "enum": ["CivicEvent", "Complaint", "ProposedAgendaItem"]
  }
}
```

---

## Solution: Thread Artifact + Community Sidebar

### Core Architecture Changes

#### 1. Thread Artifact (First-Class Artifact)

**Opens in workspace tabs** like events/complaints/bills:

```
┌────────────────────────────────────────────────┐
│ Tabs: [Event] [Thread: Housing Meeting] [X]   │
├────────────────────────────────────────────────┤
│ Thread Artifact                                │
│                                                │
│ 💬 Discussion: Planning Commission Oct 20     │
│ ─────────────────────────────────────────────  │
│ Context Preview:                               │
│ ┌──────────────────────────────────────────┐   │
│ │ 📅 Planning Commission Meeting           │   │
│ │ Oct 20, 7pm - Item 7.2: Use Permit       │   │
│ │ [Click to view full event]               │   │
│ └──────────────────────────────────────────┘   │
│                                                │
│ 15 participants • 42 messages                  │
│                                                │
│ [Real-time chat messages via Socket.io...]    │
│                                                │
│ Alice: "Anyone planning to attend?"            │
│ Bob: "Yes, let's coordinate beforehand"        │
│ You: [Type message...]                         │
└────────────────────────────────────────────────┘
```

**Component**: `ThreadArtifact.vue`
- Props: `thread_id`, `focal_point` (type, id, title)
- Reuses: `CoordinationChat.vue` for messaging UI
- Adds: Context preview, participant list, thread metadata

#### 2. Community Sidebar Panel

**New sidebar section** showing active discussions:

```
┌──────────────────────┐
│ Jurisdiction Tree    │
├──────────────────────┤
│ 📝 My Issues (3)     │
├──────────────────────┤
│ 💬 Active Discussions│  ← NEW!
│                      │
│ 🔥 Hot Threads       │
│ • Housing Meeting    │
│   15 people, 42 msgs │
│                      │
│ • Main St Traffic    │
│   8 people, 23 msgs  │
│                      │
│ 📅 Event Threads     │
│ • Oct 20 Planning    │
│ • Oct 15 Council     │
│                      │
│ 🏡 Issue Threads     │
│ • Pothole cleanup    │
│ • Noise complaint    │
│                      │
│ [Filter: All | Events│
│  | Complaints |      │
│  Proposals]          │
└──────────────────────┘
```

**Component**: `DiscussionsPanel.vue`
- API: `GET /api/threads?jurisdiction={id}` (needs implementation)
- Filters: By focal_point_type, recency, activity
- Actions: Click thread → opens ThreadArtifact

#### 3. Enable Threads Everywhere

**EventArtifact.vue** - Actions tab:
```vue
<button @click="openEventThread">
  💬 Join Discussion (15 people)
</button>
```

**ComplaintArtifact.vue** - Replace nested chat:
```vue
<!-- BEFORE (Session 27) -->
<CoordinationChat :complaint="complaint" />  <!-- Nested, hidden -->

<!-- AFTER (Session 32+) -->
<button @click="openComplaintThread">
  💬 Join Discussion (8 people)
</button>
```

**BillArtifact.vue** / **ProgramArtifact.vue** - Enable civic education discussions:
```vue
<button @click="openLegislativeThread">
  💬 Discuss This Bill
</button>
```

---

## Implementation Plan

### Phase 1: Thread Artifact (Session 32+) - ~5h

**Backend Endpoints** (~2h):
```python
# src/civic_api_integrated.py

@app.get("/api/threads")
def get_threads(
    jurisdiction: Optional[str] = None,
    focal_point_type: Optional[str] = None,  # "CivicEvent" | "Complaint" | "ProposedAgendaItem"
    limit: int = 20
):
    """List active discussion threads"""
    threads = community_storage.get_threads(
        jurisdiction=jurisdiction,
        focal_point_type=focal_point_type,
        limit=limit
    )
    return {"threads": threads, "count": len(threads)}

@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str):
    """Get single thread with messages + context"""
    thread = community_storage.get_thread(thread_id)
    messages = community_storage.get_messages(thread_id)

    # Hydrate focal point context
    if thread["focal_point_type"] == "CivicEvent":
        focal_point = load_event(thread["focal_point_id"])
    elif thread["focal_point_type"] == "Complaint":
        focal_point = complaint_storage.get_complaint(thread["focal_point_id"])

    return {
        "thread": thread,
        "messages": messages,
        "focal_point": focal_point
    }

@app.post("/api/threads")
def create_thread(data: dict):
    """Create discussion thread for focal point"""
    thread_id = community_storage.create_thread(
        focal_point_type=data["focal_point_type"],
        focal_point_id=data["focal_point_id"],
        creator_user_id=data["user_id"]
    )
    return {"thread_id": thread_id}
```

**Database Updates** (~30min):
```sql
-- migrations/006_add_thread_discovery.sql

-- Add index for thread listing
CREATE INDEX idx_threads_jurisdiction ON coordination_threads(created_at DESC);

-- Add participant count cache
ALTER TABLE coordination_threads ADD COLUMN participant_count INTEGER DEFAULT 0;
ALTER TABLE coordination_threads ADD COLUMN message_count INTEGER DEFAULT 0;

-- Trigger to update counts
CREATE TRIGGER update_thread_counts
AFTER INSERT ON thread_messages
FOR EACH ROW
BEGIN
  UPDATE coordination_threads
  SET message_count = message_count + 1
  WHERE id = NEW.thread_id;
END;
```

**Frontend Components** (~2.5h):

1. **ThreadArtifact.vue** (~1.5h):
```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import CoordinationChat from './CoordinationChat.vue'
import { api } from '@/services/api'

const props = defineProps<{
  threadId: string
}>()

const workspaceStore = useWorkspaceStore()
const thread = ref(null)
const focalPoint = ref(null)

onMounted(async () => {
  const data = await api.getThread(props.threadId)
  thread.value = data.thread
  focalPoint.value = data.focal_point
})

function openFocalPoint() {
  // Open linked event/complaint/proposal in new tab
  workspaceStore.openArtifact({
    type: thread.value.focal_point_type.toLowerCase(),
    id: thread.value.focal_point_id,
    title: focalPoint.value.title
  })
}
</script>

<template>
  <div class="thread-artifact">
    <div class="thread-header">
      <h2>💬 Discussion</h2>
      <div class="thread-meta">
        {{ thread?.participant_count }} participants • {{ thread?.message_count }} messages
      </div>
    </div>

    <!-- Context Preview -->
    <div class="focal-point-preview" @click="openFocalPoint">
      <div v-if="thread?.focal_point_type === 'CivicEvent'" class="event-preview">
        <span class="preview-icon">📅</span>
        <div class="preview-content">
          <div class="preview-title">{{ focalPoint?.title }}</div>
          <div class="preview-meta">{{ focalPoint?.when }}</div>
        </div>
      </div>
      <div v-else-if="thread?.focal_point_type === 'Complaint'" class="complaint-preview">
        <span class="preview-icon">🏡</span>
        <div class="preview-content">
          <div class="preview-title">{{ focalPoint?.description }}</div>
          <div class="preview-meta">{{ focalPoint?.issue_type }}</div>
        </div>
      </div>
      <button class="view-context-btn">View Full Context →</button>
    </div>

    <!-- Reuse CoordinationChat component -->
    <CoordinationChat
      :thread-id="threadId"
      :focal-point="focalPoint"
    />
  </div>
</template>
```

2. **DiscussionsPanel.vue** (~1h):
```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { api } from '@/services/api'

const workspaceStore = useWorkspaceStore()
const threads = ref([])
const filter = ref('all') // 'all' | 'events' | 'complaints' | 'proposals'

async function loadThreads() {
  const focalPointType = filter.value === 'all' ? null
    : filter.value === 'events' ? 'CivicEvent'
    : filter.value === 'complaints' ? 'Complaint'
    : 'ProposedAgendaItem'

  const data = await api.getThreads({ focal_point_type: focalPointType })
  threads.value = data.threads
}

function openThread(thread) {
  workspaceStore.openArtifact({
    type: 'thread',
    id: thread.id,
    title: `Discussion: ${thread.focal_point_title}`
  })
}

onMounted(loadThreads)
</script>

<template>
  <div class="discussions-panel">
    <div class="panel-header">
      <h3>💬 Active Discussions</h3>
    </div>

    <div class="filter-tabs">
      <button @click="filter = 'all'; loadThreads()">All</button>
      <button @click="filter = 'events'; loadThreads()">Events</button>
      <button @click="filter = 'complaints'; loadThreads()">Issues</button>
    </div>

    <div class="threads-list">
      <div
        v-for="thread in threads"
        :key="thread.id"
        class="thread-item"
        @click="openThread(thread)"
      >
        <div class="thread-icon">
          {{ thread.focal_point_type === 'CivicEvent' ? '📅' : '🏡' }}
        </div>
        <div class="thread-info">
          <div class="thread-title">{{ thread.focal_point_title }}</div>
          <div class="thread-stats">
            {{ thread.participant_count }} people, {{ thread.message_count }} msgs
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
```

### Phase 2: Enable Threads in Existing Artifacts (~2h)

**Update EventArtifact.vue**:
```vue
<script setup lang="ts">
// Add thread handling
const hasThread = ref(false)
const threadId = ref(null)

async function checkForThread() {
  const data = await api.getThreads({
    focal_point_type: 'CivicEvent',
    focal_point_id: props.event.id
  })
  if (data.threads.length > 0) {
    hasThread.value = true
    threadId.value = data.threads[0].id
  }
}

async function openEventThread() {
  if (!hasThread.value) {
    // Create thread
    const data = await api.createThread({
      focal_point_type: 'CivicEvent',
      focal_point_id: props.event.id,
      user_id: userStore.userId
    })
    threadId.value = data.thread_id
  }

  // Open ThreadArtifact
  workspaceStore.openArtifact({
    type: 'thread',
    id: threadId.value,
    title: `Discussion: ${props.event.title}`
  })
}
</script>

<template>
  <!-- In Actions section -->
  <button @click="openEventThread" class="action-button">
    💬 {{ hasThread ? `Join Discussion (${participantCount} people)` : 'Start Discussion' }}
  </button>
</template>
```

**Update ComplaintArtifact.vue** - Remove nested CoordinationChat:
```vue
<!-- REMOVE this entire section -->
<div class="coordination-section">
  <CoordinationChat :complaint="complaint" />
</div>

<!-- REPLACE with button -->
<button @click="openComplaintThread" class="action-button">
  💬 Join Discussion ({{ thread?.participant_count || 0 }} people)
</button>
```

### Phase 3: Community Discovery (~1h)

**Add DiscussionsPanel to App.vue sidebar**:
```vue
<aside class="workspace-sidebar">
  <JurisdictionTree />
  <MyIssuesPanel />
  <DiscussionsPanel />  <!-- NEW! -->
  <LegislativePanel />
</aside>
```

---

## Success Criteria

### Must Have (Session 32+)
- [ ] ThreadArtifact opens in tabs (like events/complaints)
- [ ] DiscussionsPanel shows active threads
- [ ] Click thread in sidebar → opens ThreadArtifact
- [ ] EventArtifact has "Join Discussion" button
- [ ] Threads reuse CoordinationChat component (no rewrite)
- [ ] Real-time messaging still works via Socket.io

### Nice to Have
- [ ] Thread activity indicators (unread message count)
- [ ] "Hot threads" ranking (most active today)
- [ ] Search threads by keyword
- [ ] Notification when someone joins your thread

---

## PMF Strategy Alignment

**Complaint→Meeting Attendance Conversion**:

**Before** (Discussions hidden):
```
User files complaint → Sees matched events → ??? (no social proof)
```

**After** (Discussions visible):
```
User files complaint → Sees matched events → "15 people discussing this meeting" → Joins thread → Coordinates attendance → Shows up together
```

**Events as Social Hubs**:
- Every public meeting gets a discussion thread automatically
- "Join Discussion" replaces isolated "Add to Calendar" action
- Social proof: "X people planning to attend"
- Coordination: "Let's meet 30min before to prep"
- Follow-up: "What happened at the meeting?"

**Discovery Loop**:
- User browses events → Sees active discussions → Joins thread → Meets neighbors → Follows more issues → Creates more discussions → Network effects!

---

## Technical Notes

### Reuse Existing Code

**Already Implemented** (Session 27):
- ✅ `CoordinationChat.vue` - Real-time chat UI
- ✅ `civic_socketio_server.py` - Socket.io messaging
- ✅ `civic_participation.db` - threads/messages tables
- ✅ `complaint_storage.py` / `community_storage.py` - Data layer

**Only Need**:
- ThreadArtifact wrapper component (~150 lines)
- DiscussionsPanel listing component (~100 lines)
- Backend thread listing endpoint (~50 lines)
- Wire "Join Discussion" buttons in existing artifacts (~20 lines each)

**Total Effort**: ~5-6 hours implementation

### Schema Compliance

**civic-app-schema.json already supports this!**

```json
"DiscussionGroup": {
  "focal_point_type": {
    "enum": ["CivicEvent", "Complaint", "ProposedAgendaItem"]
  },
  "focal_point_id": { "type": "string" },
  "member_count": { "type": "integer" }
}
```

No schema changes needed - just UI/routing changes!

---

## Next Steps

1. **Session 32**: Implement ThreadArtifact component
2. **Session 33**: Implement DiscussionsPanel
3. **Session 34**: Wire up "Join Discussion" in EventArtifact
4. **Session 35**: Remove nested chat from ComplaintArtifact
5. **Session 36**: Testing + polish

**Estimated Timeline**: 3-4 sessions (~12-16 hours total)

**Branch**: `mcp-conversational-integration`
**Related Docs**:
- `FRONTEND_TECHNICAL_ARCHITECTURE.md` - Artifact system
- `CHAT_ROUTING_ARCHITECTURE.md` - Chat integration
- `civic-app-schema.json` - DiscussionGroup schema

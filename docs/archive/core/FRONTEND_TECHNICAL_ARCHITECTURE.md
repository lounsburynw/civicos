# Civic Conversational OS - Frontend Technical Architecture
## IDE-Inspired Civic Engagement Platform

**Version**: 2.2
**Date**: 2025-11-05
**Status**: Sessions 1-64 Complete | Session 65 Next (Email Pre-Population)

---

## Implementation Guide

For step-by-step implementation instructions, see **`FRONTEND_IMPLEMENTATION_ROADMAP.md`**. This document provides the **conceptual architecture** and design system; the roadmap provides **executable code examples** and validation criteria.

**Reading Order**:
1. Read this document (ARCHITECTURE) for conceptual understanding
2. Follow ROADMAP for layer-by-layer implementation with Claude Code
3. Reference this document's Part 5.3 for backend API status during implementation

---

## Executive Summary

Transform the Civic Conversational OS from a **chat-first interface** into a **workspace-first platform** modeled after IDEs like VSCode. Users navigate civic data through a **jurisdiction tree**, interact with **artifact-like dynamic windows** (events, complaints, legislative context, discussions), and compose actions in a multi-pane environment that grows in complexity as users demonstrate civic engagement.

**🆕 Chat Routing (Session 26 - 2025-10-22)**: The platform now uses **OpenAI function calling** to enable natural language navigation. Users can say "show housing meetings in Berkeley" and the system automatically dispatches to the correct function with extracted parameters. See `docs/CHAT_ROUTING_ARCHITECTURE.md` for complete details.

### Building on Stellar Current Foundation

**CRITICAL**: This architecture **enhances** the existing `civic-conversational-OS.html` rather than replacing it. The current design is stellar:
- ✅ **Solarized Light color scheme** - professional, readable, distinctive
- ✅ **Smooth transitions** - 0.2-0.3s ease throughout
- ✅ **Clean message bubbles** - no avatars, perfect readability
- ✅ **Centered empty states** - welcoming conversation starter
- ✅ **Collapsible sidebar** - smooth 300px → 120px collapse
- ✅ **Action chips** - rounded pills with perfect hover states
- ✅ **Welcome modal** - excellent onboarding UX

**Existing Frontend Assets**:
- `frontend/mcp-civic-server/civic-conversational-OS.html` - Production UI (203KB of stellar design)
- `frontend/mcp-civic-server/README-UX-Templates.md` - Phase 1/2/3 UX evolution templates
- `frontend/mcp-civic-server/index.html` - Template showcase and navigation
- `frontend/mcp-civic-server/DEVELOPMENT.md` - MCP server development log
- Phase templates: onboarding, chat, mobile, transparency dashboards

### Core Architectural Shift

**From**: Single conversational chat interface (current - stellar)
**To**: Multi-pane workspace with conversational intelligence embedded throughout (enhanced)

**IDE Analogy Elements** (NEW):
- **Sidebar**: Jurisdiction tree navigator (enhances current collapsible sidebar)
- **Editor Area**: Multiple tabs/panes for civic "artifacts" (new capability)
- **Command Palette**: Quick search/action launcher (Cmd+K / Ctrl+K) (new capability)
- **Status Bar**: Real-time civic activity updates (new capability)
- **Panels**: Bottom/side panels for chat (reuses current chat design), timeline, neighbors
- **Extensions**: Modular features users "enable" as they level up (progressive disclosure)

**Design Continuity Promise**: All new components will match the Solarized aesthetic, transition timing, and interaction patterns from `civic-conversational-OS.html`.

---

## Part 1: Conceptual Architecture

**Backend Implementation Status Legend**:
- ✅ **Backend Available** - Endpoint exists and ready to use
- ⏳ **Backend Needed (Phase 1)** - Required for MVP, needs implementation
- 🔮 **Backend Future** - Phase 2+ feature, defer implementation
- 🎨 **Frontend Only** - No backend dependency

### 1.1 The Civic IDE Workspace

```
┌─────────────────────────────────────────────────────────────────────┐
│ Oakland Civic OS                                   [user@oakland] ●  │
├──────────────────┬──────────────────────────────────────────────────┤
│                  │                                                   │
│ ▼ JURISDICTIONS  │  💬 Chat (70%)          📄 Artifact (30%)        │
│   🏛️ Oakland     │                         Planning Commission       │
│   🏛️ Berkeley    │  [Context: Item 7.2]                            │
│                  │                         ⭐ Item 7.2: Use Permit   │
│ ▼ DISCUSSIONS(5) │  User: Tell me about   📋 Agenda (expanded)      │
│   HOT TODAY      │  this item             🏛️ Legislative Context    │
│   📋 Pothole     │                                                   │
│   📋 Housing     │  AI: This is a housing [Draft Comment]           │
│                  │  development for...                               │
│ ▶ MY ISSUES      │                                                   │
│                  │  [Input: "Ask about this item..."]               │
│ ▶ LEGISLATIVE    │                                                   │
│                  │                                                   │
└──────────────────┴──────────────────────────────────────────────────┘
```

### 1.2 Core Components

#### **A. Sidebar Navigation (Collapsible Sections)** ✅ **IMPLEMENTED**
**Purpose**: Multi-context spatial navigation with progressive disclosure
**Status**: ✅ **Complete** (Sessions 36-63: Initial implementation → State management refactor - 2025-11-04)
**Backend Status**: `GET /api/jurisdictions` endpoint implemented (2025-10-13)
**UI Pattern**: Collapsible sections with smooth animations (NOT tab-based)

**Implementation**:
- Component: `CollapsibleSection.vue` (stateless with computed props)
- Store: `sidebar.ts` (single source of truth for all section state)
- Multiple sections visible simultaneously
- Architecture: Pinia store controls all sidebar state, clean unidirectional data flow
- All 6 sections connected: Profile, Jurisdictions, Events, Discussions, Issues, Legislative
- Familiar UX pattern with smooth transitions
- Multi-context awareness (see discussions AND jurisdictions AND issues)

**Sidebar Structure**:
```javascript
SidebarSections = {
  "JURISDICTIONS": {
    defaultExpanded: true,
    progressive: false,  // Always visible
    content: {
      "🏛️ Oakland": {events: 45, issues: 12},
      "🏛️ Berkeley": {events: 35, issues: 8},
      "🏛️ Alameda County": {events: 12, issues: 3}
    }
  },

  "DISCUSSIONS": {
    defaultExpanded: true,
    progressive: false,  // Always visible
    badgeCount: 5,       // Total active threads
    content: {
      "HOT TODAY": [
        {title: "ANOTHER HUGE POTHOLE!!!", messages: 5, participants: 1},
        {title: "Housing development on Main St", messages: 3, participants: 2}
      ],
      "ALL DISCUSSIONS": [
        // All threads...
      ]
    }
  },

  "MY ISSUES": {
    defaultExpanded: false,
    progressive: true,   // Appears after filing first complaint
    unlockTrigger: "filed_complaint",
    content: [
      {title: "Pothole on Main St", status: "matched", events: 1},
      {title: "Broken streetlight", status: "open", events: 0}
    ]
  },

  "LEGISLATIVE CONTEXT": {
    defaultExpanded: false,
    progressive: true,   // Appears after exploring 3+ housing events
    unlockTrigger: "explored_3_housing_events",
    content: {
      "State Bills": [{bill: "SB 35", topic: "housing"}],
      "Federal Programs": [{program: "CDBG", allocation: "$2.67M"}]
    }
  }
}
```

**Collapsible Section Features**:
- **Multiple sections expanded**: Users can see Jurisdictions + Discussions simultaneously
- **Smooth animations**: 0.3s ease transitions (matches existing design system)
- **State persistence**: Expand/collapse state saved to localStorage
- **Badge counts**: "DISCUSSIONS (5)" shows active thread count
- **Progressive disclosure**: MY ISSUES, LEGISLATIVE sections appear based on user actions
- **Keyboard navigation**: Space/Enter to toggle, Tab to move between sections
- **Independent scrolling**: Each expanded section scrolls independently (max-height: 40vh)

---

#### **B. Artifact System (Editor Area)**

**Concept**: Civic "objects" users can open, manipulate, and compose with

**Artifact Types**:

1. **Event Artifact** (CivicEvent) ✅ **Backend Available**
   - Multi-tab view: Overview | Agenda | Context | Actions
   - **Overview Tab**: Title, date, location, impact summary
   - **Agenda Tab**: Parsed agenda items with actionability scores
   - **Context Tab**: Legislative context (state bills, federal programs, financial context)
   - **Actions Tab**: Draft comment, calendar add, **"Join Discussion" → opens Thread Artifact**
   - **Backend**: Uses `GET /api/events/{id}` (already implemented)
   - **🆕 Social Integration**: Every event can have a discussion thread (focal_point_type: "CivicEvent")

2. **Complaint Artifact** (User-Generated) ✅ **Backend Available**
   - Status indicator: Open | Matched | Community Formed | Escalated
   - **Matched Events Section**: Shows linked civic meetings
   - **Similar Issues Panel**: Neighbors with same complaint
   - **Timeline View**: Activity history, government responses
   - **🆕 Social Integration**: **"Join Discussion" → opens Thread Artifact** (not nested chat widget)
   - **Backend**: `GET /api/complaints?user_id={user}` ✅ implemented
   - **Backend**: `POST /api/complaints` ✅ via conversation endpoint

3. **Proposal Artifact** (ProposedAgendaItem) 🔮 **Backend Future (Phase 5)**
   - **Collaborative editing**: Multiple users can contribute
   - **Support Counter**: Shows backing from neighbors
   - **Target Event Selector**: Choose which meeting to submit to
   - **Status Tracker**: Draft → Submitted → Accepted/Rejected
   - **Backend**: Requires `POST /api/proposals` (Phase 5 implementation)

4. **Thread Artifact** (First-Class Discussion) 🔮 **Backend Future (Phase 5)** - **PRIORITY UPGRADE**
   - **Purpose**: Make discussions visible, not buried in ComplaintArtifact
   - **Focal Point Reference**: Links to ANY artifact type (Event, Complaint, ProposedAgendaItem)
   - **Chat Interface**: Real-time messaging (Socket.io - already implemented!)
   - **Context Preview**: Shows linked artifact (event details, complaint summary, proposal text)
   - **Member List**: Active participants with follow status
   - **Action Coordination**: "Let's meet before City Council" scheduling
   - **Why This Matters**: Events should be social coordination hubs (PMF strategy!)
   - **Backend**: Uses existing `DiscussionGroup` schema (civic-app-schema.json:599-615)
   - **Backend Status**: Socket.io server exists (`civic_socketio_server.py`), needs thread creation/listing endpoints

5. **Comment Draft Artifact** (Civic Participation) ✅ **Backend Available (Session 37-38)** - **PMF CRITICAL**
   - **Purpose**: Transform passive browsing into active civic participation
   - **Structured Input Form**: Captures position, key concern, personal context BEFORE AI generation
   - **Dual-Purpose Data**: Input serves as both AI prompt context AND reusable civic data
   - **AI Generation**: gpt-4o-mini generates personalized 2-3 paragraph comment from structured input
   - **Draft Editor**: Fully editable textarea with visual cues and character hints
   - **Export Actions**: Copy to clipboard, download as .txt, email to council
   - **Why This Matters**: Core PMF conversion feature (complaint → meeting → **public comment**)
   - **Backend**: `POST /api/events/:event_id/draft-comment` ✅ (Session 37)
   - **Backend**: `POST /api/comments`, `GET /api/comments`, `GET /api/events/:event_id/comment-stats` ✅ (Session 38 documented, Session 39 implementation)
   - **Frontend**: CommentDraftArtifact.vue (Session 37), PositionSelector/KeyConcernInput/PersonalContextForm (Session 39)
   - **Next Phase**: Stats aggregation ("15 support, 3 oppose"), coordination signals ("12 others share your position"), council summary cards
   - **Architecture**: See `docs/COMMENT_DRAFTING_ARCHITECTURE.md` for complete 15-part design

6. **Legislative Context Artifact** (Educational) 🔮 **Backend Future (Phase 4)**
   - **State Legislation Panel**: Bills affecting local issues
   - **Federal Programs Panel**: HUD CDBG, DOT grants, etc.
   - **Leverage Points Explainer**: How residents can influence
   - **Cross-Reference Links**: "See which events relate to SB-9"
   - **Backend**: Requires `GET /api/legislative/{id}`, `GET /api/events?legislative_ref={id}` (Phase 4)

**Artifact Tab System**:
```javascript
// Users can have multiple artifacts open simultaneously
OpenArtifacts = [
  {type: "event", id: "event-123", title: "Planning Commission Oct 20", pinned: true},
  {type: "complaint", id: "complaint-456", title: "Pothole on Main St"},
  {type: "legislative", id: "sb-9", title: "SB-9 Housing Context"}
]
```

**Tab Actions**:
- **Pin**: Keep artifact open permanently
- **Close**: Remove from workspace (saved in history)
- **Split View**: Compare two artifacts side-by-side
- **Maximize**: Full-screen focus mode

---

#### **C. Command Palette (Cmd+K / Ctrl+K)** 🎨 **Frontend Only**

**Purpose**: Quick search and action launcher without mouse
**Backend Status**: No backend dependency - client-side fuzzy search with Fuse.js

**Command Categories**:

1. **Navigation**:
   ```
   > Go to: Berkeley City Council
   > Search events: housing
   > Find issues: traffic
   ```

2. **Actions**:
   ```
   > File complaint: [type description]
   > Draft comment for: [event]
   > Connect with neighbors on: [issue]
   ```

3. **Views**:
   ```
   > Timeline: All upcoming events
   > Dashboard: My civic activity
   > Map: Geographic issue clustering
   ```

4. **Shortcuts**:
   ```
   > What's happening this week?
   > Show my tracked issues
   > Refresh event data
   ```

**Intelligent Suggestions**:
- **Context-aware**: Suggests actions based on current artifact
- **Learning**: Adapts to user's frequent actions
- **Natural language**: "Report a pothole" works as command

---

#### **D. Conversational Intelligence (Embedded Panel)** ✅ **Backend Available** 🆕 **Chat Routing (Session 26)**

**Purpose**: AI copilot woven throughout workspace, not standalone chat
**Backend Status**:
- ✅ `POST /api/conversation` - General conversational API with complaint detection
- ✅ `POST /api/chat/route` - **NEW (Session 26)** - OpenAI function calling for intent recognition
  - Natural language → precise function dispatch
  - 6 core functions: search_events, file_complaint, view_legislative_context, draft_comment, view_my_complaints, explain_event
  - Cost: ~$0.30/month for 100 users
  - See `docs/CHAT_ROUTING_ARCHITECTURE.md` for details

**Integration Points**:

1. **Artifact Assistance**:
   - **In Event Artifact**: "Explain this agenda item in plain language"
   - **In Complaint Form**: "How should I describe this issue?"
   - **In Proposal Draft**: "Suggest improvements to my argument"

2. **Smart Suggestions**:
   - **Proactive Tips**: "💡 This meeting relates to your tracked issue"
   - **Learning Moments**: "🎓 This is a good time for public comment"
   - **Community Connections**: "👥 5 neighbors care about this too"

3. **Panel Modes**:
   - **Bottom Panel** (default): Minimized chat for quick questions
   - **Side Panel**: Full conversation history
   - **Inline**: Contextual help within artifacts

**Conversational UI Flow** (with Chat Routing):
```javascript
// User types natural language message
async handleUserMessage(message) {
  // Route message through OpenAI function calling
  const action = await routeChatMessage(message, conversationId, currentContext);

  // Dispatch based on intent
  switch (action.action) {
    case 'search_events':
      // Open EventList with filters from action.parameters
      openEventList({
        query: action.parameters.query,
        jurisdiction: action.parameters.jurisdiction
      });
      break;

    case 'file_complaint':
      // Open ComplaintForm with pre-filled data
      openComplaintForm({
        description: action.parameters.description,
        address: action.parameters.address
      });
      break;

    case 'respond':
      // Just show conversational response
      addMessageToChat(action.message);
      break;
  }
}

// Proactive suggestions (existing functionality)
Artifact.onOpen(event_id) {
  AI.analyzeContext(event_id, user_context);

  ChatPanel.addMessage({
    role: "assistant",
    content: "This meeting discusses housing on Main St. You filed a complaint about traffic on Main St last week - want to link them?",
    actions: [
      {label: "Link my complaint", type: "link_issue_to_event"},
      {label: "Draft comment", type: "compose_comment"},
      {label: "Dismiss", type: "dismiss"}
    ]
  });
}
```

---

#### **E. Progressive Disclosure & Earned Complexity** 🎨 **Frontend Only (with state tracking)**

**Philosophy**: Start simple, reveal features through demonstrated interest
**Backend Status**: Frontend user profile tracking (localStorage/Pinia store). Optional future: sync with backend user profile service

**User Experience Levels**:

1. **New Users** (Visits: 0-2):
   - **Visible**: Jurisdiction tree (events only), single artifact view, bottom chat panel
   - **Hidden**: Issue filing, neighbors panel, legislative context, proposals
   - **Trigger**: "Want to report an issue?" appears after viewing 3+ events

2. **Returning Users** (Visits: 3-10, 1+ action):
   - **New Unlocks**: Issue filing, similar issues panel, calendar integration
   - **Hidden**: Discussion groups, proposal system, budget context
   - **Trigger**: "Connect with neighbors?" after filing 2+ issues

3. **Expert Users** (Visits: 10+, 5+ actions):
   - **Full Access**: All features, expert shortcuts, batch operations
   - **Advanced**: Multi-artifact split views, custom dashboards, API access
   - **Trigger**: "Enable expert mode?" notification

**Feature Revelation Strategy**:
```javascript
ProgressiveDisclosure = {
  "issue_filing": {
    trigger: "viewed_3_events",
    message: "💡 Noticed a local issue? You can report it here and I'll match it to relevant meetings."
  },
  "neighbor_clustering": {
    trigger: "filed_2_issues",
    message: "👥 Did you know 5 neighbors reported similar issues? Connect with them to coordinate action."
  },
  "proposal_system": {
    trigger: "attended_meeting || submitted_comment",
    message: "🎯 Ready to propose an agenda item? Your experience makes you eligible to suggest topics for upcoming meetings."
  },
  "legislative_context": {
    trigger: "explored_3_housing_events",
    message: "📚 Want to understand how state bills affect local decisions? I can show you the legislative context."
  }
}
```

---

## Part 2: Technical Architecture

### 2.1 Frontend Stack Recommendation

**Framework**: Vue 3 with Composition API
**Why**: Progressive, component-based, excellent TypeScript support, smaller bundle than React

**Key Libraries**:
```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.0",           // State management
    "splitpanes": "^3.1.0",      // Split views
    "vue-draggable-plus": "^0.5.0", // Drag-and-drop
    "fuse.js": "^7.0.0",         // Fuzzy search
    "@vueuse/core": "^10.9.0",   // Composable utilities
    "date-fns": "^3.0.0",        // Date formatting
    "mapbox-gl": "^3.0.0",       // Map view
    "chart.js": "^4.4.0"         // Visualizations (optional)
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "vitest": "^1.0.0",
    "@vue/test-utils": "^2.4.0",
    "typescript": "^5.3.0"
  }
}
```

### 2.2 State Management Architecture

**Pinia Stores** (with Context Management integration - 2025-11-01):

```javascript
// stores/workspace.js
export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    openArtifacts: [],
    activeArtifactId: null,
    layout: 'single', // 'single' | 'split-h' | 'split-v' | 'grid'
    sidebarCollapsed: false,
    chatPanelVisible: true
  }),
  actions: {
    openArtifact(artifact) {
      const existing = this.openArtifacts.find(a => a.id === artifact.id);
      if (!existing) {
        this.openArtifacts.push(artifact);
      }
      this.activeArtifactId = artifact.id;
    },
    closeArtifact(artifact_id) {
      this.openArtifacts = this.openArtifacts.filter(a => a.id !== artifact_id);
    }
  }
});

// stores/jurisdiction.js
export const useJurisdictionStore = defineStore('jurisdiction', {
  state: () => ({
    tree: [],
    expandedNodes: new Set(),
    selectedJurisdiction: null
  }),
  actions: {
    async loadJurisdictions() {
      const response = await fetch('/api/jurisdictions');
      this.tree = await response.json();
    }
  }
});

// stores/sidebar.js (NEW - Session 36)
export const useSidebarStore = defineStore('sidebar', {
  state: () => ({
    sections: {
      jurisdictions: true,    // Expanded by default
      discussions: true,      // Expanded by default
      myIssues: false,        // Collapsed by default (progressive)
      legislative: false      // Collapsed by default (progressive)
    }
  }),
  actions: {
    toggleSection(sectionName: string) {
      this.sections[sectionName] = !this.sections[sectionName];
      // Persist to localStorage
      localStorage.setItem('sidebar-sections', JSON.stringify(this.sections));
    },
    loadFromLocalStorage() {
      const saved = localStorage.getItem('sidebar-sections');
      if (saved) {
        this.sections = JSON.parse(saved);
      }
    }
  }
});

// stores/user.js
export const useUserStore = defineStore('user', {
  state: () => ({
    id: null,
    experience_level: 'new', // 'new' | 'returning' | 'expert'
    civic_profile: null,
    preferences: {}
  }),
  getters: {
    canAccessFeature: (state) => (feature) => {
      // Progressive disclosure logic
      const featureGates = {
        'issue_filing': state.civic_profile.visits >= 3,
        'neighbor_connections': state.civic_profile.interactions >= 5,
        'proposal_system': state.civic_profile.comments_submitted >= 1
      };
      return featureGates[feature] || false;
    }
  }
});

// stores/context.ts (NEW - 2025-11-01)
// See CONTEXT_MANAGEMENT_ARCHITECTURE.md for complete schema
export const useContextStore = defineStore('context', {
  state: () => ({
    registry: new Map<string, ContextElement>(),
    activeMode: 'navigation' as ChatMode,
    userContextPreferences: {
      maxElements: 5,
      autoIncludeRelated: true
    }
  }),

  actions: {
    registerContext(element: ContextElement) {
      // Deduplication via content_hash
      const existing = this.findByContentHash(element.content_hash);
      if (existing) {
        this.update(existing.id, { accessed_at: new Date() });
        return;
      }

      this.registry.set(element.id, element);
      this.updateIndexes(element);
      this.pruneIfNeeded();
    },

    getActiveContext(): ContextElement[] {
      const modeConfig = CHAT_MODES[this.activeMode];
      return Array.from(this.registry.values())
        .filter(modeConfig.contextFilter)
        .sort((a, b) => scorePriority(a, b))
        .slice(0, modeConfig.maxElements);
    }
  }
});
```

### 2.3 API Client Architecture

**Centralized API Service** (with backend implementation status):

```typescript
// services/api.ts
import type { CivicEvent, Complaint, Jurisdiction } from '@/types';

class CivicAPI {
  private baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

  // ⏳ NOT IMPLEMENTED - needs GET /api/jurisdictions
  async getJurisdictions(): Promise<Jurisdiction[]> {
    const response = await fetch(`${this.baseURL}/api/jurisdictions`);
    return response.json();
  }

  // ✅ IMPLEMENTED - uses GET /api/events
  async getEvents(filters?: {jurisdiction_id?: string, project_type?: string}): Promise<CivicEvent[]> {
    const params = new URLSearchParams(filters as any);
    const response = await fetch(`${this.baseURL}/api/events?${params}`);
    return response.json();
  }

  // ✅ IMPLEMENTED - uses GET /api/events/{id}
  async getEvent(id: string): Promise<CivicEvent> {
    const response = await fetch(`${this.baseURL}/api/events/${id}`);
    return response.json();
  }

  // ⏳ NOT IMPLEMENTED - needs POST /api/complaints (storage exists, but no standalone endpoint)
  async fileComplaint(complaint: Partial<Complaint>): Promise<Complaint> {
    const response = await fetch(`${this.baseURL}/api/complaints`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(complaint)
    });
    return response.json();
  }

  // ⏳ NOT IMPLEMENTED - needs GET /api/complaints?user_id={user}
  async getComplaints(user_id: string): Promise<Complaint[]> {
    const response = await fetch(`${this.baseURL}/api/complaints?user_id=${user_id}`);
    return response.json();
  }

  // ✅ IMPLEMENTED - uses POST /api/conversation (includes complaint detection)
  async sendMessage(message: string, context?: any): Promise<any> {
    const response = await fetch(`${this.baseURL}/api/conversation`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message, context})
    });
    return response.json();
  }
}

export const api = new CivicAPI();
```

### 2.4 Component Structure

**Build Order**: Implement components following the **abstraction-first strategy** in `FRONTEND_IMPLEMENTATION_ROADMAP.md`:
- **Layer 1**: Design system + types (most abstract)
- **Layer 2**: Core components (JurisdictionTree, EventArtifact)
- **Layer 3**: State management (Pinia stores) + services (API client)
- **Layer 4**: Integration (WorkspaceContainer)
- **Layer 5**: Features (ComplaintArtifact, etc. - most concrete)

See ROADMAP for complete implementation sequence with validation gates between layers.

```
src/
├── components/
│   ├── workspace/
│   │   ├── WorkspaceContainer.vue       # Root layout manager (Layer 4)
│   │   ├── CommandPalette.vue           # Cmd+K search (Layer 5)
│   │   └── StatusBar.vue                # Bottom status bar (Layer 5)
│   ├── sidebar/
│   │   ├── JurisdictionTree.vue         # Tree navigator (Layer 2)
│   │   ├── DiscussionsPanel.vue         # Discussions list (Layer 2) [Session 32]
│   │   ├── MyIssuesPanel.vue            # User's complaints (Layer 2) [Session 21]
│   │   ├── LegislativePanel.vue         # Legislative context (Layer 2) [Session 20]
│   │   ├── SearchPanel.vue              # Search interface (Layer 5)
│   │   └── NeighborsPanel.vue           # Community sidebar (Layer 5)
│   ├── artifacts/
│   │   ├── ArtifactContainer.vue        # Tab manager (Layer 4)
│   │   ├── EventArtifact.vue            # Event details (Layer 2)
│   │   ├── ComplaintArtifact.vue        # Issue details (Layer 5)
│   │   ├── ProposalArtifact.vue         # Proposal drafting (Layer 5)
│   │   ├── ThreadArtifact.vue           # Discussion thread (Layer 5) [Session 31]
│   │   └── LegislativeArtifact.vue      # Bill/program details (Layer 5)
│   ├── panels/
│   │   ├── ChatPanel.vue                # Conversational AI (Layer 5)
│   │   └── TimelinePanel.vue            # Chronological view (Layer 5)
│   └── shared/
│       ├── CollapsibleSection.vue       # (Layer 2) [NEW - Session 36] ⭐
│       ├── ActionButton.vue             # (Layer 2)
│       ├── EventCard.vue                # (Layer 2)
│       └── StatusBadge.vue              # (Layer 2)
├── stores/
│   ├── workspace.ts                     # (Layer 3)
│   ├── jurisdiction.ts                  # (Layer 3)
│   ├── sidebar.ts                       # (Layer 3) [NEW - Session 36] ⭐
│   ├── user.ts                          # (Layer 3)
│   └── chat.ts                          # (Layer 3)
├── services/
│   ├── api.ts                           # (Layer 3)
│   └── websocket.ts                     # (Layer 5)
├── types/
│   └── civic.ts                         # TypeScript interfaces (Layer 1)
└── App.vue                              # (Layer 4)
```

---

## Part 3: Design System (Building on Stellar Current Design)

### 3.1 Design Philosophy: Preserve What Works

**CRITICAL**: The current `civic-conversational-OS.html` has a **stellar design** that users love. The workspace evolution must **enhance, not replace** this foundation.

**Design System File**: During implementation, the design system will be extracted to `frontend/civic-workspace/src/design-system.css`. See `FRONTEND_IMPLEMENTATION_ROADMAP.md` Layer 1.1 for the complete extraction process with validation criteria. This file will preserve all design tokens from the current UI.

**Core Design Principles to Preserve**:
1. **Solarized Light aesthetic** - Professional, readable, distinctive
2. **Smooth transitions** - 0.2-0.3s ease transitions throughout
3. **No avatars** - Clean, minimalist message bubbles
4. **Centered empty states** - Input centered when conversation starts
5. **Collapsible sidebar** - Smooth 300px → 120px collapse
6. **Action chips** - Rounded pill buttons (border-radius: 16px)
7. **Subtle shadows** - Solarized-tinted shadows (not harsh black)
8. **Typography** - Inter font with careful hierarchy

**Existing Frontend Documentation**:
- `frontend/mcp-civic-server/README-UX-Templates.md` - Phase 1/2/3 UX evolution
- `frontend/mcp-civic-server/civic-conversational-OS.html` - Production UI (stellar design)
- `frontend/mcp-civic-server/DEVELOPMENT.md` - Development log
- `frontend/mcp-civic-server/index.html` - Template showcase

### 3.2 Color Palette (Solarized - DO NOT CHANGE)

**Current Colors** (from `civic-conversational-OS.html` - **PRESERVE EXACTLY**):
```css
:root {
  --primary: #268bd2;              /* Solarized blue */
  --primary-light: #eee8d5;        /* Solarized base2 (light highlight) */
  --text-primary: #073642;         /* Solarized base02 (darkest readable text) */
  --text-secondary: #586e75;       /* Solarized base01 (secondary content) */
  --background: #fdf6e3;           /* Solarized base3 (background) */
  --background-secondary: #eee8d5; /* Solarized base2 (background highlights) */
  --background-extra-light: #fffbf0; /* Even lighter than base3 for chat area */
  --border: #d3d3d3;               /* Softer border for Solarized */
  --shadow: 0 2px 16px rgba(101, 123, 131, 0.15); /* Solarized-tinted shadows */
  --shadow-subtle: 0 1px 3px rgba(101, 123, 131, 0.1);
  --accent-green: #859900;         /* Solarized green */
  --accent-orange: #cb4b16;        /* Solarized orange */
  --accent-red: #dc322f;           /* Solarized red */
  --accent-purple: #6c71c4;        /* Solarized violet */
  --gradient: linear-gradient(135deg, var(--primary) 0%, var(--accent-purple) 100%);
}
```

**New Semantic Colors** (for workspace UI):
```css
:root {
  /* Status colors */
  --status-open: var(--accent-orange);
  --status-matched: var(--accent-green);
  --status-escalated: var(--accent-purple);
  --status-resolved: var(--text-secondary);

  /* Panel backgrounds */
  --sidebar-bg: var(--background-secondary);
  --artifact-bg: var(--background);
  --panel-bg: var(--background-extra-light);

  /* Interactive elements */
  --hover-bg: #e8dfc8;
  --active-bg: #d9cdb0;
  --focus-ring: var(--primary);
}
```

### 3.3 Typography (Preserve Current System)

**Font Stack** (from `civic-conversational-OS.html`):
```css
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Display', system-ui, sans-serif;
  line-height: 1.5;
}

/* Headings */
h1, h2, h3 {
  font-weight: 600;
  line-height: 1.2;
}

/* Message content */
.message-content {
  font-size: 15px;
  line-height: 1.5;
}

/* Input text */
.message-input {
  font-size: 16px;
  line-height: 1.4;
}

/* Centered empty state title */
.civic-title {
  font-size: 48px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1;
}

/* Code/Data (for artifact headers, IDs) */
.artifact-id, .jurisdiction-id {
  font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
  font-size: 0.9em;
}
```

### 3.4 Spacing System (8px grid)

```css
:root {
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
}
```

### 3.5 Component Patterns (Evolved from Current Design)

**Artifact Window** (NEW - but using current design language):
```css
.artifact-window {
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow); /* Use existing Solarized-tinted shadow */
  display: flex;
  flex-direction: column;
  height: 100%;
  transition: all 0.3s ease; /* Match existing transition timing */
}

.artifact-header {
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.artifact-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  padding: 0 var(--space-md);
}

.artifact-tabs button {
  padding: var(--space-sm) var(--space-md);
  border: none;
  background: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease; /* Match existing button transitions */
}

.artifact-tabs button.active {
  border-bottom-color: var(--primary);
  color: var(--primary);
}

.artifact-body {
  padding: var(--space-lg);
  overflow-y: auto;
  flex: 1;
}
```

**Message Bubbles** (PRESERVE - already perfect):
```css
.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.5;
}

.message.ai .message-content {
  background: var(--background-secondary);
  border-top-left-radius: 4px;
}

.message.user .message-content {
  background: var(--primary);
  color: white;
  border-top-right-radius: 4px;
}
```

**Action Chips** (PRESERVE - current design is stellar):
```css
.action-chip {
  background: var(--primary-light);
  color: var(--primary);
  border: none;
  border-radius: 16px;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-chip:hover {
  background: var(--primary);
  color: white;
}
```

**Collapsible Section** (Sessions 36-63 - State management with Pinia store):
```css
/* CollapsibleSection.vue component styles */
.collapsible-section {
  border-bottom: 1px solid var(--border);
}

.collapsible-section-header {
  display: flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  cursor: pointer;
  user-select: none;
  transition: background 0.2s ease;
}

.collapsible-section-header:hover {
  background: var(--hover-bg);
}

.collapsible-section-header:focus {
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
}

.collapsible-section-chevron {
  margin-right: var(--space-xs);
  transition: transform 0.3s ease;
  font-size: 0.8em;
  color: var(--text-secondary);
}

.collapsible-section-chevron.expanded {
  transform: rotate(90deg);
}

.collapsible-section-icon {
  margin-right: var(--space-xs);
  font-size: 1em;
}

.collapsible-section-title {
  flex: 1;
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.collapsible-section-badge {
  background: var(--primary);
  color: white;
  font-size: 0.75em;
  padding: 2px 6px;
  border-radius: 10px;
  margin-left: var(--space-xs);
}

.collapsible-section-content {
  overflow: hidden;
  transition: height 0.3s ease;
}

.collapsible-section-content.collapsed {
  height: 0 !important;
}

/* Panel scroll behavior within sections */
.collapsible-section-content > * {
  max-height: 40vh; /* Prevent one section from dominating */
  overflow-y: auto;
}
```

**Tree Node** (existing - but matching current aesthetic):
```css
.tree-node {
  display: flex;
  align-items: center;
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
  border-radius: 6px; /* Match sidebar collapse toggle */
  user-select: none;
  transition: all 0.2s ease; /* Match existing transitions */
}

.tree-node:hover {
  background: var(--primary-light); /* Match existing hover states */
  color: var(--primary);
}

.tree-node.active {
  background: var(--primary);
  color: white;
  font-weight: 600;
}

.tree-node-icon {
  margin-right: var(--space-xs);
  font-size: 1.1em;
}

.tree-node-badge {
  margin-left: auto;
  background: var(--primary);
  color: white;
  font-size: 0.75em;
  padding: 2px 6px;
  border-radius: 10px;
}
```

**Sidebar Collapse Button** (PRESERVE - from current design):
```css
.sidebar-collapse-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all 0.2s ease;
  color: var(--text-secondary);
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
}

.sidebar-collapse-toggle:hover {
  background: var(--primary-light);
  color: var(--primary);
}
```

**Welcome Modal** (PRESERVE - stellar onboarding):
```css
.welcome-modal {
  background: var(--background);
  border-radius: 16px;
  padding: 32px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
  text-align: center;
  transform: scale(0.95);
  transition: transform 0.3s ease;
}

.sample-question {
  background: var(--primary-light);
  border: 1px solid transparent;
  border-radius: 24px;
  padding: 12px 20px;
  color: var(--primary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 14px;
  text-align: left;
  border: 1px solid var(--border);
}

.sample-question:hover {
  background: var(--primary);
  color: white;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 123, 255, 0.25);
  border-color: var(--primary);
}
```

---

## Part 4: Success Metrics & Rollout Strategy

### 4.1 Key Performance Indicators

**Phase 1 (Foundation)**:
- [ ] 80% of users successfully navigate jurisdiction tree within first visit
- [ ] Average time-to-open-event < 5 seconds
- [ ] Command palette usage > 10% of navigation actions

**Phase 2 (Complaint Integration)**:
- [ ] 30% of users file at least one complaint
- [ ] Complaint→event match rate > 30%
- [ ] Complaint→action conversion > 10%

**Phase 3 (Multi-Artifact)**:
- [ ] Power users (>10 visits) open average 2.5 artifacts per session
- [ ] Tab usage > 40% among returning users
- [ ] Workspace persistence adoption > 60%

**Phase 4 (Legislative Context)**:
- [ ] Context tab view rate > 25% for housing/budget events
- [ ] Legislative artifact opens > 15% of users who view context
- [ ] User comprehension survey: >70% understand state/local connection

**Phase 5 (Community)**:
- [ ] Neighbor connection rate > 20% among complaint filers
- [ ] Discussion group formation > 10% of matched complaints
- [ ] Proposal submissions > 5% of active groups

### 4.2 Rollout Strategy

**Stage 1: Dogfooding** (2 weeks)
- Internal team use only
- Test all workflows with real civic data
- Fix critical bugs, refine UX

**Stage 2: Beta Users** (4 weeks)
- Invite 50 civically-engaged users
- Focus on Berkeley (best data quality)
- Weekly feedback sessions

**Stage 3: Soft Launch** (6 weeks)
- Public access with "beta" label
- Monitor analytics, iterate on pain points
- Expand to Oakland, San Rafael

**Stage 4: Full Launch**
- Remove beta label
- Marketing push (blog posts, social media)
- Foundation demos for grant applications

---

## Part 5: Migration from Current Frontend

### 5.1 Compatibility Strategy

**Option A: Parallel Deployment** (Recommended)
- Run old chat UI at `/legacy`
- New workspace UI at `/` (default)
- User preference toggle to switch
- Gradual migration over 3 months

**Option B: Staged Replacement**
- Keep chat panel, add sidebar/artifacts incrementally
- Hybrid UI during transition
- Full replacement after Phase 3

### 5.2 Data Migration

**No backend changes required** - Workspace UI consumes same API endpoints:
- `GET /api/events` → Powers jurisdiction tree and event artifacts
- `POST /api/conversation` → Powers chat panel
- `POST /api/complaints` → Powers complaint artifacts

**New endpoints needed** (non-breaking):
- `GET /api/jurisdictions` → Sidebar navigation
- `GET /api/complaints?user_id={user}` → My Issues section
- `GET /api/legislative/{id}` → Legislative artifacts

---

## Part 5.3: Backend API Requirements Status

This section documents which backend endpoints are **available**, which are **needed for Phase 1 MVP**, and which can be **deferred to future phases**.

### ✅ Phase 1 Available (Current Backend)

**Event Management**:
```
GET  /api/events                        # List all civic events (schema-compliant)
GET  /api/events/{id}                   # Single event details
GET  /api/legistar/{city}/events        # Legistar API events (Oakland, Santa Rosa, Sonoma County)
```

**Conversation & Complaints**:
```
POST /api/conversation                  # AI conversation + complaint detection ✨ Phase 1 MVP
  Request: { message, conversation_id?, user_id?, city?, state?, interests[] }
  Response Types:
    - complaint_matched: { response, grouped_actions[], complaint_id }
    - complaint_no_match: { response, complaint_id, metadata }
    - clarification_needed: { response, metadata.clarification_type }
    - general: { response, actions[], conversation_id }
```

**Agenda Integration**:
```
GET  /api/agenda/{event_id}             # Agenda integration status
GET  /api/agenda/{event_id}/discover    # Discover agenda URL
GET  /api/agenda/{event_id}/parse       # Parse agenda content
```

**Data Management**:
```
GET  /api/refresh                       # Data refresh (secure implementation)
POST /api/refresh-data                  # Manual data refresh
GET  /api/status                        # API health check
GET  /health                            # Health check (public)
```

### ✅ Phase 1 Complete (Newly Implemented - 2025-10-13)

These critical Phase 1 endpoints have been implemented and tested. Frontend development is now **fully unblocked** for MVP.

#### 1. GET /api/jurisdictions ✅ **IMPLEMENTED**
**Purpose**: Populate jurisdiction tree sidebar
**Status**: **Available** - Ready for frontend integration
**Implementation**: `src/civic_api_integrated.py:623-770`

**Response Format**:
```typescript
{
  jurisdictions: [
    {
      id: "city-berkeley",
      name: "Berkeley",
      type: "city",
      event_count: 35,
      issue_count: 12,
      cdbg_allocation: "$2.67M"
    }
  ],
  metadata: {
    total_jurisdictions: 23,
    total_events: 170,
    total_issues: 48
  }
}
```

**Implementation Details**:
- Aggregates from `data/events/events_*.json` files using regex pattern matching
- Counts events per jurisdiction (uses max count across multiple files)
- Queries `civic_participation.db` for issue counts via `ComplaintStorage`
- Loads CDBG allocations from `data/jurisdiction_overrides/{jurisdiction_id}.json`
- Returns sorted by event_count descending
- Handles jurisdiction_id to display name mapping via `CITY_CONFIGS`

**Test Results**: ✅ All tests passing (23 jurisdictions, 170 events, 48 issues)

---

#### 2. GET /api/complaints?user_id={user} ✅ **IMPLEMENTED**
**Purpose**: "My Issues" section (track user's filed complaints)
**Status**: **Available** - Ready for frontend integration
**Implementation**: `src/civic_api_integrated.py:772-849`, `src/complaint_storage.py:140-200`

**Response Format**:
```typescript
{
  complaints: [
    {
      id: "complaint-uuid",
      user_id: "user123",
      description: "Pothole on Main St",
      issue_type: "transportation",
      jurisdiction_id: "city-berkeley",
      status: "matched" | "open" | "escalated" | "resolved",
      created_at: "2025-10-13T10:00:00Z",
      updated_at: "2025-10-13T11:00:00Z",
      matched_events: [
        {
          event_id: "event-123",
          match_score: 0.85,
          match_reason: "Transportation topic + Main St location"
        }
      ],
      related_complaints: ["complaint-uuid-2"],
      discussion_group_id: null,
      location: {
        address: "Main St & 5th Ave",
        latitude: 37.8715,
        longitude: -122.2730
      }
    }
  ],
  metadata: {
    total_complaints: 1,
    matched_count: 0,
    open_count: 1
  }
}
```

**Implementation Details**:
- New method: `ComplaintStorage.get_user_complaints(user_id)`
- Retrieves all complaints for user with matched events
- Includes similar complaints via `find_similar_complaints()` (issue_type + jurisdiction matching)
- Returns related_complaints array for clustering UI
- Supports discussion_group_id field (Phase 2 feature, currently null)
- Properly formats location data when available

**Test Results**: ✅ All tests passing (empty users return [], filed complaints return with metadata)

---

### ⏳ Phase 1 Remaining (Optional)

#### 3. POST /api/complaints (standalone endpoint)
**Purpose**: File complaint outside of conversation flow
**Priority**: **MEDIUM** (complaint filing currently works via /api/conversation)
**Complexity**: ~60 lines (wrap existing complaint_handler)

**Request Format**:
```typescript
{
  user_id: "user123",
  description: "Broken streetlight on Elm St",
  issue_type: "public_safety",
  jurisdiction_id: "city-berkeley",
  location?: {
    address: "Elm St & 5th Ave",
    latitude: 37.8715,
    longitude: -122.2730
  }
}
```

**Response Format**:
```typescript
{
  complaint_id: "complaint-uuid",
  status: "matched" | "no_match",
  matched_events: [...],  // If matched
  similar_complaints_count: 3
}
```

**Implementation Notes**:
- Wrap `complaint_handler.handle_message()` with direct complaint creation
- Bypass LLM intent detection (assume complaint from this endpoint)

---

### 🔮 Phase 2+ Needed (Future Features)

These endpoints support advanced features. Implement **only after Phase 1 PMF validation**.

#### POST /api/complaints/{id}/link-event
**Purpose**: Manually link complaint to civic event
**Phase**: 2 (Complaint-to-Civic Phase 2 - drag-and-drop linking)
**Complexity**: ~40 lines

**Request**: `{ event_id: "event-123" }`
**Response**: `{ success: true, complaint: {...}, linked_event: {...} }`

---

#### GET /api/legislative/{id}
**Purpose**: Legislative artifact details
**Phase**: 4 (Legislative Context Phase)
**Complexity**: ~100 lines (query legislative_context_cache + hydration)

**Response Format**:
```typescript
{
  id: "sb-9",
  bill: "SB 9",
  title: "Housing Development: Approvals",
  status: "Chaptered",
  summary: "...",
  leverage_point: "...",
  official_url: "...",
  related_events: [
    {
      event_id: "event-123",
      title: "Planning Commission Meeting",
      relevance: "Implements SB 9 duplex requirements"
    }
  ]
}
```

---

#### GET /api/events?legislative_ref={id}
**Purpose**: Find events related to specific legislation
**Phase**: 4 (Legislative Context Phase)
**Complexity**: ~30 lines (filter events by legislative_context field)

---

#### POST /api/discussions
**Purpose**: Create discussion group
**Phase**: 5 (Community Features)
**Complexity**: ~150 lines (new discussion system)

**Request**: `{ title, focal_point: {type: "complaint"|"event", id}, initial_members[] }`
**Response**: `{ discussion_id, invite_url, initial_state }`

---

#### GET /api/discussions/{id}/messages
**Purpose**: Get discussion messages
**Phase**: 5 (Community Features)
**Complexity**: ~80 lines (message storage + pagination)

---

#### POST /api/proposals
**Purpose**: Submit proposed agenda item
**Phase**: 5 (Community Features)
**Complexity**: ~200 lines (proposal workflow system)

**Request**: `{ title, description, target_event_id, supporters[] }`
**Response**: `{ proposal_id, status, submission_deadline }`

---

### 📋 Implementation Order

**Implementation Note**: When implementing components in `FRONTEND_IMPLEMENTATION_ROADMAP.md`, check this section (Part 5.3) for backend status before each layer. Use mock data for ⏳ and 🔮 endpoints until backend is ready. The ROADMAP includes inline status comments in code examples.

**Immediate (Weeks 1-2)**: Phase 1 blockers
1. GET /api/jurisdictions (sidebar blocking)
2. GET /api/complaints?user_id={user} (complaint tracking blocking)
3. POST /api/complaints (optional - can defer if /api/conversation sufficient)

**Phase 2 (After MVP validation)**: Complaint-to-Civic Phase 2
4. POST /api/complaints/{id}/link-event (drag-and-drop feature)

**Phase 4 (After Multi-Artifact adoption)**: Legislative Context
5. GET /api/legislative/{id} (legislative artifacts)
6. GET /api/events?legislative_ref={id} (cross-references)

**Phase 5 (After Legislative Context proven)**: Community Features
7. POST /api/discussions (discussion groups)
8. GET /api/discussions/{id}/messages (chat interface)
9. POST /api/proposals (proposal system)

---

### 🚨 Frontend Development Strategy During Gap

While waiting for Phase 1 endpoints:

1. **Mock Data Providers**: Create mock implementations of missing endpoints
   ```typescript
   // services/api.mock.ts
   export const mockAPI = {
     getJurisdictions: () => Promise.resolve(MOCK_JURISDICTIONS),
     getComplaints: () => Promise.resolve(MOCK_COMPLAINTS)
   };
   ```

2. **Feature Flags**: Toggle between mock and real API
   ```typescript
   const USE_MOCK = import.meta.env.VITE_USE_MOCK_API === 'true';
   const api = USE_MOCK ? mockAPI : realAPI;
   ```

3. **Progressive Enhancement**: Build UI components first, wire API calls later
   - JurisdictionTree component works with static data
   - ComplaintArtifact component shows mock complaints
   - Add real API integration once endpoints available

4. **TODO Comments**: Mark all mock API calls clearly
   ```typescript
   // TODO: Replace with real API once GET /api/jurisdictions implemented
   const jurisdictions = await mockAPI.getJurisdictions();
   ```

---

## Part 6: Open Questions & Decisions Needed

### 6.1 Technical Decisions

1. **Framework Choice**: Vue 3, React 18, or Svelte 4?
   - **Recommendation**: Vue 3 (progressive, smaller bundle, excellent DX)

2. **Real-time Communication**: WebSockets or polling for discussion groups?
   - **Recommendation**: Polling for Phase 1, WebSockets in Phase 2

3. **Map Provider**: Mapbox, Google Maps, or OpenStreetMap?
   - **Recommendation**: Mapbox (best DX, generous free tier)

4. **Mobile Strategy**: Responsive web app or native mobile apps?
   - **Recommendation**: Responsive web first, native apps in 2026 if PMF proven

### 6.2 UX Decisions

1. **Default View**: Should new users see jurisdiction tree or welcome screen?
   - **Recommendation**: Welcome screen with "Choose your city" prompt

2. **Chat Panel Position**: Bottom, right, or floating?
   - **Recommendation**: Bottom (familiar from IDEs, doesn't compete with sidebar)

3. **Artifact Limits**: Max number of open artifacts?
   - **Recommendation**: 10 tabs (performance considerations)

4. **Feature Gating**: Should experts pay for advanced features?
   - **Recommendation**: No - foundation-funded, all features free

### 6.3 Business Logic

1. **User Authentication**: Required or optional?
   - **Current**: Optional (anonymous usage)
   - **Future**: Required for filing complaints, saving workspaces
   - **Recommendation**: Delay enforced auth until Phase 2

2. **Data Freshness**: How often to auto-refresh events?
   - **Recommendation**: Daily automated refresh, manual "Refresh" button

3. **Moderation**: Who moderates discussion groups?
   - **Recommendation**: Community self-moderation + flag system, staff review for Phase 1

---

## Part 7: References & Related Documentation

### 7.1 Frontend Documentation & Assets

**Current Production UI**:
- **`frontend/mcp-civic-server/civic-conversational-OS.html`** (203KB)
  - **Status**: Production-ready, stellar design
  - **Features**: Solarized Light theme, collapsible sidebar, welcome modal, action chips, message bubbles
  - **Preserve**: All CSS variables, transitions, component patterns
  - **Role**: Foundation for workspace evolution

**UX Evolution Templates**:
- **`frontend/mcp-civic-server/README-UX-Templates.md`**
  - **Phase 1**: Onboarding + Simple Chat (confidence building)
  - **Phase 2**: Mobile + Core Features (real-world usage optimization)
  - **Phase 3**: Transparency + Architecture (democratic legitimacy)
  - **Usage**: Reference these phases when implementing progressive disclosure

**Template Showcase**:
- **`frontend/mcp-civic-server/index.html`** - Navigation hub for all phase templates
- `phase1-onboarding.html` - Clean Apple/OpenAI-inspired onboarding
- `phase1-chat.html` - ChatGPT-style conversational interface
- `phase2-mobile-dashboard.html` - Mobile-first civic dashboard
- `phase2-chat.html` - Location-aware mobile chat
- `phase3-transparency-dashboard.html` - Radical transparency with source verification
- `phase3-chat.html` - Educational chat with civic process explanation

**MCP Server Integration**:
- **`frontend/mcp-civic-server/README.md`** - MCP server architecture
  - Tools: `compose_public_comment`, `get_comment_guidelines`
  - Resources: `civic-opportunities://san-rafael/meetings`
  - Goal: 5-10% newsletter-to-action conversion
- **`frontend/mcp-civic-server/DEVELOPMENT.md`** - Development log and status
- **`frontend/mcp-civic-server/civic_server.py`** - FastMCP server implementation

**Design Assets**:
- `favicon-adaptive.svg` - Adaptive icon for light/dark mode
- Multiple favicon variants (simple, large, cursor, white, dark)
- Logo SVG with hover states

### 7.2 Backend & Architecture Documentation

**Existing Documentation**:
- `CHAT_ROUTING_ARCHITECTURE.md` - **NEW (Session 26)** - Chat-first navigation with OpenAI function calling
- `COMMUNITY_CIVIC_PMF_STRATEGY.md` - PMF hypothesis and engagement strategy
- `COMPLAINT_TO_CIVIC_TECHNICAL_ARCHITECTURE.md` - Backend complaint system
- `COMPLAINT_TO_CIVIC_IMPLEMENTATION_ROADMAP.md` - Layer-by-layer implementation
- `FRONTEND_IMPLEMENTATION_ROADMAP.md` - Frontend step-by-step guide
- `FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md` - Legislative enrichment
- `API_DOCUMENTATION.md` - Complete API specifications (includes /api/chat/route)
- `civic-app-schema.json` - Complete data schema

**Backend Capabilities**:
- **Multi-platform extraction**: Legistar, CivicClerk, Granicus, HTML (26+ cities)
- **Legislative enrichment**: State bills + federal programs (17.2% enrichment rate)
- **Financial context**: CDBG allocations ($11.4M tracked)
- **Complaint handling**: Issue filing, matching, clustering
- **Conversational API**: OpenAI-powered context-aware responses

**API Endpoints** (Current):
```
GET  /api/events
GET  /api/events/{id}
POST /api/conversation
POST /api/chat/route          # NEW (Session 26) - Chat routing with function calling
POST /api/complaints
GET  /api/status
```

**API Endpoints** (Needed):
```
GET  /api/jurisdictions
GET  /api/complaints?user_id={user}
POST /api/complaints/{id}/link-event
GET  /api/legislative/{id}
GET  /api/events?legislative_ref={id}
POST /api/discussions
GET  /api/discussions/{id}/messages
POST /api/proposals
```

**Chat Routing Functions** (Session 26):
```
search_events              # Search civic meetings/events
file_complaint             # Report local issue
view_legislative_context   # Browse state bills/federal programs
draft_comment              # Generate public comment
view_my_complaints         # Show user's filed complaints
explain_event              # Get detailed event explanation
```

---

## Part 8: Phase 3 UX Refinement Decisions (2025-10-22)

### 8.1 Location-Based Multi-Jurisdiction Architecture

**Status**: ✅ **APPROVED** for pilot launch
**Decision Date**: 2025-10-22

**Core Approach**: Address-based multi-jurisdiction scoping (Option C - Full Hierarchy)

#### Location Entry Flow

```javascript
// User lands on platform
LocationEntry = {
  "prompt": "What's your address?",
  "geocoding": "Google Maps API (accurate, $0.005/request)",
  "example": "123 Oak St, Oakland, CA 94612",

  // Geocoding determines overlapping jurisdictions
  "jurisdiction_detection": {
    "city": "Oakland (city-oakland)",
    "county": "Alameda County (alameda-county)",
    "state_assembly": "District 18",
    "state_senate": "District 9",
    "congressional": "District 12"
  },

  // UI shows scoped context
  "user_interface": {
    "primary_location": "Oakland Civic OS",
    "jurisdiction_tree": [
      "🏛️ City of Oakland (45 events, 23 issues)",
      "🏛️ Alameda County (12 events, 5 issues)",
      "🏛️ California State (read-only legislative context)"
    ]
  }
}
```

#### Anti-Bot Protection

**Requirement**: Proof-of-location before pilot launch

**Implementation Strategy**:
1. **Primary Method**: IP geolocation validation
   - User's IP must be within ~50 miles of claimed address
   - Prevents mass astroturfing from out-of-state actors

2. **Optional Enhancement**: Physical QR code verification
   - Partner with local businesses, community centers, libraries
   - QR codes unlock full features (posting, following)
   - Read-only access without QR code

3. **Future Methods** (post-pilot):
   - SMS verification with area code matching
   - Utility bill upload (privacy-preserving, one-time)
   - Community member vouching system

**Privacy Considerations**:
- IP addresses NOT stored, only validated
- Exact address stored only as lat/lng for jurisdiction detection
- Display name = street name only (e.g., "Oak St neighbor")

#### Legislative Context Scoping

**State Bills**: Filtered to Oakland-specific relevance

```javascript
LegislativeContextScope = {
  "default_display": "Bills affecting Oakland specifically",

  "filtering_logic": {
    "sb35_housing": "Show - Oakland has 17.2% enrichment rate",
    "ab705_education": "Show - Oakland has schools affected",
    "random_rural_bill": "Hide - not relevant to Oakland"
  },

  "search_option": "View all CA state bills (user-initiated)",
  "ui_pattern": "Default: local relevance, Search: full catalog"
}
```

**Federal Programs**: All programs shown (CDBG, HOME, etc.) with Oakland-specific allocations highlighted

### 8.2 Side-by-Side Layout Architecture (Option A - APPROVED)

**Decision**: Chat primary (70% when artifact open), Artifact slides in from right (30%)
**Status**: ✅ **APPROVED for Session 31 Implementation**
**Rationale**: Civic engagement is conversational - chat is primary interface, artifacts appear in response

#### Layout Specification

```
┌─────────────────────────────────────────────────────────┐
│ Civic Conversational OS               [user@oakland] ●  │
├────────────────────┬────────────────────────────────────┤
│                    │                                     │
│  💬 Chat (45%)     │  📄 Event Artifact (55%)           │
│                    │                                     │
│  [Context: Item    │  Planning Commission - Jan 15      │
│   7.2 - Use       │                                     │
│   Permit]         │  📋 Agenda Items (expanded)         │
│                    │  ⭐ 7.2: Use Permit - 123 Main St   │
│  User: Tell me    │     Housing development, 20 units   │
│  about this item  │     🏛️ SB 423 (Streamlining)       │
│                    │     💬 Draft Comment →             │
│  AI: This is a    │  📄 7.3: Zoning Variance            │
│  housing dev...   │  [... collapsed items ...]          │
│                    │                                     │
│  [Input box]      │  🏛️ Legislative Context             │
│                    │  SB 35, AB 1287, CDBG               │
└────────────────────┴────────────────────────────────────┘
```

**Key Features**:
- Both surfaces always visible (no scrolling conflict)
- Side-by-side allows AI to explain while user reads agenda
- Mobile: Stack vertically (chat on top, artifact below)
- Resizable divider (save preference in localStorage)

#### Option A Implementation Details (Session 31)

**Default State (No Artifacts)**:
Chat occupies full width, providing spacious conversational interface. User sees welcome prompt, can type naturally.

**After Chat Routes (Artifact Opens)**:
1. Artifact slides in from right (0.3s smooth transition)
2. Chat narrows to 70% width (maintains visibility)
3. Both surfaces visible simultaneously
4. User can continue conversation while viewing artifact

**Component Architecture**:
```vue
<!-- App.vue - Revised Layout -->
<div class="workspace-root">
  <aside class="workspace-sidebar">
    <JurisdictionTree />
    <MyIssuesPanel />
    <LegislativePanel />
  </aside>

  <!-- Center area: Chat + Artifact split -->
  <div class="center-area">
    <div class="chat-pane" :class="{ 'narrowed': hasOpenArtifacts }">
      <ChatPanel />
    </div>

    <transition name="slide-in-right">
      <div v-if="hasOpenArtifacts" class="artifact-pane">
        <TabBar />
        <div class="artifact-content">
          <EventArtifact v-if="activeArtifact.type === 'event'" ... />
        </div>
      </div>
    </transition>
  </div>
</div>
```

**CSS Architecture**:
```css
.center-area {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.chat-pane {
  flex: 1;
  transition: flex 0.3s ease;
}

.chat-pane.narrowed {
  flex: 0 0 70%;
  border-right: 1px solid var(--border);
}

.artifact-pane {
  flex: 0 0 30%;
  background: var(--background);
}

.slide-in-right-enter-active,
.slide-in-right-leave-active {
  transition: all 0.3s ease;
}

.slide-in-right-enter-from,
.slide-in-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

@media (max-width: 768px) {
  .center-area { flex-direction: column; }
  .chat-pane, .chat-pane.narrowed { flex: 1; }
  .artifact-pane { flex: 1; border-top: 1px solid var(--border); }
}
```

**Implementation Phases**:
1. **Phase 1** (1.5h): Add center-area container, move ChatPanel
2. **Phase 2** (1h): Implement slide-in animations
3. **Phase 3** (1.5h): Update ChatPanel (remove mode prop), test tabs
4. **Phase 4** (1h): Mobile responsive testing

**Success Criteria**:
- ✅ Chat defaults to full-width (no artifacts)
- ✅ Artifact slides in smoothly (0.3s, no jank)
- ✅ Chat narrows to 70% when artifact opens
- ✅ Both surfaces visible simultaneously
- ✅ Mobile stacks vertically (50/50 split)

**Alternative Approaches (Rejected)**:
- **Option B** (Sidebar Chat): Conflicts with jurisdiction tree, too constrained
- **Option C** (Overlay): Can't see both simultaneously on desktop
- **Option D** (Floating Widget): "Customer support" stigma

### 8.3 EventArtifact Tab Structure (UPDATED Session 49)

**Decision**: Tab-based layout for different event contexts (Details | Discussion | Drafts)

**⚠️ UPDATED 2025-11-01**: EventArtifact now uses **3 tabs** instead of vertical sections (Sessions 34-49)

#### Implementation Pattern

```vue
<!-- EventArtifact.vue structure (Sessions 34-49) -->
<div class="event-artifact">
  <!-- Tab Navigation -->
  <div class="tab-navigation">
    <button
      :class="['tab-button', { active: activeTab === 'details' }]"
      @click="activeTab = 'details'"
    >
      <FileText :size="16" />
      Details
    </button>

    <button
      :class="['tab-button', { active: activeTab === 'discussion' }]"
      @click="switchTab('discussion')"
    >
      <MessageCircle :size="16" />
      Discussion
      <span v-if="followInfo.follower_count > 0" class="tab-badge">
        {{ followInfo.follower_count }}
      </span>
    </button>

    <!-- NEW: Drafts tab (Session 49) -->
    <button
      :class="['tab-button', { active: activeTab === 'drafts' }]"
      @click="activeTab = 'drafts'"
    >
      <Edit3 :size="16" />
      Drafts
      <span v-if="draftCount > 0" class="tab-badge">
        {{ draftCount }}
      </span>
    </button>
  </div>

  <!-- Tab Content -->
  <div class="tab-content">
    <!-- Details Tab -->
    <div v-if="activeTab === 'details'" class="details-content">
      <!-- Meeting Overview -->
      <section class="meeting-overview">
        <h1>Planning Commission Meeting - Jan 15</h1>
        <p>When, where, how to participate</p>
      </section>

      <!-- Agenda Items (expandable) -->
      <section class="agenda-items">
        <h2>📋 Agenda Items (8 items, 3 actionable)</h2>
        <div class="agenda-item actionable">
          ⭐ 7.2: Use Permit - 123 Main St
          <button @click="draftComment">💬 Draft Comment</button>
        </div>
      </section>

      <!-- Legislative Context -->
      <section class="legislative-context">
        <h2>🏛️ Legislative Context (2 bills, 1 program)</h2>
        [Detailed bill/program information]
      </section>
    </div>

    <!-- Discussion Tab (Session 34) -->
    <div v-if="activeTab === 'discussion'" class="discussion-content">
      <CoordinationChat
        v-if="followInfo.thread_id"
        :thread-id="followInfo.thread_id"
        :user-id="userId"
      />
    </div>

    <!-- Drafts Tab (Session 49) -->
    <div v-if="activeTab === 'drafts'" class="drafts-content">
      <DraftWorkspace
        :event="event"
        :selected-agenda-items="selectedAgendaItems"
        :all-drafts="allDrafts"
        @draft-updated="loadDrafts"
      />
    </div>
  </div>
</div>
```

**Design Rationale**:
- **Details tab**: Event info, agenda items, legislative context (default view)
- **Discussion tab** (Session 34): In-app coordination for followers (social focal point)
- **Drafts tab** (Session 49): All comment drafts for this event (eliminates tab proliferation)
- Tab badges show activity counts (discussion participants, draft count)
- Users can switch tabs while preserving context (selected agenda items persist)
- Foundation for chat integration (Session 50): chat detects activeTab for context-aware prompts

### 8.4 Progressive Disclosure Strategy

**Decision**: Hide sidebars by default, reveal based on user actions

#### Disclosure Rules

```javascript
UIVisibilityRules = {
  "first_visit": {
    "visible": ["large_centered_chat", "location_entry"],
    "hidden": ["jurisdiction_tree", "legislative_panel", "issues_panel"]
  },

  "after_first_query": {
    "trigger": "User asks 'What housing meetings are coming up?'",
    "action": "Show JurisdictionTree sidebar (auto-expanded to relevant city)",
    "display": "EventList results in center"
  },

  "after_first_complaint": {
    "trigger": "User files complaint",
    "action": "Show MyIssuesPanel sidebar",
    "display": "ComplaintArtifact in center"
  },

  "legislative_context": {
    "trigger": "User explores 3+ housing events",
    "action": "💡 'Want to understand state/federal context?' → Show LegislativePanel"
  }
}
```

**Anti-Pattern**: Never show all 3 sidebars at once on first visit

### 8.5 Context-Aware Chat Architecture

**Decision**: Single global chat with visual context indicators (Option A + visual enhancements)

#### Chat Context Display

```vue
<div class="chat-panel">
  <!-- Context Indicator (always visible when artifact open) -->
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

  <!-- Chat History -->
  <div class="chat-messages">
    <!-- Messages here -->
  </div>

  <!-- Input -->
  <div class="chat-input">
    <textarea placeholder="Ask about this agenda item..."></textarea>
  </div>
</div>
```

**Context Switching Logic**:
```javascript
// When user clicks artifact tab
onActiveTabChange(newTab) {
  chat.context = {
    type: newTab.type,  // 'event' | 'complaint' | 'bill'
    id: newTab.id,
    title: newTab.title
  };

  // Visual update
  contextBar.update(`Discussing: ${newTab.title}`);
}

// When user asks question
onChatMessage(message) {
  // Send context to API
  api.sendMessage({
    message,
    context: chat.context  // AI knows we're discussing specific artifact
  });
}
```

**Future Evolution** (Option C - Hybrid): Add "Focus Chat on This Event" button for power users who want parallel investigations

---

## Conclusion

This architecture **enhances** the Civic Conversational OS from a stellar chat-first interface into a **workspace-first platform** inspired by modern IDEs, while **preserving all existing design elements** that users love.

### Evolution, Not Revolution

**Preserve** (from `civic-conversational-OS.html`):
- ✅ Solarized Light color scheme
- ✅ Smooth 0.2-0.3s transitions
- ✅ Message bubbles without avatars
- ✅ Action chip interactions
- ✅ Welcome modal onboarding
- ✅ Centered empty states
- ✅ Collapsible sidebar animations

**Enhance** (new workspace capabilities):
- 🆕 Address-based location entry with multi-jurisdiction scoping
- 🆕 Side-by-side layout (chat + artifact, equal partners)
- 🆕 Agenda items as embedded expandable sections
- 🆕 Progressive disclosure (sidebars hidden by default)
- 🆕 Context-aware chat with visual indicators
- 🆕 Jurisdiction tree navigation
- 🆕 Legislative context visualization (Oakland-specific)
- 🆕 Community collaboration features
- 🆕 Proof-of-location anti-bot measures

**Key Differentiators**:
1. **Spatial navigation** (jurisdiction tree) complements conversational interface
2. **Multi-artifact workflows** enable power users to compare, link, and coordinate
3. **Progressive disclosure** ensures new users see familiar chat interface
4. **Legislative context** surfaces state/federal connections automatically
5. **Community features** enable neighbor-to-neighbor organizing
6. **Design continuity** maintains brand identity and user trust

**Timeline**: 32-46 weeks (6-9 months) for full implementation
**Estimated Effort**: 2 full-time frontend engineers + 1 designer
**Foundation Positioning**: "The IDE for local democracy" - professional tools for civic engagement at scale

This architecture supports the **Complaint-to-Civic PMF strategy** while building infrastructure for **long-term civic engagement pathways**: neighborhood frustration → community formation → civic action → electoral participation.

### Next Steps

1. **Review this architecture** with stakeholders for approval
2. **Study existing design** in `civic-conversational-OS.html`
3. **Reference phase templates** in `README-UX-Templates.md`
4. **Understand MCP integration** from `frontend/mcp-civic-server/README.md`
5. **Begin implementation** following `FRONTEND_IMPLEMENTATION_ROADMAP.md`
6. **Test with beta users** in Berkeley first (best data quality)

**Design Mantra**: "Enhance the stellar foundation, don't replace it."

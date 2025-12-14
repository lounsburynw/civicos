# Frontend Implementation Roadmap
## Optimized for Claude Code Context Management

**Version**: 1.0
**Date**: 2025-10-13
**Purpose**: Sequential implementation guide organized by abstraction degree

---

## How to Use This Roadmap

This document provides **step-by-step implementation instructions** for building the Civic Workspace architecture. Before starting:

1. **Read `FRONTEND_TECHNICAL_ARCHITECTURE.md`** for conceptual understanding
2. **Reference Part 5.3** for backend API status before implementing each layer
3. **Review Part 7.1** for existing frontend assets to preserve
4. **Understand Part 1.E** for progressive disclosure philosophy

This roadmap is optimized for Claude Code context management with clear validation gates between layers.

### Building on Stellar Current Foundation

**CRITICAL**: Read `FRONTEND_TECHNICAL_ARCHITECTURE.md` Part 7.1 for complete context on existing frontend assets. The current `civic-conversational-OS.html` (203KB) has production-quality design that must be preserved exactly.

---

## Roadmap Philosophy

**Abstraction-First Architecture**: Build from design system → types → components → state → integration → features

**Why This Order**:
1. **Design system defines constraints** - get visual language right first
2. **Types enable compile-time safety** - define contracts before implementation
3. **Components are building blocks** - create reusable atoms before molecules
4. **State management connects components** - wire up data flow after UI exists
5. **Integration is most volatile** - defer backend connections until UI stable
6. **Features are iterative** - layer on complexity as users demonstrate interest

**Context Management Strategy**:
- Each layer has **minimal context requirements** from previous layers
- Claude Code can implement each layer in **separate focused sessions**
- **Validation gates** between layers prevent cascading failures
- **Rollback points** at each layer boundary

### Backend Dependency Tracking

Each component is marked with backend status (from ARCHITECTURE Part 5.3):
- ✅ **Available** - Backend endpoint ready
- ⏳ **Needed Phase 1** - Blocks MVP, implement before layer
- 🔮 **Future** - Phase 2+ feature, mock for now
- 🎨 **Frontend Only** - No backend dependency

See `FRONTEND_TECHNICAL_ARCHITECTURE.md` Part 5.3 for complete endpoint documentation.

---

## Layer 1: Design System & Type Definitions (Most Abstract)
### Estimated Time: 1-2 weeks | Context: Design tokens + Schema only

### 1.1 Extract Design System from Current UI

**File**: New file `frontend/civic-workspace/src/design-system.css`

**Purpose**: Preserve stellar Solarized design from `civic-conversational-OS.html`

**Changes Required**:

```css
/**
 * Civic Conversational OS Design System
 * Extracted from civic-conversational-OS.html (203KB stellar design)
 * DO NOT MODIFY without consulting original file
 */

:root {
  /* Solarized Color Palette - PRESERVE EXACTLY */
  --primary: #268bd2;              /* Solarized blue */
  --primary-light: #eee8d5;        /* Solarized base2 */
  --text-primary: #073642;         /* Solarized base02 */
  --text-secondary: #586e75;       /* Solarized base01 */
  --background: #fdf6e3;           /* Solarized base3 */
  --background-secondary: #eee8d5; /* Solarized base2 */
  --background-extra-light: #fffbf0;
  --border: #d3d3d3;
  --shadow: 0 2px 16px rgba(101, 123, 131, 0.15);
  --shadow-subtle: 0 1px 3px rgba(101, 123, 131, 0.1);
  --accent-green: #859900;
  --accent-orange: #cb4b16;
  --accent-red: #dc322f;
  --accent-purple: #6c71c4;
  --gradient: linear-gradient(135deg, var(--primary) 0%, var(--accent-purple) 100%);

  /* Status Colors (NEW) */
  --status-open: var(--accent-orange);
  --status-matched: var(--accent-green);
  --status-escalated: var(--accent-purple);
  --status-resolved: var(--text-secondary);

  /* Panel Backgrounds (NEW) */
  --sidebar-bg: var(--background-secondary);
  --artifact-bg: var(--background);
  --panel-bg: var(--background-extra-light);

  /* Interactive Elements (NEW) */
  --hover-bg: #e8dfc8;
  --active-bg: #d9cdb0;
  --focus-ring: var(--primary);

  /* Spacing System (8px grid) */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;

  /* Typography */
  --font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Display', system-ui, sans-serif;
  --font-mono: 'SF Mono', 'Consolas', 'Monaco', monospace;
  --font-size-sm: 13px;
  --font-size-base: 15px;
  --font-size-lg: 16px;
  --font-size-xl: 48px;

  /* Transitions - PRESERVE EXACT TIMING */
  --transition-fast: 0.2s ease;
  --transition-base: 0.3s ease;

  /* Border Radius */
  --radius-sm: 4px;
  --radius-base: 8px;
  --radius-lg: 16px;
  --radius-pill: 24px;
}

/* Base Styles - PRESERVE FROM CURRENT */
body {
  font-family: var(--font-family);
  line-height: 1.5;
  color: var(--text-primary);
  background: var(--background);
}

/* Message Bubbles - PRESERVE EXACTLY */
.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  font-size: var(--font-size-base);
  line-height: 1.5;
}

.message.ai .message-content {
  background: var(--background-secondary);
  border-top-left-radius: var(--radius-sm);
}

.message.user .message-content {
  background: var(--primary);
  color: white;
  border-top-right-radius: var(--radius-sm);
}

/* Action Chips - PRESERVE EXACTLY */
.action-chip {
  background: var(--primary-light);
  color: var(--primary);
  border: none;
  border-radius: var(--radius-lg);
  padding: 6px 12px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-chip:hover {
  background: var(--primary);
  color: white;
}

/* Sidebar Collapse Toggle - PRESERVE EXACTLY */
.sidebar-collapse-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  transition: all var(--transition-fast);
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

/* NEW Component Patterns */

/* Artifact Window */
.artifact-window {
  background: var(--artifact-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  height: 100%;
  transition: all var(--transition-base);
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
  transition: all var(--transition-fast);
  color: var(--text-secondary);
}

.artifact-tabs button.active {
  border-bottom-color: var(--primary);
  color: var(--primary);
  font-weight: 600;
}

.artifact-body {
  padding: var(--space-lg);
  overflow-y: auto;
  flex: 1;
}

/* Tree Node */
.tree-node {
  display: flex;
  align-items: center;
  padding: var(--space-xs) var(--space-sm);
  cursor: pointer;
  border-radius: 6px;
  user-select: none;
  transition: all var(--transition-fast);
  color: var(--text-primary);
}

.tree-node:hover {
  background: var(--primary-light);
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

/* Status Badge */
.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.status-badge.open {
  background: var(--status-open);
  color: white;
}

.status-badge.matched {
  background: var(--status-matched);
  color: white;
}

.status-badge.escalated {
  background: var(--status-escalated);
  color: white;
}

.status-badge.resolved {
  background: var(--status-resolved);
  color: white;
}
```

**Validation Criteria**:
- [ ] All CSS variables extracted from current UI
- [ ] Color values match exactly
- [ ] Transition timings preserved (0.2s, 0.3s)
- [ ] Border radius values consistent
- [ ] New component patterns use existing variables

**Claude Code Session Requirements**:
- Context: `frontend/mcp-civic-server/civic-conversational-OS.html` (lines 100-400 for CSS)
- Tools: Read, Write (new file)
- Validation: Visual inspection of color palette

---

### 1.2 Define TypeScript Interfaces

**File**: New file `frontend/civic-workspace/src/types/civic.ts`

**Purpose**: Type-safe contracts matching backend schema

```typescript
/**
 * TypeScript interfaces for Civic Conversational OS
 * Matches civic-app-schema.json
 */

// Core Entities

export interface CivicEvent {
  id: string;
  title: string;
  jurisdiction_id: string;
  start_time: string; // ISO 8601
  end_time?: string;
  location?: string;
  meeting_url?: string;
  description?: string;
  participation_opportunities: ParticipationOpportunity[];
  legislative_context?: LegislativeContext;
  _metadata?: Record<string, any>;
}

export interface ParticipationOpportunity {
  item_number?: string;
  item_title: string;
  description: string;
  actionability_assessment: ActionabilityAssessment;
  project_types: ProjectType[];
  comment_deadline?: string;
  participation_mechanisms: ParticipationMechanism[];
}

export interface ActionabilityAssessment {
  is_actionable: boolean;
  evidence: string[];
  time_sensitivity: 'immediate' | 'near_term' | 'long_term';
  confidence_score: number;
}

export type ProjectType =
  | 'housing'
  | 'transportation'
  | 'environment'
  | 'budget'
  | 'education'
  | 'development'
  | 'public_safety'
  | 'community'
  | 'elections'
  | 'governance';

export interface ParticipationMechanism {
  action_type: 'email' | 'calendar' | 'link' | 'phone' | 'in_person' | 'comment_submit';
  action_label: string;
  action_target: string;
  urgency_level?: 'high' | 'medium' | 'low';
}

export interface LegislativeContext {
  state_legislation?: StateBill[];
  federal_programs?: FederalProgram[];
  relevance_summary?: string;
}

export interface StateBill {
  bill: string;
  title: string;
  status: string;
  leverage_point: string;
  official_url: string;
}

export interface FederalProgram {
  program_name: string;
  agency: string;
  leverage_point: string;
  fy2025_allocation?: string;
  info_url: string;
}

export interface Complaint {
  id: string;
  user_id: string;
  description: string;
  issue_type: ProjectType;
  jurisdiction_id: string;
  location?: {
    address: string;
    latitude: number;
    longitude: number;
  };
  status: 'open' | 'matched' | 'community_formed' | 'escalated' | 'resolved';
  created_at: string;
  updated_at: string;
  matched_events: EventReference[];
  related_complaints: string[];
  discussion_group_id?: string;
}

export interface EventReference {
  event_id: string;
  match_score: number;
  match_reason: string;
}

export interface Jurisdiction {
  id: string;
  name: string;
  type: 'city' | 'county' | 'district';
  event_count?: number;
  issue_count?: number;
  cdbg_allocation?: string;
}

// Workspace Types

export interface ArtifactTab {
  id: string;
  type: ArtifactType;
  title: string;
  pinned: boolean;
  data: any; // CivicEvent | Complaint | etc.
}

export type ArtifactType = 'event' | 'complaint' | 'proposal' | 'discussion' | 'legislative';

export interface WorkspaceLayout {
  mode: 'single' | 'split-h' | 'split-v' | 'grid';
  openTabs: ArtifactTab[];
  activeTabId: string | null;
  sidebarCollapsed: boolean;
  chatPanelVisible: boolean;
  chatPanelHeight: number;
}

export interface UserProfile {
  id: string;
  email?: string;
  display_name?: string;
  civic_profile: CivicProfile;
  preferences: UserPreferences;
}

export interface CivicProfile {
  visits: number;
  interactions: number;
  comments_submitted: number;
  issues_filed: number;
  experience_level: 'new' | 'returning' | 'expert';
}

export interface UserPreferences {
  notifications_enabled: boolean;
  default_jurisdiction?: string;
  workspace_layouts?: Record<string, WorkspaceLayout>;
}

// API Response Types

export interface APIResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

export interface ConversationRequest {
  message: string;
  context?: {
    type: ArtifactType;
    id: string;
  };
  user_id?: string;
}

export interface ConversationResponse {
  response: string;
  actions?: ParticipationMechanism[];
  suggested_artifacts?: ArtifactTab[];
}
```

**Validation Criteria**:
- [ ] All types match `civic-app-schema.json` definitions
- [ ] Enums match backend enums exactly
- [ ] Optional fields marked with `?`
- [ ] Date fields typed as `string` with comment
- [ ] Frontend-specific types separated from backend types

**Claude Code Session Requirements**:
- Context: `civic-app-schema.json`, `src/civic_api_integrated.py` (endpoint signatures)
- Tools: Write (new file)
- Validation: `tsc --noEmit src/types/civic.ts`

---

## Layer 2: Core Components (Abstract)
### Estimated Time: 2-3 weeks | Context: Design system + Types only

### 2.1 Jurisdiction Tree Component ✅ **Backend Available**

**File**: New file `frontend/civic-workspace/src/components/sidebar/JurisdictionTree.vue`

**Purpose**: Tree navigator for spatial data navigation

**Backend Status**: ✅ `GET /api/jurisdictions` endpoint implemented (2025-10-13). Ready for integration. See `src/civic_api_integrated.py:623-770` for implementation details.

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { Jurisdiction, CivicEvent, Complaint } from '@/types/civic';
import { api } from '@/services/api';

// Props
const props = defineProps<{
  initialJurisdiction?: string;
}>();

// Emits
const emit = defineEmits<{
  (e: 'open-artifact', artifact: { type: string; id: string }): void;
  (e: 'jurisdiction-change', jurisdiction: Jurisdiction): void;
}>();

// State
const jurisdictions = ref<Jurisdiction[]>([]);
const expandedNodes = ref<Set<string>>(new Set());
const selectedJurisdiction = ref<string | null>(null);
const loading = ref(false);

// Lifecycle
onMounted(async () => {
  await loadJurisdictions();
  if (props.initialJurisdiction) {
    expandNode(props.initialJurisdiction);
  }
});

// Methods
async function loadJurisdictions() {
  loading.value = true;
  try {
    jurisdictions.value = await api.getJurisdictions();
  } catch (error) {
    console.error('Failed to load jurisdictions:', error);
  } finally {
    loading.value = false;
  }
}

function toggleNode(jurisdictionId: string) {
  if (expandedNodes.value.has(jurisdictionId)) {
    expandedNodes.value.delete(jurisdictionId);
  } else {
    expandedNodes.value.add(jurisdictionId);
  }
}

function expandNode(jurisdictionId: string) {
  expandedNodes.value.add(jurisdictionId);
  selectedJurisdiction.value = jurisdictionId;
  const jurisdiction = jurisdictions.value.find(j => j.id === jurisdictionId);
  if (jurisdiction) {
    emit('jurisdiction-change', jurisdiction);
  }
}

function openEvent(eventId: string) {
  emit('open-artifact', { type: 'event', id: eventId });
}

function isExpanded(jurisdictionId: string): boolean {
  return expandedNodes.value.has(jurisdictionId);
}
</script>

<template>
  <div class="jurisdiction-tree">
    <div v-if="loading" class="tree-loading">
      Loading jurisdictions...
    </div>

    <div v-else class="tree-container">
      <div class="tree-header">
        <h3>📍 Jurisdictions</h3>
      </div>

      <div class="tree-nodes">
        <div
          v-for="jurisdiction in jurisdictions"
          :key="jurisdiction.id"
          class="tree-node-group"
        >
          <div
            class="tree-node"
            :class="{ active: selectedJurisdiction === jurisdiction.id }"
            @click="expandNode(jurisdiction.id)"
          >
            <span class="tree-node-icon">
              {{ isExpanded(jurisdiction.id) ? '▼' : '▶' }}
            </span>
            <span class="tree-node-label">{{ jurisdiction.name }}</span>
            <span
              v-if="jurisdiction.event_count"
              class="tree-node-badge"
            >
              {{ jurisdiction.event_count }}
            </span>
          </div>

          <!-- Child nodes (events, issues) -->
          <div v-if="isExpanded(jurisdiction.id)" class="tree-children">
            <div class="tree-section">
              <div class="tree-section-header">🏛️ Events</div>
              <!-- Events will be loaded dynamically -->
            </div>

            <div class="tree-section">
              <div class="tree-section-header">🗣️ Issues</div>
              <!-- Issues will be loaded in Phase 2 -->
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.jurisdiction-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--sidebar-bg);
  overflow-y: auto;
}

.tree-header {
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
}

.tree-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tree-nodes {
  flex: 1;
  padding: var(--space-sm);
}

.tree-node-group {
  margin-bottom: var(--space-xs);
}

.tree-children {
  padding-left: var(--space-lg);
  margin-top: var(--space-xs);
}

.tree-section {
  margin-bottom: var(--space-sm);
}

.tree-section-header {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  padding: var(--space-xs) var(--space-sm);
}

.tree-loading {
  padding: var(--space-lg);
  text-align: center;
  color: var(--text-secondary);
}
</style>
```

**Validation Criteria**:
- [ ] Tree expands/collapses smoothly (0.2s transition)
- [ ] Badge indicators show event counts
- [ ] Active state uses Solarized blue
- [ ] Hover states match design system
- [ ] Keyboard navigation works (arrow keys)

**Claude Code Session Requirements**:
- Context: `src/types/civic.ts`, `design-system.css`
- Tools: Write (new file)
- Validation: Visual inspection in Storybook or dev server

---

### 2.2 Event Artifact Component ✅ **Available**

**File**: New file `frontend/civic-workspace/src/components/artifacts/EventArtifact.vue`

**Purpose**: Display civic event with tabbed interface

**Backend Status**: Uses `GET /api/events/{id}` endpoint (already implemented). Legislative context included via existing enrichment pipeline.

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { CivicEvent, ParticipationMechanism } from '@/types/civic';
import { api } from '@/services/api';

// Props
const props = defineProps<{
  eventId: string;
}>();

// Emits
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'action', action: ParticipationMechanism): void;
}>();

// State
const event = ref<CivicEvent | null>(null);
const activeTab = ref<'overview' | 'agenda' | 'context' | 'actions'>('overview');
const loading = ref(false);

// Computed
const formattedDate = computed(() => {
  if (!event.value) return '';
  const date = new Date(event.value.start_time);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric'
  });
});

// Lifecycle
onMounted(async () => {
  await loadEvent();
});

// Methods
async function loadEvent() {
  loading.value = true;
  try {
    event.value = await api.getEvent(props.eventId);
  } catch (error) {
    console.error('Failed to load event:', error);
  } finally {
    loading.value = false;
  }
}

function handleAction(action: ParticipationMechanism) {
  emit('action', action);
}
</script>

<template>
  <div class="artifact-window event-artifact">
    <!-- Header -->
    <div class="artifact-header">
      <div class="artifact-title">
        <h2 v-if="event">{{ event.title }}</h2>
        <div v-if="event" class="artifact-subtitle">
          {{ formattedDate }}
        </div>
      </div>
      <div class="artifact-controls">
        <button class="control-btn" @click="$emit('close')">×</button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="artifact-tabs">
      <button
        :class="{ active: activeTab === 'overview' }"
        @click="activeTab = 'overview'"
      >
        Overview
      </button>
      <button
        :class="{ active: activeTab === 'agenda' }"
        @click="activeTab = 'agenda'"
      >
        Agenda
      </button>
      <button
        v-if="event?.legislative_context"
        :class="{ active: activeTab === 'context' }"
        @click="activeTab = 'context'"
      >
        Context
      </button>
      <button
        :class="{ active: activeTab === 'actions' }"
        @click="activeTab = 'actions'"
      >
        Actions
      </button>
    </div>

    <!-- Body -->
    <div class="artifact-body">
      <!-- Loading State -->
      <div v-if="loading" class="loading-state">
        Loading event details...
      </div>

      <!-- Overview Tab -->
      <div v-else-if="activeTab === 'overview' && event" class="tab-content">
        <p v-if="event.description">{{ event.description }}</p>
        <div v-if="event.location" class="event-location">
          <strong>Location:</strong> {{ event.location }}
        </div>
        <div v-if="event.meeting_url" class="event-link">
          <a :href="event.meeting_url" target="_blank">Join Meeting →</a>
        </div>
      </div>

      <!-- Agenda Tab -->
      <div v-else-if="activeTab === 'agenda' && event" class="tab-content">
        <div
          v-for="(opp, index) in event.participation_opportunities"
          :key="index"
          class="agenda-item"
        >
          <div class="agenda-item-header">
            <span v-if="opp.item_number" class="item-number">
              {{ opp.item_number }}
            </span>
            <h4>{{ opp.item_title }}</h4>
          </div>
          <p>{{ opp.description }}</p>
          <div class="project-types">
            <span
              v-for="type in opp.project_types"
              :key="type"
              class="project-type-tag"
            >
              {{ type }}
            </span>
          </div>
        </div>
      </div>

      <!-- Context Tab -->
      <div v-else-if="activeTab === 'context' && event?.legislative_context" class="tab-content">
        <!-- State Legislation -->
        <div v-if="event.legislative_context.state_legislation?.length" class="context-section">
          <h3>Related State Legislation</h3>
          <div
            v-for="bill in event.legislative_context.state_legislation"
            :key="bill.bill"
            class="bill-card"
          >
            <h4>{{ bill.bill }} - {{ bill.status }}</h4>
            <p>{{ bill.title }}</p>
            <p class="leverage-point">🎯 {{ bill.leverage_point }}</p>
            <a :href="bill.official_url" target="_blank">View Bill Text →</a>
          </div>
        </div>

        <!-- Federal Programs -->
        <div v-if="event.legislative_context.federal_programs?.length" class="context-section">
          <h3>Federal Funding Context</h3>
          <div
            v-for="program in event.legislative_context.federal_programs"
            :key="program.program_name"
            class="program-card"
          >
            <h4>{{ program.program_name }}</h4>
            <p>{{ program.agency }}</p>
            <p v-if="program.fy2025_allocation" class="allocation">
              {{ program.fy2025_allocation }}
            </p>
            <p class="leverage-point">💰 {{ program.leverage_point }}</p>
          </div>
        </div>
      </div>

      <!-- Actions Tab -->
      <div v-else-if="activeTab === 'actions' && event" class="tab-content">
        <div
          v-for="(opp, index) in event.participation_opportunities"
          :key="index"
          class="opportunity-actions"
        >
          <button
            v-for="(mechanism, mIndex) in opp.participation_mechanisms"
            :key="mIndex"
            class="action-chip"
            @click="handleAction(mechanism)"
          >
            {{ mechanism.action_label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.event-artifact {
  /* Inherits from .artifact-window in design-system.css */
}

.artifact-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.artifact-subtitle {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.control-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all var(--transition-fast);
}

.control-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
}

.tab-content {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.agenda-item {
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-md);
}

.agenda-item-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.item-number {
  background: var(--primary-light);
  color: var(--primary);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.project-types {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: var(--space-sm);
}

.project-type-tag {
  background: var(--background-secondary);
  color: var(--text-primary);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}

.bill-card,
.program-card {
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-md);
}

.leverage-point {
  font-style: italic;
  color: var(--text-secondary);
  margin: var(--space-sm) 0;
}

.context-section {
  margin-bottom: var(--space-xl);
}

.context-section h3 {
  margin-bottom: var(--space-md);
}
</style>
```

**Validation Criteria**:
- [ ] All tabs render correctly
- [ ] Tab transitions smooth (fadeIn animation)
- [ ] Action buttons use existing action-chip class
- [ ] Legislative context displays when present
- [ ] Close button works

**Claude Code Session Requirements**:
- Context: `src/types/civic.ts`, `design-system.css`, sample event JSON
- Tools: Write (new file)
- Validation: Test with real event data from `/api/events`

---

## Layer 3: State Management & Services (Concrete)
### Estimated Time: 1-2 weeks | Context: Types + Components

### 3.1 API Service Layer ✅ **Phase 1 Complete**

**File**: New file `frontend/civic-workspace/src/services/api.ts`

**Purpose**: Centralized API client with type safety

**Backend Status**: Phase 1 endpoints complete (2025-10-13). All critical MVP endpoints now available. See inline status comments for implementation details.

```typescript
import type {
  CivicEvent,
  Complaint,
  Jurisdiction,
  ConversationRequest,
  ConversationResponse,
  APIResponse
} from '@/types/civic';

class CivicAPI {
  private baseURL: string;

  constructor() {
    this.baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';
  }

  // Jurisdictions
  // ✅ IMPLEMENTED (2025-10-13) - uses GET /api/jurisdictions (src/civic_api_integrated.py:623)
  async getJurisdictions(): Promise<Jurisdiction[]> {
    const response = await fetch(`${this.baseURL}/api/jurisdictions`);
    if (!response.ok) {
      throw new Error(`Failed to fetch jurisdictions: ${response.statusText}`);
    }
    const data = await response.json();
    return data.jurisdictions; // Response includes {jurisdictions: [], metadata: {}}
  }

  // Events
  // ✅ IMPLEMENTED - uses GET /api/events
  async getEvents(filters?: {
    jurisdiction_id?: string;
    project_type?: string;
    start_date?: string;
  }): Promise<CivicEvent[]> {
    const params = new URLSearchParams(filters as any);
    const response = await fetch(`${this.baseURL}/api/events?${params}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch events: ${response.statusText}`);
    }
    return response.json();
  }

  // ✅ IMPLEMENTED - uses GET /api/events/{id}
  async getEvent(id: string): Promise<CivicEvent> {
    const response = await fetch(`${this.baseURL}/api/events/${id}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch event: ${response.statusText}`);
    }
    return response.json();
  }

  // Complaints
  // ⏳ OPTIONAL - standalone POST /api/complaints (filing works via /api/conversation)
  async fileComplaint(complaint: Partial<Complaint>): Promise<Complaint> {
    const response = await fetch(`${this.baseURL}/api/complaints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(complaint)
    });
    if (!response.ok) {
      throw new Error(`Failed to file complaint: ${response.statusText}`);
    }
    return response.json();
  }

  // ✅ IMPLEMENTED (2025-10-13) - uses GET /api/complaints?user_id={user} (src/civic_api_integrated.py:772)
  async getComplaints(user_id: string): Promise<Complaint[]> {
    const response = await fetch(`${this.baseURL}/api/complaints?user_id=${user_id}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch complaints: ${response.statusText}`);
    }
    const data = await response.json();
    return data.complaints; // Response includes {complaints: [], metadata: {}}
  }

  // 🔮 FUTURE - needs GET /api/complaints/{id} (Phase 2)
  async getComplaint(id: string): Promise<Complaint> {
    const response = await fetch(`${this.baseURL}/api/complaints/${id}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch complaint: ${response.statusText}`);
    }
    return response.json();
  }

  // Conversation
  // ✅ IMPLEMENTED - uses POST /api/conversation (includes complaint detection)
  async sendMessage(request: ConversationRequest): Promise<ConversationResponse> {
    const response = await fetch(`${this.baseURL}/api/conversation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    if (!response.ok) {
      throw new Error(`Failed to send message: ${response.statusText}`);
    }
    return response.json();
  }
}

export const api = new CivicAPI();
```

**Validation Criteria**:
- [ ] All API methods typed correctly
- [ ] Error handling consistent
- [ ] Environment variable support works
- [ ] Fetch calls follow REST conventions

**Claude Code Session Requirements**:
- Context: `src/types/civic.ts`, `src/civic_api_integrated.py` (endpoint signatures)
- Tools: Write (new file)
- Validation: `tsc --noEmit src/services/api.ts`

---

### 3.2 Workspace Store (Pinia)

**File**: New file `frontend/civic-workspace/src/stores/workspace.ts`

**Purpose**: Manage open artifacts, layout, sidebar state

```typescript
import { defineStore } from 'pinia';
import type { ArtifactTab, WorkspaceLayout, ArtifactType } from '@/types/civic';

export const useWorkspaceStore = defineStore('workspace', {
  state: (): WorkspaceLayout => ({
    mode: 'single',
    openTabs: [],
    activeTabId: null,
    sidebarCollapsed: false,
    chatPanelVisible: true,
    chatPanelHeight: 200
  }),

  getters: {
    activeTab: (state): ArtifactTab | null => {
      return state.openTabs.find(tab => tab.id === state.activeTabId) || null;
    },

    hasOpenTabs: (state): boolean => {
      return state.openTabs.length > 0;
    },

    pinnedTabs: (state): ArtifactTab[] => {
      return state.openTabs.filter(tab => tab.pinned);
    }
  },

  actions: {
    openArtifact(artifact: { type: ArtifactType; id: string; title: string; data: any }) {
      // Check if already open
      const existing = this.openTabs.find(tab => tab.id === artifact.id);
      if (existing) {
        this.activeTabId = existing.id;
        return;
      }

      // Create new tab
      const newTab: ArtifactTab = {
        id: artifact.id,
        type: artifact.type,
        title: artifact.title,
        pinned: false,
        data: artifact.data
      };

      this.openTabs.push(newTab);
      this.activeTabId = newTab.id;
    },

    closeArtifact(artifactId: string) {
      const index = this.openTabs.findIndex(tab => tab.id === artifactId);
      if (index === -1) return;

      this.openTabs.splice(index, 1);

      // Set new active tab
      if (this.activeTabId === artifactId) {
        if (this.openTabs.length > 0) {
          // Activate previous tab or first tab
          const newIndex = Math.min(index, this.openTabs.length - 1);
          this.activeTabId = this.openTabs[newIndex].id;
        } else {
          this.activeTabId = null;
        }
      }
    },

    pinArtifact(artifactId: string) {
      const tab = this.openTabs.find(tab => tab.id === artifactId);
      if (tab) {
        tab.pinned = true;
      }
    },

    unpinArtifact(artifactId: string) {
      const tab = this.openTabs.find(tab => tab.id === artifactId);
      if (tab) {
        tab.pinned = false;
      }
    },

    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed;
    },

    toggleChatPanel() {
      this.chatPanelVisible = !this.chatPanelVisible;
    },

    setChatPanelHeight(height: number) {
      this.chatPanelHeight = Math.max(100, Math.min(height, 600));
    },

    setLayoutMode(mode: WorkspaceLayout['mode']) {
      this.mode = mode;
    },

    // Persistence
    saveLayout() {
      const layout: WorkspaceLayout = {
        mode: this.mode,
        openTabs: this.openTabs,
        activeTabId: this.activeTabId,
        sidebarCollapsed: this.sidebarCollapsed,
        chatPanelVisible: this.chatPanelVisible,
        chatPanelHeight: this.chatPanelHeight
      };
      localStorage.setItem('civic_workspace_layout', JSON.stringify(layout));
    },

    loadLayout() {
      const saved = localStorage.getItem('civic_workspace_layout');
      if (saved) {
        try {
          const layout = JSON.parse(saved) as WorkspaceLayout;
          this.$patch(layout);
        } catch (error) {
          console.error('Failed to restore workspace layout:', error);
        }
      }
    }
  }
});
```

**Validation Criteria**:
- [ ] Open/close artifact methods work
- [ ] Active tab tracking correct
- [ ] Pin/unpin functionality works
- [ ] LocalStorage persistence works
- [ ] State updates trigger UI re-renders

**Claude Code Session Requirements**:
- Context: `src/types/civic.ts`, Pinia documentation
- Tools: Write (new file)
- Validation: Unit tests with Vitest

---

## Layer 4: Workspace Integration (Concrete)
### Estimated Time: 2-3 weeks | Context: All previous layers

### 4.1 Main Workspace Container

**File**: New file `frontend/civic-workspace/src/components/workspace/WorkspaceContainer.vue`

**Purpose**: Root layout manager connecting all components

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useWorkspaceStore } from '@/stores/workspace';
import JurisdictionTree from '@/components/sidebar/JurisdictionTree.vue';
import EventArtifact from '@/components/artifacts/EventArtifact.vue';
import { api } from '@/services/api';

const workspaceStore = useWorkspaceStore();

onMounted(() => {
  workspaceStore.loadLayout();
});

function handleOpenArtifact({ type, id }: { type: string; id: string }) {
  // Load artifact data based on type
  if (type === 'event') {
    api.getEvent(id).then(event => {
      workspaceStore.openArtifact({
        type: 'event',
        id,
        title: event.title,
        data: event
      });
    });
  }
}

function handleCloseArtifact(id: string) {
  workspaceStore.closeArtifact(id);
  workspaceStore.saveLayout();
}
</script>

<template>
  <div class="workspace-container">
    <!-- Sidebar -->
    <aside
      class="workspace-sidebar"
      :class="{ collapsed: workspaceStore.sidebarCollapsed }"
    >
      <div class="sidebar-header">
        <button
          class="sidebar-collapse-toggle"
          @click="workspaceStore.toggleSidebar"
        >
          {{ workspaceStore.sidebarCollapsed ? '▶' : '◀' }}
        </button>
      </div>

      <JurisdictionTree @open-artifact="handleOpenArtifact" />
    </aside>

    <!-- Main Content Area -->
    <main class="workspace-main">
      <!-- Artifact Tabs -->
      <div v-if="workspaceStore.hasOpenTabs" class="artifact-tabs-bar">
        <button
          v-for="tab in workspaceStore.openTabs"
          :key="tab.id"
          class="tab-button"
          :class="{ active: tab.id === workspaceStore.activeTabId }"
          @click="workspaceStore.activeTabId = tab.id"
        >
          {{ tab.title }}
          <span
            v-if="!tab.pinned"
            class="tab-close"
            @click.stop="handleCloseArtifact(tab.id)"
          >
            ×
          </span>
        </button>
      </div>

      <!-- Active Artifact -->
      <div class="artifact-container">
        <EventArtifact
          v-if="workspaceStore.activeTab?.type === 'event'"
          :event-id="workspaceStore.activeTab.id"
          @close="handleCloseArtifact(workspaceStore.activeTab.id)"
        />

        <!-- Empty State -->
        <div v-else-if="!workspaceStore.hasOpenTabs" class="empty-state">
          <h1 class="civic-title">Civic Conversational OS</h1>
          <p>Select a jurisdiction from the sidebar to get started</p>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.workspace-container {
  display: flex;
  height: 100vh;
  background: var(--background);
}

.workspace-sidebar {
  width: 300px;
  border-right: 1px solid var(--border);
  transition: width var(--transition-base);
  display: flex;
  flex-direction: column;
}

.workspace-sidebar.collapsed {
  width: 120px;
}

.sidebar-header {
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
}

.workspace-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.artifact-tabs-bar {
  display: flex;
  gap: var(--space-xs);
  padding: var(--space-sm);
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
  overflow-x: auto;
}

.tab-button {
  padding: var(--space-sm) var(--space-md);
  border: none;
  background: var(--background);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.tab-button.active {
  background: var(--artifact-bg);
  border-bottom: 2px solid var(--primary);
}

.tab-close {
  font-size: 18px;
  opacity: 0.5;
}

.tab-close:hover {
  opacity: 1;
  color: var(--accent-red);
}

.artifact-container {
  flex: 1;
  overflow: hidden;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: var(--space-2xl);
}

.civic-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: var(--space-md);
  background: var(--gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
</style>
```

**Validation Criteria**:
- [ ] Sidebar collapse animation smooth (0.3s)
- [ ] Tab switching instantaneous
- [ ] Empty state shows centered title
- [ ] Layout persists across refreshes

**Claude Code Session Requirements**:
- Context: All component files, stores, design system
- Tools: Write (new file), Bash (dev server)
- Validation: Manual testing in browser

---

## Layer 5: Feature Implementation (Most Concrete)
### Estimated Time: 4-6 weeks | Context: Full workspace

**Note**: This layer contains phase-specific features from the roadmap. Implement incrementally based on PMF validation.

**Feature Implementation Reference**: This layer shows **ComplaintArtifact as a reference implementation**. For complete specifications of all 5 artifact types (Event, Complaint, Proposal, Discussion, Legislative), see `FRONTEND_TECHNICAL_ARCHITECTURE.md` Part 1.B. Follow the same component pattern for additional artifacts.

**Phase Alignment**:
- **Phase 1** (Weeks 1-8): Sidebar navigation ✓, Event artifact ✓, Command palette, Chat panel
- **Phase 2** (Weeks 9-14): **Complaint artifact** ⏳ (Backend needs GET /api/complaints?user_id), Issue filing, Drag-and-drop
- **Phase 3** (Weeks 15-20): Tab system ✓ (Layer 4), Split view, Workspace persistence ✓ (Layer 4)
- **Phase 4** (Weeks 21-26): Context tab ✓ (EventArtifact), Legislative artifact, Budget context
- **Phase 5** (Weeks 27-34): Neighbors panel, Discussion groups, Proposals

---

### 5.1 ComplaintArtifact Component (Phase 2 - Complaint-to-Civic)

**File**: New file `frontend/civic-workspace/src/components/artifacts/ComplaintArtifact.vue`

**Purpose**: Display user-filed complaint with matched events and similar issues

**Backend Dependencies**: ✅ **GET /api/complaints?user_id={user}** implemented (2025-10-13). Ready for integration. See `src/civic_api_integrated.py:772-849`.

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { Complaint, ParticipationMechanism } from '@/types/civic';
import { api } from '@/services/api';

// Props
const props = defineProps<{
  complaintId: string;
}>();

// Emits
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'open-event', eventId: string): void;
  (e: 'link-event'): void;
}>();

// State
const complaint = ref<Complaint | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// Computed
const statusColor = computed(() => {
  if (!complaint.value) return 'open';
  return complaint.value.status;
});

const formattedDate = computed(() => {
  if (!complaint.value) return '';
  const date = new Date(complaint.value.created_at);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
});

const hasMatches = computed(() => {
  return complaint.value && complaint.value.matched_events.length > 0;
});

// Lifecycle
onMounted(async () => {
  await loadComplaint();
});

// Methods
async function loadComplaint() {
  loading.value = true;
  error.value = null;
  try {
    // ✅ GET /api/complaints/{id} available (2025-10-13) for single complaint fetch
    // Alternative: Use getComplaints(user_id) and filter client-side
    complaint.value = await api.getComplaint(props.complaintId);
  } catch (err) {
    console.error('Failed to load complaint:', err);
    error.value = 'Could not load complaint. Please try again.';
  } finally {
    loading.value = false;
  }
}

function openMatchedEvent(eventId: string) {
  emit('open-event', eventId);
}

function handleLinkEvent() {
  emit('link-event');
}
</script>

<template>
  <div class="artifact-window complaint-artifact">
    <!-- Header -->
    <div class="artifact-header">
      <div class="artifact-title">
        <div class="title-row">
          <h2>My Issue</h2>
          <span class="status-badge" :class="statusColor">
            {{ statusColor }}
          </span>
        </div>
        <div class="artifact-subtitle">
          Filed {{ formattedDate }}
        </div>
      </div>
      <div class="artifact-controls">
        <button class="control-btn" @click="$emit('close')">×</button>
      </div>
    </div>

    <!-- Body -->
    <div class="artifact-body">
      <!-- Loading State -->
      <div v-if="loading" class="loading-state">
        Loading complaint details...
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="error-state">
        <p class="error-message">{{ error }}</p>
        <button class="action-chip" @click="loadComplaint">
          Retry
        </button>
      </div>

      <!-- Complaint Content -->
      <div v-else-if="complaint" class="complaint-content">
        <!-- Description Section -->
        <div class="section">
          <h3>Description</h3>
          <p class="description">{{ complaint.description }}</p>

          <div class="meta-row">
            <span class="meta-item">
              <strong>Type:</strong> {{ complaint.issue_type }}
            </span>
            <span class="meta-item">
              <strong>Location:</strong> {{ complaint.jurisdiction_id }}
            </span>
          </div>

          <div v-if="complaint.location" class="meta-row">
            <span class="meta-item">
              <strong>Address:</strong> {{ complaint.location.address }}
            </span>
          </div>
        </div>

        <!-- Matched Events Section -->
        <div v-if="hasMatches" class="section">
          <h3>Relevant Civic Meetings ({{ complaint.matched_events.length }})</h3>
          <div class="matched-events-list">
            <div
              v-for="match in complaint.matched_events"
              :key="match.event_id"
              class="matched-event-card"
              @click="openMatchedEvent(match.event_id)"
            >
              <div class="match-score">
                {{ Math.round(match.match_score * 100) }}% match
              </div>
              <div class="match-reason">
                {{ match.match_reason }}
              </div>
              <button class="action-chip">
                View Meeting →
              </button>
            </div>
          </div>
        </div>

        <!-- No Matches Section -->
        <div v-else class="section">
          <div class="no-matches">
            <p>
              💡 No upcoming meetings found yet. We'll notify you when relevant
              meetings are scheduled.
            </p>
            <button class="action-chip" @click="handleLinkEvent">
              Manually Link to Meeting
            </button>
          </div>
        </div>

        <!-- Similar Complaints Section -->
        <div v-if="complaint.related_complaints.length > 0" class="section">
          <h3>Similar Issues ({{ complaint.related_complaints.length }})</h3>
          <p class="similar-hint">
            Other residents have reported similar issues. Connect with them to
            coordinate civic action.
          </p>
          <div class="similar-complaints-list">
            <div
              v-for="relatedId in complaint.related_complaints"
              :key="relatedId"
              class="similar-complaint-card"
            >
              <span class="complaint-icon">🗣️</span>
              <span class="complaint-ref">Issue #{{ relatedId.slice(0, 8) }}</span>
            </div>
          </div>
        </div>

        <!-- Timeline Section -->
        <div class="section">
          <h3>Timeline</h3>
          <div class="timeline">
            <div class="timeline-item">
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <strong>Filed</strong>
                <span class="timeline-date">{{ formattedDate }}</span>
              </div>
            </div>
            <div v-if="hasMatches" class="timeline-item">
              <div class="timeline-dot matched"></div>
              <div class="timeline-content">
                <strong>Matched to meetings</strong>
                <span class="timeline-date">
                  {{ new Date(complaint.updated_at).toLocaleDateString() }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.complaint-artifact {
  /* Inherits from .artifact-window in design-system.css */
}

.title-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.artifact-title h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.artifact-subtitle {
  margin-top: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.control-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-secondary);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all var(--transition-fast);
}

.control-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
}

.loading-state,
.error-state {
  padding: var(--space-2xl);
  text-align: center;
  color: var(--text-secondary);
}

.error-message {
  color: var(--accent-red);
  margin-bottom: var(--space-md);
}

.error-hint {
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  background: var(--background-secondary);
  padding: var(--space-md);
  border-radius: var(--radius-base);
}

.complaint-content {
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.section {
  margin-bottom: var(--space-xl);
  padding-bottom: var(--space-xl);
  border-bottom: 1px solid var(--border);
}

.section:last-child {
  border-bottom: none;
}

.section h3 {
  margin: 0 0 var(--space-md) 0;
  font-size: 16px;
  font-weight: 600;
}

.description {
  line-height: 1.6;
  margin-bottom: var(--space-md);
}

.meta-row {
  display: flex;
  gap: var(--space-lg);
  margin-top: var(--space-sm);
}

.meta-item {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.matched-events-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.matched-event-card {
  padding: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.matched-event-card:hover {
  border-color: var(--primary);
  background: var(--primary-light);
}

.match-score {
  display: inline-block;
  background: var(--status-matched);
  color: white;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  margin-bottom: var(--space-sm);
}

.match-reason {
  margin-bottom: var(--space-sm);
  color: var(--text-secondary);
}

.no-matches {
  padding: var(--space-lg);
  background: var(--background-secondary);
  border-radius: var(--radius-base);
  text-align: center;
}

.no-matches p {
  margin-bottom: var(--space-md);
}

.similar-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-md);
}

.similar-complaints-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.similar-complaint-card {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-sm);
  background: var(--background-secondary);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
}

.complaint-icon {
  font-size: 1.2em;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--status-open);
  margin-top: 4px;
  flex-shrink: 0;
}

.timeline-dot.matched {
  background: var(--status-matched);
}

.timeline-content {
  display: flex;
  flex-direction: column;
}

.timeline-date {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}
</style>
```

**Validation Criteria**:
- [ ] Status badge displays correctly (open/matched/escalated/resolved)
- [ ] Matched events are clickable and emit `open-event`
- [ ] Similar complaints section shows when available
- [ ] Timeline updates based on complaint status
- [ ] Error state handles missing backend endpoint gracefully

**Claude Code Session Requirements**:
- Context: `src/types/civic.ts`, `design-system.css`, `src/complaint_storage.py` (Complaint schema)
- Tools: Write (new file)
- Validation: Test with mock complaint data until backend endpoint available

**Rollback Point**:
```bash
git commit -m "Add ComplaintArtifact component for Phase 2 complaint tracking"
```

---

## Layer 6: Testing & Validation (Quality)
### Estimated Time: Ongoing | Context: All implementation layers

### 6.1 Component Tests with Vitest

**File**: New file `frontend/civic-workspace/tests/components/JurisdictionTree.spec.ts`

```typescript
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import JurisdictionTree from '@/components/sidebar/JurisdictionTree.vue';
import { api } from '@/services/api';

// Mock API
vi.mock('@/services/api', () => ({
  api: {
    getJurisdictions: vi.fn()
  }
}));

describe('JurisdictionTree', () => {
  it('loads jurisdictions on mount', async () => {
    const mockJurisdictions = [
      { id: 'city-berkeley', name: 'Berkeley', type: 'city', event_count: 10 }
    ];

    (api.getJurisdictions as any).mockResolvedValue(mockJurisdictions);

    const wrapper = mount(JurisdictionTree);

    await wrapper.vm.$nextTick();

    expect(api.getJurisdictions).toHaveBeenCalled();
    expect(wrapper.text()).toContain('Berkeley');
  });

  it('expands node on click', async () => {
    const wrapper = mount(JurisdictionTree);

    // ... test expansion logic
  });

  it('emits open-artifact when event clicked', async () => {
    const wrapper = mount(JurisdictionTree);

    // ... test event emission
  });
});
```

**Validation Criteria**:
- [ ] All components have unit tests
- [ ] API calls are mocked
- [ ] User interactions tested (clicks, keyboard)
- [ ] Edge cases covered (empty states, errors)

---

## Implementation Sequencing Strategy

### Phase 1: Foundation (Sessions 1-10)
**Context Required**: Design system + Types only
**Deliverables**:
- Design system extraction
- TypeScript interfaces
- Core components (sidebar, artifact)
- API service

**Validation Gate**: Components render with mock data

### Phase 2: Integration (Sessions 11-15)
**Context Required**: Components + Stores
**Deliverables**:
- Pinia stores
- Workspace container
- Tab management
- Layout persistence

**Validation Gate**: Workspace functions end-to-end with real API

### Phase 3: Features (Sessions 16-30)
**Context Required**: Full workspace
**Deliverables**:
- Complaint system
- Legislative context
- Community features
- Advanced layouts

**Validation Gate**: PMF metrics from `FRONTEND_WORKSPACE_ROADMAP.md` Part 5

---

## Context Management Tips for Claude Code

### Session Context Files

**Session 1-2 (Design System)**:
```
frontend/mcp-civic-server/civic-conversational-OS.html (CSS only)
docs/FRONTEND_WORKSPACE_ROADMAP.md (Part 4)
```

**Session 3-4 (Types)**:
```
civic-app-schema.json
src/civic_api_integrated.py (endpoint signatures)
frontend/civic-workspace/src/design-system.css
```

**Session 5-8 (Components)**:
```
frontend/civic-workspace/src/types/civic.ts
frontend/civic-workspace/src/design-system.css
data/events/events_city-berkeley_*.json (sample data)
```

**Session 9-12 (Stores & Services)**:
```
frontend/civic-workspace/src/types/civic.ts
frontend/civic-workspace/src/components/**/*.vue
Pinia documentation (reference)
```

**Session 13-15 (Integration)**:
```
All component files
All store files
frontend/civic-workspace/src/services/api.ts
```

**Session 16+ (Features)**:
```
Specific feature components
Relevant stores
docs/FRONTEND_WORKSPACE_ROADMAP.md (feature specs)
```

### Rollback Points

```bash
# After design system
git commit -m "Extract Solarized design system from current UI"

# After types
git commit -m "Define TypeScript interfaces matching backend schema"

# After core components
git commit -m "Implement JurisdictionTree and EventArtifact components"

# After services
git commit -m "Add API service layer with type safety"

# After stores
git commit -m "Implement Pinia stores for workspace state"

# After integration
git commit -m "Wire up workspace container with all components"

# After each feature
git commit -m "Add [feature name] to workspace"
```

### Validation Commands

```bash
# Type checking
npm run type-check  # tsc --noEmit

# Component tests
npm run test  # vitest

# Visual testing
npm run dev  # Vite dev server

# Build
npm run build  # Production build

# Lint
npm run lint  # ESLint + Prettier
```

---

## Success Criteria

### Phase 1 MVP Success
- [ ] Sidebar navigation functional
- [ ] Events open in artifact panes
- [ ] Tab switching works
- [ ] Design system matches current UI exactly
- [ ] Zero TypeScript errors
- [ ] All components tested

### Phase 2 Enhancement Triggers
Only implement Phase 2 features if:
- [ ] Phase 1 deployed to production
- [ ] User feedback positive (>70% satisfaction)
- [ ] Performance acceptable (<3s load time)
- [ ] No critical bugs

---

## Estimated Total Effort

**Development Time**: 32-46 weeks across phases
**Testing Time**: Ongoing (20% of dev time)
**Documentation**: 2-3 weeks
**Total**: ~40-55 weeks for full implementation

**Phase 1 Complexity Budget**: ~5,000 lines
- Design system: ~500 lines
- Types: ~300 lines
- Components: ~2,000 lines
- Stores/Services: ~800 lines
- Tests: ~1,400 lines

---

## Next Steps

1. **Review this roadmap** with user for approval
2. **Start Session 1**: Design system extraction
3. **Commit after each layer** for rollback safety
4. **Validate gates** before proceeding to next layer
5. **Test with real users** as soon as Phase 1 MVP ready
6. **Measure PMF metrics** before building Phase 2

---

**This roadmap enables high-fidelity frontend implementation with minimal context overhead per session, following the proven abstraction-first pattern from the backend complaint-to-civic system.**

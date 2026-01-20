<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import type { CivicEvent, FollowInfoResponse, ActionableItem } from '@/types/civic';
import { useChatStore } from '@/stores/chat';
import { useWorkspaceStore } from '@/stores/workspace';
import { useContextStore } from '@/stores/context';
import { api } from '@/services/api';
import { createEventContext } from '@/utils/contextHelpers';
import { ArtifactIds } from '@/utils/artifactIds';
import FollowButton from './FollowButton.vue';
import CoordinationChat from './CoordinationChat.vue';
import AgendaItems from './AgendaItems.vue';
import ThreadArtifact from './ThreadArtifact.vue';
import DraftWorkspace from './DraftWorkspace.vue';
import { ChevronRight, Calendar, FileText, Phone, Mail, Users, MessageCircle, Edit3 } from 'lucide-vue-next';

const props = withDefaults(defineProps<{
  event: CivicEvent;
  mode?: 'full' | 'detail'; // 'full' for tabs, 'detail' for split-pane
}>(), {
  mode: 'full'
});

const emit = defineEmits<{
  'close': [];
  'open-as-tab': [event: CivicEvent];
}>();

const chatStore = useChatStore();
const workspaceStore = useWorkspaceStore();
const contextStore = useContextStore();

// TODO: Replace with actual user ID from auth store
const userId = 'demo_user';

// Context registration tracking
const contextId = ref<string>();

// Follow info for coordination chat
const followInfo = ref<FollowInfoResponse>({
  follower_count: 0,
  thread_id: null,
  your_following: false
});

// Mock action counts (TODO: Replace with real data from backend)
const mockActionCounts = ref({
  attending: Math.floor(Math.random() * 10), // Random 0-9
  emailed: Math.floor(Math.random() * 15)     // Random 0-14
});

// Collapsible section state
const isAgendaExpanded = ref(false); // Collapsed by default
const isLegislativeExpanded = ref(false); // Collapsed by default
const isEventDetailsExpanded = ref(false); // Collapsed by default

// Tab state (details vs discussion vs drafts)
const activeTab = ref<'details' | 'discussion' | 'drafts'>('details');

// Track selected agenda items for drafting
const selectedAgendaItems = ref<ActionableItem[]>([]);

// Draft state management (Session 49)
interface DraftSummary {
  draft_id: string;
  content: string;
  content_preview: string;
  structured_summary: any;
  personal_context: any;
  selected_agenda_items: string[];
  created_at: string;
  updated_at: string;
  submitted: boolean;
  tags?: string[];
}

const allDrafts = ref<DraftSummary[]>([]);
const draftCount = computed(() => allDrafts.value.length);

// Load drafts for this event
async function loadDrafts() {
  try {
    const response = await api.getAllDrafts(props.event.id, userId);
    allDrafts.value = response.drafts;
  } catch (err) {
    console.error('[EventArtifact] Failed to load drafts:', err);
  }
}

// Format full date with time
function formatDateTime(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });
}

// Format deadline
function formatDeadline(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    return 'Passed';
  } else if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Tomorrow';
  } else if (diffDays < 7) {
    return `${diffDays} days`;
  } else {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
  }
}

// Generate .ics calendar file
function addToCalendar() {
  const event = props.event;
  const start = new Date(event.when).toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
  const end = new Date(new Date(event.when).getTime() + 2 * 60 * 60 * 1000)
    .toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';

  const icsContent = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'BEGIN:VEVENT',
    `DTSTART:${start}`,
    `DTEND:${end}`,
    `SUMMARY:${event.title}`,
    `DESCRIPTION:${event.description.replace(/\n/g, '\\n')}`,
    `LOCATION:${event.location || event.jurisdiction.name}`,
    `URL:${event.source_url}`,
    'END:VEVENT',
    'END:VCALENDAR'
  ].join('\r\n');

  const blob = new Blob([icsContent], { type: 'text/calendar' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${event.id}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Draft public comment - Session 49: Switch to drafts tab instead of opening artifact
function draftComment() {
  // Switch to drafts tab
  activeTab.value = 'drafts';

  // DraftWorkspace will auto-load or generate draft based on selection
  // If no drafts exist, it will auto-generate on mount
  console.log('[EventArtifact] Switched to Drafts tab with selection:', selectedAgendaItems.value.length);
}

// Handle agenda item selection changes
function handleAgendaSelectionChanged(items: ActionableItem[]) {
  selectedAgendaItems.value = items;
}

// Copy event link
function copyLink() {
  navigator.clipboard.writeText(props.event.source_url);
  alert('Event link copied to clipboard!');
}

// Format bill ID for display (ca-sb9 → SB 9)
function formatBillId(id: string): string {
  if (!id) return '';
  // Remove jurisdiction prefix (ca-, us-, etc.)
  const withoutPrefix = id.replace(/^[a-z]{2}-/, '');
  // Convert to uppercase and add space before number (sb9 → SB 9)
  return withoutPrefix.replace(/([a-z]+)(\d+)/i, (_, letters, numbers) => {
    return `${letters.toUpperCase()} ${numbers}`;
  });
}

// Email council (stub for now)
function handleEmailCouncil() {
  // TODO: Open email template modal with pre-filled council contacts
  alert('Email template coming soon! You\'ll be able to email council members about: ' + props.event.title);
}

// Has legislative context
const hasLegislativeContext = computed(() => {
  const ctx = props.event.legislative_context;
  return (ctx?.state_legislation && ctx.state_legislation.length > 0) ||
         (ctx?.federal_programs && ctx.federal_programs.length > 0);
});

// Has CDBG allocation
const hasCDBGAllocation = computed(() => {
  return props.event.legislative_context?.jurisdiction_specific?.CDBG?.amount;
});

/**
 * Load follow info for coordination chat
 */
async function loadFollowInfo() {
  try {
    const info = await api.getFollowInfo('event', props.event.id, userId);
    followInfo.value = info;
  } catch (err) {
    console.error('[EventArtifact] Failed to load follow info:', err);
  }
}

/**
 * Handle follow status change from FollowButton
 */
function handleFollowChanged(info: FollowInfoResponse) {
  followInfo.value = info;
  console.log('[EventArtifact] Follow info updated:', info);
}

// Load follow info on mount
onMounted(async () => {
  // Check if we should open to a specific tab (e.g., 'discussion' from DiscussionsPanel)
  const currentArtifact = workspaceStore.activeArtifact;
  if (currentArtifact?.initialTab && currentArtifact.id === props.event.id) {
    activeTab.value = currentArtifact.initialTab as 'details' | 'discussion' | 'drafts';
  }

  loadFollowInfo();
  loadDrafts();

  // Register context element
  const contextElement = await createEventContext(
    props.event,
    ArtifactIds.event(props.event), // Centralized ID generation (Session 53.5)
    'primary'
  );
  contextId.value = contextStore.register(contextElement);
  console.log('[EventArtifact] Context registered:', contextId.value);
});

// Session 54: Context persists when tab closes (removed onUnmounted hook)
// Context is now only removed via explicit "X" button in ContextIndicator
// This enables multi-document workflows (e.g., keep discussion in context while drafting)

// Session 50 fix: Watch for artifact switches AND initialTab changes
watch(
  () => workspaceStore.activeArtifact,
  (newArtifact) => {
    if (newArtifact?.id === props.event.id && newArtifact.initialTab) {
      console.log('[EventArtifact] Switching to tab:', newArtifact.initialTab);
      activeTab.value = newArtifact.initialTab as 'details' | 'discussion' | 'drafts';
    }
  },
  { deep: true, immediate: true } // Deep watch to catch initialTab updates
);

// Update context when tab changes
watch(activeTab, (newTab) => {
  if (contextId.value) {
    const element = contextStore.get(contextId.value);
    if (element?.metadata.event) {
      contextStore.update(contextId.value, {
        metadata: {
          ...element.metadata,
          event: {
            ...element.metadata.event,
            active_tab: newTab
          }
        }
      });
      console.log('[EventArtifact] Context updated with tab:', newTab);
    }
  }
});

// Open as tab (for detail mode)
function openAsTab() {
  emit('open-as-tab', props.event);
}

// Open discussion thread as standalone artifact
function openDiscussion() {
  console.log('[EventArtifact] openDiscussion called, followInfo:', followInfo.value);

  if (!followInfo.value.thread_id) {
    alert('No discussion thread yet. Follow this event to start one!');
    return;
  }

  // Log the thread_id we're about to open
  console.log('[EventArtifact] Opening thread artifact with ID:', followInfo.value.thread_id);

  // Emit event to open thread artifact
  workspaceStore.openArtifact({
    id: followInfo.value.thread_id,
    type: 'thread',
    title: props.event.title,
    data: {
      threadId: followInfo.value.thread_id,
      focalType: 'event',
      focalId: props.event.id
    }
  });
}

/**
 * Switch to a specific tab (handles auto-follow for discussion tab)
 */
async function switchTab(tab: 'details' | 'discussion' | 'drafts') {
  // If switching to discussion tab and not following, auto-follow first
  if (tab === 'discussion' && !followInfo.value.your_following) {
    await followEvent(false); // false = don't open in new tab, we're switching tabs here
  }
  activeTab.value = tab;
}

/**
 * Toggle follow status (header button click)
 */
async function toggleFollow() {
  if (followInfo.value.your_following) {
    // Unfollow
    await unfollowEvent();
  } else {
    // Follow (don't auto-open discussion)
    await followEvent(false);
  }
}

/**
 * Follow this event (optionally open discussion)
 */
async function followEvent(openDiscussionAfter = true) {
  try {
    const result = await api.createFollow(
      userId,
      'event',
      props.event.id,
      props.event.jurisdiction.id
    );

    // Update follow info
    followInfo.value = {
      follower_count: result.follower_count,
      thread_id: result.thread_id,
      your_following: result.your_following
    };

    // Only open discussion if requested
    if (openDiscussionAfter && result.thread_id) {
      openDiscussion();
    }
  } catch (err) {
    console.error('[EventArtifact] Failed to follow event:', err);
    alert('Failed to join discussion. Please try again.');
  }
}

/**
 * Unfollow this event
 */
async function unfollowEvent() {
  try {
    const result = await api.deleteFollow(
      userId,
      'event',
      props.event.id
    );

    // Update follow info
    followInfo.value = {
      ...followInfo.value,
      follower_count: result.follower_count,
      your_following: result.your_following
    };
  } catch (err) {
    console.error('[EventArtifact] Failed to unfollow event:', err);
    alert('Failed to unfollow. Please try again.');
  }
}
</script>

<template>
  <div class="event-artifact" :class="{ 'detail-mode': mode === 'detail' }">
    <!-- Header (Full Mode - with tabs and close button) -->
    <div v-if="mode === 'full'" class="artifact-header">
      <div class="header-left">
        <!-- Header Tabs (Details/Discussion/Drafts) -->
        <div class="header-tabs">
          <button
            class="header-tab-button"
            :class="{ 'active': activeTab === 'details' }"
            @click="switchTab('details')"
          >
            <FileText :size="16" />
            Details
          </button>
          <button
            class="header-tab-button"
            :class="{ 'active': activeTab === 'discussion' }"
            @click="switchTab('discussion')"
          >
            <MessageCircle :size="16" />
            Discussion
          </button>
          <button
            class="header-tab-button"
            :class="{ 'active': activeTab === 'drafts' }"
            @click="switchTab('drafts')"
          >
            <Edit3 :size="16" />
            Drafts
            <span v-if="draftCount > 0" class="tab-badge">
              {{ draftCount }}
            </span>
          </button>
        </div>
      </div>

      <!-- Follow Button (LinkedIn-style) -->
      <button
        class="follow-btn"
        :class="{ 'is-following': followInfo.your_following }"
        @click="toggleFollow"
      >
        <span v-if="!followInfo.your_following">+ Follow</span>
        <span v-else>Following</span>
      </button>

      <button class="close-btn" @click="emit('close')" title="Close tab">
        <span class="icon">×</span>
      </button>
    </div>

    <!-- Header (Detail Mode - simpler, with open-as-tab button) -->
    <div v-else class="artifact-header detail-header">
      <h2 class="artifact-title">{{ event.title }}</h2>
      <button class="open-as-tab-button" @click="openAsTab" title="Open as tab (Enter)">
        Open in Tab →
      </button>
    </div>

    <!-- Content -->
    <div class="artifact-body" :class="{ 'discussion-mode': activeTab === 'discussion' }">
      <!-- Details Tab Content -->
      <div v-if="activeTab === 'details'" class="details-content">
        <!-- Event Title (Prominent) -->
        <h1 class="event-title">{{ event.title }}</h1>

        <!-- Compact metadata line (like IssueArtifact) -->
        <div class="event-metadata-compact">
          <span class="meta-item">{{ formatDateTime(event.when) }}</span>
          <span class="meta-separator">•</span>
          <span class="meta-item" :class="{ 'deadline-passed': formatDeadline(event.deadline) === 'Passed' }">
            Comment Deadline: {{ formatDeadline(event.deadline) }}
          </span>
          <span v-if="event.jurisdiction" class="meta-separator">•</span>
          <span v-if="event.jurisdiction" class="meta-item">{{ event.jurisdiction.name }}</span>
          <button
            class="calendar-icon-btn-inline"
            @click="addToCalendar"
            title="Add to calendar"
          >
            <Calendar :size="14" />
          </button>
        </div>

        <!-- Badges -->
        <div class="artifact-badges">
          <span v-if="event.project_type" class="category-badge" :class="event.project_type">
            {{ event.project_type }}
          </span>
        </div>

        <!-- Description (elevated - right after title) -->
        <div v-if="event.description && event.description !== 'Calendar event'" class="event-description">
          {{ event.description }}
        </div>

        <!-- Event Details (collapsible - contains location, type, contact) -->
        <div class="collapsible-section event-details-section" :class="{ 'is-expanded': isEventDetailsExpanded }">
          <button
            class="collapsible-header"
            @click="isEventDetailsExpanded = !isEventDetailsExpanded"
          >
            <ChevronRight
              :size="16"
              class="collapse-icon"
              :class="{ 'is-rotated': isEventDetailsExpanded }"
            />
            <FileText :size="18" class="section-icon" />
            <span class="section-title">Event Details</span>
          </button>

          <div v-if="isEventDetailsExpanded" class="collapsible-content">
            <div class="detail-rows">
              <div v-if="event.location" class="detail-row">
                <span class="detail-label">Location</span>
                <span class="detail-value">{{ event.location }}</span>
              </div>
              <div v-if="event.meeting_type" class="detail-row">
                <span class="detail-label">Type</span>
                <span class="detail-value">{{ event.meeting_type.replace(/_/g, ' ') }}</span>
              </div>
              <div v-if="event.contact_info && event.contact_info.name" class="detail-row">
                <span class="detail-label">Contact</span>
                <span class="detail-value">
                  {{ event.contact_info.name }}
                  <span v-if="event.contact_info.title" class="contact-title-inline">({{ event.contact_info.title }})</span>
                </span>
              </div>
              <div v-if="event.contact_info && event.contact_info.email" class="detail-row">
                <span class="detail-label">Email</span>
                <span class="detail-value">
                  <a :href="`mailto:${event.contact_info.email}`" class="contact-email-link">{{ event.contact_info.email }}</a>
                </span>
              </div>
              <div v-if="event.contact_info && event.contact_info.phone" class="detail-row">
                <span class="detail-label">Phone</span>
                <span class="detail-value">{{ event.contact_info.phone }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Take Action Panel -->
        <div class="take-action-section">
          <h3 class="actions-title">Take Action</h3>
          <div class="action-buttons-row">
            <button class="action-btn primary" @click="draftComment" title="AI-assisted comment draft">
              <FileText :size="16" />
              <span v-if="selectedAgendaItems.length === 0">Draft Comment</span>
              <span v-else-if="selectedAgendaItems.length === 1">Draft Comment ({{ selectedAgendaItems.length }} item selected)</span>
              <span v-else>Draft Comment ({{ selectedAgendaItems.length }} items selected)</span>
            </button>
            <button class="action-btn" @click="addToCalendar" title="Add to your calendar">
              <Calendar :size="16" />
              Add to Calendar
            </button>
          </div>
        </div>

        <!-- Summary Statistics Bar -->
        <div class="summary-stats-bar">
          <div class="summary-stat" v-if="mockActionCounts.attending > 0">
            <Calendar :size="14" />
            {{ mockActionCounts.attending }} {{ mockActionCounts.attending === 1 ? 'person' : 'people' }} attending
          </div>
          <div class="summary-stat" v-if="followInfo.follower_count > 0">
            <Users :size="14" />
            {{ followInfo.follower_count }} {{ followInfo.follower_count === 1 ? 'neighbor' : 'neighbors' }} involved
          </div>
          <div class="summary-stat" v-if="mockActionCounts.emailed > 0">
            <Users :size="14" />
            {{ mockActionCounts.emailed }} {{ mockActionCounts.emailed === 1 ? 'action' : 'actions' }} taken
          </div>
        </div>

      <!-- Agenda Items (Session 23) - Now collapsible -->
      <div
        v-if="event.agenda_expansion && event.agenda_expansion.actionable_items && event.agenda_expansion.actionable_items.length > 0"
        class="collapsible-section agenda-section"
        :class="{ 'is-expanded': isAgendaExpanded }"
      >
        <button
          class="collapsible-header"
          @click="isAgendaExpanded = !isAgendaExpanded"
        >
          <ChevronRight
            :size="16"
            class="collapse-icon"
            :class="{ 'is-rotated': isAgendaExpanded }"
          />
          <FileText :size="18" class="section-icon" />
          <span class="section-title">Agenda Items</span>
          <span class="item-count">({{ event.agenda_expansion.actionable_items.length }})</span>
        </button>

        <div v-if="isAgendaExpanded" class="collapsible-content">
          <AgendaItems
            :items="event.agenda_expansion.actionable_items"
            @selection-changed="handleAgendaSelectionChanged"
          />
        </div>
      </div>

      <!-- Relevant Legislation - Now collapsible -->
      <div
        v-if="hasLegislativeContext"
        class="collapsible-section legislative-section"
        :class="{ 'is-expanded': isLegislativeExpanded }"
      >
        <button
          class="collapsible-header"
          @click="isLegislativeExpanded = !isLegislativeExpanded"
        >
          <ChevronRight
            :size="16"
            class="collapse-icon"
            :class="{ 'is-rotated': isLegislativeExpanded }"
          />
          <span class="section-icon">⚖️</span>
          <span class="section-title">Relevant Legislation</span>
          <span class="legislative-summary">
            ({{ event.legislative_context?.state_legislation?.length || 0 }} bills,
            {{ event.legislative_context?.federal_programs?.length || 0 }} programs)
          </span>
        </button>

        <div v-if="isLegislativeExpanded" class="collapsible-content">

        <!-- CDBG Allocation -->
        <div v-if="hasCDBGAllocation" class="cdbg-allocation">
          <div class="cdbg-header">
            <span class="cdbg-icon">💰</span>
            <strong>CDBG Allocation ({{ event.jurisdiction.name }})</strong>
          </div>
          <div class="cdbg-amount">
            {{ event.legislative_context?.jurisdiction_specific?.CDBG?.amount }}
          </div>
          <div v-if="event.legislative_context?.jurisdiction_specific?.CDBG?.allocation_deadline"
               class="cdbg-deadline">
            Deadline: {{ event.legislative_context.jurisdiction_specific.CDBG.allocation_deadline }}
          </div>
        </div>

        <!-- State Bills -->
        <div v-if="event.legislative_context?.state_legislation?.length" class="legislative-subsection">
          <h4 class="subsection-title">State Legislation</h4>
          <div
            v-for="bill in event.legislative_context.state_legislation"
            :key="bill.bill"
            class="legislative-item"
          >
            <div class="item-header">
              <div class="bill-id-and-name">
                <span class="bill-id">{{ formatBillId(bill.bill) }}</span>
                <span class="bill-name">{{ bill.bill }}</span>
              </div>
              <span class="bill-status">{{ bill.status }}</span>
            </div>
            <div class="item-title">{{ bill.title }}</div>
            <div class="item-leverage">
              <strong>Leverage Point:</strong> {{ bill.leverage_point }}
            </div>
            <a :href="bill.official_url" target="_blank" class="item-link">
              View Official Text →
            </a>
          </div>
        </div>

        <!-- Federal Programs -->
        <div v-if="event.legislative_context?.federal_programs?.length" class="legislative-subsection">
          <h4 class="subsection-title">Federal Programs</h4>
          <div
            v-for="program in event.legislative_context.federal_programs"
            :key="program.program_name"
            class="legislative-item"
          >
            <div class="item-header">
              <span class="program-name">{{ program.program_name }}</span>
              <span v-if="program.fy2025_allocation" class="program-allocation">
                {{ program.fy2025_allocation }}
              </span>
            </div>
            <div class="item-agency">{{ program.agency }}</div>
            <div class="item-leverage">
              <strong>Leverage Point:</strong> {{ program.leverage_point }}
            </div>
            <a :href="program.info_url" target="_blank" class="item-link">
              Learn More →
            </a>
          </div>
        </div>
        </div>
      </div>

      </div>

      <!-- Discussion Tab Content -->
      <div v-if="activeTab === 'discussion' && followInfo.thread_id" class="discussion-tab-content">
        <ThreadArtifact :thread-id="followInfo.thread_id" :embedded="true" />
      </div>

      <!-- Drafts Tab Content (Session 49) -->
      <div v-if="activeTab === 'drafts'" class="drafts-tab-content">
        <DraftWorkspace
          :event="event"
          :selected-agenda-items="selectedAgendaItems"
          :all-drafts="allDrafts"
          @draft-updated="loadDrafts"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.event-artifact {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--background);
}

/* Header */
.artifact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-lg) var(--space-xl);
  background: var(--background);
  border-bottom: 1px solid var(--border);
  gap: var(--space-md);
  flex-shrink: 0;
}

/* Detail Mode Header (simpler) */
.artifact-header.detail-header {
  padding: var(--space-md) var(--space-lg);
  background: var(--background);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex: 1;
  min-width: 0;
}

.artifact-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.detail-mode .artifact-title {
  font-size: var(--font-size-base);
  white-space: normal;
  line-height: 1.4;
}

.close-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-base);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  transition: all var(--transition-fast);
}

.close-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
}

/* Header Tabs (moved from content area) */
.header-tabs {
  display: flex;
  gap: 2px;
  align-items: flex-end;
}

.header-tab-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-bottom: none;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border-radius: 6px 6px 0 0; /* Round top corners only */
  position: relative;
  margin-bottom: -1px; /* Overlap with header border */
}

.header-tab-button:hover {
  color: var(--text-primary);
  background: var(--background);
}

.header-tab-button.active {
  color: var(--primary);
  background: var(--background); /* Match content background */
  border-color: var(--border);
  border-bottom: 1px solid var(--background); /* Hide bottom border to connect with content */
  font-weight: 600;
  z-index: 1; /* Appear on top */
}

/* Tab badge for counts (Session 49) */
.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  background: var(--primary);
  color: white;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
}

.header-tab-button.active .tab-badge {
  background: var(--primary);
}

/* LinkedIn-style Follow Button (in header) */
.follow-btn {
  padding: 6px 16px;
  border-radius: 16px; /* Rounded pill shape like LinkedIn */
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--primary);
  background: transparent;
  color: var(--primary);
  margin-right: var(--space-md);
}

.follow-btn:hover {
  background: rgba(38, 139, 210, 0.08);
}

/* Following state - filled background */
.follow-btn.is-following {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.follow-btn.is-following:hover {
  background: #1c6fa0; /* darker blue */
  border-color: #1c6fa0;
}

/* Open as Tab Button (detail mode) */
.open-as-tab-button {
  padding: var(--space-xs) var(--space-md);
  background: var(--primary);
  color: white;
  border: 1px solid var(--primary);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.open-as-tab-button:hover {
  background: var(--accent-purple);
  border-color: var(--accent-purple);
  transform: translateY(-1px);
  box-shadow: var(--shadow-subtle);
}

/* Body */
.artifact-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xl);
  background: var(--background);
}

.detail-mode .artifact-body {
  padding: var(--space-lg);
}

/* Discussion Mode - when Discussion tab is active */
.artifact-body.discussion-mode {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Discussion Tab Content */
.discussion-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Drafts Tab Content (Session 49) */
.drafts-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}


/* Take Action Section (matches IssueArtifact) */
.take-action-section {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.actions-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

.action-buttons-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
}

.action-btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.action-btn.primary:hover {
  background: var(--primary-hover);
}

/* Summary Statistics Bar (matches IssueArtifact) */
.summary-stats-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 4px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
  flex-wrap: wrap;
}

.summary-stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.summary-stat svg {
  color: var(--text-secondary);
  opacity: 0.8;
}

/* Badges - Minimal GitHub-style (matches IssueArtifact) */
.artifact-badges {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.category-badge {
  display: inline-flex;
  padding: 4px 10px;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: capitalize;
  border: 1px solid rgba(0, 0, 0, 0.12); /* Very subtle border */
}

/* Keep minimal - no per-category colors */

.engagement-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.engagement-badge.tier-quick { background: var(--accent-green); color: white; }
.engagement-badge.tier-full { background: var(--accent-orange); color: white; }
.engagement-badge.tier-expert { background: var(--accent-purple); color: white; }

/* Event Title (Prominent) */
.event-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.3;
}

/* Compact metadata line (like IssueArtifact) */
.event-metadata-compact {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  font-size: 14px;
  color: var(--text-secondary);
}

.meta-item {
  color: var(--text-secondary);
}

.meta-item.deadline-passed {
  color: var(--accent-orange);
  font-weight: 600;
}

.meta-separator {
  opacity: 0.5;
}

/* Calendar icon button - inline in compact metadata */
.calendar-icon-btn-inline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 6px;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  margin-left: 8px;
}

.calendar-icon-btn-inline:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--primary);
  transform: translateY(-1px);
}

.calendar-icon-btn-inline:active {
  transform: translateY(0);
}

/* Event Description (elevated - right after title) */
.event-description {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--background-secondary);
  border-radius: 8px;
  border: 1px solid var(--border);
  white-space: pre-wrap;
}

/* Event Details collapsible section */
.event-details-section {
  margin-bottom: 16px;
}

.detail-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.detail-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  flex: 1;
}

/* Contact info inline in detail rows */
.contact-title-inline {
  color: var(--text-secondary);
  font-size: 13px;
  margin-left: 4px;
}

.contact-email-link {
  color: var(--primary);
  text-decoration: none;
  font-weight: 500;
}

.contact-email-link:hover {
  text-decoration: underline;
}

/* Content Sections */
.content-section {
  margin-bottom: 20px;
}

.content-section.highlight {
  padding: var(--space-lg);
  background: var(--background-secondary);
  border-radius: var(--radius-base);
  border: 1px solid var(--border);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-md) 0;
}

.section-icon {
  font-size: 20px;
}

.section-content {
  font-size: var(--font-size-base);
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
}

/* Legislative Section */
.legislative-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-lg);
  gap: var(--space-md);
}

.legislative-summary {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: 600;
}

/* CDBG Allocation - Subtle styling */
.cdbg-allocation {
  padding: 12px 16px;
  background: var(--background-secondary);
  border-left: 3px solid var(--accent-orange);
  border-radius: 4px;
  margin-bottom: 20px;
}

.cdbg-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-weight: 600;
}

.cdbg-icon {
  font-size: 14px;
}

.cdbg-amount {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.cdbg-deadline {
  font-size: 13px;
  color: var(--text-secondary);
}

/* Legislative Subsections - Minimal styling */
.legislative-subsection {
  margin-bottom: 24px;
}

.legislative-subsection:last-child {
  margin-bottom: 0;
}

.subsection-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.legislative-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
}

.legislative-item:last-child {
  border-bottom: none;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}

.bill-id-and-name {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.bill-id {
  font-size: 14px;
  font-weight: 700;
  color: var(--primary);
  white-space: nowrap;
}

.bill-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.program-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
}

.bill-status {
  font-size: 11px;
  padding: 2px 6px;
  background: transparent;
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
}

.program-allocation {
  font-size: 11px;
  padding: 2px 6px;
  background: transparent;
  color: var(--accent-orange);
  border: 1px solid var(--accent-orange);
  border-radius: 3px;
  font-weight: 600;
}

.item-title {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
  margin-bottom: 6px;
  line-height: 1.5;
}

.item-agency {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.item-leverage {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 6px;
}

.item-leverage strong {
  display: none; /* Hide "Leverage Point:" label for cleaner look */
}

.item-link {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  color: var(--primary);
  font-weight: 500;
  text-decoration: none;
  transition: color var(--transition-fast);
}

.item-link:hover {
  color: var(--primary);
  text-decoration: underline;
}

/* Collapsible Sections - EXACT match to IssueArtifact */
.collapsible-section {
  /* Lightweight sections - no heavy borders */
  margin-bottom: 16px;
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 0;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  outline: none;
}

.collapsible-header:hover .section-title {
  color: var(--primary);
}

.collapsible-header:focus {
  outline: none; /* Ensure no blue border on focus */
}

.collapse-icon {
  color: var(--text-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.collapse-icon.is-rotated {
  transform: rotate(90deg);
}

/* Collapsible section titles (overrides other .section-title) */
.collapsible-header .section-title {
  margin: 0;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-secondary);
  flex: 1;
  line-height: 1.4;
}

.section-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
  font-size: 18px;
}

.item-count,
.legislative-summary {
  color: var(--text-secondary);
  font-size: 13px;
  margin-left: auto;
}

.collapsible-content {
  padding: 12px 20px;
  background: var(--background); /* Lighter background - content area */
  border-top: 1px solid var(--border);
}

/* Agenda section - no padding/background (AgendaItems has its own styling) */
.agenda-section .collapsible-content {
  padding: 0;
  background: transparent;
  border-top: none;
}

/* Override AgendaItems heavy styling to be minimal like IssueArtifact sections */
.agenda-section :deep(.agenda-items) {
  margin-bottom: 0;
  padding: 16px 20px;
  background: transparent;
  border: none;
  border-radius: 0;
}

.agenda-section :deep(.agenda-header) {
  margin-bottom: 12px;
}

.agenda-section :deep(.agenda-title) {
  font-size: 14px;
  font-weight: 600;
}

.agenda-section :deep(.section-icon) {
  font-size: 16px;
}

/* Action Buttons */
.action-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-md);
  padding-top: var(--space-lg);
  border-top: 2px solid var(--border);
  margin-top: var(--space-xl);
}

.action-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
  white-space: nowrap;
}

.action-button.primary {
  background: var(--primary);
  color: white;
  border: 2px solid var(--primary);
}

.action-button.primary:hover {
  background: var(--accent-purple);
  border-color: var(--accent-purple);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.action-button.secondary {
  background: var(--background);
  color: var(--primary);
  border: 2px solid var(--primary);
}

.action-button.secondary:hover {
  background: var(--primary);
  color: white;
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.action-button.tertiary {
  background: var(--background-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.action-button.tertiary:hover {
  background: var(--background);
  color: var(--text-primary);
  border-color: var(--primary);
}

.button-icon {
  font-size: 18px;
}

/* Responsive */
@media (max-width: 768px) {
  .artifact-body {
    padding: var(--space-lg) var(--space-md);
  }

  .artifact-header {
    padding: var(--space-md);
  }

  .header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-sm);
  }

  .artifact-title {
    white-space: normal;
  }

  .meta-row {
    grid-template-columns: 1fr;
  }

  .action-buttons {
    grid-template-columns: 1fr;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

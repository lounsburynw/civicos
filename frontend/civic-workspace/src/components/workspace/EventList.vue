<script setup lang="ts">
import { computed, watch, ref, onMounted, onUnmounted } from 'vue';
import type { CivicEvent, Jurisdiction, ProjectType } from '@/types/civic';
import { useEventsStore } from '@/stores/events';
import { useWorkspaceStore } from '@/stores/workspace';
import { ArtifactIds } from '@/utils/artifactIds';
import { MessageCircle } from 'lucide-vue-next';
import { api } from '@/services/api';

const props = defineProps<{
  jurisdiction: Jurisdiction | null;
}>();

const emit = defineEmits<{
  'event-select': [event: CivicEvent];
}>();

// Stores
const eventsStore = useEventsStore();
const workspaceStore = useWorkspaceStore();

// Selected event index for keyboard navigation
const selectedIndex = ref(0);

// Available project types for filtering
const PROJECT_TYPES: Array<{ value: ProjectType | 'all'; label: string; icon: string }> = [
  { value: 'all', label: 'All', icon: '📋' },
  { value: 'housing', label: 'Housing', icon: '🏠' },
  { value: 'transportation', label: 'Transportation', icon: '🚌' },
  { value: 'environment', label: 'Environment', icon: '🌳' },
  { value: 'budget', label: 'Budget', icon: '💰' },
  { value: 'development', label: 'Development', icon: '🏗️' },
  { value: 'public_safety', label: 'Public Safety', icon: '🚨' },
  { value: 'community', label: 'Community', icon: '👥' },
];

// Watch for jurisdiction changes
watch(() => props.jurisdiction, async (newJurisdiction) => {
  if (newJurisdiction) {
    await eventsStore.fetchEventsForJurisdiction(newJurisdiction.id);
  }
}, { immediate: true });

// Computed: loading, error, filtered events
const loading = computed(() => {
  return props.jurisdiction
    ? eventsStore.isLoadingForJurisdiction(props.jurisdiction.id)
    : false;
});

const error = computed(() => {
  return props.jurisdiction
    ? eventsStore.getErrorForJurisdiction(props.jurisdiction.id)
    : null;
});

const filteredEvents = computed(() => {
  if (!props.jurisdiction) return [];
  return eventsStore.getFilteredEvents(props.jurisdiction.id);
});

// Load events (for retry button)
async function loadEvents(jurisdictionId: string) {
  await eventsStore.fetchEventsForJurisdiction(jurisdictionId, true); // Force refresh
}

// Format date for display
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Tomorrow';
  } else if (diffDays < 7) {
    return `In ${diffDays} days`;
  } else {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
  }
}

// Handle event card click
function handleEventClick(event: CivicEvent, index: number) {
  selectedIndex.value = index;
  emit('event-select', event);
}

// Check if event is selected
function isEventSelected(event: CivicEvent): boolean {
  return workspaceStore.selectedEventInList?.id === event.id;
}

// Keyboard navigation
function handleKeyDown(e: KeyboardEvent) {
  if (filteredEvents.value.length === 0) return;

  // Arrow Down: Next event
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex.value = Math.min(selectedIndex.value + 1, filteredEvents.value.length - 1);
    emit('event-select', filteredEvents.value[selectedIndex.value]);
  }
  // Arrow Up: Previous event
  else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0);
    emit('event-select', filteredEvents.value[selectedIndex.value]);
  }
  // Enter: Open selected event as tab
  else if (e.key === 'Enter') {
    e.preventDefault();
    const selectedEvent = filteredEvents.value[selectedIndex.value];
    if (selectedEvent) {
      // Open as tab instead of just selecting
      workspaceStore.openArtifact({
        id: ArtifactIds.event(selectedEvent), // Centralized ID generation (Session 53.5)
        type: 'event',
        title: selectedEvent.title,
        data: selectedEvent
      });
    }
  }
  // Escape: Clear selection
  else if (e.key === 'Escape') {
    e.preventDefault();
    workspaceStore.clearEventInList();
  }
}

// Register keyboard listeners
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

// Get engagement tier badge color
function getEngagementTierClass(tier?: string): string {
  switch (tier) {
    case 'quick_action':
      return 'tier-quick';
    case 'full_engagement':
      return 'tier-full';
    case 'expert_level':
      return 'tier-expert';
    default:
      return '';
  }
}

// Format engagement tier label
function formatEngagementTier(tier?: string): string {
  switch (tier) {
    case 'quick_action':
      return 'Quick Action';
    case 'full_engagement':
      return 'Full Engagement';
    case 'expert_level':
      return 'Expert Level';
    default:
      return '';
  }
}

// Discussion stats (Session 33 - Event Discovery)
const discussionStats = ref<Map<string, { participant_count: number, message_count: number, thread_id: string }>>(new Map());

async function loadDiscussionStats(events: CivicEvent[]) {
  if (events.length === 0) return;

  const eventIds = events.map(e => e.id);
  try {
    const response = await api.getEventDiscussionStats(eventIds);
    const statsMap = new Map(response.stats.map((s: { event_id: string; thread_id: string; participant_count: number; message_count: number }) => [s.event_id, s]));
    discussionStats.value = statsMap;
  } catch (err) {
    console.error('Failed to load discussion stats:', err);
  }
}

// Call when events change
watch(() => filteredEvents.value, (events) => {
  loadDiscussionStats(events);
}, { immediate: true });

function openDiscussion(event: CivicEvent) {
  const stats = discussionStats.value.get(event.id);
  if (stats) {
    workspaceStore.openArtifact({
      type: 'thread',
      id: stats.thread_id,
      title: event.title,
      data: { thread_id: stats.thread_id, event }
    });
  }
}

function startDiscussion(event: CivicEvent) {
  // Open EventArtifact where user can start a thread
  workspaceStore.openArtifact({
    type: 'event',
    id: ArtifactIds.event(event), // Centralized ID generation (Session 53.5)
    title: event.title,
    data: event
  });
}
</script>

<template>
  <div class="event-list">
    <!-- Header with filters -->
    <div class="event-list-header">
      <h2 class="event-list-title">
        {{ jurisdiction?.name || 'Events' }}
      </h2>
      <div class="event-count">
        {{ filteredEvents.length }} {{ filteredEvents.length === 1 ? 'event' : 'events' }}
      </div>
    </div>

    <!-- Project Type Filters -->
    <div class="event-filters">
      <button
        v-for="type in PROJECT_TYPES"
        :key="type.value"
        class="filter-button"
        :class="{ active: eventsStore.selectedProjectType === type.value }"
        @click="eventsStore.setProjectTypeFilter(type.value)"
      >
        <span class="filter-icon">{{ type.icon }}</span>
        <span class="filter-label">{{ type.label }}</span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="event-list-state">
      <div class="loading-spinner">
        <div class="spinner"></div>
      </div>
      <p class="state-message">Loading events...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="event-list-state error">
      <div class="error-icon">⚠️</div>
      <p class="state-message">{{ error }}</p>
      <button v-if="jurisdiction" @click="loadEvents(jurisdiction.id)" class="retry-button">
        Try Again
      </button>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredEvents.length === 0 && jurisdiction" class="event-list-state empty">
      <div class="empty-icon">📭</div>
      <p class="state-message">
        {{ eventsStore.selectedProjectType === 'all'
          ? 'No upcoming events found'
          : `No ${eventsStore.selectedProjectType} events found`
        }}
      </p>
      <button
        v-if="eventsStore.selectedProjectType !== 'all'"
        @click="eventsStore.setProjectTypeFilter('all')"
        class="reset-filter-button"
      >
        Show All Events
      </button>
    </div>

    <!-- Event Cards -->
    <div v-else class="event-cards">
      <div
        v-for="(event, index) in filteredEvents"
        :key="event.id"
        class="event-card"
        :class="{ selected: isEventSelected(event) }"
        @click="handleEventClick(event, index)"
      >
        <!-- Event Header -->
        <div class="event-card-header">
          <h3 class="event-title">{{ event.title }}</h3>
          <div class="event-badges">
            <span v-if="event.project_type" class="category-badge" :class="event.project_type">
              {{ event.project_type }}
            </span>
            <span
              v-if="event.engagement_tier"
              class="engagement-badge"
              :class="getEngagementTierClass(event.engagement_tier)"
            >
              {{ formatEngagementTier(event.engagement_tier) }}
            </span>
          </div>
        </div>

        <!-- Event Meta -->
        <div class="event-meta">
          <div class="meta-item">
            <span class="meta-icon">📅</span>
            <span class="meta-text">{{ formatDate(event.when) }}</span>
          </div>
          <div v-if="event.meeting_type" class="meta-item">
            <span class="meta-icon">🏛️</span>
            <span class="meta-text">{{ event.meeting_type.replace('_', ' ') }}</span>
          </div>
        </div>

        <!-- Impact Summary -->
        <p v-if="event.impact_summary" class="event-summary">
          {{ event.impact_summary }}
        </p>

        <!-- Legislative Context Indicator -->
        <div v-if="event.legislative_context?.state_legislation_refs?.length || event.legislative_context?.federal_program_refs?.length"
             class="legislative-indicator">
          <span class="legislative-icon">⚖️</span>
          <span class="legislative-text">
            {{ event.legislative_context.state_legislation_refs?.length || 0 }} state bills,
            {{ event.legislative_context.federal_program_refs?.length || 0 }} federal programs
          </span>
        </div>

        <!-- Discussion Activity Indicator (Session 33) -->
        <div v-if="discussionStats.get(event.id)" class="discussion-activity">
          <MessageCircle :size="16" class="discussion-icon" />
          <span class="discussion-text">
            <strong>{{ discussionStats.get(event.id)!.participant_count }}</strong> people discussing
            • {{ discussionStats.get(event.id)!.message_count }} messages
          </span>
          <button @click.stop="openDiscussion(event)" class="join-discussion-btn">
            Join Discussion
          </button>
        </div>

        <!-- Start Discussion Button (if no activity) -->
        <button v-else @click.stop="startDiscussion(event)" class="start-discussion-btn">
          <MessageCircle :size="14" />
          Start Discussion
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.event-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Header */
.event-list-header {
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--background-secondary);
}

.event-list-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--primary);
  margin: 0;
}

.event-count {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

/* Filters */
.event-filters {
  display: flex;
  gap: var(--space-xs);
  padding: var(--space-md) var(--space-xl);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  background: var(--background);
}

.filter-button {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--border);
  background: var(--background);
  color: var(--text-secondary);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.filter-button:hover {
  background: var(--background-secondary);
  color: var(--text-primary);
  border-color: var(--primary);
}

.filter-button.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.filter-icon {
  font-size: 1.1em;
}

.filter-label {
  font-size: var(--font-size-sm);
}

/* Event Cards */
.event-cards {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-lg) var(--space-xl);
}

.event-card {
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  padding: var(--space-lg);
  margin-bottom: var(--space-md);
  box-shadow: var(--shadow-subtle);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.event-card:hover {
  box-shadow: var(--shadow);
  border-color: var(--primary);
  transform: translateY(-2px);
}

/* Selected state for split-pane view */
.event-card.selected {
  border-left: 4px solid var(--primary);
  background: var(--hover-bg);
  box-shadow: var(--shadow);
}

.event-card:last-child {
  margin-bottom: 0;
}

/* Event Card Header */
.event-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}

.event-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  flex: 1;
  line-height: 1.4;
}

.event-badges {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  align-items: flex-end;
}

/* Category Badge (from design system) */
.category-badge {
  background: var(--primary-light);
  color: var(--primary);
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.category-badge.housing {
  background: #FFF3E0;
  color: #E65100;
}

.category-badge.transportation {
  background: #E3F2FD;
  color: #0D47A1;
}

.category-badge.environment {
  background: #E8F5E9;
  color: #1B5E20;
}

.category-badge.budget {
  background: #FFF9C4;
  color: #F57F17;
}

.category-badge.development {
  background: #F3E5F5;
  color: #6A1B9A;
}

.category-badge.public_safety {
  background: #FFEBEE;
  color: #C62828;
}

.category-badge.community {
  background: #E1F5FE;
  color: #0277BD;
}

/* Engagement Tier Badge */
.engagement-badge {
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.engagement-badge.tier-quick {
  background: var(--accent-green);
  color: white;
}

.engagement-badge.tier-full {
  background: var(--accent-orange);
  color: white;
}

.engagement-badge.tier-expert {
  background: var(--accent-purple);
  color: white;
}

/* Event Meta */
.event-meta {
  display: flex;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.meta-icon {
  font-size: 1em;
}

.meta-text {
  text-transform: capitalize;
}

/* Event Summary */
.event-summary {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  line-height: 1.5;
  margin: var(--space-sm) 0;
}

/* Legislative Indicator */
.legislative-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  margin-top: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  background: var(--primary-light);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}

.legislative-icon {
  font-size: 1em;
}

.legislative-text {
  color: var(--primary);
  font-weight: 500;
}

/* Discussion Activity Indicator (Session 33) */
.discussion-activity {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
  padding: var(--space-sm);
  background: rgba(38, 139, 210, 0.1); /* Blue tint */
  border-radius: var(--radius-base);
  border-left: 3px solid var(--primary);
}

.discussion-icon {
  color: var(--primary);
  flex-shrink: 0;
}

.discussion-text {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.join-discussion-btn {
  padding: 4px 12px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.join-discussion-btn:hover {
  background: var(--accent-purple);
}

.start-discussion-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 4px 8px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  margin-top: var(--space-sm);
}

.start-discussion-btn:hover {
  color: var(--primary);
  border-color: var(--primary);
}

/* State Messages */
.event-list-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl);
  text-align: center;
}

.state-message {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: var(--space-md) 0;
}

/* Loading */
.loading-spinner {
  margin-bottom: var(--space-md);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error */
.event-list-state.error .error-icon {
  font-size: 48px;
  margin-bottom: var(--space-sm);
}

.retry-button {
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-lg);
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.retry-button:hover {
  background: var(--accent-purple);
}

/* Empty State */
.event-list-state.empty .empty-icon {
  font-size: 64px;
  margin-bottom: var(--space-md);
}

.reset-filter-button {
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-lg);
  background: var(--background-secondary);
  color: var(--primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.reset-filter-button:hover {
  background: var(--primary);
  color: white;
}

/* Responsive */
@media (max-width: 768px) {
  .event-list-header,
  .event-filters,
  .event-cards {
    padding-left: var(--space-md);
    padding-right: var(--space-md);
  }

  .event-card-header {
    flex-direction: column;
    gap: var(--space-sm);
  }

  .event-badges {
    align-items: flex-start;
    flex-direction: row;
  }

  .filter-label {
    display: none;
  }
}
</style>

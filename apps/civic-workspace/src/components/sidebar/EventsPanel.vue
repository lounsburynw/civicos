<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { Calendar, Search, X, Home, Train, Leaf, DollarSign, Building2, Lightbulb, XCircle } from 'lucide-vue-next';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import { useVisualEnhancements } from '@/composables/useVisualEnhancements';
import { api } from '@/services/api';
import type { CivicEvent, ProjectType } from '@/types/civic';
import type { Component } from 'vue';

const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();
const { isSectionPulsing, isFilterHighlighted } = useVisualEnhancements(); // Session 59

// State
const allEvents = ref<CivicEvent[]>([]);
const followedEventIds = ref<Set<string>>(new Set());
const discussionStats = ref<Map<string, { discussion_count: number; participant_count: number }>>(new Map());
const loading = ref(true);
const error = ref<string | null>(null);
const searchQuery = ref('');
const activeOwnershipFilter = ref<'all' | 'following'>('all'); // Default to 'all'
const activeDateFilters = ref<Set<'past' | 'upcoming'>>(new Set(['past', 'upcoming'])); // Both by default
const activeTopicFilters = ref<Set<ProjectType>>(new Set()); // Empty = show all topics
const showChatHint = ref(false);
const chatHintTopic = ref('');
const chatHintType = ref<'topic' | 'search'>('topic'); // Track hint type
const hoverTimeout = ref<number | null>(null); // For delayed hover hint
const chatHintsDismissed = ref(false); // Persistent dismissal via localStorage

// Random search examples for chat hint (training wheels)
const searchExamples = [
  'zoning changes',
  'affordable housing',
  'budget discussions',
  'parking regulations',
  'tree removal permits',
  'bike lane projects',
  'rent control',
  'public safety funding',
  'climate action plans',
  'sidewalk repairs'
];

// Top 5 topics to display (most relevant for civic engagement)
const topTopics: Array<{ value: ProjectType; label: string; icon: Component; color: string }> = [
  { value: 'housing', label: 'Housing', icon: Home, color: '#cb4b16' }, // Orange - housing crisis
  { value: 'transportation', label: 'Transportation', icon: Train, color: '#268bd2' }, // Blue - transit
  { value: 'environment', label: 'Environment', icon: Leaf, color: '#859900' }, // Green - nature
  { value: 'budget', label: 'Budget', icon: DollarSign, color: '#b58900' }, // Yellow - money
  { value: 'development', label: 'Development', icon: Building2, color: '#6c71c4' } // Violet - planning
];

/**
 * Ownership filters with counts
 */
const ownershipFilters = computed(() => {
  const followingCount = allEvents.value.filter(e => followedEventIds.value.has(e.id)).length;

  return [
    { value: 'all' as const, label: 'All', count: allEvents.value.length },
    { value: 'following' as const, label: 'Following', count: followingCount }
  ];
});

/**
 * Get ownership-filtered events for date counts
 */
const ownershipFilteredEvents = computed(() => {
  if (activeOwnershipFilter.value === 'following') {
    return allEvents.value.filter(e => followedEventIds.value.has(e.id));
  }
  return allEvents.value;
});

/**
 * Date filters with counts (toggleable)
 */
const dateFilters = computed(() => {
  const now = new Date();
  return [
    { value: 'past' as const, label: 'Past', count: ownershipFilteredEvents.value.filter(e => new Date(e.when) < now).length },
    { value: 'upcoming' as const, label: 'Upcoming', count: ownershipFilteredEvents.value.filter(e => new Date(e.when) >= now).length }
  ];
});

/**
 * Get ownership+date filtered events for topic counts
 */
const ownershipAndDateFilteredEvents = computed(() => {
  let filtered = ownershipFilteredEvents.value;

  // Apply date filter
  if (activeDateFilters.value.size > 0 && activeDateFilters.value.size < 2) {
    const now = new Date();
    filtered = filtered.filter(e => {
      const eventDate = new Date(e.when);
      const isPast = eventDate < now;
      if (activeDateFilters.value.has('past') && isPast) return true;
      if (activeDateFilters.value.has('upcoming') && !isPast) return true;
      return false;
    });
  }

  return filtered;
});

/**
 * Topic filters with counts (toggleable, multi-select)
 */
const topicFilters = computed(() => {
  return topTopics.map(topic => {
    const count = ownershipAndDateFilteredEvents.value.filter(e => e.project_type === topic.value).length;
    return {
      ...topic,
      count
    };
  });
});

/**
 * Filtered events based on jurisdiction, ownership, date, topic, and search query
 */
const filteredEvents = computed(() => {
  let filtered = allEvents.value;

  // Jurisdiction filter (if a jurisdiction is selected, only show its events)
  if (workspaceStore.selectedJurisdiction) {
    filtered = filtered.filter(e => e.jurisdiction?.id === workspaceStore.selectedJurisdiction?.id);
  }

  // Ownership filter
  if (activeOwnershipFilter.value === 'following') {
    filtered = filtered.filter(e => followedEventIds.value.has(e.id));
  }

  // Date filter (toggleable - if none selected, show all; if only one selected, filter)
  if (activeDateFilters.value.size > 0 && activeDateFilters.value.size < 2) {
    const now = new Date();
    filtered = filtered.filter(e => {
      const eventDate = new Date(e.when);
      const isPast = eventDate < now;
      if (activeDateFilters.value.has('past') && isPast) return true;
      if (activeDateFilters.value.has('upcoming') && !isPast) return true;
      return false;
    });
  }

  // Topic filter (toggleable, multi-select - if none selected, show all)
  if (activeTopicFilters.value.size > 0) {
    filtered = filtered.filter(e => {
      if (!e.project_type) return false;
      return activeTopicFilters.value.has(e.project_type);
    });
  }

  // Search filter
  if (searchQuery.value?.trim()) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(e =>
      e.title?.toLowerCase().includes(query) ||
      e.jurisdiction?.name?.toLowerCase().includes(query) ||
      e.description?.toLowerCase().includes(query)
    );
  }

  // Sort by date (upcoming first, then past in reverse chronological order)
  const now = new Date();
  return filtered.sort((a, b) => {
    const dateA = new Date(a.when);
    const dateB = new Date(b.when);
    const aIsUpcoming = dateA >= now;
    const bIsUpcoming = dateB >= now;

    // Upcoming events first, sorted chronologically
    if (aIsUpcoming && !bIsUpcoming) return -1;
    if (!aIsUpcoming && bIsUpcoming) return 1;

    // Within same category, sort by date
    if (aIsUpcoming) {
      return dateA.getTime() - dateB.getTime(); // Upcoming: earliest first
    } else {
      return dateB.getTime() - dateA.getTime(); // Past: most recent first
    }
  });
});

/**
 * Load events from API
 */
async function loadEvents() {
  loading.value = true;
  error.value = null;

  try {
    allEvents.value = await api.getEvents();
    console.log('[EventsPanel] Loaded events:', allEvents.value.length);

    // Load discussion stats for all events
    if (allEvents.value.length > 0) {
      await loadDiscussionStats(allEvents.value.map(e => e.id));
    }
  } catch (err: any) {
    console.error('[EventsPanel] Failed to load events:', err);
    error.value = err.message || 'Failed to load events';
  } finally {
    loading.value = false;
  }
}

/**
 * Load user follows to determine which events they're following
 */
async function loadFollows() {
  try {
    const response = await api.getUserFollows(userStore.userId);

    // Extract event IDs from follows
    const eventFollows = response.follows.filter(f => f.focal_type === 'event');
    followedEventIds.value = new Set(eventFollows.map(f => f.focal_id));

    console.log('[EventsPanel] Loaded follows:', {
      total: response.metadata.total_follows,
      events: response.metadata.event_follows,
      followedIds: Array.from(followedEventIds.value)
    });
  } catch (err: any) {
    console.error('[EventsPanel] Error loading follows:', err);
    // Don't show error to user - follows are optional
  }
}

/**
 * Load discussion stats for events
 */
async function loadDiscussionStats(eventIds: string[]) {
  try {
    const response = await api.getEventDiscussionStats(eventIds);

    // Build map of event_id -> stats
    const statsMap = new Map();
    response.stats.forEach(stat => {
      statsMap.set(stat.event_id, {
        discussion_count: stat.message_count, // API returns message_count, we rename to discussion_count for clarity
        participant_count: stat.participant_count
      });
    });

    discussionStats.value = statsMap;
    console.log('[EventsPanel] Loaded discussion stats:', discussionStats.value.size);
  } catch (err: any) {
    console.error('[EventsPanel] Error loading discussion stats:', err);
    // Don't show error - discussion stats are optional
  }
}

/**
 * Toggle date filter (Past/Upcoming)
 */
function toggleDateFilter(filter: 'past' | 'upcoming') {
  if (activeDateFilters.value.has(filter)) {
    // Prevent deselecting both - keep at least one selected
    if (activeDateFilters.value.size > 1) {
      activeDateFilters.value.delete(filter);
    }
  } else {
    activeDateFilters.value.add(filter);
  }
  // Trigger reactivity
  activeDateFilters.value = new Set(activeDateFilters.value);
}

/**
 * Toggle topic filter (multi-select)
 */
function toggleTopicFilter(topic: ProjectType) {
  if (activeTopicFilters.value.has(topic)) {
    activeTopicFilters.value.delete(topic);
  } else {
    activeTopicFilters.value.add(topic);
  }
  // Trigger reactivity
  activeTopicFilters.value = new Set(activeTopicFilters.value);
}

/**
 * Handle topic filter hover - show chat hint after delay
 */
function handleTopicHoverStart(topic: ProjectType) {
  // Clear any existing timeout
  if (hoverTimeout.value !== null) {
    clearTimeout(hoverTimeout.value);
  }

  // Set new timeout to show hint after 1 second
  hoverTimeout.value = setTimeout(() => {
    showChatHintFor(topic);
    hoverTimeout.value = null;
  }, 1000) as unknown as number;
}

/**
 * Handle search input hover - show chat hint after delay
 */
function handleSearchHoverStart() {
  // Clear any existing timeout
  if (hoverTimeout.value !== null) {
    clearTimeout(hoverTimeout.value);
  }

  // Set new timeout to show hint after 1 second
  hoverTimeout.value = setTimeout(() => {
    showChatHintForSearch();
    hoverTimeout.value = null;
  }, 1000) as unknown as number;
}

/**
 * Handle hover end - cancel pending hint (universal)
 */
function handleHoverEnd() {
  if (hoverTimeout.value !== null) {
    clearTimeout(hoverTimeout.value);
    hoverTimeout.value = null;
  }
}

/**
 * Show chat hint toast for topic filters (training wheels for chat adoption)
 */
function showChatHintFor(topic: ProjectType) {
  // Don't show if user has permanently dismissed hints
  if (chatHintsDismissed.value) return;

  const topicLabel = topTopics.find(t => t.value === topic)?.label.toLowerCase() || topic;
  chatHintTopic.value = topicLabel;
  chatHintType.value = 'topic';
  showChatHint.value = true;

  // Auto-hide after 5 seconds
  setTimeout(() => {
    showChatHint.value = false;
  }, 5000);
}

/**
 * Show chat hint toast for search input (training wheels for chat adoption)
 */
function showChatHintForSearch() {
  // Don't show if user has permanently dismissed hints
  if (chatHintsDismissed.value) return;

  // Pick a random example from the pool
  const randomExample = searchExamples[Math.floor(Math.random() * searchExamples.length)];
  chatHintTopic.value = randomExample;
  chatHintType.value = 'search';
  showChatHint.value = true;

  // Auto-hide after 5 seconds
  setTimeout(() => {
    showChatHint.value = false;
  }, 5000);
}

/**
 * Permanently dismiss chat hints (save to localStorage)
 */
function dismissChatHintsPermanently() {
  chatHintsDismissed.value = true;
  showChatHint.value = false;
  localStorage.setItem('civic-hide-chat-hints', 'true');
  console.log('[EventsPanel] Chat hints permanently dismissed');
}

/**
 * Handle chat hint click - focus chat input and pre-fill query
 */
function handleChatHintClick() {
  // Find chat input (ChatPanel uses .message-input or .welcome-message-input)
  const chatInput = document.querySelector('.message-input, .welcome-message-input') as HTMLTextAreaElement;

  if (chatInput) {
    let query = '';

    // Generate query based on hint type
    if (chatHintType.value === 'topic') {
      query = `show ${chatHintTopic.value} meetings`;
    } else if (chatHintType.value === 'search') {
      query = `search for ${chatHintTopic.value}`;
    }

    // Set the value
    chatInput.value = query;

    // Focus the input
    chatInput.focus();

    // Scroll chat into view if needed
    chatInput.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Trigger input event for Vue's v-model reactivity
    const inputEvent = new Event('input', { bubbles: true, cancelable: true });
    chatInput.dispatchEvent(inputEvent);

    // Also trigger a focus event to ensure textarea is active
    chatInput.dispatchEvent(new Event('focus', { bubbles: true }));

    console.log('[EventsPanel] Pre-filled chat with:', query);
  } else {
    console.warn('[EventsPanel] Could not find chat input element');
  }

  // Hide toast
  showChatHint.value = false;
}

/**
 * Open event as artifact (tab)
 */
function openEvent(event: CivicEvent) {
  // Track event view for progressive disclosure
  userStore.incrementEventsViewed();

  workspaceStore.openArtifact({
    id: event.id,
    type: 'event',
    title: event.title,
    data: event
  });
}

/**
 * Format date for display
 */
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  const isPast = date < now;

  // Upcoming events: "In X days" or "Tomorrow" or "Today"
  if (!isPast) {
    const daysUntil = Math.ceil(-diffDays);
    if (daysUntil === 0) return 'Today';
    if (daysUntil === 1) return 'Tomorrow';
    return `In ${daysUntil} days`;
  }

  // Past events: "X days ago" or "Yesterday" or relative
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;

  // Older: show formatted date
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Get discussion count for an event
 */
function getDiscussionCount(eventId: string): number {
  return discussionStats.value.get(eventId)?.discussion_count || 0;
}

onMounted(async () => {
  // Load chat hints dismissal preference from localStorage
  const dismissed = localStorage.getItem('civic-hide-chat-hints');
  chatHintsDismissed.value = dismissed === 'true';

  await Promise.all([
    loadEvents(),
    loadFollows()
  ]);
});

// Session 77: Update active query result count when filtered events change
watch(filteredEvents, (newEvents) => {
  if (workspaceStore.eventsViewMode === 'query_results' && workspaceStore.activeQuery) {
    workspaceStore.setActiveQuery({
      ...workspaceStore.activeQuery,
      resultCount: newEvents.length
    })
  }
});

// Cleanup hover timeout on unmount
onBeforeUnmount(() => {
  if (hoverTimeout.value !== null) {
    clearTimeout(hoverTimeout.value);
  }
});

/**
 * Apply filters programmatically (for AI assistant to use same logic as user)
 * This ensures the AI interacts with filters exactly as a user would.
 */
function applyFilters(filters: {
  topic?: ProjectType
  dateRange?: 'past' | 'upcoming' | 'all'
  searchQuery?: string
  jurisdiction?: string  // jurisdiction_id to filter by (or 'all' for no filter)
  replace?: boolean      // NEW: If true, clear existing filters before applying (default: true for independent queries)
}) {
  const shouldReplace = filters.replace !== false  // Default to true if not specified

  // Apply search query
  if (filters.searchQuery !== undefined) {
    searchQuery.value = filters.searchQuery ?? ''
  }

  // Apply jurisdiction filter
  if (filters.jurisdiction !== undefined) {
    if (filters.jurisdiction === 'all') {
      // Clear jurisdiction selection to show all
      workspaceStore.selectJurisdiction(null)
    } else {
      // Find jurisdiction from events (since each event has a jurisdiction object)
      const eventWithJurisdiction = allEvents.value.find(
        e => e.jurisdiction?.id === filters.jurisdiction
      )
      if (eventWithJurisdiction?.jurisdiction) {
        workspaceStore.selectJurisdiction(eventWithJurisdiction.jurisdiction)
      }
    }
  }

  // Apply topic filter
  if (filters.topic) {
    // Clear existing topic filters for independent queries (replace mode)
    // Keep existing filters for multi-operation queries (accumulate mode)
    if (shouldReplace) {
      activeTopicFilters.value.clear()
    }

    // Add the new topic
    if (!activeTopicFilters.value.has(filters.topic)) {
      toggleTopicFilter(filters.topic)
    }
  }

  // Apply date range
  if (filters.dateRange) {
    if (filters.dateRange === 'past') {
      activeDateFilters.value = new Set(['past'])
    } else if (filters.dateRange === 'upcoming') {
      activeDateFilters.value = new Set(['upcoming'])
    } else {
      activeDateFilters.value = new Set(['past', 'upcoming'])
    }
  }

  console.log('[EventsPanel] Applied programmatic filters:', {
    searchQuery: searchQuery.value,
    topics: Array.from(activeTopicFilters.value),
    dateFilters: Array.from(activeDateFilters.value),
    jurisdiction: filters.jurisdiction,
    mode: shouldReplace ? 'replace' : 'accumulate'
  })
}

/**
 * Clear all filters (return to default view)
 */
function clearAllFilters() {
  searchQuery.value = ''
  activeTopicFilters.value = new Set()
  activeDateFilters.value = new Set(['past', 'upcoming'])
  activeOwnershipFilter.value = 'all'
}

/**
 * Clear active query (Session 77)
 */
function clearQuery() {
  workspaceStore.clearActiveQuery()
  clearAllFilters()
}

// Expose methods so parent/ChatPanel can interact with the panel
defineExpose({
  loadEvents,
  loadFollows,
  applyFilters,
  clearAllFilters,
  clearQuery
});
</script>

<template>
  <div class="events-panel">
    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>Loading events...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button @click="loadEvents" class="retry-button">Try Again</button>
    </div>

    <!-- Content -->
    <div v-else class="panel-content">
      <!-- Session 77: Query Results Banner -->
      <div v-if="workspaceStore.eventsViewMode === 'query_results' && workspaceStore.activeQuery" class="query-results-banner">
        <div class="query-info">
          <Search :size="14" class="query-icon" />
          <div class="query-text">
            <div class="query-title">Query Results</div>
            <div class="query-description">{{ workspaceStore.activeQuery.rawQuery }}</div>
            <div class="query-operations">
              {{ workspaceStore.activeQuery.operations.length }} operation(s) •
              {{ workspaceStore.activeQuery.resultCount }} event(s)
            </div>
          </div>
        </div>
        <button @click="clearQuery" class="clear-query-btn" title="Clear query and return to filters">
          <XCircle :size="16" />
        </button>
      </div>

      <!-- Search Bar -->
      <div
        class="search-bar"
        @mouseenter="handleSearchHoverStart"
        @mouseleave="handleHoverEnd"
      >
        <Search :size="14" class="search-icon" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search events..."
          class="search-input"
        />
        <button
          v-if="searchQuery"
          @click="searchQuery = ''"
          class="clear-btn"
          title="Clear search"
        >
          <X :size="14" />
        </button>
      </div>

      <!-- Combined Ownership + Date Filter -->
      <div class="filter-bar combined-filter">
        <!-- 'All' filter -->
        <button
          class="filter-btn"
          :class="{ active: activeOwnershipFilter === 'all' }"
          @click="activeOwnershipFilter = 'all'"
        >
          All
          <span class="filter-count">{{ ownershipFilters.find(f => f.value === 'all')?.count }}</span>
        </button>

        <!-- Visual divider after 'All' -->
        <div class="filter-divider"></div>

        <!-- Following filter -->
        <button
          class="filter-btn"
          :class="{ active: activeOwnershipFilter === 'following' }"
          @click="activeOwnershipFilter = 'following'"
        >
          Following
          <span class="filter-count">{{ ownershipFilters.find(f => f.value === 'following')?.count }}</span>
        </button>

        <!-- Visual divider before date filters -->
        <div class="filter-divider"></div>

        <!-- Date filters (toggleable) -->
        <button
          v-for="filter in dateFilters"
          :key="filter.value"
          class="filter-btn"
          :class="{ active: activeDateFilters.has(filter.value) }"
          @click="toggleDateFilter(filter.value)"
        >
          {{ filter.label }}
          <span class="filter-count">{{ filter.count }}</span>
        </button>
      </div>

      <!-- Topic Filter Row (NEW - training wheels for chat) -->
      <div class="filter-bar topic-filter">
        <button
          v-for="topic in topicFilters"
          :key="topic.value"
          class="filter-btn topic-btn"
          :class="{
            active: activeTopicFilters.has(topic.value),
            highlighted: isFilterHighlighted('events', topic.value)
          }"
          @click="toggleTopicFilter(topic.value)"
          @mouseenter="handleTopicHoverStart(topic.value)"
          @mouseleave="handleHoverEnd"
          :title="`Filter by ${topic.label} meetings`"
        >
          <component :is="topic.icon" :size="14" class="topic-icon" :style="{ color: topic.color }" />
          {{ topic.label }}
          <span class="filter-count">{{ topic.count }}</span>
        </button>
      </div>

      <!-- Chat Hint Toast (shows when user hovers topic filter or search) -->
      <transition name="slide-down">
        <div
          v-if="showChatHint"
          class="chat-hint-toast"
        >
          <div class="hint-main" @click="handleChatHintClick" title="Click to try it in chat">
            <Lightbulb :size="16" class="hint-icon" />
            <span class="hint-text" v-if="chatHintType === 'topic'">
              Try typing "<strong>show {{ chatHintTopic }} meetings</strong>" in chat
            </span>
            <span class="hint-text" v-else-if="chatHintType === 'search'">
              Try asking in chat: "<strong>search for {{ chatHintTopic }}</strong>"
            </span>
            <button
              @click.stop="showChatHint = false"
              class="hint-close"
              title="Dismiss"
            >
              <X :size="12" />
            </button>
          </div>
          <div class="hint-footer">
            <button
              @click.stop="dismissChatHintsPermanently"
              class="hint-dismiss-forever"
              title="Don't show these hints again"
            >
              Don't show again
            </button>
          </div>
        </div>
      </transition>

      <!-- Events List -->
      <div class="section">
        <h4
          class="section-title"
          :class="{ 'pulsing': isSectionPulsing('events') }"
        >
          All Events
        </h4>
        <div v-if="filteredEvents.length === 0" class="empty-state">
          <p>No events found. Try adjusting your filters or check back later.</p>
        </div>
        <div v-else class="event-list">
          <button
            v-for="event in filteredEvents"
            :key="event.id"
            @click="openEvent(event)"
            class="event-item"
          >
            <Calendar :size="16" class="event-icon" />
            <div class="event-info">
              <!-- Title row -->
              <div class="event-title-row">
                <div class="event-title">{{ event.title }}</div>
              </div>

              <!-- Jurisdiction (monospace, secondary) -->
              <div class="event-jurisdiction">{{ event.jurisdiction?.name || 'Unknown' }}</div>

              <!-- Stats row -->
              <div class="event-stats">
                <span>{{ formatDate(event.when) }}</span>
                <span class="stat-separator">•</span>
                <span>{{ event.agenda_expansion?.actionable_items?.length || 0 }} items</span>
                <template v-if="getDiscussionCount(event.id) > 0">
                  <span class="stat-separator">•</span>
                  <span>{{ getDiscussionCount(event.id) }} discussing</span>
                </template>
              </div>
            </div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.events-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--background);
  padding: 0; /* Flush with sidebar edges */
  flex: 1; /* Use available space */
}

/* Loading & Error States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-xl) var(--spacing-xl) var(--space-md); /* Match left margin */
  text-align: center;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: var(--spacing-md);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-button {
  margin-top: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--border-radius);
  cursor: pointer;
  font-weight: 500;
  transition: background 0.2s;
}

.retry-button:hover {
  background: var(--primary-hover);
}

/* Panel Content */
.panel-content {
  padding-left: var(--space-md); /* Left margin for breathing room */
}

/* Session 77: Query Results Banner */
.query-results-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px var(--space-md) 12px 0; /* Right padding, left handled by parent */
  background: linear-gradient(135deg, #fdf6e3 0%, #eee8d5 100%); /* Solarized warm gradient */
  border-bottom: 2px solid var(--accent-orange);
  margin-bottom: 8px;
}

.query-info {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.query-icon {
  color: var(--accent-orange);
  flex-shrink: 0;
  margin-top: 2px;
}

.query-text {
  flex: 1;
  min-width: 0;
}

.query-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.query-description {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 4px;
  word-wrap: break-word;
}

.query-operations {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
}

.clear-query-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  border: none;
  background: rgba(203, 75, 22, 0.1);
  color: var(--accent-orange);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.clear-query-btn:hover {
  background: var(--accent-orange);
  color: white;
  transform: scale(1.05);
}

/* Search Bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px var(--space-md) 8px 0; /* Right padding, left handled by parent */
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  margin-bottom: 8px;
}

.search-icon {
  color: var(--text-secondary);
  opacity: 0.6;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  padding: 0;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--text-secondary);
  opacity: 0.6;
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 3px;
  transition: background 0.12s ease;
  flex-shrink: 0;
}

.clear-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-primary);
}

/* Filter Bar */
.filter-bar {
  display: flex;
  gap: 4px;
  padding: 8px var(--space-md) 8px 0; /* Right padding, left handled by parent */
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
  margin-bottom: 8px;
}

.combined-filter {
  padding-top: 6px;
  padding-bottom: 8px;
  align-items: center;
}

.filter-divider {
  width: 1px;
  height: 16px;
  background: var(--border);
  margin: 0 8px;
  flex-shrink: 0;
}

.filter-btn {
  padding: 4px 8px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 4px;
}

.filter-btn:hover {
  background: rgba(0, 0, 0, 0.04);
  color: var(--text-primary);
}

.filter-btn.active {
  background: var(--primary);
  color: white;
  font-weight: 600;
}

/* Session 59: Filter highlight animation for "AI uses same UI" teaching moment */
.filter-btn.highlighted {
  animation: filter-highlight 800ms ease-out;
}

@keyframes filter-highlight {
  0% {
    background-color: var(--primary);
    border-color: var(--primary);
    transform: scale(1.05);
  }
  100% {
    background-color: initial;
    border-color: initial;
    transform: scale(1);
  }
}

.filter-count {
  padding: 2px 4px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.2);
  font-size: 10px;
  font-weight: 600;
}

.filter-btn.active .filter-count {
  background: rgba(255, 255, 255, 0.3);
}

/* Topic Filter Row */
.topic-filter {
  padding-top: 6px;
  padding-bottom: 6px;
  flex-wrap: wrap;
}

.topic-btn {
  display: flex;
  align-items: center;
  gap: 4px;
}

.topic-icon {
  flex-shrink: 0;
  opacity: 0.7;
  transition: opacity 0.12s ease;
}

.topic-btn:hover .topic-icon {
  opacity: 1;
}

.topic-btn.active .topic-icon {
  opacity: 1;
  filter: brightness(1.2);
}

/* Chat Hint Toast (training wheels for chat adoption) */
.chat-hint-toast {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  margin: 0 var(--space-md) 8px 0; /* Right margin, left handled by parent */
  margin-left: var(--space-md);
  background: #fdf6e3; /* Solarized base3 - warm light background */
  border: 1.5px solid var(--accent-orange);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.4;
  box-shadow: 0 2px 8px rgba(203, 75, 22, 0.15); /* Orange shadow */
  transition: all 0.2s ease;
  text-align: left;
  width: calc(100% - var(--space-md) * 2);
}

.hint-main {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex: 1;
}

.hint-main:hover {
  opacity: 0.9;
}

.chat-hint-toast:hover {
  background: #fff8e8; /* Slightly warmer on hover */
  border-color: var(--accent-orange);
  box-shadow: 0 4px 12px rgba(203, 75, 22, 0.25);
  transform: translateY(-1px);
}

.hint-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
  border-top: 1px solid rgba(203, 75, 22, 0.15);
}

.hint-icon {
  color: var(--accent-orange);
  flex-shrink: 0;
  opacity: 0.9;
}

.hint-text {
  flex: 1;
  color: var(--text-primary);
}

.hint-text strong {
  font-weight: 600;
  color: var(--accent-orange);
  background: rgba(203, 75, 22, 0.08);
  padding: 1px 4px;
  border-radius: 3px;
}

.hint-close {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.12s ease;
  flex-shrink: 0;
  opacity: 0.7;
}

.hint-close:hover {
  background: rgba(203, 75, 22, 0.12);
  color: var(--accent-orange);
  opacity: 1;
}

.hint-dismiss-forever {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px 6px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.12s ease;
  font-size: 11px;
  font-weight: 500;
  opacity: 0.7;
}

.hint-dismiss-forever:hover {
  background: rgba(203, 75, 22, 0.1);
  color: var(--accent-orange);
  opacity: 1;
}

/* Slide-down animation for toast */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from {
  transform: translateY(-10px);
  opacity: 0;
}

.slide-down-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

.section {
  padding: 8px var(--space-md) 8px 0; /* Right padding only, left handled by parent */
  border: none;
  background: transparent;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 8px 0;
  opacity: 0.8;
}

/* Session 59: Pulse animation for "AI uses same UI" teaching moment */
.section-title.pulsing {
  animation: pulse 600ms cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 var(--primary);
  }
  50% {
    transform: scale(1.02);
    box-shadow: 0 0 0 4px rgba(38, 139, 210, 0.3);
  }
}

.empty-state {
  padding: var(--spacing-lg) var(--spacing-lg) var(--spacing-lg) 0; /* Right padding, left handled by parent */
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

/* Event List - VSCode Minimal Style */
.event-list {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tighter gaps like VSCode */
}

.event-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px var(--space-md) 6px 0; /* Right padding, left handled by parent */
  background: transparent;
  border: none;
  border-radius: 0; /* No radius - flush edges */
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
  width: 100%;
}

.event-item:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover */
}

.event-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.event-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px; /* Tighter */
}

.event-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.event-title {
  font-size: 14px; /* Improved readability */
  font-weight: 500; /* Less bold */
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.event-jurisdiction {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
  margin-bottom: 2px;
}

.event-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
  opacity: 0.8;
}

.stat-separator {
  margin: 0 2px;
  opacity: 0.5;
}

/* Scrollbar Styling */
.panel-content::-webkit-scrollbar {
  width: 6px;
}

.panel-content::-webkit-scrollbar-track {
  background: var(--background);
}

.panel-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.panel-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

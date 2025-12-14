<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { MessageCircle, Calendar, AlertCircle, Search, X } from 'lucide-vue-next';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import { ArtifactIds } from '@/utils/artifactIds';
import { api } from '@/services/api';

interface Thread {
  thread_id: string;
  focal_type: string;
  focal_id: string;
  focal_point_title: string;
  focal_point_display_title?: string; // Full title for display in sidebar
  participant_count: number;
  message_count: number;
  created_at: string;
  last_message_at: string | null;
}

const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();
const allThreads = ref<Thread[]>([]);
const followedFocalIds = ref<Set<string>>(new Set()); // Focal IDs (issues/events) user is following
const loading = ref(true);
const error = ref<string | null>(null);
const searchQuery = ref('');
const activeOwnershipFilter = ref<'hot' | 'all' | 'mine' | 'following'>('hot'); // Default to 'hot'
const activeFocalTypeFilters = ref<Set<'issue' | 'event'>>(new Set(['issue', 'event'])); // Default to both selected (show all)

/**
 * Ownership filters with counts
 */
const ownershipFilters = computed(() => {
  const now = new Date();
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);

  // Count hot threads (activity in last 24 hours)
  const hotCount = allThreads.value.filter(t => {
    if (!t.last_message_at) return false;
    const lastActive = new Date(t.last_message_at);
    return lastActive >= oneDayAgo;
  }).length;

  // Get count of threads user is following (focal points they follow)
  const followingCount = allThreads.value.filter(t => followedFocalIds.value.has(t.focal_id)).length;

  // TODO: Implement "Mine" - threads where user has posted messages
  // For now, "Mine" shows threads user is participating in (has follow record)
  const mineCount = followingCount; // Placeholder - same as following for now

  return [
    { value: 'all' as const, label: 'All', count: allThreads.value.length },
    { value: 'hot' as const, label: 'Hot', count: hotCount },
    { value: 'mine' as const, label: 'Mine', count: mineCount },
    { value: 'following' as const, label: 'Following', count: followingCount }
  ];
});

/**
 * Get ownership-filtered threads for focal type counts
 */
const ownershipFilteredThreads = computed(() => {
  if (activeOwnershipFilter.value === 'hot') {
    const now = new Date();
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    return allThreads.value.filter(t => {
      if (!t.last_message_at) return false;
      const lastActive = new Date(t.last_message_at);
      return lastActive >= oneDayAgo;
    });
  }
  if (activeOwnershipFilter.value === 'mine' || activeOwnershipFilter.value === 'following') {
    // For now, both "mine" and "following" show threads where user follows the focal point
    return allThreads.value.filter(t => followedFocalIds.value.has(t.focal_id));
  }
  return allThreads.value;
});

/**
 * Focal type filters with counts (toggleable)
 */
const focalTypeFilters = computed(() => {
  return [
    { value: 'issue' as const, label: 'Issues', count: ownershipFilteredThreads.value.filter(t => t.focal_type === 'issue').length },
    { value: 'event' as const, label: 'Events', count: ownershipFilteredThreads.value.filter(t => t.focal_type === 'event').length }
  ];
});

/**
 * Filtered threads based on ownership, focal type, and search query
 */
const activeThreads = computed(() => {
  let filtered = allThreads.value;

  // Apply ownership filter
  if (activeOwnershipFilter.value === 'hot') {
    // Filter to threads with activity in last 24 hours
    const now = new Date();
    const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    filtered = filtered.filter(t => {
      if (!t.last_message_at) return false;
      const lastActive = new Date(t.last_message_at);
      return lastActive >= oneDayAgo;
    });
    // Sort by message count (most active first)
    filtered = filtered.sort((a, b) => b.message_count - a.message_count);
  } else if (activeOwnershipFilter.value === 'mine' || activeOwnershipFilter.value === 'following') {
    // Filter to threads where user follows the focal point
    filtered = filtered.filter(t => followedFocalIds.value.has(t.focal_id));
  }

  // Apply focal type filter (toggleable - if none selected, show all)
  if (activeFocalTypeFilters.value.size > 0 && activeFocalTypeFilters.value.size < 2) {
    filtered = filtered.filter(t => activeFocalTypeFilters.value.has(t.focal_type as 'issue' | 'event'));
  }
  // If both selected or none selected, show all focal types

  // Apply search filter
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(t => {
      // Search in: focal_point_title, focal_point_display_title
      return (
        t.focal_point_title?.toLowerCase().includes(query) ||
        t.focal_point_display_title?.toLowerCase().includes(query)
      );
    });
  }

  return filtered;
});

/**
 * Load active discussion threads
 */
async function loadThreads() {
  loading.value = true;
  error.value = null;

  try {
    const data = await api.getThreads({ limit: 20 });
    allThreads.value = data.threads;

    // For issue threads, fetch full title (ai_title) for display
    // focal_point_title is now short_name (e.g., "EVICTION-9")
    // We want to show ai_title in sidebar but use short_name for tab
    await enrichThreadsWithFullTitles(allThreads.value);
  } catch (err: any) {
    console.error('Failed to load threads:', err);
    error.value = err.message || 'Failed to load discussions';
  } finally {
    loading.value = false;
  }
}

/**
 * Enrich issue threads with full ai_title for sidebar display
 */
async function enrichThreadsWithFullTitles(threads: Thread[]) {
  const issueThreads = threads.filter(t => t.focal_type === 'issue');

  // Fetch full issue data for each issue thread
  const enrichPromises = issueThreads.map(async (thread) => {
    try {
      const issue = await api.getIssue(thread.focal_id);
      // Set display title to ai_title (full title), keep focal_point_title as short_name for tab
      thread.focal_point_display_title = issue.ai_title || issue.description?.substring(0, 80) + '...';
    } catch (err: any) {
      // Silently fallback to short_name if issue not found (404) or other error
      if (err?.message?.includes('not found')) {
        console.warn(`Issue ${thread.focal_id} not found, using short_name`);
      } else {
        console.error(`Failed to enrich thread ${thread.thread_id}:`, err);
      }
      // Fallback to short_name if enrichment fails
      thread.focal_point_display_title = thread.focal_point_title;
    }
  });

  await Promise.all(enrichPromises);
}

/**
 * Open thread in workspace
 * For issue threads, open the issue artifact directly (consolidated IssueArtifact with discussion tab)
 * For event threads, open as thread artifact
 */
async function openThread(thread: Thread) {
  try {
    if (thread.focal_type === 'issue') {
      // Fetch full issue data and open as issue artifact with discussion tab active
      const issue = await api.getIssue(thread.focal_id);
      workspaceStore.openArtifact({
        type: 'issue',
        id: ArtifactIds.issue(thread.focal_id), // Centralized ID generation (Session 53.5)
        title: thread.focal_point_title, // Use short_name for tab
        data: issue,
        initialTab: 'discussion' // Open directly to discussion tab
      });
    } else {
      // For event threads, open as thread artifact
      workspaceStore.openArtifact({
        type: 'thread',
        id: ArtifactIds.thread(thread.thread_id), // Centralized ID generation (Session 53.5)
        title: thread.focal_point_title,
        data: thread
      });
    }
  } catch (err: any) {
    console.error('Failed to open thread:', err);
    alert(`Failed to open discussion: ${err.message}`);
  }
}

/**
 * Get icon for focal point type
 * Calendar for event threads, AlertCircle for issue threads
 */
function getFocalIcon(focalType: string) {
  return focalType === 'event' ? Calendar : AlertCircle;
}

/**
 * Load user follows to determine which threads they're following
 */
async function loadFollows() {
  try {
    const response = await api.getUserFollows(userStore.userId);

    // Extract focal IDs from all follows (issues + events)
    followedFocalIds.value = new Set(response.follows.map(f => f.focal_id));

    console.log('[DiscussionsPanel] Loaded follows:', {
      total: response.metadata.total_follows,
      issues: response.metadata.issue_follows,
      events: response.metadata.event_follows,
      followedIds: Array.from(followedFocalIds.value)
    });
  } catch (err: any) {
    console.error('[DiscussionsPanel] Error loading follows:', err);
    // Don't show error to user - follows are optional, just log it
  }
}

/**
 * Toggle focal type filter (Issues/Events)
 */
function toggleFocalTypeFilter(focalType: 'issue' | 'event') {
  if (activeFocalTypeFilters.value.has(focalType)) {
    // Prevent deselecting both - keep at least one selected
    if (activeFocalTypeFilters.value.size > 1) {
      activeFocalTypeFilters.value.delete(focalType);
    }
  } else {
    activeFocalTypeFilters.value.add(focalType);
  }
  // Trigger reactivity
  activeFocalTypeFilters.value = new Set(activeFocalTypeFilters.value);
}

onMounted(async () => {
  await Promise.all([
    loadThreads(),
    loadFollows()
  ]);
});

// Expose methods so parent can refresh the panel
defineExpose({
  loadThreads,
  loadFollows
});
</script>

<template>
  <div class="discussions-panel">
    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>Loading discussions...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <p>{{ error }}</p>
      <button @click="loadThreads" class="retry-button">Try Again</button>
    </div>

    <!-- Content -->
    <div v-else class="panel-content">
      <!-- Search Bar -->
      <div class="search-bar">
        <Search :size="14" class="search-icon" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search discussions..."
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

      <!-- Combined Ownership + Focal Type Filter -->
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

        <!-- Other ownership filters (Hot, Mine, Following) -->
        <button
          v-for="filter in ownershipFilters.filter(f => f.value !== 'all')"
          :key="filter.value"
          class="filter-btn"
          :class="{ active: activeOwnershipFilter === filter.value }"
          @click="activeOwnershipFilter = filter.value"
        >
          {{ filter.label }}
          <span class="filter-count">{{ filter.count }}</span>
        </button>

        <!-- Visual divider before focal type filters -->
        <div class="filter-divider"></div>

        <!-- Focal type filters (toggleable) -->
        <button
          v-for="filter in focalTypeFilters"
          :key="filter.value"
          class="filter-btn"
          :class="{ active: activeFocalTypeFilters.has(filter.value) }"
          @click="toggleFocalTypeFilter(filter.value)"
        >
          {{ filter.label }}
          <span class="filter-count">{{ filter.count }}</span>
        </button>
      </div>

      <!-- All Discussions -->
      <div class="section">
        <h4 class="section-title">All Discussions</h4>
        <div v-if="activeThreads.length === 0" class="empty-state">
          <p>No discussions yet. Start a conversation by commenting on an event or issue!</p>
        </div>
        <div v-else class="thread-list">
          <button
            v-for="thread in activeThreads"
            :key="thread.thread_id"
            @click="openThread(thread)"
            class="thread-item"
          >
            <component :is="getFocalIcon(thread.focal_type)" :size="16" class="thread-icon" />
            <div class="thread-info">
              <div class="thread-title-row">
                <div class="thread-title">{{ thread.focal_point_display_title || thread.focal_point_title }}</div>
                <!-- Unread badge (placeholder for future enhancement) -->
                <div v-if="false" class="unread-badge"></div>
              </div>
              <!-- Show short_name as secondary text for issue threads -->
              <div v-if="thread.focal_type === 'issue' && thread.focal_point_display_title" class="thread-short-name">
                {{ thread.focal_point_title }}
              </div>
              <!-- Participant avatars (placeholder for future enhancement) -->
              <!-- <div class="participant-avatars">
                <img v-for="userId in participantIds.slice(0, 3)" :key="userId" :src="getAvatarUrl(userId)" class="avatar-small" />
                <span v-if="thread.participant_count > 3" class="more-count">+{{ thread.participant_count - 3 }}</span>
              </div> -->
              <div class="thread-stats">
                <MessageCircle :size="11" />
                {{ thread.message_count }} {{ thread.message_count === 1 ? 'message' : 'messages' }}
                <span class="stat-separator">•</span>
                {{ thread.participant_count }} {{ thread.participant_count === 1 ? 'person' : 'people' }}
              </div>
              <!-- Last message preview (placeholder for future enhancement) -->
              <!-- <div v-if="thread.last_message_preview" class="last-message">{{ thread.last_message_preview }}</div> -->
            </div>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.discussions-panel {
  display: flex;
  flex-direction: column;
  background: var(--background);
  padding: 0; /* Flush with sidebar edges */
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

.empty-state {
  padding: var(--spacing-lg) var(--spacing-lg) var(--spacing-lg) 0; /* Right padding, left handled by parent */
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

/* Thread List - VSCode Minimal Style */
.thread-list {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tighter gaps like VSCode */
}

.thread-item {
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

.thread-item:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover */
}

.thread-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.thread-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px; /* Tighter */
}

.thread-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.thread-title {
  font-size: 14px; /* Improved readability */
  font-weight: 500; /* Less bold */
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.unread-badge {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  flex-shrink: 0;
}

.thread-short-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
  margin-bottom: 2px;
}

.thread-stats {
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

/* Participant avatars (for future use) */
.participant-avatars {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.avatar-small {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--background);
  margin-left: -8px;
  object-fit: cover;
}

.avatar-small:first-child {
  margin-left: 0;
}

.more-count {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  font-weight: 500;
  margin-left: 4px;
}

.last-message {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-style: italic;
  margin-top: 2px;
}
</style>

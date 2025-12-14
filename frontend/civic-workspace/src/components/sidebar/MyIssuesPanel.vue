<template>
  <div class="my-issues-panel">
    <!-- Search Bar -->
    <div class="search-bar">
      <Search :size="14" class="search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Search issues..."
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

    <!-- Active Filters Display + Clear Button -->
    <div v-if="hasActiveFilters" class="active-filters-bar">
      <div class="active-filters">
        <span v-if="activeCategoryFilter" class="filter-chip">
          {{ activeCategoryFilter }}
          <button @click="activeCategoryFilter = null" class="chip-remove">×</button>
        </span>
        <span v-if="activeJurisdictionFilter" class="filter-chip">
          {{ getJurisdictionDisplayName(activeJurisdictionFilter) }}
          <button @click="activeJurisdictionFilter = null" class="chip-remove">×</button>
        </span>
      </div>
      <button @click="clearAllFilters" class="clear-all-btn" title="Clear all filters">
        Clear All
      </button>
    </div>

    <!-- Combined Ownership + Status Filter -->
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

      <!-- Other ownership filters (Mine, Following) -->
      <button
        v-for="filter in ownershipFilters.filter(f => f.value !== 'all')"
        :key="filter.value"
        class="filter-btn"
        :class="{ active: activeOwnershipFilter === filter.value }"
        @click="activeOwnershipFilter = filter.value"
      >
        {{ filter.label }}
        <span v-if="filter.count !== undefined" class="filter-count">
          {{ filter.count }}
        </span>
      </button>

      <!-- Visual divider before status filters -->
      <div class="filter-divider"></div>

      <!-- Status filters (toggleable) -->
      <button
        v-for="filter in statusFilters"
        :key="filter.value"
        class="filter-btn"
        :class="{ active: activeStatusFilters.has(filter.value) }"
        @click="toggleStatusFilter(filter.value)"
      >
        {{ filter.label }}
        <span v-if="filter.count !== undefined" class="filter-count">
          {{ filter.count }}
        </span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading your issues...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <AlertCircle :size="32" class="error-icon" />
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadIssues">
        Retry
      </button>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredComplaints.length === 0 && !isLoading" class="empty-state">
      <p v-if="activeOwnershipFilter === 'all'">
        No issues filed yet. Click "Report Issue" to get started.
      </p>
      <p v-else>
        No {{ activeOwnershipFilter }} issues found.
      </p>
    </div>

    <!-- Issues List (VSCode-minimal style) -->
    <div v-else class="issues-list">
      <button
        v-for="issue in filteredComplaints"
        :key="issue.id"
        class="issue-item"
        @click="openIssue(issue)"
      >
        <AlertCircle :size="16" class="issue-icon" />
        <div class="issue-info">
          <!-- Title (ai_title or description) -->
          <div class="issue-title-row">
            <div class="issue-title">
              {{ issue.ai_title || truncateText(issue.description, 60) }}
            </div>
          </div>

          <!-- Short name (monospace, secondary) -->
          <div v-if="issue.short_name" class="issue-short-name">
            {{ issue.short_name }}
          </div>

          <!-- Stats row -->
          <div class="issue-stats">
            <span class="status-indicator" :class="`status-${issue.status}`">
              {{ getStatusLabel(issue.status) }}
            </span>
            <span class="stat-separator">•</span>
            <span>{{ formatDate(issue.created_at) }}</span>
            <template v-if="issue.matched_events?.length">
              <span class="stat-separator">•</span>
              <span>{{ issue.matched_events.length }} {{ issue.matched_events.length === 1 ? 'meeting' : 'meetings' }}</span>
            </template>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { AlertCircle, Search, X } from 'lucide-vue-next';
import { api } from '@/services/api';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import { ArtifactIds } from '@/utils/artifactIds';
import type { Issue } from '@/types/civic';

const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();

// State
const allIssues = ref<Issue[]>([]);
const followedIssueIds = ref<Set<string>>(new Set()); // Issue IDs the user is following
const isLoading = ref(false);
const error = ref('');
const searchQuery = ref('');
const activeOwnershipFilter = ref<'all' | 'mine' | 'following'>('all'); // Default to 'all'
const activeStatusFilters = ref<Set<'open' | 'closed'>>(new Set(['open', 'closed'])); // Default to both selected (show all)
// Session 61: Chat navigation filters
const activeCategoryFilter = ref<string | null>(null);
const activeJurisdictionFilter = ref<string | null>(null);

// Ownership filters with counts
const ownershipFilters = computed(() => {
  // Get count of issues user is following
  const followingCount = allIssues.value.filter(i => followedIssueIds.value.has(i.id)).length;

  return [
    { value: 'all' as const, label: 'All', count: allIssues.value.length },
    { value: 'mine' as const, label: 'Mine', count: allIssues.value.filter(i => i.user_id === userStore.userId).length },
    { value: 'following' as const, label: 'Following', count: followingCount }
  ];
});

// Get ownership-filtered issues for status counts
const ownershipFilteredIssues = computed(() => {
  if (activeOwnershipFilter.value === 'mine') {
    return allIssues.value.filter(i => i.user_id === userStore.userId);
  } else if (activeOwnershipFilter.value === 'following') {
    // Filter to only issues user is following
    return allIssues.value.filter(i => followedIssueIds.value.has(i.id));
  }
  return allIssues.value;
});

// Status filters with counts (toggleable, no "All")
const statusFilters = computed(() => {
  return [
    { value: 'open' as const, label: 'Open', count: ownershipFilteredIssues.value.filter(i => i.status === 'open').length },
    { value: 'closed' as const, label: 'Closed', count: ownershipFilteredIssues.value.filter(i => i.status === 'closed').length }
  ];
});

// Check if any non-default filters are active (Session 62)
const hasActiveFilters = computed(() => {
  return activeCategoryFilter.value !== null || activeJurisdictionFilter.value !== null;
});

// Filtered issues based on ownership, status, category, jurisdiction, and search query
const filteredComplaints = computed(() => {
  let filtered = allIssues.value;

  // Apply ownership filter
  if (activeOwnershipFilter.value === 'mine') {
    filtered = filtered.filter(i => i.user_id === userStore.userId);
  } else if (activeOwnershipFilter.value === 'following') {
    // Filter to only issues user is following
    filtered = filtered.filter(i => followedIssueIds.value.has(i.id));
  }

  // Apply status filter (toggleable - if none selected, show all)
  if (activeStatusFilters.value.size > 0 && activeStatusFilters.value.size < 2) {
    filtered = filtered.filter(i => activeStatusFilters.value.has(i.status as 'open' | 'closed'));
  }
  // If both selected or none selected, show all statuses

  // Session 61: Apply category filter (issue_type in database)
  if (activeCategoryFilter.value) {
    filtered = filtered.filter(i => i.issue_type === activeCategoryFilter.value);
  }

  // Session 61: Apply jurisdiction filter
  if (activeJurisdictionFilter.value) {
    filtered = filtered.filter(i => i.jurisdiction_id === activeJurisdictionFilter.value);
  }

  // Apply search filter
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(i => {
      // Search in: ai_title, description, short_name, location address
      return (
        i.ai_title?.toLowerCase().includes(query) ||
        i.description?.toLowerCase().includes(query) ||
        i.short_name?.toLowerCase().includes(query) ||
        i.location?.address?.toLowerCase().includes(query)
      );
    });
  }

  return filtered;
});

// Lifecycle
onMounted(async () => {
  await Promise.all([
    loadIssues(),
    loadFollows()
  ]);
});

// Methods
async function loadFollows() {
  try {
    const response = await api.getUserFollows(userStore.userId);

    // Extract issue IDs from follows
    const issueFollows = response.follows.filter(f => f.focal_type === 'issue');
    followedIssueIds.value = new Set(issueFollows.map(f => f.focal_id));

    console.log('[MyIssuesPanel] Loaded follows:', {
      total: response.metadata.total_follows,
      issues: response.metadata.issue_follows,
      followedIds: Array.from(followedIssueIds.value)
    });
  } catch (err: any) {
    console.error('[MyIssuesPanel] Error loading follows:', err);
    // Don't show error to user - follows are optional, just log it
  }
}

function toggleStatusFilter(status: 'open' | 'closed') {
  if (activeStatusFilters.value.has(status)) {
    // Prevent deselecting both - keep at least one selected
    if (activeStatusFilters.value.size > 1) {
      activeStatusFilters.value.delete(status);
    }
  } else {
    activeStatusFilters.value.add(status);
  }
  // Trigger reactivity
  activeStatusFilters.value = new Set(activeStatusFilters.value);
}

/**
 * Clear all category and jurisdiction filters (Session 62)
 */
function clearAllFilters() {
  activeCategoryFilter.value = null;
  activeJurisdictionFilter.value = null;
  searchQuery.value = '';
  console.log('[MyIssuesPanel] All filters cleared');
}

/**
 * Get human-readable jurisdiction name from ID (Session 62)
 */
function getJurisdictionDisplayName(jurisdictionId: string): string {
  if (!jurisdictionId || jurisdictionId === 'all') return 'All';

  // Remove 'city-' prefix and capitalize
  const name = jurisdictionId.replace(/^city-/, '').replace(/-/g, ' ');
  return name.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

async function loadIssues() {
  isLoading.value = true;
  error.value = '';

  try {
    // Always load all issues initially, then filter client-side
    // This allows switching between All/Mine/Following without reloading
    allIssues.value = await api.getComplaints(null);

    console.log('[MyIssuesPanel] Loaded issues:', allIssues.value);
  } catch (err: any) {
    console.error('[MyIssuesPanel] Error loading issues:', err);
    error.value = err.message || 'Failed to load issues';
  } finally {
    isLoading.value = false;
  }
}

function openIssue(issue: Issue) {
  // Debug: Check what title we're using
  const tabTitle = issue.short_name || issue.ai_title || truncateText(issue.description, 50);
  console.log('[MyIssuesPanel] Opening issue:', {
    id: issue.id,
    short_name: issue.short_name,
    ai_title: issue.ai_title,
    tabTitle: tabTitle
  });

  // Open issue as an artifact (tab) with details tab active
  workspaceStore.openArtifact({
    id: ArtifactIds.issue(issue.id), // Centralized ID generation (Session 53.5)
    type: 'issue',
    title: tabTitle,
    data: issue,
    initialTab: 'details' // Open to details tab (not discussion)
  });
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'Open',
    matched: 'Matched',
    community_formed: 'Community',
    escalated: 'Escalated',
    resolved: 'Resolved'
  };
  return labels[status] || status;
}

function formatIssueType(issueType: string): string {
  return issueType
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength).trim() + '...';
}

/**
 * Apply filters programmatically (for AI assistant chat navigation)
 * Session 61: Issues chat navigation
 */
function applyFilters(filters: {
  ownership?: 'all' | 'mine' | 'following'
  status?: 'all' | 'open' | 'closed' | 'matched'
  category?: string
  jurisdiction?: string
  searchQuery?: string
}) {
  console.log('[MyIssuesPanel] Applying programmatic filters:', filters);

  // Session 63: Handle ownership independently from status
  if (filters.ownership !== undefined) {
    activeOwnershipFilter.value = filters.ownership;
  } else {
    // Default to 'mine' if not specified
    activeOwnershipFilter.value = 'mine';
  }

  // Apply status filter (independent from ownership)
  if (filters.status !== undefined) {
    if (filters.status === 'all') {
      // Show all statuses
      activeStatusFilters.value = new Set(['open', 'closed']);
    } else if (filters.status === 'open') {
      // Show only open issues
      activeStatusFilters.value = new Set(['open']);
    } else if (filters.status === 'closed') {
      // Show only closed issues
      activeStatusFilters.value = new Set(['closed']);
    } else if (filters.status === 'matched') {
      // "matched" is a subset of "open" in this UI
      activeStatusFilters.value = new Set(['open']);
      // Note: Additional filtering by matched status would require more granular status tracking
    }
  }

  // Apply category filter
  if (filters.category !== undefined) {
    if (filters.category === 'all' || !filters.category) {
      activeCategoryFilter.value = null;
    } else {
      activeCategoryFilter.value = filters.category;
    }
  }

  // Apply jurisdiction filter
  if (filters.jurisdiction !== undefined) {
    if (filters.jurisdiction === 'all' || !filters.jurisdiction) {
      activeJurisdictionFilter.value = null;
    } else {
      activeJurisdictionFilter.value = filters.jurisdiction;
    }
  }

  // Apply search query
  if (filters.searchQuery !== undefined) {
    searchQuery.value = filters.searchQuery ?? '';
  }

  console.log('[MyIssuesPanel] Filters applied:', {
    statusFilters: Array.from(activeStatusFilters.value),
    ownership: activeOwnershipFilter.value,
    category: activeCategoryFilter.value,
    jurisdiction: activeJurisdictionFilter.value,
    search: searchQuery.value
  });
}

/**
 * Get current filtered issues count (Session 62)
 */
function getFilteredCount(): number {
  return filteredComplaints.value.length;
}

// Expose methods so they can be called from parent
defineExpose({
  loadIssues,
  loadFollows,
  applyFilters,
  getFilteredCount
});
</script>

<style scoped>
.my-issues-panel {
  display: flex;
  flex-direction: column;
  background: var(--background);
  padding: 0;
}

/* Search Bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px var(--space-md);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
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
  font-size: 13px;
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

/* Filter Bars */
.filter-bar {
  display: flex;
  gap: 4px;
  padding: 6px var(--space-md);
  overflow-x: auto;
  flex-shrink: 0;
}

.combined-filter {
  border-bottom: 1px solid var(--border);
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
  font-size: 11px;
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

/* Active Filters Bar (Session 62) */
.active-filters-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px var(--space-md);
  background: rgba(var(--primary-rgb, 38, 132, 255), 0.05);
  border-bottom: 1px solid var(--border);
  gap: 8px;
  flex-shrink: 0;
}

.active-filters {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--primary);
  color: white;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

.chip-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  padding: 0;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border-radius: 50%;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.12s ease;
}

.chip-remove:hover {
  background: rgba(255, 255, 255, 0.3);
}

.clear-all-btn {
  padding: 4px 10px;
  border: 1px solid var(--primary);
  border-radius: 4px;
  background: white;
  color: var(--primary);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  white-space: nowrap;
}

.clear-all-btn:hover {
  background: var(--primary);
  color: white;
}

/* Loading & Error States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-xl) var(--spacing-xl) var(--space-md);
  text-align: center;
  color: var(--text-secondary);
}

.spinner {
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

.error-icon {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-md);
}

.retry-btn {
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

.retry-btn:hover {
  background: var(--primary-hover);
}

/* Empty State */
.empty-state {
  padding: var(--spacing-lg) var(--spacing-lg) var(--spacing-lg) var(--space-md);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

/* Issues List - VSCode Minimal Style */
.issues-list {
  padding-left: var(--space-md); /* Left margin for breathing room */
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tight gaps like VSCode */
}

.issue-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px var(--space-md) 6px 0; /* Right padding, left handled by parent */
  background: transparent;
  border: none;
  border-radius: 0; /* Flush edges */
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
  width: 100%;
}

.issue-item:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover */
}

.issue-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.issue-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.issue-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.issue-title {
  font-size: 14px; /* Match EventsPanel */
  font-weight: 500; /* Less bold */
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.issue-short-name {
  font-size: 11px; /* Match EventsPanel jurisdiction size */
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
  margin-bottom: 2px;
}

.issue-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px; /* Match EventsPanel stats size */
  color: var(--text-secondary);
  font-weight: 400;
  opacity: 0.8;
}

.status-indicator {
  font-weight: 500;
}

.status-open {
  color: var(--yellow);
}

.status-matched {
  color: var(--blue);
}

.status-community_formed {
  color: var(--green);
}

.status-escalated {
  color: var(--orange);
}

.status-resolved {
  color: var(--base01);
}

.stat-separator {
  margin: 0 2px;
  opacity: 0.5;
}
</style>

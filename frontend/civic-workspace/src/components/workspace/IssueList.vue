<script setup lang="ts">
import { computed, watch, ref } from 'vue';
import type { Issue, OperationalIssue, Jurisdiction } from '@/types/civic';
import { useOperationalStore } from '@/stores/operational';
import { useWorkspaceStore } from '@/stores/workspace';
import { api } from '@/services/api';
import { ArtifactIds } from '@/utils/artifactIds';

const props = defineProps<{
  jurisdictionId: string | null;
  userId: string;
}>();

const emit = defineEmits<{
  'issue-select': [issue: Issue | OperationalIssue];
}>();

// Stores
const operationalStore = useOperationalStore();
const workspaceStore = useWorkspaceStore();

// State
const policyIssues = ref<Issue[]>([]);
const loadingPolicy = ref(false);
const errorPolicy = ref<string | null>(null);
const tierFilter = ref<'all' | 'operational' | 'policy'>('all');

// Watch for jurisdiction changes
watch(() => props.jurisdictionId, async (newJurisdictionId) => {
  if (newJurisdictionId) {
    await Promise.all([
      loadOperationalIssues(newJurisdictionId),
      loadPolicyIssues(newJurisdictionId)
    ]);
  }
}, { immediate: true });

// Load operational issues from SeeClickFix
async function loadOperationalIssues(jurisdictionId: string) {
  try {
    await operationalStore.fetchOperationalIssues(jurisdictionId, {
      status: 'open',
      perPage: 50
    });
  } catch (err) {
    console.error('Failed to load operational issues:', err);
  }
}

// Load policy issues (native platform)
async function loadPolicyIssues(jurisdictionId: string) {
  loadingPolicy.value = true;
  errorPolicy.value = null;
  try {
    const response = await api.searchIssues({
      user_id: props.userId,
      jurisdiction: jurisdictionId,
      status: 'open'
    });
    policyIssues.value = response.issues;
  } catch (err) {
    errorPolicy.value = err instanceof Error ? err.message : 'Failed to load policy issues';
    console.error('Failed to load policy issues:', err);
  } finally {
    loadingPolicy.value = false;
  }
}

// Computed
const operationalIssues = computed(() => {
  return props.jurisdictionId
    ? operationalStore.getIssuesForJurisdiction(props.jurisdictionId)
    : [];
});

const loading = computed(() => {
  const opLoading = props.jurisdictionId
    ? operationalStore.isLoadingForJurisdiction(props.jurisdictionId)
    : false;
  return opLoading || loadingPolicy.value;
});

const hasError = computed(() => {
  const opError = props.jurisdictionId
    ? operationalStore.getErrorForJurisdiction(props.jurisdictionId)
    : null;
  return opError || errorPolicy.value;
});

// Unified issue list (typed union for type safety)
type UnifiedIssue = (Issue & { _tier: 'policy' }) | (OperationalIssue & { _tier: 'operational' });

const allIssues = computed((): UnifiedIssue[] => {
  const operational = operationalIssues.value.map(issue => ({ ...issue, _tier: 'operational' as const }));
  const policy = policyIssues.value.map(issue => ({ ...issue, _tier: 'policy' as const }));

  // Sort: policy issues first (higher engagement), then operational by created_at
  return [...policy, ...operational].sort((a, b) => {
    if (a._tier === 'policy' && b._tier === 'operational') return -1;
    if (a._tier === 'operational' && b._tier === 'policy') return 1;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
});

const filteredIssues = computed(() => {
  if (tierFilter.value === 'all') return allIssues.value;
  return allIssues.value.filter(issue => issue._tier === tierFilter.value);
});

const operationalCount = computed(() => operationalIssues.value.length);
const policyCount = computed(() => policyIssues.value.length);
const totalCount = computed(() => operationalCount.value + policyCount.value);

// Type guards
function isOperational(issue: UnifiedIssue): issue is OperationalIssue & { _tier: 'operational' } {
  return issue._tier === 'operational';
}

function isPolicy(issue: UnifiedIssue): issue is Issue & { _tier: 'policy' } {
  return issue._tier === 'policy';
}

// Handle issue card click
function handleIssueClick(issue: UnifiedIssue) {
  if (isOperational(issue)) {
    // Open operational issue artifact
    workspaceStore.openArtifact({
      id: `operational-issue-${issue.id}`,
      type: 'issue',
      title: issue.title,
      data: issue
    });
  } else {
    // Open policy issue artifact
    const policyIssue = issue as Issue & { _tier: 'policy' };
    workspaceStore.openArtifact({
      id: `issue-${policyIssue.id}`,
      type: 'issue',
      title: policyIssue.ai_title || policyIssue.description,
      data: policyIssue
    });
  }
  emit('issue-select', issue);
}

// Format date
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffTime = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
  }
}

// Get follower count display
function getFollowerDisplay(issue: UnifiedIssue): string {
  if (isOperational(issue)) {
    // For operational issues, reporter count is implicit (1+ from SeeClickFix)
    return '1+ neighbor reported';
  } else {
    // For policy issues, show organizing count
    // TODO: Add follower count to Issue type
    return '234 residents organizing'; // Placeholder
  }
}
</script>

<template>
  <div class="issue-list">
    <!-- Tier Filters (minimal style like Discussions) -->
    <div class="filter-bar minimal-filter">
      <button
        class="filter-btn-minimal"
        :class="{ active: tierFilter === 'all' }"
        @click="tierFilter = 'all'"
      >
        All <span class="count">{{ totalCount }}</span>
      </button>
      <span class="filter-separator">|</span>
      <button
        class="filter-btn-minimal"
        :class="{ active: tierFilter === 'operational' }"
        @click="tierFilter = 'operational'"
      >
        Operational <span class="count">{{ operationalCount }}</span>
      </button>
      <span class="filter-separator">|</span>
      <button
        class="filter-btn-minimal"
        :class="{ active: tierFilter === 'policy' }"
        @click="tierFilter = 'policy'"
      >
        Policy <span class="count">{{ policyCount }}</span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="issue-list-state">
      <div class="loading-spinner">
        <div class="spinner"></div>
      </div>
      <p class="state-message">Loading issues...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="hasError" class="issue-list-state error">
      <div class="error-icon">⚠️</div>
      <p class="state-message">{{ hasError }}</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredIssues.length === 0 && jurisdictionId" class="issue-list-state empty">
      <div class="empty-icon">📭</div>
      <p class="state-message">
        {{ tierFilter === 'all'
          ? 'No issues found'
          : tierFilter === 'operational'
            ? 'No operational issues reported'
            : 'No policy campaigns active'
        }}
      </p>
      <button
        v-if="tierFilter !== 'all'"
        @click="tierFilter = 'all'"
        class="reset-filter-button"
      >
        Show All Issues
      </button>
    </div>

    <!-- Issue Cards -->
    <div v-else class="issue-cards">
      <div
        v-for="issue in filteredIssues"
        :key="issue.id"
        class="issue-card"
        :class="{ operational: isOperational(issue), policy: isPolicy(issue) }"
        @click="handleIssueClick(issue)"
      >
        <!-- Issue Title (clean, like discussion title) -->
        <div class="issue-title">
          {{ isOperational(issue) ? issue.title : (issue.ai_title || issue.description.substring(0, 60) + '...') }}
        </div>

        <!-- Issue Meta (minimal, like "1 message • 1 person") -->
        <div class="issue-meta">
          <span>{{ formatDate(issue.created_at) }}</span>
          <span class="meta-dot">•</span>
          <span>{{ getFollowerDisplay(issue) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.issue-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Minimal Filter Bar (matches Discussions style) */
.filter-bar.minimal-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px var(--space-md);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-secondary);
}

.filter-btn-minimal {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0;
  font-size: 12px;
  transition: color 0.2s;
}

.filter-btn-minimal:hover {
  color: var(--text-primary);
}

.filter-btn-minimal.active {
  color: var(--primary);
  font-weight: 500;
}

.filter-btn-minimal .count {
  font-weight: normal;
  color: inherit;
}

.filter-separator {
  color: var(--text-secondary);
  user-select: none;
  opacity: 0.6;
}

/* States */
.issue-list-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl);
  text-align: center;
  flex: 1;
}

.loading-spinner {
  margin-bottom: var(--space-md);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.state-message {
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  margin: 0;
}

.error-icon,
.empty-icon {
  font-size: 48px;
  margin-bottom: var(--space-3);
}

.reset-filter-button,
.retry-button {
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--primary);
  border-radius: var(--radius-base);
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  transition: all 0.2s;
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.reset-filter-button:hover,
.retry-button:hover {
  background: var(--primary);
  color: white;
}

/* Issue Cards - VSCode Minimal Style (matches Discussions) */
.issue-cards {
  flex: 1;
  overflow-y: auto;
  padding: 8px var(--space-md) var(--space-md) var(--space-md);
  display: flex;
  flex-direction: column;
  gap: 0; /* No gap - items have their own spacing */
}

.issue-card {
  padding: 8px var(--space-md) 8px 10px;
  border: none;
  border-left: 3px solid transparent;
  border-radius: 0;
  background: transparent;
  cursor: pointer;
  transition: background-color 0.12s ease, border-color 0.12s ease;
}

.issue-card:hover {
  background: rgba(0, 0, 0, 0.04);
}

.issue-card.operational {
  border-left-color: var(--accent-orange);
}

.issue-card.policy {
  border-left-color: var(--accent-purple);
}

/* Issue Title - Match Discussions Thread Title */
.issue-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 4px 0;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Issue Meta - Match Discussions Thread Stats */
.issue-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  margin: 0;
  opacity: 0.8;
  font-weight: 400;
}

.meta-dot {
  margin: 0 2px;
  opacity: 0.5;
}
</style>

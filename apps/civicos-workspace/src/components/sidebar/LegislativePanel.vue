<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useLegislativeStore, type LegislativeTopic } from '@/stores/legislative'
import { useWorkspaceStore } from '@/stores/workspace'
import type { StateBill, FederalProgram } from '@/types/civic'
import { ArtifactIds } from '@/utils/artifactIds'
import { ChevronRight, ChevronDown, Home, Train, Leaf, DollarSign, GraduationCap, FileText, Building2, Search, X } from 'lucide-vue-next'
import type { Component } from 'vue'

// Stores
const legislativeStore = useLegislativeStore()
const workspaceStore = useWorkspaceStore()

// Local state
const expandedItems = ref<Set<string>>(new Set())
const activeLevelFilters = ref<Set<'state' | 'federal'>>(new Set(['state', 'federal'])) // Both by default

// Topic options for dropdown
const topicOptions: { value: LegislativeTopic; label: string; icon: Component; color: string }[] = [
  { value: 'housing', label: 'Housing', icon: Home, color: '#cb4b16' }, // Orange - housing crisis
  { value: 'transportation', label: 'Transportation', icon: Train, color: '#268bd2' }, // Blue - transit
  { value: 'environment', label: 'Environment', icon: Leaf, color: '#859900' }, // Green - nature
  { value: 'budget', label: 'Budget', icon: DollarSign, color: '#b58900' }, // Yellow - money
  { value: 'education', label: 'Education', icon: GraduationCap, color: '#6c71c4' } // Violet - education
]

// Computed: Get total count across all topics
const allTopicsCount = computed(() => {
  const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']
  let totalBills = 0
  let totalPrograms = 0

  topics.forEach(topic => {
    totalBills += legislativeStore.cache.stateBills[topic]?.length || 0
    totalPrograms += legislativeStore.cache.federalPrograms[topic]?.length || 0
  })

  return totalBills + totalPrograms
})

// Computed: Get counts for each topic
const topicCounts = computed(() => {
  return topicOptions.map(topic => {
    const bills = legislativeStore.cache.stateBills[topic.value]?.length || 0
    const programs = legislativeStore.cache.federalPrograms[topic.value]?.length || 0
    return {
      ...topic,
      count: bills + programs
    }
  })
})

// Computed: Level filters with counts (toggleable)
const levelFilters = computed(() => {
  // Session 68.5: Defensive coding - handle undefined data from failed API calls
  const stateBills = legislativeStore.currentStateBills?.length || 0
  const federalPrograms = legislativeStore.currentFederalPrograms?.length || 0

  return [
    { value: 'state' as const, label: 'State', count: stateBills },
    { value: 'federal' as const, label: 'Federal', count: federalPrograms }
  ]
})

// Computed: Unified list of all legislative items (bills + programs)
const allLegislativeItems = computed(() => {
  const items: Array<{
    id: string
    title: string
    type: 'state' | 'federal'
    data: any
  }> = []

  // If no topic selected (showing all), aggregate across all topics
  if (!legislativeStore.selectedTopic) {
    const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']

    // Add state bills if filter active
    if (activeLevelFilters.value.has('state')) {
      topics.forEach(topic => {
        const bills = legislativeStore.cache.stateBills[topic] || []
        // Apply search filter if present
        const filteredBills = legislativeStore.searchQuery
          ? bills.filter(bill => {
              const query = legislativeStore.searchQuery.toLowerCase()
              return bill.bill.toLowerCase().includes(query) ||
                     bill.title.toLowerCase().includes(query) ||
                     bill.leverage_point.toLowerCase().includes(query)
            })
          : bills

        filteredBills.forEach(bill => {
          items.push({
            id: bill.bill,
            title: bill.title,
            type: 'state',
            data: bill
          })
        })
      })
    }

    // Add federal programs if filter active
    if (activeLevelFilters.value.has('federal')) {
      topics.forEach(topic => {
        const programs = legislativeStore.cache.federalPrograms[topic] || []
        // Apply search filter if present
        const filteredPrograms = legislativeStore.searchQuery
          ? programs.filter(program => {
              const query = legislativeStore.searchQuery.toLowerCase()
              return program.program_name.toLowerCase().includes(query) ||
                     program.agency.toLowerCase().includes(query) ||
                     program.leverage_point.toLowerCase().includes(query)
            })
          : programs

        filteredPrograms.forEach(program => {
          items.push({
            id: program.program_name,
            title: program.program_name,
            type: 'federal',
            data: program
          })
        })
      })
    }
  } else {
    // Specific topic selected - use store's filtered results
    // Add state bills if filter active
    if (activeLevelFilters.value.has('state')) {
      // Session 68.5: Defensive coding - handle undefined data from failed API calls
      const bills = legislativeStore.currentStateBills || []
      bills.forEach(bill => {
        items.push({
          id: bill.bill,
          title: bill.title,
          type: 'state',
          data: bill
        })
      })
    }

    // Add federal programs if filter active
    if (activeLevelFilters.value.has('federal')) {
      // Session 68.5: Defensive coding - handle undefined data from failed API calls
      const programs = legislativeStore.currentFederalPrograms || []
      programs.forEach(program => {
        items.push({
          id: program.program_name,
          title: program.program_name,
          type: 'federal',
          data: program
        })
      })
    }
  }

  return items
})

// Lifecycle
onMounted(async () => {
  // Pre-fetch all topics for filter counts (in background)
  const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']
  topics.forEach(topic => {
    if (!legislativeStore.isCacheFresh(topic)) {
      legislativeStore.fetchLegislativeData(topic)
    }
  })

  // Default to 'All' (null) - don't auto-select a specific topic
  if (legislativeStore.selectedTopic !== null && legislativeStore.selectedTopic !== undefined) {
    // Keep existing selection if there is one
  } else {
    legislativeStore.setSelectedTopic(null)
  }
})

// Watch for topic changes to fetch data
watch(() => legislativeStore.selectedTopic, (newTopic) => {
  if (newTopic && !legislativeStore.isCacheFresh(newTopic)) {
    legislativeStore.fetchLegislativeData(newTopic)
  }
})

// Methods
function toggleItemExpand(itemId: string) {
  if (expandedItems.value.has(itemId)) {
    expandedItems.value.delete(itemId)
  } else {
    expandedItems.value.add(itemId)
  }
}

function isItemExpanded(itemId: string): boolean {
  return expandedItems.value.has(itemId)
}

function openBillArtifact(bill: StateBill) {
  workspaceStore.openArtifact({
    id: ArtifactIds.bill(bill), // Centralized ID generation (Session 53.5)
    type: 'bill',
    title: bill.title,
    data: bill
  })
}

function openProgramArtifact(program: FederalProgram) {
  workspaceStore.openArtifact({
    id: ArtifactIds.program(program), // Centralized ID generation (Session 53.5)
    type: 'program',
    title: program.program_name,
    data: program
  })
}

function handleRefresh() {
  if (legislativeStore.selectedTopic) {
    legislativeStore.refreshTopic(legislativeStore.selectedTopic)
  }
}

/**
 * Toggle level filter (State/Federal)
 */
function toggleLevelFilter(level: 'state' | 'federal') {
  if (activeLevelFilters.value.has(level)) {
    // Prevent deselecting both - keep at least one selected
    if (activeLevelFilters.value.size > 1) {
      activeLevelFilters.value.delete(level)
    }
  } else {
    activeLevelFilters.value.add(level)
  }
  // Trigger reactivity
  activeLevelFilters.value = new Set(activeLevelFilters.value)
}

/**
 * Apply filters programmatically (for AI assistant to use same logic as user)
 * This ensures the AI interacts with filters exactly as a user would.
 */
function applyFilters(filters: {
  topic?: LegislativeTopic | 'all' | null
  searchQuery?: string
  level?: 'state' | 'federal' | 'both'
}) {
  // Apply topic filter
  if (filters.topic !== undefined) {
    if (filters.topic === 'all' || filters.topic === null) {
      legislativeStore.setSelectedTopic(null)
    } else {
      legislativeStore.setSelectedTopic(filters.topic)
    }
  }

  // Apply search query
  if (filters.searchQuery !== undefined) {
    legislativeStore.setSearchQuery(filters.searchQuery)
  }

  // Apply level filter
  if (filters.level) {
    if (filters.level === 'state') {
      activeLevelFilters.value = new Set(['state'])
    } else if (filters.level === 'federal') {
      activeLevelFilters.value = new Set(['federal'])
    } else {
      activeLevelFilters.value = new Set(['state', 'federal'])
    }
  }

  console.log('[LegislativePanel] Applied programmatic filters:', {
    topic: legislativeStore.selectedTopic,
    searchQuery: legislativeStore.searchQuery,
    level: Array.from(activeLevelFilters.value)
  })
}

/**
 * Clear all filters (return to default view)
 */
function clearAllFilters() {
  legislativeStore.setSearchQuery('')
  legislativeStore.setSelectedTopic(null) // Default to all
  activeLevelFilters.value = new Set(['state', 'federal']) // Default to both
}

// Expose methods so parent/ChatPanel can interact with the panel
defineExpose({
  applyFilters,
  clearAllFilters
})
</script>

<template>
  <div class="legislative-panel">
    <!-- Search Bar -->
    <div class="search-bar">
      <Search :size="14" class="search-icon" />
      <input
        type="text"
        :value="legislativeStore.searchQuery"
        @input="(e) => legislativeStore.setSearchQuery((e.target as HTMLInputElement).value)"
        placeholder="Search bills and programs..."
        class="search-input"
      />
      <button
        v-if="legislativeStore.searchQuery"
        @click="legislativeStore.clearSearch()"
        class="clear-btn"
        title="Clear search"
      >
        <X :size="14" />
      </button>
    </div>

    <!-- Topic Filter Bar -->
    <div class="filter-bar topic-filter">
      <!-- All Topics Button -->
      <button
        class="filter-btn"
        :class="{ active: legislativeStore.selectedTopic === null }"
        @click="legislativeStore.setSelectedTopic(null)"
        title="View all legislative topics"
      >
        All
        <span class="filter-count">{{ allTopicsCount }}</span>
      </button>

      <!-- Divider -->
      <div class="filter-divider"></div>

      <!-- Individual Topic Buttons -->
      <button
        v-for="topic in topicCounts"
        :key="topic.value"
        class="filter-btn topic-btn"
        :class="{ active: legislativeStore.selectedTopic === topic.value }"
        @click="legislativeStore.setSelectedTopic(topic.value)"
        :title="`View ${topic.label} legislation`"
      >
        <component :is="topic.icon" :size="14" class="topic-icon" :style="{ color: topic.color }" />
        {{ topic.label }}
        <span class="filter-count">{{ topic.count }}</span>
      </button>
    </div>

    <!-- Level Filter Bar (State/Federal) -->
    <div class="filter-bar level-filter">
      <button
        v-for="filter in levelFilters"
        :key="filter.value"
        class="filter-btn"
        :class="{ active: activeLevelFilters.has(filter.value) }"
        @click="toggleLevelFilter(filter.value)"
      >
        {{ filter.label }}
        <span class="filter-count">{{ filter.count }}</span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="legislativeStore.isLoading" class="panel-loading">
      <div class="loading-spinner"></div>
      <p>Loading legislative data...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="legislativeStore.currentError" class="panel-error">
      <p>{{ legislativeStore.currentError }}</p>
      <button @click="handleRefresh" class="retry-button">
        Retry
      </button>
    </div>

    <!-- Content -->
    <div v-else-if="legislativeStore.hasData || legislativeStore.selectedTopic === null" class="panel-content">
      <!-- Unified Legislative Items List -->
      <div v-if="allLegislativeItems.length > 0" class="section">
        <div class="item-list">
          <div
            v-for="item in allLegislativeItems"
            :key="item.id"
            class="legislative-item-card"
          >
            <div class="item-header" @click="toggleItemExpand(item.id)">
              <span class="expand-icon">
                <ChevronRight v-if="!isItemExpanded(item.id)" :size="14" />
                <ChevronDown v-else :size="14" />
              </span>
              <div class="item-title-block">
                <div class="item-title-row">
                  <span class="item-title">{{ item.title }}</span>
                  <span class="item-badge" :class="item.type">
                    {{ item.type === 'state' ? 'State' : 'Federal' }}
                  </span>
                </div>
                <span v-if="item.type === 'state'" class="item-meta">
                  {{ item.data.status }}
                </span>
                <span v-else class="item-meta">
                  {{ item.data.agency }}
                </span>
              </div>
            </div>

            <!-- State Bill Details -->
            <div v-if="isItemExpanded(item.id) && item.type === 'state'" class="item-details">
              <div class="item-summary">
                <p class="summary-text">{{ item.data.leverage_point }}</p>
              </div>
              <div class="item-actions">
                <button @click="openBillArtifact(item.data)" class="action-btn primary">
                  Open
                </button>
                <a :href="item.data.official_url" target="_blank" class="action-btn secondary">
                  Official Text
                </a>
              </div>
            </div>

            <!-- Federal Program Details -->
            <div v-if="isItemExpanded(item.id) && item.type === 'federal'" class="item-details">
              <div class="item-summary">
                <p class="summary-text">{{ item.data.leverage_point }}</p>
                <p v-if="item.data.fy2025_allocation" class="summary-allocation">
                  FY2025 Allocation: {{ item.data.fy2025_allocation }}
                </p>
              </div>
              <div class="item-actions">
                <button @click="openProgramArtifact(item.data)" class="action-btn primary">
                  Open
                </button>
                <a :href="item.data.info_url" target="_blank" class="action-btn secondary">
                  Program Info
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty Results -->
      <div v-else class="empty-search">
        <p v-if="legislativeStore.searchQuery">No results found for "{{ legislativeStore.searchQuery }}"</p>
        <p v-else-if="legislativeStore.selectedTopic === null">No {{ activeLevelFilters.has('state') && !activeLevelFilters.has('federal') ? 'state bills' : activeLevelFilters.has('federal') && !activeLevelFilters.has('state') ? 'federal programs' : 'results' }} found across all topics.</p>
        <p v-else>No {{ activeLevelFilters.has('state') && !activeLevelFilters.has('federal') ? 'state bills' : activeLevelFilters.has('federal') && !activeLevelFilters.has('state') ? 'federal programs' : 'results' }} found for this topic.</p>
        <button v-if="legislativeStore.searchQuery" @click="legislativeStore.clearSearch()" class="action-btn">
          Clear Search
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.legislative-panel {
  display: flex;
  flex-direction: column;
  background: var(--background); /* Light background */
  padding: 0; /* Flush with sidebar edges */
}

/* Filter Bar */
.filter-bar {
  display: flex;
  gap: 4px;
  padding: 8px var(--space-md) 8px var(--space-md);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
  margin-bottom: 0;
}

.topic-filter {
  padding-top: 8px;
  padding-bottom: 8px;
  flex-wrap: wrap;
}

.level-filter {
  padding-top: 6px;
  padding-bottom: 6px;
}

.filter-divider {
  width: 1px;
  background: var(--border);
  margin: 0 4px;
  opacity: 0.5;
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

/* Search Bar */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px var(--space-md);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  margin-bottom: 0;
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

/* Loading State */
.panel-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl);
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
  margin-bottom: var(--space-md);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Error State */
.panel-error {
  padding: var(--space-lg);
  text-align: center;
  color: var(--text-secondary);
}

.panel-error p {
  margin-bottom: var(--space-md);
  color: var(--red);
}

.retry-button {
  background: var(--primary);
  color: var(--background);
  border: none;
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: all var(--transition-base);
}

.retry-button:hover {
  background: var(--blue);
  transform: translateY(-1px);
}

/* Content */
.panel-content {
  padding-left: var(--space-md); /* Left margin for breathing room */
}

.section {
  padding: 8px var(--space-md) 8px 0; /* Right padding only, left handled by parent */
  margin-bottom: var(--space-lg);
}

/* Unified Item List - VSCode Minimal Style */
.item-list {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tighter gaps like VSCode */
}

.legislative-item-card {
  background: transparent;
  border: none;
  border-radius: 0; /* No radius - flush edges */
  overflow: visible;
  transition: background-color 0.12s ease;
}

.legislative-item-card:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover */
}

.item-header {
  display: flex;
  align-items: flex-start;
  padding: 6px var(--space-md) 6px 0; /* Tighter padding, right only */
  cursor: pointer;
  user-select: none;
  transition: background-color 0.12s ease;
}

.item-header:hover {
  background: transparent; /* Hover handled by parent */
}

.expand-icon {
  color: var(--text-secondary);
  opacity: 0.5; /* Subtle chevron */
  margin-right: 10px;
  margin-top: 1px;
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: opacity 0.12s ease;
}

.legislative-item-card:hover .expand-icon {
  opacity: 1;
}

.item-title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px; /* Tighter */
}

.item-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.item-title {
  font-size: 14px; /* Match EventsPanel */
  font-weight: 500; /* Less bold */
  color: var(--text-primary);
  line-height: 1.3;
  flex: 1;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  flex-shrink: 0;
  opacity: 0.85;
}

.item-badge.state {
  background: rgba(38, 139, 210, 0.12); /* Blue tint */
  color: #268bd2;
}

.item-badge.federal {
  background: rgba(108, 113, 196, 0.12); /* Violet tint */
  color: #6c71c4;
}

.item-meta {
  font-size: 11px; /* Match event jurisdiction size */
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
}

/* Details */
.item-details {
  padding: 6px var(--space-md) 8px 0; /* Match minimal style */
  padding-left: 34px; /* Indent to align with content (14px icon + 10px gap + 10px extra) */
  margin-top: 2px;
  margin-bottom: 4px;
  background: transparent; /* No background */
  border-top: none; /* No border */
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  opacity: 0.85;
}

.summary-allocation {
  font-size: 11px;
  color: var(--text-primary);
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  margin: 0;
  opacity: 0.8;
  letter-spacing: 0.01em;
}

.item-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.12s ease;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  text-align: center;
  white-space: nowrap;
  border: 1px solid transparent;
}

.action-btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.action-btn.primary:hover {
  background: var(--blue);
  border-color: var(--blue);
}

.action-btn.secondary {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border);
}

.action-btn.secondary:hover {
  background: rgba(0, 0, 0, 0.03);
  color: var(--primary);
  border-color: var(--primary);
}

/* Empty States */
.empty-state,
.empty-search {
  padding: var(--space-2xl) var(--space-2xl) var(--space-2xl) 0; /* Right padding, left handled by parent */
  text-align: center;
  color: var(--text-secondary);
}

.empty-state p,
.empty-search p {
  margin-bottom: var(--space-md);
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

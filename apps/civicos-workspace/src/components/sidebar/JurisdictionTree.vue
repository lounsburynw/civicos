<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { Jurisdiction } from '@/types/civic';
import { api } from '@/services/api';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import { ChevronRight, ChevronDown, MapPin, DollarSign } from 'lucide-vue-next';

// Store
const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();

// Emits
const emit = defineEmits<{
  (e: 'jurisdiction-select', jurisdiction: Jurisdiction): void;
}>();

// State
const jurisdictions = ref<Jurisdiction[]>([]);
const expandedNodes = ref<Set<string>>(new Set());
const loading = ref(false);
const error = ref<string | null>(null);

// Computed: Filtered jurisdictions based on user location
const filteredJurisdictions = computed(() => {
  // If user has set a location, filter to their jurisdictions only
  if (userStore.hasLocation && userStore.jurisdictionIds.length > 0) {
    return jurisdictions.value.filter(j =>
      userStore.jurisdictionIds.includes(j.id)
    );
  }
  // Otherwise, show all jurisdictions
  return jurisdictions.value;
});

// Computed: Group jurisdictions by state -> county -> cities
const groupedJurisdictions = computed(() => {
  const stateMap = new Map<string, Map<string, Jurisdiction[]>>();

  filteredJurisdictions.value.forEach(jurisdiction => {
    const state = jurisdiction.state || 'Unknown';
    const county = jurisdiction.county || 'Unknown';

    if (!stateMap.has(state)) {
      stateMap.set(state, new Map());
    }
    const countyMap = stateMap.get(state)!;

    if (!countyMap.has(county)) {
      countyMap.set(county, []);
    }
    countyMap.get(county)!.push(jurisdiction);
  });

  return stateMap;
});

// Lifecycle
onMounted(async () => {
  await loadJurisdictions();
  // Auto-expand California and first county
  expandedNodes.value.add('state-California');
  if (groupedJurisdictions.value.get('California')) {
    const firstCounty = groupedJurisdictions.value.get('California')!.keys().next().value;
    expandedNodes.value.add(`county-${firstCounty}`);
  }
});

// Methods
async function loadJurisdictions() {
  loading.value = true;
  error.value = null;
  try {
    jurisdictions.value = await api.getJurisdictions();
  } catch (err) {
    console.error('Failed to load jurisdictions:', err);
    error.value = err instanceof Error ? err.message : 'Failed to load jurisdictions';
  } finally {
    loading.value = false;
  }
}

function toggleNode(nodeId: string) {
  if (expandedNodes.value.has(nodeId)) {
    expandedNodes.value.delete(nodeId);
  } else {
    expandedNodes.value.add(nodeId);
  }
}

function selectJurisdiction(jurisdiction: Jurisdiction) {
  // Clear selected event when switching jurisdictions
  workspaceStore.clearEvent();
  emit('jurisdiction-select', jurisdiction);
}

function isExpanded(nodeId: string): boolean {
  return expandedNodes.value.has(nodeId);
}

function isSelected(jurisdictionId: string): boolean {
  return workspaceStore.selectedJurisdiction?.id === jurisdictionId;
}
</script>

<template>
  <div class="jurisdiction-tree">
    <!-- Loading State -->
    <div v-if="loading" class="tree-loading">
      <div class="loading-spinner"></div>
      <p>Loading jurisdictions...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="tree-error">
      <p>{{ error }}</p>
      <button @click="loadJurisdictions" class="retry-button">
        Retry
      </button>
    </div>

    <!-- Tree Content -->
    <div v-else class="tree-container">
      <div class="tree-nodes">
        <!-- State Level -->
        <div
          v-for="[stateName, countyMap] of groupedJurisdictions"
          :key="`state-${stateName}`"
          class="tree-state-group"
        >
          <div
            class="tree-node state-node"
            @click="toggleNode(`state-${stateName}`)"
          >
            <span class="tree-node-icon">
              <ChevronRight v-if="!isExpanded(`state-${stateName}`)" :size="12" />
              <ChevronDown v-else :size="12" />
            </span>
            <MapPin :size="14" class="tree-node-emoji" style="color: #2aa198" />
            <span class="tree-node-label">{{ stateName }}</span>
          </div>

          <!-- County Level -->
          <div v-if="isExpanded(`state-${stateName}`)" class="tree-children">
            <div
              v-for="[countyName, cities] of countyMap"
              :key="`county-${countyName}`"
              class="tree-county-group"
            >
              <div
                class="tree-node county-node"
                @click="toggleNode(`county-${countyName}`)"
              >
                <span class="tree-node-icon">
                  <ChevronRight v-if="!isExpanded(`county-${countyName}`)" :size="12" />
                  <ChevronDown v-else :size="12" />
                </span>
                <MapPin :size="13" class="tree-node-emoji" style="color: #2aa198" />
                <span class="tree-node-label">{{ countyName }}</span>
                <span class="tree-node-badge">{{ cities.length }}</span>
              </div>

              <!-- City Level -->
              <div v-if="isExpanded(`county-${countyName}`)" class="tree-children">
                <template v-for="city in cities" :key="city.id">
                  <div
                    class="tree-node city-node"
                    :class="{ active: isSelected(city.id) }"
                    @click.stop="selectJurisdiction(city)"
                  >
                    <span class="tree-node-label">{{ city.name }}</span>
                    <span
                      v-if="city.event_count"
                      class="tree-node-badge"
                      :class="{ active: isSelected(city.id) }"
                    >
                      {{ city.event_count }}
                    </span>
                  </div>

                  <!-- City Details (when selected) -->
                  <div
                    v-if="isSelected(city.id) && city.cdbg_allocation"
                    class="city-details"
                  >
                    <div class="city-detail-item">
                      <DollarSign :size="11" style="color: #b58900; opacity: 0.8" />
                      CDBG: {{ city.cdbg_allocation }}
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.jurisdiction-tree {
  display: flex;
  flex-direction: column;
  background: var(--background); /* Light background */
  padding: 0; /* Flush with sidebar edges */
}

/* Tree Nodes */
.tree-nodes {
  flex: 1;
  padding: 8px var(--space-md) 8px 0; /* Match other panels - right padding, left handled by parent */
  padding-left: var(--space-md); /* Left margin for breathing room */
}

.tree-state-group {
  margin-bottom: var(--space-md);
}

.tree-county-group {
  margin-bottom: var(--space-xs);
}

.tree-node {
  display: flex;
  align-items: center;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.12s ease;
  user-select: none;
}

/* State Level - Bold and Prominent */
.state-node {
  font-weight: 600;
  font-size: 13px; /* Slightly smaller, refined */
  padding: 6px 8px; /* Tighter */
  background: transparent; /* No background by default */
  margin-bottom: 4px;
  gap: 6px;
}

.state-node:hover {
  background: rgba(0, 0, 0, 0.03); /* Very subtle */
}

/* County Level - Medium Emphasis */
.county-node {
  font-weight: 500;
  font-size: 12px; /* Match refined typography */
  padding: 5px 8px; /* Tighter */
  margin-bottom: 2px;
  gap: 6px;
}

.county-node:hover {
  background: rgba(0, 0, 0, 0.03);
}

/* City Level - Standard */
.city-node {
  font-weight: 400;
  font-size: 13px; /* Improved readability */
  padding: 5px 8px 5px 16px; /* Tighter with left indent */
  margin-left: 0;
  border-left: none; /* Remove border for cleaner look */
}

.city-node:hover {
  background: rgba(0, 0, 0, 0.04);
}

.city-node.active {
  background: var(--primary);
  color: white;
}

.city-node.active .tree-node-label {
  font-weight: 500;
  color: white;
}

.tree-node-icon {
  color: var(--text-secondary);
  opacity: 0.5; /* Subtle chevron */
  transition: all 0.12s ease;
  width: 12px;
  height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tree-node:hover .tree-node-icon {
  opacity: 1;
}

.tree-node-emoji {
  flex-shrink: 0;
  opacity: 0.65;
  margin-right: 6px;
  transition: opacity 0.12s ease;
}

.tree-node:hover .tree-node-emoji {
  opacity: 0.9;
}

.tree-node.expanded .tree-node-icon {
  transform: rotate(0deg);
}

.tree-node.active .tree-node-icon {
  color: var(--background);
}

.tree-node-label {
  flex: 1;
  color: var(--text-primary);
  line-height: 1.3;
}

.tree-node-badge {
  font-size: 10px; /* Smaller, refined */
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 8px;
  font-weight: 600;
  min-width: 18px;
  text-align: center;
  opacity: 0.8;
}

.tree-node-badge.active {
  background: rgba(255, 255, 255, 0.3);
  color: white;
  opacity: 1;
}

/* Expanded Children */
.tree-children {
  padding-left: 16px; /* Tighter indent */
  margin-top: 2px;
}

/* City Details */
.city-details {
  margin-left: 24px;
  padding: 4px 8px;
  margin-top: 2px;
  margin-bottom: 4px;
}

.city-detail-item {
  font-size: 11px; /* Improved readability */
  color: var(--text-secondary);
  padding: 3px 0;
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0.9;
}

/* Loading State */
.tree-loading {
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
.tree-error {
  padding: var(--space-lg);
  text-align: center;
  color: var(--text-secondary);
}

.tree-error p {
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

.retry-button:active {
  transform: translateY(0);
}
</style>

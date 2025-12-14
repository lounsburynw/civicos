<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { ActionableItem } from '@/types/civic';
import { ChevronRight, FileText } from 'lucide-vue-next';

const props = withDefaults(defineProps<{
  items: ActionableItem[];
  totalItems?: number;
  actionableCount?: number;
}>(), {
  totalItems: undefined,
  actionableCount: undefined
});

const emit = defineEmits<{
  'selection-changed': [selectedItems: ActionableItem[]];
}>();

// Calculate totals if not provided
const computedTotalItems = computed(() => props.totalItems ?? props.items?.length ?? 0);
const computedActionableCount = computed(() =>
  props.actionableCount ?? props.items?.filter(item => item.actionable).length ?? 0
);

// Track expanded items (use Set for efficient lookups)
const expandedItems = ref<Set<string>>(new Set());

// Track selected items for comment drafting
const selectedItems = ref<Set<string>>(new Set());

// Toggle expand/collapse (chevron click)
function toggleExpand(itemRef: string, event: Event) {
  event.stopPropagation(); // Prevent selection toggle
  if (expandedItems.value.has(itemRef)) {
    expandedItems.value.delete(itemRef);
  } else {
    expandedItems.value.add(itemRef);
  }
}

// Toggle selection (card click)
function toggleSelection(itemRef: string) {
  if (selectedItems.value.has(itemRef)) {
    selectedItems.value.delete(itemRef);
  } else {
    selectedItems.value.add(itemRef);
  }

  // Emit selection change with full item objects
  const selected = props.items.filter(item => selectedItems.value.has(item.item_ref));
  emit('selection-changed', selected);
}

// Check if item is expanded
function isExpanded(itemRef: string): boolean {
  return expandedItems.value.has(itemRef);
}

// Check if item is selected
function isSelected(itemRef: string): boolean {
  return selectedItems.value.has(itemRef);
}

// Get project type label
function getProjectTypeLabel(type: string): string {
  return type.replace(/_/g, ' ').replace(/-/g, ' ');
}

// Format federal program names (remove underscores, shorten if needed)
function formatLegislativeRef(ref: string): string {
  // For federal programs with very long names, try to shorten
  if (ref.includes('_')) {
    // Replace underscores with spaces
    let formatted = ref.replace(/_/g, ' ');

    // If it's really long (>50 chars), try to abbreviate
    if (formatted.length > 50) {
      // Common abbreviations
      formatted = formatted
        .replace('environmental protection agency', 'EPA')
        .replace('department of energy', 'DOE')
        .replace('department of housing and urban development', 'HUD')
        .replace('department of transportation', 'DOT');
    }

    return formatted;
  }

  // For state bills, just uppercase (ca-sb1053 → CA-SB1053)
  return ref.toUpperCase();
}

// Initialize: expand actionable items by default
onMounted(() => {
  props.items?.forEach(item => {
    if (item.actionable) {
      expandedItems.value.add(item.item_ref);
    }
  });
});
</script>

<template>
  <div class="agenda-items">
    <div class="agenda-header">
      <div class="header-left">
        <h3 class="agenda-title">
          <span class="section-icon">📋</span>
          Agenda Items
        </h3>
        <div class="agenda-count">
          {{ computedTotalItems }} items, <strong>{{ computedActionableCount }} actionable</strong>
        </div>
      </div>
    </div>

    <div class="items-list">
      <div
        v-for="item in items"
        :key="item.item_ref"
        class="agenda-item"
        :class="{
          actionable: item.actionable,
          selected: isSelected(item.item_ref)
        }"
        @click="toggleSelection(item.item_ref)"
      >
        <!-- Item Header (clickable for selection) -->
        <div class="item-header">
          <div class="header-left-content">
            <ChevronRight
              :size="16"
              class="expand-icon"
              :class="{ 'is-rotated': isExpanded(item.item_ref) }"
              @click="toggleExpand(item.item_ref, $event)"
            />
            <span class="item-number">{{ item.item_ref }}</span>
            <span class="item-title">{{ item.title }}</span>
          </div>
        </div>

        <!-- Item Body (collapsible) -->
        <div v-if="isExpanded(item.item_ref)" class="item-body">
          <!-- Description -->
          <p class="item-description">{{ item.description }}</p>

          <!-- Actionable Because -->
          <div v-if="item.actionable && item.actionable_because" class="actionable-reason">
            <strong>Why this matters:</strong> {{ item.actionable_because }}
          </div>

          <!-- Project Type Badges -->
          <div v-if="item.project_types && item.project_types.length > 0" class="project-badges">
            <span
              v-for="projectType in item.project_types"
              :key="projectType"
              class="project-badge"
              :class="projectType"
            >
              {{ getProjectTypeLabel(projectType) }}
            </span>
          </div>

          <!-- Legislative Context -->
          <div
            v-if="item.legislative_context &&
                  (item.legislative_context.state_legislation_refs?.length ||
                   item.legislative_context.federal_program_refs?.length)"
            class="item-legislative-context"
          >
            <div class="legislative-header">
              <span class="legislative-icon">⚖️</span>
              <strong>Related Legislation:</strong>
            </div>
            <div class="legislative-refs">
              <span
                v-for="bill in item.legislative_context.state_legislation_refs"
                :key="bill"
                class="ref-badge state"
              >
                {{ formatLegislativeRef(bill) }}
              </span>
              <span
                v-for="program in item.legislative_context.federal_program_refs"
                :key="program"
                class="ref-badge federal"
              >
                {{ formatLegislativeRef(program) }}
              </span>
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agenda-items {
  margin-bottom: var(--space-xl);
  padding: var(--space-lg);
  background: var(--background-secondary);
  border: 2px solid var(--primary);
  border-radius: var(--radius-base);
}

/* Header */
.agenda-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-lg);
  gap: var(--space-md);
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.agenda-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.section-icon {
  font-size: 18px;
}

.agenda-count {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
}

.agenda-count strong {
  color: var(--primary);
  font-weight: 700;
}

/* Items List */
.items-list {
  display: flex;
  flex-direction: column;
  /* No gap - items separated by borders */
}

/* Agenda Item - Ultra-minimal (matches app collapsible sections) */
.agenda-item {
  background: transparent;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  transition: all 0.15s ease;
  cursor: pointer;
  border-left: 3px solid transparent;
}

.agenda-item:last-child {
  border-bottom: none;
}

/* Subtle indicator for actionable items - no loud colors */
.agenda-item.actionable .item-number {
  font-weight: 700;
  color: var(--primary);
}

.agenda-item:hover {
  background: var(--background-secondary);
}

/* Selected state - subtle blue highlight with left accent border */
.agenda-item.selected {
  background: rgba(38, 139, 210, 0.1); /* --primary at 10% opacity */
  border-left: 3px solid var(--primary);
  transition: all 0.15s ease;
}

.agenda-item.selected:hover {
  background: rgba(38, 139, 210, 0.15); /* Slightly brighter on hover */
}

/* Item Header - matches collapsible-header aesthetic */
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  user-select: none;
  transition: background var(--transition-fast);
}

.header-left-content {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.item-number {
  font-weight: 700;
  color: var(--primary);
  font-size: 13px;
  min-width: 30px;
  flex-shrink: 0;
}

.item-title {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Expand icon - matches app collapsible sections */
.expand-icon {
  color: var(--text-secondary);
  transition: transform 0.2s, color 0.15s;
  flex-shrink: 0;
  cursor: pointer;
  padding: 2px;
  border-radius: 2px;
}

.expand-icon:hover {
  color: var(--primary);
  background: var(--background-secondary);
}

.expand-icon.is-rotated {
  transform: rotate(90deg);
}

/* Item Body - matches collapsible-content aesthetic */
.item-body {
  padding: 0 0 16px 22px; /* Left padding aligns with text after chevron */
  animation: slideDown 0.2s ease-out;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.item-description {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

/* Actionable Reason - Neutral styling (matches app aesthetic) */
.actionable-reason {
  padding: 12px 16px;
  background: var(--background-secondary);
  border-left: 2px solid var(--border);
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

.actionable-reason strong {
  color: var(--text-primary);
  font-weight: 600;
}

/* Project Badges - Minimal GitHub-style */
.project-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.project-badge {
  padding: 4px 10px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
}

/* Legislative Context - Minimal styling */
.item-legislative-context {
  padding: 12px 0;
  background: transparent;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legislative-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-primary);
}

.legislative-icon {
  font-size: 14px;
}

.legislative-refs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* Legislative badges - Minimal GitHub-style (matches project badges) */
.ref-badge {
  padding: 4px 10px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
}

/* No color differentiation - keep it minimal */
.ref-badge.state,
.ref-badge.federal {
  /* Same style for both */
}

/* Responsive */
@media (max-width: 768px) {
  .agenda-items {
    padding: var(--space-md);
  }

  .item-header {
    padding: 8px 0;
  }

  .item-body {
    padding: 0 0 12px 22px;
  }

  .header-left-content {
    flex-wrap: wrap;
  }

  .item-title {
    white-space: normal;
    flex: 1 1 100%;
  }
}
</style>

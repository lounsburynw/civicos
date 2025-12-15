<script setup lang="ts">
import { computed } from 'vue';
import { ChevronRight, ChevronDown, Plus } from 'lucide-vue-next';
import type { Component } from 'vue';

interface Props {
  title: string;
  icon?: Component; // Lucide icon component
  iconColor?: string; // Optional color for the icon (Solarized accent)
  defaultExpanded?: boolean;
  forceExpanded?: boolean; // Force expanded regardless of store (for new users)
  externalExpanded?: boolean; // Session 63: External control from Pinia store (SINGLE SOURCE OF TRUTH)
  badgeCount?: number;
  storageKey: string; // Still required for backward compatibility, but not used
  actionIcon?: Component; // Optional action button icon (e.g., Plus)
  actionTooltip?: string; // Tooltip for action button
  noMaxHeight?: boolean; // Allow section to expand fully without height constraint
}

const props = withDefaults(defineProps<Props>(), {
  defaultExpanded: true,
  forceExpanded: false,
  externalExpanded: undefined,
  badgeCount: undefined,
  icon: undefined,
  iconColor: undefined,
  actionIcon: undefined,
  actionTooltip: undefined,
  noMaxHeight: false
});

const emit = defineEmits<{
  action: []
  toggle: [] // Session 63: Emit toggle event for parent to handle (updates store)
}>();

// Session 63: Computed expanded state (Pinia store is single source of truth)
// Priority: forceExpanded > externalExpanded > defaultExpanded
const isExpanded = computed(() => {
  if (props.forceExpanded) return true;
  if (props.externalExpanded !== undefined) return props.externalExpanded;
  return props.defaultExpanded;
});

// Toggle expand/collapse - emit event for parent to handle
function toggle() {
  emit('toggle');
}

// Handle keyboard navigation
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    toggle();
  }
}

// Handle action button click
function handleAction(e: MouseEvent) {
  e.stopPropagation(); // Prevent toggle from firing
  emit('action');
}
</script>

<template>
  <div class="collapsible-section">
    <!-- Header -->
    <div
      class="collapsible-section-header"
      role="button"
      tabindex="0"
      :aria-expanded="isExpanded"
      @click="toggle"
      @keydown="handleKeydown"
    >
      <span class="collapsible-section-chevron">
        <ChevronRight v-if="!isExpanded" :size="12" />
        <ChevronDown v-else :size="12" />
      </span>
      <component
        v-if="icon"
        :is="icon"
        :size="14"
        class="collapsible-section-icon"
        :style="iconColor ? { color: iconColor } : {}"
      />
      <span class="collapsible-section-title">{{ title }}</span>
      <span
        v-if="badgeCount !== undefined && badgeCount > 0"
        class="collapsible-section-badge"
      >
        {{ badgeCount }}
      </span>
      <button
        v-if="actionIcon"
        class="collapsible-section-action"
        :title="actionTooltip"
        @click="handleAction"
      >
        <component :is="actionIcon" :size="14" />
      </button>
    </div>

    <!-- Content -->
    <div
      class="collapsible-section-content"
      :class="{ collapsed: !isExpanded, 'no-max-height': noMaxHeight }"
    >
      <slot />
    </div>
  </div>
</template>

<style scoped>
.collapsible-section {
  border-bottom: 1px solid var(--border);
}

.collapsible-section-header {
  display: flex;
  align-items: center;
  padding: 10px var(--space-md) 6px var(--space-md);
  cursor: pointer;
  user-select: none;
  transition: all 0.12s ease;
  gap: 6px;
  background: var(--background-secondary); /* Subtle shading to distinguish from content */
}

.collapsible-section-header:hover {
  background: var(--hover-bg);
}

.collapsible-section-header:hover .collapsible-section-chevron {
  opacity: 1; /* Chevron becomes more visible on hover */
}

.collapsible-section-header:focus {
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
}

.collapsible-section-chevron {
  color: var(--text-secondary);
  width: 12px;
  height: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.12s ease;
  opacity: 0.5; /* More subtle by default */
}

.collapsible-section-icon {
  flex-shrink: 0;
  opacity: 0.65; /* Subtle but visible for accent colors */
  transition: opacity 0.12s ease;
}

.collapsible-section-header:hover .collapsible-section-icon {
  opacity: 0.9; /* More visible on hover */
}

.collapsible-section-title {
  flex: 1;
  font-weight: 600;
  font-size: 12px; /* Improved readability for civic users */
  text-transform: uppercase;
  letter-spacing: 0.08em; /* Slightly wider for readability at smaller size */
  color: var(--text-secondary);
  opacity: 0.85; /* Subtle, refined */
}

.collapsible-section-badge {
  background: var(--primary);
  color: white;
  font-size: 9px; /* Smaller, more refined */
  padding: 2px 5px;
  border-radius: 8px;
  margin-left: auto; /* Push to right edge */
  font-weight: 600;
  min-width: 16px;
  text-align: center;
  opacity: 0.9;
}

.collapsible-section-action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  margin-left: 4px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.12s ease;
  color: var(--text-secondary);
  opacity: 0.5;
  flex-shrink: 0;
}

.collapsible-section-action:hover {
  background: var(--background);
  opacity: 1;
}

.collapsible-section-action:active {
  transform: scale(0.95);
}

/* When badge isn't present, push action button to right */
.collapsible-section-header:not(:has(.collapsible-section-badge)) .collapsible-section-action {
  margin-left: auto;
}

.collapsible-section-content {
  max-height: 400px; /* Constrain height so sections don't push others out of view */
  overflow-y: auto; /* Allow scrolling within each section */
  overflow-x: hidden;
  transition: max-height 0.3s ease, opacity 0.3s ease;
  opacity: 1;
}

.collapsible-section-content.no-max-height {
  max-height: none; /* Allow full expansion */
}

.collapsible-section-content.collapsed {
  max-height: 0;
  opacity: 0;
  overflow: hidden; /* Prevent scrollbar flash during collapse animation */
}

/* Scrollbar styling for section content */
.collapsible-section-content::-webkit-scrollbar {
  width: 6px;
}

.collapsible-section-content::-webkit-scrollbar-track {
  background: var(--background);
}

.collapsible-section-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.collapsible-section-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

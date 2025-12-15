<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import type { Component } from 'vue';

interface SplitPaneProps {
  minLeftWidth?: number;
  minRightWidth?: number;
  defaultLeftWidth?: number; // Percentage
  collapsible?: boolean;
}

const props = withDefaults(defineProps<SplitPaneProps>(), {
  minLeftWidth: 280,
  minRightWidth: 400,
  defaultLeftWidth: 60,
  collapsible: true
});

// State
const containerRef = ref<HTMLElement | null>(null);
const isDragging = ref(false);
const splitPaneWidth = ref(props.defaultLeftWidth); // Percentage
const leftPaneCollapsed = ref(false);
const rightPaneCollapsed = ref(false);

// LocalStorage keys
const STORAGE_KEY_WIDTH = 'civic_split_pane_width';
const STORAGE_KEY_LEFT_COLLAPSED = 'civic_split_pane_left_collapsed';
const STORAGE_KEY_RIGHT_COLLAPSED = 'civic_split_pane_right_collapsed';

// Computed: actual widths
const leftPaneStyle = computed(() => {
  if (leftPaneCollapsed.value) {
    return { width: '0px', minWidth: '0px' };
  }
  return { width: `${splitPaneWidth.value}%` };
});

const rightPaneStyle = computed(() => {
  if (rightPaneCollapsed.value) {
    return { width: '0px', minWidth: '0px' };
  }
  return { width: `${100 - splitPaneWidth.value}%` };
});

// Handle drag start
function handleMouseDown(e: MouseEvent) {
  if (leftPaneCollapsed.value || rightPaneCollapsed.value) {
    return; // Don't allow dragging when collapsed
  }

  e.preventDefault();
  isDragging.value = true;

  const onMouseMove = (e: MouseEvent) => {
    if (!isDragging.value || !containerRef.value) return;

    const containerWidth = containerRef.value.offsetWidth;
    const newWidth = (e.clientX / containerWidth) * 100;

    // Calculate min/max percentages
    const minLeftPercent = (props.minLeftWidth / containerWidth) * 100;
    const minRightPercent = (props.minRightWidth / containerWidth) * 100;
    const maxLeftPercent = 100 - minRightPercent;

    // Clamp the width
    splitPaneWidth.value = Math.max(minLeftPercent, Math.min(maxLeftPercent, newWidth));
  };

  const onMouseUp = () => {
    isDragging.value = false;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
  };

  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);
}

// Toggle collapse
function toggleLeftPane() {
  leftPaneCollapsed.value = !leftPaneCollapsed.value;
}

function toggleRightPane() {
  rightPaneCollapsed.value = !rightPaneCollapsed.value;
}

// Expand both panes (called when both are collapsed)
function expandBoth() {
  leftPaneCollapsed.value = false;
  rightPaneCollapsed.value = false;
}

// Persist to localStorage
watch(splitPaneWidth, () => {
  localStorage.setItem(STORAGE_KEY_WIDTH, splitPaneWidth.value.toString());
});

watch(leftPaneCollapsed, () => {
  localStorage.setItem(STORAGE_KEY_LEFT_COLLAPSED, leftPaneCollapsed.value.toString());
});

watch(rightPaneCollapsed, () => {
  localStorage.setItem(STORAGE_KEY_RIGHT_COLLAPSED, rightPaneCollapsed.value.toString());
});

// Load from localStorage on mount
onMounted(() => {
  const savedWidth = localStorage.getItem(STORAGE_KEY_WIDTH);
  if (savedWidth) {
    splitPaneWidth.value = parseFloat(savedWidth);
  }

  const savedLeftCollapsed = localStorage.getItem(STORAGE_KEY_LEFT_COLLAPSED);
  if (savedLeftCollapsed) {
    leftPaneCollapsed.value = savedLeftCollapsed === 'true';
  }

  const savedRightCollapsed = localStorage.getItem(STORAGE_KEY_RIGHT_COLLAPSED);
  if (savedRightCollapsed) {
    rightPaneCollapsed.value = savedRightCollapsed === 'true';
  }
});

// Expose toggle methods for keyboard shortcuts
defineExpose({
  toggleLeftPane,
  toggleRightPane
});
</script>

<template>
  <div ref="containerRef" class="split-pane-container">
    <!-- Left Pane (Event List) -->
    <div
      class="split-pane-left"
      :class="{ collapsed: leftPaneCollapsed }"
      :style="leftPaneStyle"
    >
      <div v-if="!leftPaneCollapsed" class="split-pane-content">
        <slot name="left" />
      </div>

      <!-- Collapse button for left pane -->
      <button
        v-if="collapsible && !leftPaneCollapsed"
        class="collapse-button collapse-left"
        @click="toggleLeftPane"
        title="Hide event list (Cmd+B)"
      >
        ◀
      </button>
    </div>

    <!-- Drag Handle -->
    <div
      v-if="!leftPaneCollapsed && !rightPaneCollapsed"
      class="split-pane-handle"
      :class="{ dragging: isDragging }"
      @mousedown="handleMouseDown"
    />

    <!-- Right Pane (Event Detail) -->
    <div
      class="split-pane-right"
      :class="{ collapsed: rightPaneCollapsed }"
      :style="rightPaneStyle"
    >
      <div v-if="!rightPaneCollapsed" class="split-pane-content">
        <slot name="right" />
      </div>

      <!-- Collapse button for right pane -->
      <button
        v-if="collapsible && !rightPaneCollapsed"
        class="collapse-button collapse-right"
        @click="toggleRightPane"
        title="Hide details (Cmd+Shift+B)"
      >
        ▶
      </button>
    </div>

    <!-- Expand buttons (when collapsed) -->
    <button
      v-if="leftPaneCollapsed && !rightPaneCollapsed"
      class="expand-button expand-left"
      @click="toggleLeftPane"
      title="Show event list (Cmd+B)"
    >
      ▶
    </button>

    <button
      v-if="rightPaneCollapsed && !leftPaneCollapsed"
      class="expand-button expand-right"
      @click="toggleRightPane"
      title="Show details (Cmd+Shift+B)"
    >
      ◀
    </button>

    <!-- Both collapsed state -->
    <div v-if="leftPaneCollapsed && rightPaneCollapsed" class="both-collapsed-state">
      <p>Both panes are collapsed</p>
      <button @click="expandBoth" class="expand-both-button">
        Show Both Panes
      </button>
    </div>
  </div>
</template>

<style scoped>
.split-pane-container {
  display: flex;
  height: 100%;
  overflow: hidden;
  position: relative;
  background: var(--background-secondary);
}

/* Panes */
.split-pane-left,
.split-pane-right {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  transition: width var(--transition-base), opacity var(--transition-base);
}

.split-pane-left.collapsed,
.split-pane-right.collapsed {
  width: 0 !important;
  min-width: 0 !important;
  opacity: 0;
  overflow: hidden;
}

.split-pane-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Drag Handle */
.split-pane-handle {
  width: 6px;
  background: var(--border);
  cursor: col-resize;
  transition: background var(--transition-fast);
  position: relative;
  flex-shrink: 0;
  user-select: none;
}

.split-pane-handle:hover {
  background: var(--primary);
}

.split-pane-handle.dragging {
  background: var(--primary);
}

/* Wider hit area for dragging */
.split-pane-handle::before {
  content: '';
  position: absolute;
  left: -4px;
  right: -4px;
  top: 0;
  bottom: 0;
  z-index: 1;
}

/* Collapse Buttons */
.collapse-button {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  padding: var(--space-xs) var(--space-xs);
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  z-index: 10;
  color: var(--text-secondary);
}

.collapse-button:hover {
  background: var(--hover-bg);
  border-color: var(--primary);
  color: var(--primary);
}

.collapse-left {
  right: var(--space-md);
}

.collapse-right {
  left: var(--space-md);
}

/* Expand Buttons (when collapsed) */
.expand-button {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  padding: var(--space-sm) var(--space-xs);
  background: var(--primary);
  border: 1px solid var(--primary);
  border-radius: var(--radius-base);
  font-size: 14px;
  cursor: pointer;
  transition: all var(--transition-fast);
  z-index: 20;
  color: white;
  box-shadow: var(--shadow);
}

.expand-button:hover {
  background: var(--accent-purple);
  border-color: var(--accent-purple);
  transform: translateY(-50%) scale(1.1);
}

.expand-left {
  left: var(--space-md);
}

.expand-right {
  right: var(--space-md);
}

/* Both Collapsed State */
.both-collapsed-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  z-index: 15;
}

.both-collapsed-state p {
  color: var(--text-secondary);
  margin-bottom: var(--space-md);
}

.expand-both-button {
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

.expand-both-button:hover {
  background: var(--accent-purple);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

/* Responsive: Mobile */
@media (max-width: 768px) {
  .split-pane-container {
    flex-direction: column;
  }

  .split-pane-left,
  .split-pane-right {
    width: 100% !important;
  }

  .split-pane-left.collapsed {
    height: 0 !important;
  }

  .split-pane-right.collapsed {
    height: 0 !important;
  }

  .split-pane-handle {
    display: none; /* Hide drag handle on mobile */
  }

  .collapse-button {
    top: var(--space-md);
    transform: none;
  }

  .collapse-left {
    bottom: var(--space-md);
    top: auto;
  }

  .collapse-right {
    top: var(--space-md);
  }
}

/* Responsive: Tablet */
@media (min-width: 769px) and (max-width: 1024px) {
  /* Reduce minimum widths for tablets */
  .split-pane-left {
    min-width: 240px;
  }

  .split-pane-right {
    min-width: 320px;
  }
}
</style>

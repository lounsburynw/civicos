<script setup lang="ts">
import { computed, ref, onMounted } from 'vue';
import { useContextStore } from '@/stores/context';
import { useWorkspaceStore } from '@/stores/workspace';
import { Calendar, Scale, Building, MessageCircle, Edit3, AlertCircle, FileText, X, ChevronDown, ChevronUp } from 'lucide-vue-next';
import type { ContextElement } from '@/types/context';

const contextStore = useContextStore();
const workspaceStore = useWorkspaceStore();
const expanded = ref(true);

// Load expanded state from localStorage
onMounted(() => {
  const savedState = localStorage.getItem('civic-context-indicator-expanded');
  if (savedState !== null) {
    expanded.value = savedState === 'true';
  }

  // Collapse by default on mobile
  if (window.innerWidth < 768) {
    expanded.value = false;
  }
});

// Save expanded state to localStorage
function toggleExpanded() {
  expanded.value = !expanded.value;
  localStorage.setItem('civic-context-indicator-expanded', String(expanded.value));
}

// Keyboard accessibility - handle Space/Enter for toggle
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleExpanded();
  }
}

// Get all active context elements from context store (Session 54: includes open/closed state)
const contextElements = computed(() => {
  return contextStore.activeContext.map(element => {
    // Check if artifact is currently open
    const isOpen = workspaceStore.openArtifacts.some(a => a.id === element.artifact_id);

    return {
      id: element.id,
      type: element.type,
      title: element.metadata.title,
      priority: element.priority,
      artifactId: element.artifact_id,
      data: element.data, // Store full data for reopening
      isOpen, // NEW: track open/closed state
      subContext: {
        tab: element.metadata.event?.active_tab,
        topics: element.metadata.topics.slice(0, 2).join(', ')
      }
    };
  });
});

function getIconForType(type: string) {
  const icons: Record<string, any> = {
    event: Calendar,      // Meeting/event icon
    bill: Scale,          // Law/justice icon
    program: Building,    // Government program icon
    thread: MessageCircle,// Discussion thread icon
    draft: Edit3,         // Draft comment icon
    issue: AlertCircle    // Issue/complaint icon
  };
  return icons[type] || FileText;
}

/**
 * Session 54: Focus artifact when context element is clicked
 * - If tab is closed → re-open it
 * - If tab is open but not active → switch to it
 * - If tab is already active → no-op
 */
function focusArtifact(element: any) {
  const artifactId = element.artifactId;

  // Check if artifact is already open
  const artifact = workspaceStore.openArtifacts.find(a => a.id === artifactId);

  if (!artifact) {
    // Tab is closed - reopen it
    console.log('[ContextIndicator] Reopening artifact:', artifactId);

    // Create OpenArtifact object
    const openArtifactObj = {
      id: artifactId,
      type: element.type,
      title: element.title,
      data: element.data
    };

    workspaceStore.openArtifact(openArtifactObj);
  } else {
    // Tab exists - just switch to it
    console.log('[ContextIndicator] Switching to artifact:', artifactId);
    workspaceStore.setActiveArtifact(artifactId);
  }
}

/**
 * Session 54: Remove from context AND close tab
 * Explicit removal via "X" button
 */
function removeFromContext(contextId: string) {
  // Get element before unregistering
  const element = contextStore.get(contextId);

  // Unregister from context store
  contextStore.unregister(contextId);

  // Also close the artifact tab if open
  if (element) {
    const artifactIndex = workspaceStore.openArtifacts.findIndex(a => a.id === element.artifact_id);
    if (artifactIndex !== -1) {
      workspaceStore.closeArtifact(artifactIndex);
    }
  }

  console.log('[ContextIndicator] Removed from context + closed tab:', element?.artifact_id);
}
</script>

<template>
  <div class="context-indicator">
    <div
      class="context-header"
      @click="toggleExpanded"
      @keydown="handleKeydown"
      tabindex="0"
      role="button"
      :aria-expanded="expanded"
      aria-controls="context-list"
    >
      <span class="context-icon">🧭</span>
      <span class="context-title">Active Context ({{ contextElements.length }})</span>
      <component :is="expanded ? ChevronUp : ChevronDown" :size="16" class="chevron" />
    </div>

    <Transition name="expand">
      <div v-if="expanded" id="context-list" class="context-list">
        <div
          v-for="element in contextElements"
          :key="element.id"
          :class="[
            'context-item',
            element.priority,
            element.isOpen ? 'is-open' : 'is-closed'
          ]"
          @click="focusArtifact(element)"
          role="button"
          tabindex="0"
          @keydown.enter="focusArtifact(element)"
          @keydown.space.prevent="focusArtifact(element)"
        >
          <component
            :is="getIconForType(element.type)"
            :size="16"
            class="item-icon"
            :class="{ 'icon-closed': !element.isOpen }"
          />
          <div class="item-content">
            <span class="item-title">{{ element.title }}</span>
            <span v-if="element.subContext.tab" class="item-meta">
              Tab: {{ element.subContext.tab }}
            </span>
          </div>
          <button @click.stop="removeFromContext(element.id)" class="remove-btn" :aria-label="'Remove ' + element.title + ' from context'">
            <X :size="12" />
          </button>
        </div>

        <div v-if="contextElements.length === 0" class="context-empty">
          <span>No artifacts open</span>
          <span class="context-hint">Open an event or draft to add context</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.context-indicator {
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
}

.context-header {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s ease;
}

.context-header:hover {
  background: var(--hover-bg);
}

.context-icon {
  font-size: 1.2em;
  margin-right: 0.5rem;
}

.context-title {
  flex: 1;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.chevron {
  color: var(--text-secondary);
  transition: transform 0.3s ease;
}

.context-list {
  padding: 0.5rem;
  max-height: 300px;
  overflow-y: auto;
}

.context-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 6px;
  border-left-width: 3px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.context-item.primary {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.05);
}

/* Session 54: Open tabs - blue accent, full opacity */
.context-item.is-open {
  border-left-color: var(--blue);
  opacity: 1;
}

/* Session 54: Closed but in context - gray accent, reduced opacity */
.context-item.is-closed {
  border-left-color: var(--base01);
  opacity: 0.65;
}

.context-item.is-closed .icon-closed {
  opacity: 0.5;
}

/* Session 54: Hover brings closed items back to full opacity */
.context-item.is-closed:hover {
  opacity: 1;
  border-left-color: var(--cyan);
}

.context-item:hover {
  transform: translateX(2px);
  box-shadow: var(--shadow-subtle);
  background-color: var(--base01);
}

.context-item:active {
  background-color: var(--base02);
}

.context-item:focus {
  outline: 2px solid var(--blue);
  outline-offset: -2px;
}

.item-icon {
  flex-shrink: 0;
  color: var(--text-secondary);
}

.item-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.item-title {
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.item-meta {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.remove-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  padding: 0.25rem;
  cursor: pointer;
  color: var(--text-secondary);
  border-radius: 4px;
  transition: all 0.2s ease;
}

.remove-btn:hover {
  background: var(--accent-red);
  color: white;
}

.context-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2rem 1rem;
  text-align: center;
  color: var(--text-secondary);
  gap: 0.5rem;
}

.context-hint {
  font-size: 0.85rem;
  color: var(--text-secondary);
  opacity: 0.7;
}

/* Expand transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.expand-enter-to,
.expand-leave-from {
  max-height: 300px;
  opacity: 1;
}

/* Keyboard focus styles */
.context-header:focus {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
}

.remove-btn:focus {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .context-header {
    padding: 0.5rem 0.75rem;
  }

  .context-title {
    font-size: 0.85rem;
  }

  .context-list {
    padding: 0.25rem;
    max-height: 200px;
  }

  .context-item {
    padding: 0.5rem;
    gap: 0.5rem;
  }

  .item-title {
    font-size: 0.85rem;
  }

  .item-meta {
    font-size: 0.75rem;
  }

  .context-empty {
    padding: 1.5rem 0.75rem;
  }
}
</style>

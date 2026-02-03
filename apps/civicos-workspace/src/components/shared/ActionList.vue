<script setup lang="ts">
/**
 * ActionList Component
 *
 * Displays all civic actions for an initiative with progress tracking.
 * Uses ActionFlow components for individual action display and commitment flow.
 *
 * Usage:
 *   <ActionList
 *     :initiative-id="initiative.id"
 *     :jurisdiction="jurisdiction"
 *     :user-public-key="userPublicKey"
 *     :user-committed-actions="committedActions"
 *     @sign-request="handleSignRequest"
 *     @committed="handleCommitted"
 *   />
 */
import { ref, onMounted, watch, computed } from 'vue';
import { api } from '@/services/api';
import ActionFlow from './ActionFlow.vue';
import type { CivicActionEvent, InitiativeAction } from '@/types/civic';

const props = defineProps<{
  /** Initiative ID to fetch actions for */
  initiativeId: string;
  /** Jurisdiction ID */
  jurisdiction: string;
  /** User's public key (if signed in) */
  userPublicKey?: string;
  /** Set of action IDs the user has committed to */
  userCommittedActions?: Set<string>;
}>();

const emit = defineEmits<{
  /** Emitted when user requests to sign a commitment */
  (e: 'sign-request', actionId: string, jurisdiction: string): void;
  /** Emitted when user successfully commits to an action */
  (e: 'committed', actionId: string): void;
}>();

// State
const actions = ref<CivicActionEvent[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Refs for ActionFlow components (for signing callbacks)
const actionFlowRefs = ref<Map<string, InstanceType<typeof ActionFlow>>>(new Map());

// Convert CivicActionEvent to InitiativeAction for ActionFlow compatibility
function toInitiativeAction(event: CivicActionEvent): InitiativeAction {
  // Map CivicActionType to InitiativeAction's action_type
  const typeMap: Record<string, InitiativeAction['action_type']> = {
    written_comment: 'comment',
    attend_meeting: 'attend',
    public_comment: 'comment',
    contact_official: 'contact',
    signature: 'other',
    share: 'share',
    custom: 'other'
  };

  return {
    id: event.id,
    action_type: typeMap[event.action_type] ?? 'other',
    description: event.description,
    target_count: event.target_count,
    deadline: event.deadline,
    template: event.template
  };
}

// Check if user has committed to an action
function isCommitted(actionId: string): boolean {
  if (!props.userCommittedActions) return false;
  const fullId = `action:${props.jurisdiction}:${actionId}`;
  return props.userCommittedActions.has(actionId) || props.userCommittedActions.has(fullId);
}

// Fetch actions for the initiative
async function fetchActions() {
  loading.value = true;
  error.value = null;

  try {
    actions.value = await api.getCivicActionsForInitiative(props.initiativeId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load actions';
    actions.value = [];
  } finally {
    loading.value = false;
  }
}

// Handle sign request from ActionFlow
function handleSignRequest(actionId: string, jurisdiction: string) {
  emit('sign-request', actionId, jurisdiction);
}

// Handle commitment from ActionFlow
function handleCommitted(actionId: string) {
  emit('committed', actionId);
}

// Called by parent after successful signing
function onSigningComplete(actionId: string, signature: string) {
  const actionFlow = actionFlowRefs.value.get(actionId);
  if (actionFlow) {
    actionFlow.onSigningComplete(signature);
  }
}

// Called by parent if signing fails
function onSigningFailed(actionId: string, errorMessage: string) {
  const actionFlow = actionFlowRefs.value.get(actionId);
  if (actionFlow) {
    actionFlow.onSigningFailed(errorMessage);
  }
}

// Register ActionFlow ref
function setActionFlowRef(actionId: string, el: InstanceType<typeof ActionFlow> | null) {
  if (el) {
    actionFlowRefs.value.set(actionId, el);
  } else {
    actionFlowRefs.value.delete(actionId);
  }
}

// Expose methods for parent
defineExpose({
  onSigningComplete,
  onSigningFailed,
  refresh: fetchActions
});

// Computed: has actions
const hasActions = computed(() => actions.value.length > 0);

// Lifecycle
onMounted(fetchActions);
watch(() => props.initiativeId, fetchActions);
</script>

<template>
  <div class="action-list">
    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>Loading actions...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="error-state">
      <p class="error-message">{{ error }}</p>
      <button class="retry-button" @click="fetchActions">Try again</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="!hasActions" class="empty-state">
      <p>No actions available for this initiative yet.</p>
    </div>

    <!-- Actions list -->
    <div v-else class="actions-container">
      <div class="actions-header">
        <span class="actions-count">{{ actions.length }} action{{ actions.length !== 1 ? 's' : '' }}</span>
      </div>

      <div class="actions-grid">
        <ActionFlow
          v-for="action in actions"
          :key="action.id"
          :ref="(el) => setActionFlowRef(action.id, el as InstanceType<typeof ActionFlow>)"
          :action="toInitiativeAction(action)"
          :jurisdiction="jurisdiction"
          :user-public-key="userPublicKey"
          :user-committed="isCommitted(action.id)"
          @sign-request="handleSignRequest"
          @committed="handleCommitted"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.action-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px;
  color: var(--text-secondary, #666);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-color, #e0e0e0);
  border-top-color: var(--accent-blue, #3b82f6);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px;
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
}

.error-message {
  color: var(--accent-red, #ef4444);
  margin: 0;
  font-size: 14px;
}

.retry-button {
  padding: 8px 16px;
  border: 1px solid var(--accent-blue, #3b82f6);
  border-radius: 6px;
  background: transparent;
  color: var(--accent-blue, #3b82f6);
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.retry-button:hover {
  background: rgba(59, 130, 246, 0.1);
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--text-secondary, #666);
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.actions-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.actions-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #666);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.actions-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>

<script setup lang="ts">
/**
 * ActionFlow Component
 *
 * Displays action progress and handles the commitment flow:
 * 1. Shows progress (e.g., "6/10 committed")
 * 2. User clicks to commit
 * 3. Calls Personal MCP to sign commitment
 * 4. Broadcasts signed event to relay
 * 5. Shows attribution after commitment
 *
 * Part of the Edge Intelligence action flow integration.
 */
import { ref, computed, onMounted, watch } from 'vue';
import { api } from '@/services/api';
import type { ActionCountResponse, InitiativeAction } from '@/types/civic';

const props = defineProps<{
  /** Action item from initiative */
  action: InitiativeAction;
  /** Jurisdiction ID for the action */
  jurisdiction: string;
  /** User's public key (if signed in) */
  userPublicKey?: string;
  /** Whether the user has already committed */
  userCommitted?: boolean;
}>();

const emit = defineEmits<{
  /** Emitted when user successfully commits */
  (e: 'committed', actionId: string): void;
  /** Emitted when signing is requested (parent handles MCP interaction) */
  (e: 'sign-request', actionId: string, jurisdiction: string): void;
}>();

// State
const counts = ref<ActionCountResponse | null>(null);
const loading = ref(false);
const committing = ref(false);
const error = ref<string | null>(null);
const hasCommitted = ref(props.userCommitted ?? false);

// Computed action ID
const actionId = computed(() => {
  return `action:${props.jurisdiction}:${props.action.id}`;
});

// Progress display
const progressText = computed(() => {
  if (!counts.value) return 'Loading...';
  const committed = counts.value.commitments;
  const target = counts.value.target ?? props.action.target_count;
  if (target) {
    return `${committed}/${target} committed`;
  }
  return `${committed} committed`;
});

const progressPercent = computed(() => {
  if (!counts.value) return 0;
  const target = counts.value.target ?? props.action.target_count;
  if (!target || target === 0) return 0;
  return Math.min(100, (counts.value.commitments / target) * 100);
});

const completionText = computed(() => {
  if (!counts.value) return '';
  const completions = counts.value.completions;
  if (completions === 0) return '';
  return `${completions} completed`;
});

// Deadline display
const deadlineText = computed(() => {
  if (!props.action.deadline) return null;
  const deadline = new Date(props.action.deadline);
  const now = new Date();
  const diffDays = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return 'Deadline passed';
  if (diffDays === 0) return 'Due today';
  if (diffDays === 1) return 'Due tomorrow';
  if (diffDays <= 7) return `${diffDays} days left`;

  return `Due ${deadline.toLocaleDateString()}`;
});

const isUrgent = computed(() => {
  if (!props.action.deadline) return false;
  const deadline = new Date(props.action.deadline);
  const now = new Date();
  const diffDays = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  return diffDays >= 0 && diffDays <= 3;
});

// Fetch counts
async function fetchCounts() {
  loading.value = true;
  error.value = null;

  try {
    counts.value = await api.getActionCounts(
      actionId.value,
      props.action.target_count
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load counts';
    counts.value = {
      action_id: actionId.value,
      commitments: 0,
      completions: 0,
      target: props.action.target_count
    };
  } finally {
    loading.value = false;
  }
}

// Handle commit button click
async function handleCommit() {
  if (!props.userPublicKey) {
    error.value = 'Please sign in to commit';
    return;
  }

  committing.value = true;
  error.value = null;

  // Emit sign request - parent component handles MCP interaction
  emit('sign-request', actionId.value, props.jurisdiction);
}

// Called by parent after successful signing
async function onSigningComplete(signature: string) {
  try {
    await api.commitAction({
      action_id: actionId.value,
      public_key: props.userPublicKey!,
      signature
    });

    hasCommitted.value = true;
    emit('committed', actionId.value);

    // Refresh counts
    await fetchCounts();
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to submit commitment';
  } finally {
    committing.value = false;
  }
}

// Called by parent if signing fails
function onSigningFailed(errorMessage: string) {
  error.value = errorMessage;
  committing.value = false;
}

// Expose methods for parent
defineExpose({
  onSigningComplete,
  onSigningFailed
});

// Lifecycle
onMounted(fetchCounts);
watch(() => props.action.id, fetchCounts);
watch(() => props.userCommitted, (val) => {
  hasCommitted.value = val ?? false;
});
</script>

<template>
  <div class="action-flow" :class="{ urgent: isUrgent, committed: hasCommitted }">
    <!-- Action header -->
    <div class="action-header">
      <span class="action-type">{{ action.action_type }}</span>
      <span v-if="deadlineText" class="action-deadline" :class="{ urgent: isUrgent }">
        {{ deadlineText }}
      </span>
    </div>

    <!-- Action description -->
    <p class="action-description">{{ action.description }}</p>

    <!-- Progress bar -->
    <div class="progress-section">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
      </div>
      <div class="progress-stats">
        <span class="commit-count">{{ progressText }}</span>
        <span v-if="completionText" class="completion-count">{{ completionText }}</span>
      </div>
    </div>

    <!-- Action button or status -->
    <div class="action-footer">
      <template v-if="hasCommitted">
        <div class="committed-badge">
          <span class="check-icon">&#10003;</span>
          You're committed
        </div>
        <p v-if="action.template" class="template-hint">
          Template and instructions available
        </p>
      </template>

      <template v-else>
        <button
          class="commit-button"
          :disabled="!userPublicKey || committing || loading"
          @click="handleCommit"
        >
          <span v-if="committing" class="spinner"></span>
          <span v-else>Commit to this action</span>
        </button>
        <p v-if="!userPublicKey" class="sign-in-hint">
          Sign in to commit
        </p>
      </template>
    </div>

    <!-- Error display -->
    <p v-if="error" class="error-message">{{ error }}</p>
  </div>
</template>

<style scoped>
.action-flow {
  padding: 16px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-secondary, #fafafa);
}

.action-flow.urgent {
  border-color: var(--accent-orange, #f97316);
  background: rgba(249, 115, 22, 0.05);
}

.action-flow.committed {
  border-color: var(--accent-green, #22c55e);
  background: rgba(34, 197, 94, 0.05);
}

.action-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.action-type {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary, #666);
  background: var(--bg-tertiary, #f0f0f0);
  padding: 2px 8px;
  border-radius: 4px;
}

.action-deadline {
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.action-deadline.urgent {
  color: var(--accent-orange, #f97316);
  font-weight: 600;
}

.action-description {
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-primary, #333);
  margin: 0 0 12px 0;
}

.progress-section {
  margin-bottom: 12px;
}

.progress-bar {
  height: 8px;
  background: var(--bg-tertiary, #e0e0e0);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 6px;
}

.progress-fill {
  height: 100%;
  background: var(--accent-blue, #3b82f6);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.action-flow.committed .progress-fill {
  background: var(--accent-green, #22c55e);
}

.progress-stats {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary, #666);
}

.commit-count {
  font-weight: 600;
}

.action-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.commit-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  background: var(--accent-blue, #3b82f6);
  color: white;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.commit-button:hover:not(:disabled) {
  background: var(--accent-blue-dark, #2563eb);
}

.commit-button:disabled {
  background: var(--bg-tertiary, #e0e0e0);
  color: var(--text-secondary, #999);
  cursor: not-allowed;
}

.committed-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--accent-green, #22c55e);
  color: white;
  font-size: 14px;
  font-weight: 600;
  border-radius: 6px;
}

.check-icon {
  font-size: 16px;
}

.sign-in-hint,
.template-hint {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin: 0;
  text-align: center;
}

.error-message {
  font-size: 12px;
  color: var(--accent-red, #ef4444);
  margin: 8px 0 0 0;
  text-align: center;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

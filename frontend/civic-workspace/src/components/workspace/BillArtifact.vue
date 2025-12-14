<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { StateBill } from '@/types/civic';
import { useContextStore } from '@/stores/context';
import { createBillContext } from '@/utils/contextHelpers';
import { ArtifactIds } from '@/utils/artifactIds';

const props = defineProps<{
  bill: StateBill
}>()

const emit = defineEmits<{
  'close': []
}>()

const contextStore = useContextStore();
const contextId = ref<string>();

function copyLink() {
  navigator.clipboard.writeText(props.bill.official_url)
  alert('Bill link copied to clipboard!')
}

// Register context on mount
onMounted(async () => {
  const contextElement = await createBillContext(
    props.bill,
    ArtifactIds.bill(props.bill), // Centralized ID generation (Session 53.5)
    'secondary' // Secondary: User actively opened this bill for research
  );
  contextId.value = contextStore.register(contextElement);
  console.log('[BillArtifact] Context registered:', contextId.value);
});

// Session 54: Context persists when tab closes (removed onUnmounted hook)
// Context is now only removed via explicit "X" button in ContextIndicator
// This enables multi-document workflows (e.g., keep bill in context while drafting)
</script>

<template>
  <div class="bill-artifact">
    <!-- Header -->
    <div class="artifact-header">
      <div class="header-left">
        <button class="back-button" @click="emit('close')" title="Back to legislative context">
          ← Back
        </button>
        <h2 class="artifact-title">{{ bill.bill }}</h2>
      </div>
      <button class="close-button" @click="emit('close')" title="Close">
        ✕
      </button>
    </div>

    <!-- Content -->
    <div class="artifact-body">
      <!-- Status Badge -->
      <div class="artifact-badges">
        <span class="status-badge" :class="{ active: bill.status === 'Active' }">
          {{ bill.status }}
        </span>
      </div>

      <!-- Bill Title -->
      <div class="content-section">
        <h3 class="section-title">
          <span class="section-icon">📜</span>
          Bill Title
        </h3>
        <p class="section-content bill-title-text">{{ bill.title }}</p>
      </div>

      <!-- Summary -->
      <div v-if="bill.summary" class="content-section highlight">
        <h3 class="section-title">
          <span class="section-icon">📝</span>
          Summary
        </h3>
        <p class="section-content">{{ bill.summary }}</p>
      </div>

      <!-- Leverage Point -->
      <div class="content-section leverage-section">
        <h3 class="section-title">
          <span class="section-icon">💡</span>
          How Residents Can Influence
        </h3>
        <p class="section-content">{{ bill.leverage_point }}</p>
      </div>

      <!-- Keywords -->
      <div v-if="bill.keywords && bill.keywords.length > 0" class="content-section">
        <h3 class="section-title">
          <span class="section-icon">🏷️</span>
          Keywords
        </h3>
        <div class="keywords">
          <span v-for="keyword in bill.keywords" :key="keyword" class="keyword-tag">
            {{ keyword }}
          </span>
        </div>
      </div>

      <!-- Related Events (Placeholder - Future Enhancement) -->
      <div class="content-section">
        <h3 class="section-title">
          <span class="section-icon">📅</span>
          Related Events
        </h3>
        <p class="empty-message">
          Related events will appear here when available
        </p>
      </div>

      <!-- Action Buttons -->
      <div class="action-buttons">
        <a :href="bill.official_url" target="_blank" class="action-button primary">
          <span class="button-icon">🔗</span>
          View Official Text
        </a>
        <button class="action-button secondary" @click="copyLink">
          <span class="button-icon">📋</span>
          Copy Link
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bill-artifact {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--background-secondary);
}

/* Header */
.artifact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
  gap: var(--space-md);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex: 1;
  min-width: 0;
}

.back-button {
  display: flex;
  align-items: center;
  padding: var(--space-xs) var(--space-sm);
  background: transparent;
  color: var(--primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.back-button:hover {
  background: var(--primary-light);
  border-color: var(--primary);
}

.artifact-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.close-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  font-size: 18px;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.close-button:hover {
  background: var(--error);
  color: white;
  border-color: var(--error);
}

/* Body */
.artifact-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xl);
}

/* Badges */
.artifact-badges {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.status-badge {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  background: var(--background-secondary);
  color: var(--text-secondary);
}

.status-badge.active {
  background: var(--accent-green);
  color: white;
}

/* Content Sections */
.content-section {
  margin-bottom: var(--space-xl);
}

.content-section.highlight {
  padding: var(--space-lg);
  background: var(--background-secondary);
  border-radius: var(--radius-base);
  border: 1px solid var(--border);
}

.leverage-section {
  padding: var(--space-lg);
  background: var(--primary-light);
  border-left: 4px solid var(--primary);
  border-radius: var(--radius-base);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-md) 0;
}

.section-icon {
  font-size: 20px;
}

.section-content {
  font-size: var(--font-size-base);
  color: var(--text-primary);
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
}

.bill-title-text {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--primary);
}

/* Keywords */
.keywords {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.keyword-tag {
  background: var(--primary-light);
  color: var(--primary);
  padding: 4px 10px;
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

/* Empty Message */
.empty-message {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  font-style: italic;
  margin: 0;
}

/* Action Buttons */
.action-buttons {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-md);
  padding-top: var(--space-lg);
  border-top: 2px solid var(--border);
  margin-top: var(--space-xl);
}

.action-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
  white-space: nowrap;
}

.action-button.primary {
  background: var(--primary);
  color: white;
  border: 2px solid var(--primary);
}

.action-button.primary:hover {
  background: var(--accent-purple);
  border-color: var(--accent-purple);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.action-button.secondary {
  background: var(--background);
  color: var(--primary);
  border: 2px solid var(--primary);
}

.action-button.secondary:hover {
  background: var(--primary);
  color: white;
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}

.button-icon {
  font-size: 18px;
}

/* Responsive */
@media (max-width: 768px) {
  .artifact-body {
    padding: var(--space-lg) var(--space-md);
  }

  .artifact-header {
    padding: var(--space-md);
  }

  .header-left {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-sm);
  }

  .artifact-title {
    white-space: normal;
  }

  .action-buttons {
    grid-template-columns: 1fr;
  }
}
</style>

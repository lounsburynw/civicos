<script setup lang="ts">
/**
 * TemplateView Component
 *
 * Displays action templates for committed actions:
 * 1. Shows template text with formatting
 * 2. Parses {{placeholder}} for editable fields
 * 3. Copy-to-clipboard functionality
 * 4. Optional download as text
 *
 * Part of the action flow: User commits → See template → Take action
 */
import { ref, computed, watch } from 'vue';
import { Copy, Check, Download, ChevronDown, ChevronUp } from 'lucide-vue-next';

interface Props {
  /** Template text with optional {{placeholder}} tokens */
  template: string;
  /** Additional instructions (shown separately) */
  instructions?: string;
  /** Pre-fill values from user context */
  prefill?: Record<string, string>;
}

const props = defineProps<Props>();

// State
const expanded = ref(true);
const copied = ref(false);
const editedValues = ref<Record<string, string>>({});

// Parse placeholders from template (e.g., {{name}}, {{address}})
const placeholders = computed(() => {
  const matches = props.template.match(/\{\{(\w+)\}\}/g) || [];
  return [...new Set(matches.map(m => m.slice(2, -2)))];
});

// Initialize edited values from prefill or empty
watch(() => [props.template, props.prefill], () => {
  const values: Record<string, string> = {};
  for (const key of placeholders.value) {
    values[key] = props.prefill?.[key] || editedValues.value[key] || '';
  }
  editedValues.value = values;
}, { immediate: true });

// Template with placeholders filled in
const filledTemplate = computed(() => {
  let result = props.template;
  for (const key of placeholders.value) {
    const value = editedValues.value[key] || `[${key.toUpperCase()}]`;
    result = result.replace(new RegExp(`\\{\\{${key}\\}\\}`, 'g'), value);
  }
  return result;
});

// Human-readable labels for common placeholders
const labelFor = (key: string): string => {
  const labels: Record<string, string> = {
    name: 'Your Name',
    address: 'Address',
    email: 'Email',
    phone: 'Phone',
    neighborhood: 'Neighborhood',
    city: 'City',
    date: 'Date',
    subject: 'Subject'
  };
  return labels[key] || key.charAt(0).toUpperCase() + key.slice(1);
};

// Copy to clipboard
async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(filledTemplate.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 2000);
  } catch (err) {
    console.error('Failed to copy:', err);
  }
}

// Download as text file
function downloadTemplate() {
  const blob = new Blob([filledTemplate.value], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'action-template.txt';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Toggle expand/collapse
function toggle() {
  expanded.value = !expanded.value;
}
</script>

<template>
  <div class="template-view">
    <!-- Header with toggle -->
    <div class="template-header" @click="toggle">
      <span class="template-title">Template</span>
      <component :is="expanded ? ChevronUp : ChevronDown" :size="16" class="toggle-icon" />
    </div>

    <!-- Content (collapsible) -->
    <div class="template-content" :class="{ collapsed: !expanded }">
      <!-- Editable fields (if placeholders exist) -->
      <div v-if="placeholders.length > 0" class="fields-section">
        <div class="fields-hint">Fill in your details:</div>
        <div class="fields-grid">
          <div v-for="key in placeholders" :key="key" class="field-row">
            <label :for="`field-${key}`" class="field-label">{{ labelFor(key) }}</label>
            <input
              :id="`field-${key}`"
              v-model="editedValues[key]"
              type="text"
              class="field-input"
              :placeholder="`Enter ${labelFor(key).toLowerCase()}`"
            />
          </div>
        </div>
      </div>

      <!-- Template text -->
      <div class="template-text">
        <pre>{{ filledTemplate }}</pre>
      </div>

      <!-- Instructions (if provided) -->
      <div v-if="instructions" class="instructions-section">
        <div class="instructions-label">Instructions</div>
        <p class="instructions-text">{{ instructions }}</p>
      </div>

      <!-- Actions -->
      <div class="template-actions">
        <button class="action-button" @click="copyToClipboard">
          <component :is="copied ? Check : Copy" :size="14" />
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
        <button class="action-button secondary" @click="downloadTemplate">
          <Download :size="14" />
          Download
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.template-view {
  margin-top: 12px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  background: var(--bg-primary, #fff);
  overflow: hidden;
}

.template-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-secondary, #f9f9f9);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.template-header:hover {
  background: var(--bg-tertiary, #f0f0f0);
}

.template-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.toggle-icon {
  color: var(--text-secondary, #666);
}

.template-content {
  max-height: 600px;
  overflow-y: auto;
  transition: max-height 0.3s ease, opacity 0.3s ease;
  opacity: 1;
}

.template-content.collapsed {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
}

/* Fields section */
.fields-section {
  padding: 14px;
  border-bottom: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-secondary, #f9f9f9);
}

.fields-hint {
  font-size: 12px;
  color: var(--text-secondary, #666);
  margin-bottom: 10px;
}

.fields-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #666);
}

.field-input {
  padding: 8px 10px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  font-size: 14px;
  background: var(--bg-primary, #fff);
  transition: border-color 0.15s;
}

.field-input:focus {
  outline: none;
  border-color: var(--accent-blue, #3b82f6);
}

.field-input::placeholder {
  color: var(--text-muted, #999);
}

/* Template text */
.template-text {
  padding: 14px;
}

.template-text pre {
  margin: 0;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--text-primary, #333);
}

/* Instructions */
.instructions-section {
  padding: 12px 14px;
  background: var(--bg-secondary, #f9f9f9);
  border-top: 1px solid var(--border-color, #e0e0e0);
}

.instructions-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary, #666);
  margin-bottom: 6px;
}

.instructions-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary, #333);
  margin: 0;
}

/* Actions */
.template-actions {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--border-color, #e0e0e0);
  background: var(--bg-secondary, #f9f9f9);
}

.action-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--accent-blue, #3b82f6);
  color: white;
}

.action-button:hover {
  background: var(--accent-blue-dark, #2563eb);
}

.action-button.secondary {
  background: transparent;
  border: 1px solid var(--border-color, #ddd);
  color: var(--text-primary, #333);
}

.action-button.secondary:hover {
  background: var(--bg-tertiary, #f0f0f0);
  border-color: var(--text-secondary, #999);
}
</style>

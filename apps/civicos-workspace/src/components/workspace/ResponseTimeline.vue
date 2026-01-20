<template>
  <div class="response-timeline">
    <div v-if="loading" class="timeline-loading">
      <div class="loading-spinner"></div>
      <span>Loading timeline...</span>
    </div>

    <div v-else-if="error" class="timeline-error">
      <AlertTriangle :size="16" />
      <span>{{ error }}</span>
    </div>

    <div v-else-if="timeline.length === 0" class="timeline-empty">
      <span>No timeline entries yet</span>
    </div>

    <div v-else class="timeline-entries">
      <div
        v-for="entry in timeline"
        :key="entry.entry_id"
        class="timeline-entry"
        :data-event-type="entry.event_type"
        :data-source="entry.source"
      >
        <div class="timeline-marker">
          <component :is="getEventIcon(entry)" :size="14" class="timeline-icon" />
        </div>
        <div class="timeline-content">
          <div class="timeline-header">
            <div class="timeline-info">
              <span class="timeline-type">{{ formatEventType(entry.event_type) }}</span>
              <span class="timeline-separator">·</span>
              <span class="timeline-description-inline">{{ getDescriptionFirstLine(entry.description) }}</span>
            </div>
            <span class="timeline-timestamp">{{ formatTimestamp(entry.timestamp) }}</span>
          </div>
          <!-- Multi-line description support (for closure notes) -->
          <div v-if="getDescriptionNote(entry.description)" class="timeline-note">
            {{ getDescriptionNote(entry.description) }}
          </div>
          <div v-if="entry.source !== 'user'" class="timeline-source">
            <span class="source-badge">{{ entry.source }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { IssueTimelineEntry } from '@/types/civic'
import { api } from '@/services/api'
import { FileText, RefreshCw, Circle, AlertTriangle, CheckCircle } from 'lucide-vue-next'

const props = defineProps<{
  issueId: string
}>()

const emit = defineEmits<{
  (e: 'loaded', count: number): void;
}>()

const timeline = ref<IssueTimelineEntry[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

onMounted(async () => {
  await loadTimeline()
})

async function loadTimeline() {
  try {
    loading.value = true
    error.value = null
    // Use status history endpoint (filed + status_change only)
    timeline.value = await api.getIssueStatusHistory(props.issueId)

    // Emit count to parent
    emit('loaded', timeline.value.length)
  } catch (err) {
    console.error('Error loading status history:', err)
    error.value = err instanceof Error ? err.message : 'Failed to load status history'
  } finally {
    loading.value = false
  }
}

function getEventIcon(entry: IssueTimelineEntry) {
  // Check description for specific status changes
  if (entry.event_type === 'status_change') {
    const desc = entry.description.toLowerCase()
    if (desc.includes('escalated')) {
      return AlertTriangle
    }
    if (desc.includes('resolved')) {
      return CheckCircle
    }
    return RefreshCw
  }

  // Default icons
  const icons: Record<string, any> = {
    filed: FileText,
  }
  return icons[entry.event_type] || Circle
}

function formatEventType(eventType: string): string {
  const labels: Record<string, string> = {
    filed: 'Filed',
    status_change: 'Status Changed',
  }
  return labels[eventType] || eventType
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  // Format as date
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
  })
}

function getDescriptionFirstLine(description: string): string {
  return description.split('\n')[0]
}

function getDescriptionNote(description: string): string | null {
  const lines = description.split('\n')
  return lines.length > 1 ? lines.slice(1).join('\n') : null
}

// Expose method for parent component to refresh timeline
defineExpose({
  loadTimeline
})
</script>

<style scoped>
/* Response Timeline Styles - Clean & Minimal */

.response-timeline {
  padding: 0;
}

.timeline-loading,
.timeline-error,
.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 13px;
}

.timeline-error {
  color: var(--text-secondary);
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.timeline-entries {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-entry {
  display: flex;
  gap: 12px;
  position: relative;
  padding: 10px 0;
}

/* Connecting line between entries */
.timeline-entry:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 8px; /* Center of marker */
  top: 26px; /* Below marker */
  bottom: 0;
  width: 1px;
  background: var(--border);
  opacity: 0.5;
}

.timeline-marker {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  margin-top: 3px;
}

.timeline-icon {
  color: var(--text-secondary);
  opacity: 0.5;
}

.timeline-content {
  flex: 1;
  min-width: 0;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.timeline-info {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.timeline-type {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
  flex-shrink: 0;
}

.timeline-separator {
  color: var(--text-secondary);
  opacity: 0.4;
  font-size: 13px;
}

.timeline-description-inline {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-note {
  margin-top: 6px;
  padding-left: 0;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
  font-style: italic;
  opacity: 0.9;
}

.timeline-timestamp {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  opacity: 0.7;
  flex-shrink: 0;
}

.timeline-source {
  margin-top: 6px;
}

.source-badge {
  display: inline-block;
  padding: 2px 6px;
  font-size: 10px;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  opacity: 0.6;
}

.timeline-entry[data-source="system"] .source-badge {
  color: var(--primary);
  border-color: var(--primary);
  opacity: 0.7;
}

.timeline-entry[data-source="admin"] .source-badge {
  color: var(--text-secondary);
  border-color: var(--border);
  opacity: 0.7;
}
</style>

<template>
  <div class="event-selection-modal" @click.self="$emit('close')">
    <div class="modal-container">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">🔗 Link to Events</h2>
        <p class="modal-subtitle">
          Select civic meetings related to your issue
        </p>
        <button class="close-btn" @click="$emit('close')" title="Close">
          <span class="icon">×</span>
        </button>
      </div>

      <!-- Filters -->
      <div class="filter-section">
        <div class="filter-row">
          <div class="filter-group">
            <label for="search" class="filter-label">Search</label>
            <input
              id="search"
              v-model="searchQuery"
              type="text"
              class="filter-input"
              placeholder="Search by title or description..."
            />
          </div>
        </div>
        <div class="filter-row">
          <div class="filter-group">
            <label for="jurisdiction-filter" class="filter-label">Jurisdiction</label>
            <select id="jurisdiction-filter" v-model="selectedJurisdiction" class="filter-select">
              <option value="">All jurisdictions</option>
              <option v-for="j in jurisdictions" :key="j.id" :value="j.id">
                {{ j.name }}
              </option>
            </select>
          </div>
          <div class="filter-group">
            <label for="type-filter" class="filter-label">Issue Type</label>
            <select id="type-filter" v-model="selectedType" class="filter-select">
              <option value="">All types</option>
              <option value="housing">Housing</option>
              <option value="transportation">Transportation</option>
              <option value="environment">Environment</option>
              <option value="budget">Budget</option>
              <option value="education">Education</option>
              <option value="public_safety">Public Safety</option>
              <option value="community">Community</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Event List -->
      <div class="event-list">
        <div v-if="isLoading" class="loading-state">
          <span class="spinner">⏳</span> Loading events...
        </div>
        <div v-else-if="filteredEvents.length === 0" class="empty-state">
          <span class="icon">🔍</span>
          <p>No events found matching your criteria</p>
        </div>
        <div v-else class="event-cards">
          <div
            v-for="event in filteredEvents"
            :key="event.id"
            class="event-card"
            :class="{
              'already-linked': isAlreadyLinked(event.id),
              'selected': isSelected(event.id)
            }"
            @click="toggleSelection(event.id)"
          >
            <div class="event-card-header">
              <div class="event-checkbox">
                <input
                  type="checkbox"
                  :checked="isSelected(event.id)"
                  :disabled="isAlreadyLinked(event.id)"
                  @click.stop="toggleSelection(event.id)"
                />
              </div>
              <div class="event-info">
                <h3 class="event-title">{{ event.title }}</h3>
                <div class="event-meta">
                  <span class="event-date">📅 {{ formatDate(event.when) }}</span>
                  <span v-if="event.meeting_type" class="event-type">{{ event.meeting_type }}</span>
                </div>
              </div>
              <div v-if="isAlreadyLinked(event.id)" class="linked-badge">
                ✓ Linked
              </div>
            </div>
            <div v-if="event.project_type" class="event-tags">
              <span class="event-tag">
                {{ event.project_type }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="modal-actions">
        <div class="selection-summary">
          {{ selectedEventIds.length }} event{{ selectedEventIds.length !== 1 ? 's' : '' }} selected
        </div>
        <div class="action-buttons">
          <button
            type="button"
            class="btn-secondary"
            @click="$emit('close')"
            :disabled="isLinking"
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn-primary"
            :disabled="selectedEventIds.length === 0 || isLinking"
            @click="handleLinkEvents"
          >
            <span v-if="isLinking">
              <span class="spinner">⏳</span>
              Linking...
            </span>
            <span v-else>
              Link Selected
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { api } from '@/services/api';
import type { Issue, CivicEvent, Jurisdiction } from '@/types/civic';

const props = defineProps<{
  issueId: string;
  alreadyLinkedEventIds: string[];
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'events-linked', updatedComplaint: Issue): void;
}>();

// State
const events = ref<CivicEvent[]>([]);
const jurisdictions = ref<Jurisdiction[]>([]);
const isLoading = ref(true);
const isLinking = ref(false);
const selectedEventIds = ref<string[]>([]);

// Filters
const searchQuery = ref('');
const selectedJurisdiction = ref('');
const selectedType = ref('');

// Computed
const filteredEvents = computed(() => {
  let filtered = events.value;

  // Filter by search query
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase();
    filtered = filtered.filter(event =>
      event.title?.toLowerCase().includes(query) ||
      event.description?.toLowerCase().includes(query)
    );
  }

  // Filter by jurisdiction
  if (selectedJurisdiction.value) {
    filtered = filtered.filter(event =>
      event.jurisdiction?.id === selectedJurisdiction.value
    );
  }

  // Filter by type
  if (selectedType.value) {
    filtered = filtered.filter(event =>
      event.project_type === selectedType.value
    );
  }

  // Sort by date (upcoming first)
  return filtered.sort((a, b) => {
    const dateA = new Date(a.when || '').getTime();
    const dateB = new Date(b.when || '').getTime();
    return dateA - dateB;
  });
});

// Lifecycle
onMounted(async () => {
  await Promise.all([loadEvents(), loadJurisdictions()]);
  isLoading.value = false;
});

// Methods
async function loadEvents() {
  try {
    events.value = await api.getEvents();
  } catch (error) {
    // Silently fail - UI will show empty state
  }
}

async function loadJurisdictions() {
  try {
    jurisdictions.value = await api.getJurisdictions();
  } catch (error) {
    // Silently fail - UI will show empty state
  }
}

function isAlreadyLinked(eventId: string): boolean {
  return props.alreadyLinkedEventIds.includes(eventId);
}

function isSelected(eventId: string): boolean {
  return selectedEventIds.value.includes(eventId);
}

function toggleSelection(eventId: string) {
  // Don't allow selecting already-linked events
  if (isAlreadyLinked(eventId)) {
    return;
  }

  const index = selectedEventIds.value.indexOf(eventId);
  if (index > -1) {
    selectedEventIds.value.splice(index, 1);
  } else {
    selectedEventIds.value.push(eventId);
  }
}

async function handleLinkEvents() {
  if (selectedEventIds.value.length === 0) {
    return;
  }

  isLinking.value = true;

  try {
    const response = await api.linkComplaintToEvents(
      props.issueId,
      selectedEventIds.value
    );

    // Show success message
    alert(`Successfully linked ${response.linked_count} event${response.linked_count !== 1 ? 's' : ''}!`);

    // Emit the full updated complaint
    emit('events-linked', response.complaint);
    emit('close');
  } catch (error: any) {
    alert(error.message || 'Failed to link events. Please try again.');
  } finally {
    isLinking.value = false;
  }
}

function formatDate(dateString: string | undefined): string {
  if (!dateString) return 'Date TBA';

  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  } catch {
    return dateString;
  }
}
</script>

<style scoped>
/* Modal Overlay */
.event-selection-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-md);
}

/* Modal Container */
.modal-container {
  background: var(--background);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  max-width: 800px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.modal-header {
  padding: var(--space-lg);
  border-bottom: 1px solid var(--border);
  position: relative;
}

.modal-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-xs) 0;
}

.modal-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0;
}

.close-btn {
  position: absolute;
  top: var(--space-md);
  right: var(--space-md);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 24px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.close-btn:hover {
  background: var(--hover-bg);
  color: var(--primary);
}

/* Filters */
.filter-section {
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
}

.filter-row {
  display: flex;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-group {
  flex: 1;
  min-width: 0;
}

.filter-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}

.filter-input,
.filter-select {
  width: 100%;
  padding: var(--space-sm);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--background);
  color: var(--text-primary);
  font-size: var(--font-size-base);
  font-family: var(--font-family);
  transition: all var(--transition-fast);
}

.filter-input:focus,
.filter-select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(38, 139, 210, 0.1);
}

/* Event List */
.event-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-md);
  min-height: 300px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--space-sm);
  color: var(--text-secondary);
}

.empty-state .icon {
  font-size: 48px;
}

.event-cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* Event Card */
.event-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  padding: var(--space-md);
  background: var(--background-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.event-card:hover:not(.already-linked) {
  background: var(--hover-bg);
  border-color: var(--primary);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.event-card.selected {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.05);
}

.event-card.already-linked {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--background-extra-light);
}

.event-card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  margin-bottom: var(--space-sm);
}

.event-checkbox input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  margin-top: 2px;
}

.event-checkbox input[type="checkbox"]:disabled {
  cursor: not-allowed;
}

.event-info {
  flex: 1;
  min-width: 0;
}

.event-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-xs) 0;
  line-height: 1.4;
}

.event-meta {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.event-date,
.event-type {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.linked-badge {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--accent-green);
  background: rgba(133, 153, 0, 0.1);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-sm);
  white-space: nowrap;
}

.event-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: var(--space-xs);
}

.event-tag {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  background: var(--background-extra-light);
  padding: 2px var(--space-xs);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

.event-tag-more {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  font-weight: 600;
}

/* Actions */
.modal-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border);
  background: var(--background-secondary);
}

.selection-summary {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-primary);
}

.action-buttons {
  display: flex;
  gap: var(--space-sm);
}

.btn-primary,
.btn-secondary {
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.btn-primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.btn-primary:hover:not(:disabled) {
  background: #1c6fa0;
  border-color: #1c6fa0;
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--background);
  color: var(--text-primary);
  border-color: var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--text-secondary);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.icon {
  font-style: normal;
}

/* Scrollbar */
.event-list::-webkit-scrollbar {
  width: 8px;
}

.event-list::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.event-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-sm);
}

.event-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

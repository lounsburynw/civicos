<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ChevronDown, FileText, CheckCircle2, Trash2 } from 'lucide-vue-next';
import { api } from '../../services/api';

export interface DraftSummary {
  draft_id: string;
  content: string;  // Full content for loading
  content_preview: string;  // Preview for display
  structured_summary: any;
  personal_context: any;
  selected_agenda_items: string[];
  created_at: string;
  updated_at: string;
  submitted: boolean;
  tags?: string[];  // SESSION 48: Topic tags
}

const props = defineProps<{
  drafts: DraftSummary[];
  currentDraftId: string | null;
}>();

const emit = defineEmits<{
  'select-draft': [draftId: string];
  'create-new': [];
  'draft-deleted': [draftId: string];  // SESSION 48: Notify parent of deletion
}>();

const isOpen = ref(false);

function toggleDropdown() {
  isOpen.value = !isOpen.value;
}

function selectDraft(draftId: string) {
  emit('select-draft', draftId);
  isOpen.value = false;
}

function createNewDraft() {
  emit('create-new');
  isOpen.value = false;
}

function formatDraftLabel(draft: DraftSummary): string {
  if (draft.selected_agenda_items.length === 0) {
    return 'General Comment';
  } else if (draft.selected_agenda_items.length === 1) {
    return `Item ${draft.selected_agenda_items[0]}`;
  } else {
    return `Items ${draft.selected_agenda_items.join(', ')}`;
  }
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const secondsAgo = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (secondsAgo < 60) return 'just now';

  const minutesAgo = Math.floor(secondsAgo / 60);
  if (minutesAgo < 60) return `${minutesAgo}m ago`;

  const hoursAgo = Math.floor(minutesAgo / 60);
  if (hoursAgo < 24) return `${hoursAgo}h ago`;

  const daysAgo = Math.floor(hoursAgo / 24);
  return `${daysAgo}d ago`;
}

const currentDraft = computed(() => {
  return props.drafts.find(d => d.draft_id === props.currentDraftId);
});

const currentLabel = computed(() => {
  if (!currentDraft.value) return 'No draft selected';
  return formatDraftLabel(currentDraft.value);
});

// SESSION 48: Tag filtering
const tagFilter = ref('');

const filteredDrafts = computed(() => {
  if (!tagFilter.value) return props.drafts;
  return props.drafts.filter(draft =>
    draft.tags && draft.tags.includes(tagFilter.value)
  );
});

// SESSION 48: Delete draft functionality
const deleteConfirmId = ref<string | null>(null);

function confirmDelete(draftId: string, event: Event) {
  event.stopPropagation();  // Prevent draft selection
  deleteConfirmId.value = draftId;
}

async function deleteDraft(draftId: string) {
  try {
    await api.deleteDraft(draftId);

    // Notify parent component
    emit('draft-deleted', draftId);

    deleteConfirmId.value = null;
    console.log('[DraftPicker] Deleted draft:', draftId);
  } catch (error) {
    console.error('[DraftPicker] Failed to delete draft:', error);
    alert('Failed to delete draft. Please try again.');
  }
}

function cancelDelete() {
  deleteConfirmId.value = null;
}
</script>

<template>
  <div class="draft-picker">
    <button class="draft-picker-trigger" @click="toggleDropdown">
      <FileText :size="16" />
      <span class="draft-count">Your Drafts ({{ drafts.length }})</span>
      <span class="current-label">{{ currentLabel }}</span>
      <ChevronDown :size="16" :class="{ rotated: isOpen }" />
    </button>

    <div v-if="isOpen" class="draft-picker-dropdown">
      <!-- SESSION 48: Tag filter -->
      <div class="tag-filter-section">
        <select v-model="tagFilter" class="tag-filter">
          <option value="">All Topics</option>
          <option value="housing">Housing</option>
          <option value="transportation">Transportation</option>
          <option value="environment">Environment</option>
          <option value="budget">Budget</option>
          <option value="education">Education</option>
          <option value="public_safety">Public Safety</option>
          <option value="labor">Labor</option>
          <option value="health">Health</option>
          <option value="infrastructure">Infrastructure</option>
          <option value="development">Development</option>
          <option value="governance">Governance</option>
        </select>
      </div>

      <div class="draft-list">
        <div
          v-for="draft in filteredDrafts"
          :key="draft.draft_id"
          class="draft-item"
          :class="{ active: draft.draft_id === currentDraftId }"
          @click="selectDraft(draft.draft_id)"
        >
          <div class="draft-item-header">
            <span class="draft-label">{{ formatDraftLabel(draft) }}</span>
            <div class="draft-header-actions">
              <CheckCircle2 v-if="draft.submitted" :size="14" class="submitted-icon" />
              <button
                @click="confirmDelete(draft.draft_id, $event)"
                class="delete-btn"
                title="Delete this draft"
              >
                <Trash2 :size="14" />
              </button>
            </div>
          </div>
          <!-- SESSION 48: Tag chips -->
          <div v-if="draft.tags && draft.tags.length > 0" class="draft-tags">
            <span v-for="tag in draft.tags" :key="tag" :class="`tag tag-${tag}`">
              {{ tag }}
            </span>
          </div>
          <div class="draft-item-meta">
            <span class="draft-time">{{ formatRelativeTime(draft.updated_at) }}</span>
            <span class="draft-preview">{{ draft.content_preview.substring(0, 50) }}...</span>
          </div>
        </div>
      </div>

      <div class="draft-picker-footer">
        <button class="new-draft-btn" @click="createNewDraft">
          + New Draft
        </button>
      </div>
    </div>

    <!-- SESSION 48: Confirmation dialog for deletion -->
    <div v-if="deleteConfirmId" class="delete-confirm-overlay" @click="cancelDelete">
      <div class="delete-confirm-dialog" @click.stop>
        <h4>Delete Draft?</h4>
        <p>This action cannot be undone.</p>
        <div class="dialog-actions">
          <button @click="cancelDelete" class="btn-cancel">Cancel</button>
          <button @click="deleteDraft(deleteConfirmId)" class="btn-delete">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.draft-picker {
  position: relative;
  margin-bottom: 1rem;
}

.draft-picker-trigger {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.75rem 1rem;
  background: var(--color-bg-1);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s ease;
}

.draft-picker-trigger:hover {
  background: var(--color-bg-2);
  border-color: var(--color-accent-cyan);
}

.draft-count {
  font-weight: 600;
  color: var(--color-accent-cyan);
}

.current-label {
  flex: 1;
  text-align: left;
  color: var(--color-text-dim);
  font-size: 0.9rem;
}

.draft-picker-trigger svg:last-child {
  transition: transform 0.2s ease;
}

.draft-picker-trigger svg.rotated {
  transform: rotate(180deg);
}

.draft-picker-dropdown {
  position: absolute;
  top: calc(100% + 0.5rem);
  left: 0;
  right: 0;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  z-index: 1000;
  max-height: 400px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.draft-list {
  overflow-y: auto;
  max-height: 350px;
  background: var(--background);
}

.draft-item {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s ease;
  background: var(--background);
}

.draft-item:hover {
  background: var(--background-secondary);
}

.draft-item.active {
  background: var(--primary-light);
  border-left: 3px solid var(--primary);
}

.draft-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.25rem;
}

.draft-label {
  font-weight: 600;
  color: var(--color-text);
  flex: 1;
}

.draft-header-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.submitted-icon {
  color: var(--color-accent-green);
}

.delete-btn {
  background: none;
  border: none;
  color: var(--color-text-dim);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
}

.delete-btn:hover {
  background: var(--color-accent-red);
  color: white;
}

.draft-item-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.85rem;
  color: var(--color-text-dim);
}

.draft-time {
  font-weight: 500;
}

.draft-preview {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.draft-picker-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-1);
}

.new-draft-btn {
  width: 100%;
  padding: 0.5rem;
  background: var(--color-accent-cyan);
  color: var(--color-bg-0);
  border: none;
  border-radius: 4px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.new-draft-btn:hover {
  background: var(--color-accent-blue);
}

/* SESSION 48: Tag filter section */
.tag-filter-section {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-0);
}

.tag-filter {
  width: 100%;
  padding: 0.5rem;
  background: var(--color-bg-1);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text);
  font-size: 0.9rem;
  cursor: pointer;
}

.tag-filter:focus {
  outline: none;
  border-color: var(--color-accent-cyan);
}

/* SESSION 48: Tag chips */
.draft-tags {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  margin-bottom: 0.25rem;
  flex-wrap: wrap;
}

.tag {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
}

.tag-housing {
  background: var(--color-accent-blue);
  color: white;
}

.tag-transportation {
  background: var(--color-accent-green);
  color: white;
}

.tag-environment {
  background: var(--color-accent-cyan);
  color: var(--color-bg-0);
}

.tag-budget {
  background: var(--color-accent-yellow);
  color: var(--color-bg-0);
}

.tag-education {
  background: var(--color-accent-magenta);
  color: white;
}

.tag-public_safety {
  background: var(--color-accent-red);
  color: white;
}

.tag-labor {
  background: var(--color-accent-violet);
  color: white;
}

.tag-health {
  background: var(--color-accent-orange);
  color: white;
}

.tag-infrastructure {
  background: var(--color-base01);
  color: white;
}

.tag-development {
  background: var(--color-base00);
  color: white;
}

.tag-governance {
  background: var(--color-base1);
  color: var(--color-bg-0);
}

/* SESSION 48: Delete confirmation dialog (FIXED: better visibility) */
.delete-confirm-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(2px);
}

.delete-confirm-dialog {
  background: #fdf6e3;
  border: 2px solid #073642;
  border-radius: 8px;
  padding: 1.5rem;
  min-width: 320px;
  max-width: 400px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.8);
}

.delete-confirm-dialog h4 {
  margin: 0 0 0.75rem 0;
  font-size: 1.2rem;
  color: #073642;
  font-weight: 700;
}

.delete-confirm-dialog p {
  margin: 0 0 1.5rem 0;
  color: #586e75;
  font-size: 0.95rem;
  line-height: 1.5;
}

.dialog-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.btn-cancel,
.btn-delete {
  padding: 0.6rem 1.25rem;
  border: none;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-cancel {
  background: #eee8d5;
  color: #073642;
  border: 1px solid #d3d3d3;
}

.btn-cancel:hover {
  background: #e0d9c7;
}

.btn-delete {
  background: #dc322f;
  color: #fdf6e3;
}

.btn-delete:hover {
  background: #b71c1c;
  transform: scale(1.02);
}
</style>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import type { CivicEvent, ActionableItem } from '@/types/civic';
import { api } from '@/services/api';
import { useUserStore } from '@/stores/user';
import { useWorkspaceStore } from '@/stores/workspace';
import { useDeveloperStore } from '@/stores/developer';
import { Copy, Download, Mail, RefreshCw, CheckCircle } from 'lucide-vue-next';
import PersonalContextForm from '@/components/comment-drafting/PersonalContextForm.vue';
import DraftPicker, { type DraftSummary } from './DraftPicker.vue';
import { debounce } from 'lodash-es';

const props = defineProps<{
  event: CivicEvent;
  selectedAgendaItems?: ActionableItem[] | null;
  allDrafts: DraftSummary[];
}>();

const emit = defineEmits<{
  'draft-updated': [];
}>();

const userStore = useUserStore();
const workspaceStore = useWorkspaceStore();
const developerStore = useDeveloperStore();

// Component state
const draftContent = ref('');
const isLoading = ref(false);
const wordCount = ref(0);
const speakingTime = ref('');
const structuredSummary = ref<{
  tldr: string;
  position: 'support' | 'oppose' | 'neutral' | 'questions';
  key_topics: string[];
  legislative_references: string[];
  primary_archetype?: string;
} | null>(null);
const personalContext = ref<{
  stakes?: string[];
  yearsInArea?: number;
  district?: string;
  expertise?: string;
}>({});
const showPersonalContext = ref(false);
const isLoadingProfile = ref(true);

// Draft persistence state
const draftId = ref<string | null>(null);
const lastSavedAt = ref<Date | null>(null);
const isSubmitted = ref(false);

// Session 68: Developer mode - provider info
const providerUsed = ref<string | null>(null);
const modelUsed = ref<string | null>(null);
const tokensUsed = ref<number | null>(null);

// Selection mismatch detection
const showMismatchBanner = ref(false);
const savedAgendaItems = ref<string[]>([]);

// Per-item memoized generation
const itemSections = ref<Array<{
  item_ref: string;
  item_title: string;
  content: string;
  word_count: number;
}>>([]);
const isRegeneratingItem = ref<string | null>(null);

// Computed properties
const legislativeRefs = computed(() => {
  const refs: string[] = [];

  if (props.selectedAgendaItems && props.selectedAgendaItems.length > 0) {
    props.selectedAgendaItems.forEach(item => {
      if (item.legislative_context) {
        item.legislative_context.state_legislation_refs?.forEach(ref => {
          if (!refs.includes(ref)) refs.push(ref);
        });
        item.legislative_context.federal_program_refs?.forEach(ref => {
          if (!refs.includes(ref)) refs.push(ref);
        });
      }
    });
  } else {
    const stateBills = props.event.legislative_context?.state_legislation || [];
    const federalPrograms = props.event.legislative_context?.federal_programs || [];

    stateBills.forEach((bill: any) => {
      if (bill.bill) refs.push(bill.bill);
    });

    federalPrograms.forEach((program: any) => {
      if (program.program_name) refs.push(program.program_name);
    });
  }

  return refs;
});

const clerkEmail = computed(() => {
  return props.event.contact_info?.email || null;
});

// Session 50: Check if research has been injected
const hasResearchInjected = computed(() => {
  return draftContent.value.includes('**Research Context:**');
});

// Update word count and speaking time
function updateMetrics() {
  wordCount.value = draftContent.value.trim().split(/\s+/).filter(w => w.length > 0).length;
  const mins = wordCount.value / 150;
  if (mins < 1) {
    speakingTime.value = `${Math.round(mins * 60)} seconds`;
  } else {
    speakingTime.value = `${Math.floor(mins)} minute${mins >= 2 ? 's' : ''}`;
  }
}

// Map archetype to stakes
function mapArchetypeToStakes(archetypeName: string): string[] {
  const lowerName = archetypeName.toLowerCase();
  const stakes: string[] = [];

  if (lowerName.includes('parent') || lowerName.includes('guardian')) {
    stakes.push('parent');
  }
  if (lowerName.includes('homeowner') || lowerName.includes('property')) {
    stakes.push('homeowner');
  }
  if (lowerName.includes('renter') || lowerName.includes('tenant')) {
    stakes.push('renter');
  }
  if (lowerName.includes('business') || lowerName.includes('entrepreneur')) {
    stakes.push('business_owner');
  }
  if (lowerName.includes('educator') || lowerName.includes('teacher')) {
    stakes.push('educator');
  }
  if (lowerName.includes('caregiver') || lowerName.includes('care')) {
    stakes.push('caregiver');
  }

  if (stakes.length === 0) {
    stakes.push('community_member');
  }

  return stakes;
}

// Load user profile for personal context
async function loadProfile() {
  try {
    isLoadingProfile.value = true;

    const profile = await api.getUserProfile();

    if (profile.user_id) {
      personalContext.value = {
        stakes: profile.stakes || [],
        yearsInArea: profile.years_in_area,
        district: profile.district || userStore.cityName || '',
        expertise: profile.expertise || ''
      };
    } else {
      const primaryArchetype = userStore.primaryArchetype;
      if (primaryArchetype) {
        personalContext.value = {
          stakes: mapArchetypeToStakes(primaryArchetype.name),
          district: userStore.cityName || ''
        };
      } else {
        personalContext.value = {
          district: userStore.cityName || ''
        };
      }
    }
  } catch (error) {
    console.error('Failed to load profile:', error);
    const primaryArchetype = userStore.primaryArchetype;
    if (primaryArchetype) {
      personalContext.value = {
        stakes: mapArchetypeToStakes(primaryArchetype.name),
        district: userStore.cityName || ''
      };
    }
  } finally {
    isLoadingProfile.value = false;
  }
}

// Helper: Compare two sets of agenda item IDs
function agendaItemsMatch(saved: string[], current: string[] | undefined): boolean {
  if (!current || current.length === 0) {
    return saved.length === 0;
  }

  if (saved.length !== current.length) return false;

  const savedSet = new Set(saved);
  return current.every(item => savedSet.has(item));
}

// Load or generate draft
async function loadOrGenerateDraft() {
  isLoading.value = true;

  try {
    // Get current selection
    const currentSelection = props.selectedAgendaItems?.map(item => item.item_ref) || [];

    // Find exact match across all drafts
    const matchingDraft = props.allDrafts.find(draft =>
      agendaItemsMatch(draft.selected_agenda_items, currentSelection)
    );

    if (matchingDraft) {
      await loadDraftById(matchingDraft.draft_id);
      console.log('[DraftWorkspace] ✅ Found exact match draft:', matchingDraft.draft_id);
    } else {
      console.log('[DraftWorkspace] ❌ No exact match found, generating new draft');
      await generateDraft();
    }
  } catch (error) {
    console.error('Failed to load drafts:', error);
    await generateDraft();
  } finally {
    isLoading.value = false;
  }
}

// Load specific draft by ID
async function loadDraftById(targetDraftId: string) {
  try {
    const targetDraft = props.allDrafts.find(d => d.draft_id === targetDraftId);

    if (!targetDraft) {
      console.error('[DraftWorkspace] Draft not found in allDrafts:', targetDraftId);
      return;
    }

    draftId.value = targetDraft.draft_id;
    draftContent.value = targetDraft.content;
    structuredSummary.value = targetDraft.structured_summary;
    personalContext.value = targetDraft.personal_context || {};
    lastSavedAt.value = new Date(targetDraft.updated_at);
    isSubmitted.value = targetDraft.submitted;
    savedAgendaItems.value = targetDraft.selected_agenda_items || [];
    updateMetrics();
    showMismatchBanner.value = false;
    console.log('[DraftWorkspace] Loaded draft from allDrafts:', targetDraft.draft_id);
  } catch (error) {
    console.error('[DraftWorkspace] Failed to load draft by ID:', error);
    throw error;
  }
}

async function generateDraft() {
  isLoading.value = true;

  try {
    const payload: any = {
      userId: userStore.userId,
      archetypes: userStore.archetypes,
      personalContext: personalContext.value
    };

    if (props.selectedAgendaItems && props.selectedAgendaItems.length > 0) {
      payload.agendaItemIds = props.selectedAgendaItems.map(item => item.item_ref);
    }

    const response = await api.draftComment(props.event.id, payload);

    draftId.value = (response as any).draft_id;
    draftContent.value = response.draft;
    wordCount.value = response.word_count;
    speakingTime.value = response.estimated_speaking_time;
    structuredSummary.value = response.structured_summary || null;
    lastSavedAt.value = new Date();

    // Session 68: Capture provider info for developer mode
    providerUsed.value = (response as any).provider_used || null;
    modelUsed.value = (response as any).model_used || null;
    tokensUsed.value = (response as any).usage?.total_tokens || null;

    savedAgendaItems.value = props.selectedAgendaItems?.map(item => item.item_ref) || [];

    // Session 64: Use structured sections from backend (no regex parsing!)
    if ((response as any).item_sections && (response as any).item_sections.length > 0) {
      itemSections.value = (response as any).item_sections;
      console.log('[DraftWorkspace] Received', itemSections.value.length, 'structured sections from backend');
    } else {
      itemSections.value = [];
      console.log('[DraftWorkspace] No structured sections (single-item or general draft)');
    }

    console.log('[DraftWorkspace] Generated new draft:', draftId.value);

    // Notify parent to reload drafts
    emit('draft-updated');
  } catch (error) {
    console.error('Failed to generate draft:', error);
    draftContent.value = 'Failed to generate draft. Please try again.';
  } finally {
    isLoading.value = false;
  }
}

// Autosave with debounce
const autosave = debounce(async () => {
  if (!draftId.value || !draftContent.value.trim()) return;

  try {
    const response = await api.updateDraft(draftId.value, {
      content: draftContent.value
    });
    lastSavedAt.value = new Date(response.updated_at);
    console.log('[DraftWorkspace] Autosaved draft:', draftId.value);
  } catch (error) {
    console.error('[DraftWorkspace] Autosave failed:', error);
  }
}, 2000);

// Session 50: Research injection from chat
function injectResearchIntoDraft(research: string) {
  console.log('[DraftWorkspace] injectResearchIntoDraft called with:', research.substring(0, 100));
  console.log('[DraftWorkspace] Current draft exists:', !!draftContent.value);

  if (!draftContent.value) {
    // No draft yet - generate one first, then inject
    console.log('[DraftWorkspace] No draft exists, generating with research');
    generateDraftWithResearch(research);
    return;
  }

  // Existing draft - inject research intelligently
  // Strategy: Add as a new paragraph before the closing signature
  console.log('[DraftWorkspace] Injecting into existing draft');

  const lines = draftContent.value.split('\n');
  const closingIndex = lines.findIndex(line =>
    line.includes('Thank you') || line.includes('Sincerely')
  );

  if (closingIndex >= 0) {
    // Inject before closing
    const beforeClosing = lines.slice(0, closingIndex).join('\n');
    const closing = lines.slice(closingIndex).join('\n');

    draftContent.value = `${beforeClosing}

**Research Context:**
${research}

${closing}`;
    console.log('[DraftWorkspace] Injected before closing at line', closingIndex);
  } else {
    // No closing found - append to end
    draftContent.value += `\n\n**Research Context:**\n${research}`;
    console.log('[DraftWorkspace] No closing found, appended to end');
  }

  updateMetrics();
  showToast('Research added to draft!', 'success');
}

async function generateDraftWithResearch(research: string) {
  // First generate the draft normally
  await generateDraft();

  // Then inject the research
  if (draftContent.value) {
    injectResearchIntoDraft(research);
  }
}

// Session 64: Removed regex parsing - backend now returns structured sections

// Regenerate single item
async function regenerateItem(itemRef: string) {
  isRegeneratingItem.value = itemRef;

  try {
    console.log(`[DraftWorkspace] Regenerating item ${itemRef}...`);

    const response = await api.regenerateItemComment(props.event.id, itemRef, {
      userId: userStore.userId,
      archetypes: userStore.archetypes,
      personalContext: personalContext.value
    });

    const sectionIndex = itemSections.value.findIndex(s => s.item_ref === itemRef);
    if (sectionIndex !== -1) {
      itemSections.value[sectionIndex].content = response.content;
      itemSections.value[sectionIndex].word_count = response.word_count;
    }

    rebuildDraftFromSections();

    console.log(`[DraftWorkspace] Regenerated item ${itemRef} (${response.word_count} words)`);
  } catch (error) {
    console.error('[DraftWorkspace] Failed to regenerate item:', error);
    alert('Failed to regenerate item. Please try again.');
  } finally {
    isRegeneratingItem.value = null;
  }
}

// Rebuild full draft from sections
function rebuildDraftFromSections() {
  const lines = draftContent.value.split('\n');
  const introEndIndex = lines.findIndex(line => line.startsWith('**Item'));
  const closingStartIndex = lines.findIndex(line => line.startsWith('Thank you'));

  const intro = lines.slice(0, introEndIndex).join('\n').trim();
  const closing = closingStartIndex >= 0
    ? lines.slice(closingStartIndex).join('\n').trim()
    : 'Thank you for your consideration and service to our community.\n\nSincerely,\n[Your Name]';

  const sections = itemSections.value.map(s =>
    `**Item ${s.item_ref}: ${s.item_title}**\n\n${s.content}`
  ).join('\n\n');

  draftContent.value = `${intro}\n\n${sections}\n\n${closing}`;
  updateMetrics();
}

// Handle manual edits to per-item sections
function onItemContentEdit(itemRef: string) {
  // Update word count for the edited item
  const section = itemSections.value.find(s => s.item_ref === itemRef);
  if (section) {
    section.word_count = section.content.trim().split(/\s+/).length;
  }

  // Rebuild the full draft from edited sections
  rebuildDraftFromSections();
}

// Watch for content changes
watch(draftContent, () => {
  updateMetrics();
  // Session 64: Removed regex parsing - sections come from backend
  autosave();
});

// Session 50: Watch for research content from chat
watch(
  () => workspaceStore.draftResearchContent,
  (researchContent) => {
    console.log('[DraftWorkspace] Watcher fired, researchContent:', researchContent?.substring(0, 100));
    if (researchContent) {
      console.log('[DraftWorkspace] Research content detected, injecting...');
      injectResearchIntoDraft(researchContent);
      workspaceStore.clearDraftResearchContent(); // Clear after injection
    } else {
      console.log('[DraftWorkspace] No research content to inject');
    }
  },
  { immediate: true }
);

// Export actions
function copyToClipboard() {
  navigator.clipboard.writeText(draftContent.value);
  showToast('Draft copied to clipboard!');
}

function downloadDraft() {
  const blob = new Blob([draftContent.value], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `comment-${props.event.id}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Draft downloaded!');
}

function emailDraft() {
  if (!clerkEmail.value) {
    alert('No clerk email available for this event.');
    return;
  }

  const subject = encodeURIComponent(`Public Comment: ${props.event.title}`);
  const body = encodeURIComponent(draftContent.value);
  window.location.href = `mailto:${clerkEmail.value}?subject=${subject}&body=${body}`;
  showToast('Opening email client...');
}

// Draft picker handlers
function handleDraftSelect(targetDraftId: string) {
  loadDraftById(targetDraftId);
}

function handleCreateNewDraft() {
  generateDraft();
}

function handleDraftDeleted(deletedId: string) {
  // If the deleted draft was the current one, clear state
  if (draftId.value === deletedId) {
    draftId.value = null;
    draftContent.value = '';
    structuredSummary.value = null;
  }

  // Notify parent to reload drafts
  emit('draft-updated');
}

// Toast notification system
function showToast(message: string, type: 'success' | 'error' = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    padding: 1rem 1.5rem;
    background: ${type === 'success' ? '#859900' : '#dc322f'};
    color: #fdf6e3;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    z-index: 10000;
    font-weight: 600;
    font-size: 0.95rem;
    opacity: 0;
    transform: translateY(1rem);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  `;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  }, 10);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(1rem)';
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

// Keyboard shortcuts
function handleKeyboard(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault();
    autosave();
  }

  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    if (clerkEmail.value) {
      emailDraft();
    }
  }
}

function formatRelativeTime(date: Date): string {
  const now = new Date();
  const secondsAgo = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (secondsAgo < 60) return 'just now';

  const minutesAgo = Math.floor(secondsAgo / 60);
  if (minutesAgo < 60) return `${minutesAgo}m ago`;

  const hoursAgo = Math.floor(minutesAgo / 60);
  if (hoursAgo < 24) return `${hoursAgo} hour${hoursAgo > 1 ? 's' : ''} ago`;

  const daysAgo = Math.floor(hoursAgo / 24);
  return `${daysAgo} day${daysAgo > 1 ? 's' : ''} ago`;
}

// Initialize on mount
onMounted(async () => {
  await loadProfile();
  await loadOrGenerateDraft();

  document.addEventListener('keydown', handleKeyboard);
});

// Cleanup keyboard shortcuts
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyboard);
});
</script>

<template>
  <div class="draft-workspace">
    <!-- DraftPicker (inline) -->
    <DraftPicker
      v-if="allDrafts.length > 0"
      :drafts="allDrafts"
      :current-draft-id="draftId"
      @select-draft="handleDraftSelect"
      @create-new="handleCreateNewDraft"
      @draft-deleted="handleDraftDeleted"
    />

    <!-- Structured Summary Card -->
    <div v-if="structuredSummary" class="structured-summary-card">
      <div class="tldr-section">
        <span class="tldr-label">TLDR:</span>
        <p class="tldr-text">{{ structuredSummary.tldr }}</p>
      </div>

      <div class="metadata-row">
        <span
          v-if="structuredSummary.position === 'support' || structuredSummary.position === 'oppose'"
          class="position-badge"
          :class="structuredSummary.position"
        >
          {{ structuredSummary.position.charAt(0).toUpperCase() + structuredSummary.position.slice(1) }}
        </span>

        <div v-if="structuredSummary.key_topics.length" class="topics-pills">
          <span
            v-for="topic in structuredSummary.key_topics"
            :key="topic"
            class="topic-pill"
          >
            {{ topic }}
          </span>
        </div>
      </div>
    </div>

    <!-- Draft Editor -->
    <div class="draft-editor-section">
      <div class="draft-header">
        <h3 class="draft-title">Your Comment</h3>

        <!-- Session 50: Research indicator badge -->
        <span v-if="hasResearchInjected" class="research-badge">
          <CheckCircle :size="14" />
          Research added
        </span>

        <div class="draft-meta">
          <span class="word-count">{{ wordCount }} words ({{ speakingTime }})</span>
          <span v-if="lastSavedAt" class="autosave-indicator">
            Saved {{ formatRelativeTime(lastSavedAt) }}
          </span>
        </div>

        <!-- Session 68: Developer mode badge -->
        <div v-if="developerStore.isEnabled && providerUsed" class="dev-badge">
          Dev: {{ providerUsed }}/{{ modelUsed || 'unknown' }} | {{ tokensUsed || 0 }} tokens
          <span v-if="tokensUsed" class="dev-cost">
            (~${{ developerStore.estimateCost(tokensUsed, providerUsed) }})
          </span>
        </div>
      </div>

      <!-- Loading State -->
      <div v-if="isLoading" class="loading-state">
        <RefreshCw :size="24" class="spinner" />
        <p>Generating your draft...</p>
      </div>

      <!-- Multi-item sections with regenerate buttons -->
      <div v-else-if="itemSections.length > 0" class="per-item-draft">
        <div v-for="section in itemSections" :key="section.item_ref" class="item-section">
          <div class="item-section-header">
            <strong>Item {{ section.item_ref }}: {{ section.item_title }}</strong>
            <button
              class="regenerate-btn"
              @click="regenerateItem(section.item_ref)"
              :disabled="isRegeneratingItem === section.item_ref"
            >
              <RefreshCw :size="14" :class="{ 'spinner': isRegeneratingItem === section.item_ref }" />
              Regenerate
            </button>
          </div>
          <textarea
            v-model="section.content"
            class="item-content-editable"
            @input="onItemContentEdit(section.item_ref)"
            rows="4"
          ></textarea>
          <span class="item-word-count">{{ section.word_count }} words</span>
        </div>
      </div>

      <!-- Single draft textarea -->
      <textarea
        v-else
        v-model="draftContent"
        class="draft-textarea"
        :placeholder="isLoading ? 'Generating...' : 'Your comment will appear here...'"
        :disabled="isLoading"
      ></textarea>
    </div>

    <!-- Export Actions -->
    <div class="export-actions">
      <button class="export-btn primary" @click="copyToClipboard" :disabled="!draftContent">
        <Copy :size="16" />
        Copy
      </button>
      <button class="export-btn" @click="downloadDraft" :disabled="!draftContent">
        <Download :size="16" />
        Download
      </button>
      <button class="export-btn" @click="emailDraft" :disabled="!draftContent || !clerkEmail">
        <Mail :size="16" />
        Email to Clerk
      </button>
    </div>

    <!-- Personal Context (collapsible) -->
    <div class="personal-context-section">
      <button
        class="context-toggle"
        @click="showPersonalContext = !showPersonalContext"
      >
        {{ showPersonalContext ? '▼' : '▶' }} Personal Context
      </button>
      <div v-if="showPersonalContext" class="context-content">
        <PersonalContextForm
          v-model="personalContext"
          @update="generateDraft"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.draft-workspace {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  height: 100%;
  overflow-y: auto;
  background: var(--background);
}

/* Structured Summary Card */
.structured-summary-card {
  padding: 1rem;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.tldr-section {
  margin-bottom: 0.75rem;
}

.tldr-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tldr-text {
  margin: 0.25rem 0 0 0;
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.5;
}

.metadata-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.position-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.position-badge.support {
  background: var(--accent-green);
  color: white;
}

.position-badge.oppose {
  background: var(--accent-orange);
  color: white;
}

.topics-pills {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.topic-pill {
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

/* Draft Editor Section */
.draft-editor-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.draft-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Session 50: Research badge */
.research-badge {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.75rem;
  background: var(--accent-green);
  color: white;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.draft-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-size: 13px;
  color: var(--text-secondary);
}

.word-count {
  font-weight: 500;
}

.autosave-indicator {
  color: var(--accent-green);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  color: var(--text-secondary);
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Per-item Draft */
.per-item-draft {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.item-section {
  padding: 1rem;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
}

.item-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  font-size: 14px;
  color: var(--text-primary);
}

.regenerate-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.regenerate-btn:hover {
  background: var(--background);
  color: var(--primary);
  border-color: var(--primary);
}

.regenerate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.item-content {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.item-content-editable {
  width: 100%;
  margin: 0;
  padding: 0.75rem;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  color: var(--text-primary);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  resize: vertical;
  min-height: 80px;
  transition: border-color 0.2s ease;
}

.item-content-editable:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(38, 139, 210, 0.1);
}

.item-word-count {
  display: block;
  margin-top: 0.5rem;
  font-size: 12px;
  color: var(--text-secondary);
}

/* Draft Textarea */
.draft-textarea {
  width: 100%;
  min-height: 400px;
  padding: 1rem;
  font-family: var(--font-mono);
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  resize: vertical;
}

.draft-textarea:focus {
  outline: none;
  border-color: var(--primary);
}

/* Export Actions */
.export-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.export-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.export-btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.export-btn:hover {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.export-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Personal Context */
.personal-context-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.context-toggle {
  background: transparent;
  border: none;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s ease;
}

.context-toggle:hover {
  color: var(--primary);
}

.context-content {
  margin-top: 1rem;
}

/* Session 68: Developer mode badge */
.dev-badge {
  font-size: 11px;
  color: var(--base01);
  font-family: var(--font-mono);
  margin-top: 8px;
  opacity: 0.7;
  padding: 4px 8px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 4px;
  display: inline-block;
}

.dev-cost {
  color: var(--green);
  margin-left: 4px;
}
</style>

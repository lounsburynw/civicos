<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import type { CivicEvent, ActionableItem } from '@/types/civic';
import { api } from '@/services/api';
import { useUserStore } from '@/stores/user';
import { Copy, Download, Mail, FileText, ChevronDown, RefreshCw } from 'lucide-vue-next';
import PersonalContextForm from '@/components/comment-drafting/PersonalContextForm.vue';
import DraftPicker, { type DraftSummary } from './DraftPicker.vue';
import { debounce } from 'lodash-es';

const props = defineProps<{
  event: CivicEvent;
  selectedAgendaItems?: ActionableItem[] | null;
}>();

const emit = defineEmits<{
  'close': [];
}>();

const userStore = useUserStore();

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

// Session 45: Draft persistence state
const draftId = ref<string | null>(null);
const lastSavedAt = ref<Date | null>(null);
const isSubmitted = ref(false);

// Session 45: Selection mismatch detection
const showMismatchBanner = ref(false);
const savedAgendaItems = ref<string[]>([]);  // What the draft was originally for

// Session 46: Multi-draft system
const allDrafts = ref<DraftSummary[]>([]);

// Session 47: Per-item memoized generation
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

  // If specific items are selected, gather their legislative refs
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
    // Otherwise, use event-level legislative context
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

// Format date/time
function formatDateTime(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  });
}

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
      // Fallback to archetype inference
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
    // Use archetype fallback
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

// Auto-generate draft on mount
// Session 45: Load existing draft or generate new one
async function loadOrGenerateDraft() {
  isLoading.value = true;

  try {
    // SESSION 46: Load all drafts for this event
    const draftsResponse = await api.getAllDrafts(props.event.id, userStore.userId);
    allDrafts.value = draftsResponse.drafts;

    // Get current selection
    const currentSelection = props.selectedAgendaItems?.map(item => item.item_ref) || [];

    console.log('[CommentDraft] Looking for match:', {
      currentSelection,
      totalDrafts: allDrafts.value.length,
      draftSelections: allDrafts.value.map(d => ({
        id: d.draft_id.substring(0, 8),
        items: d.selected_agenda_items
      }))
    });

    // SESSION 46: Find exact match across all drafts
    const matchingDraft = allDrafts.value.find(draft =>
      agendaItemsMatch(draft.selected_agenda_items, currentSelection)
    );

    if (matchingDraft) {
      // Load the matching draft
      await loadDraftById(matchingDraft.draft_id);
      console.log('[CommentDraft] ✅ Found exact match draft:', matchingDraft.draft_id);
    } else {
      // No exact match → generate new draft
      console.log('[CommentDraft] ❌ No exact match found, generating new draft');
      await generateDraft();
    }
  } catch (error) {
    console.error('Failed to load drafts:', error);
    // Fall back to generating new draft
    await generateDraft();
  } finally {
    isLoading.value = false;
  }
}

// SESSION 46: Load specific draft by ID (from allDrafts array)
async function loadDraftById(targetDraftId: string) {
  try {
    // Find the draft in our allDrafts array (which has full content)
    const targetDraft = allDrafts.value.find(d => d.draft_id === targetDraftId);

    if (!targetDraft) {
      console.error('[CommentDraft] Draft not found in allDrafts:', targetDraftId);
      return;
    }

    // Load the draft
    draftId.value = targetDraft.draft_id;
    draftContent.value = targetDraft.content;
    structuredSummary.value = targetDraft.structured_summary;
    personalContext.value = targetDraft.personal_context || {};
    lastSavedAt.value = new Date(targetDraft.updated_at);
    isSubmitted.value = targetDraft.submitted;
    savedAgendaItems.value = targetDraft.selected_agenda_items || [];
    updateMetrics();
    showMismatchBanner.value = false;  // Exact match, no mismatch
    console.log('[CommentDraft] Loaded draft from allDrafts:', targetDraft.draft_id);
  } catch (error) {
    console.error('[CommentDraft] Failed to load draft by ID:', error);
    throw error;
  }
}

async function generateDraft() {
  isLoading.value = true;

  try {
    // Build request payload
    const payload: any = {
      userId: userStore.userId,  // Session 41: For tracking
      archetypes: userStore.archetypes,  // Session 41: Privacy Tier 1 - personalized framing
      personalContext: personalContext.value
    };

    // If specific items are selected, pass them as agenda item IDs
    if (props.selectedAgendaItems && props.selectedAgendaItems.length > 0) {
      payload.agendaItemIds = props.selectedAgendaItems.map(item => item.item_ref);
    }

    const response = await api.draftComment(props.event.id, payload);

    draftId.value = (response as any).draft_id;  // Session 45: Backend now returns draft_id
    draftContent.value = response.draft;
    wordCount.value = response.word_count;
    speakingTime.value = response.estimated_speaking_time;
    structuredSummary.value = response.structured_summary || null;  // Session 42: Structured metadata
    lastSavedAt.value = new Date();  // Session 45: Just generated

    // Session 45: Record what this draft is for
    savedAgendaItems.value = props.selectedAgendaItems?.map(item => item.item_ref) || [];

    console.log('[CommentDraft] Generated new draft:', draftId.value);

    // SESSION 46: Reload drafts list after generating new draft
    try {
      const draftsResponse = await api.getAllDrafts(props.event.id, userStore.userId);
      allDrafts.value = draftsResponse.drafts;
    } catch (error) {
      console.error('[CommentDraft] Failed to reload drafts list:', error);
    }
  } catch (error) {
    console.error('Failed to generate draft:', error);
    draftContent.value = 'Failed to generate draft. Please try again.';
  } finally {
    isLoading.value = false;
  }
}

// Session 45: Autosave with debounce
const autosave = debounce(async () => {
  if (!draftId.value || !draftContent.value.trim()) return;

  try {
    const response = await api.updateDraft(draftId.value, {
      content: draftContent.value
    });
    lastSavedAt.value = new Date(response.updated_at);
    console.log('[CommentDraft] Autosaved draft:', draftId.value);
  } catch (error) {
    console.error('[CommentDraft] Autosave failed:', error);
  }
}, 2000);

// Session 47: Parse draft into per-item sections
function parseDraftSections(content: string) {
  // Parse "**Item X.Y: Title**" sections
  const sections: typeof itemSections.value = [];
  const regex = /\*\*Item ([\d.]+): ([^*]+)\*\*\n\n([^*]+?)(?=\n\n\*\*Item|\n\nThank you|$)/gs;

  let match;
  while ((match = regex.exec(content)) !== null) {
    sections.push({
      item_ref: match[1],
      item_title: match[2].trim(),
      content: match[3].trim(),
      word_count: match[3].trim().split(/\s+/).length
    });
  }

  itemSections.value = sections;
  console.log(`[CommentDraft] Parsed ${sections.length} item sections`);
}

// Session 47: Regenerate single item
async function regenerateItem(itemRef: string) {
  isRegeneratingItem.value = itemRef;

  try {
    console.log(`[CommentDraft] Regenerating item ${itemRef}...`);

    const response = await api.regenerateItemComment(props.event.id, itemRef, {
      userId: userStore.userId,
      archetypes: userStore.archetypes,
      personalContext: personalContext.value
    });

    // Update the section
    const sectionIndex = itemSections.value.findIndex(s => s.item_ref === itemRef);
    if (sectionIndex !== -1) {
      itemSections.value[sectionIndex].content = response.content;
      itemSections.value[sectionIndex].word_count = response.word_count;
    }

    // Rebuild full draft from sections
    rebuildDraftFromSections();

    console.log(`[CommentDraft] Regenerated item ${itemRef} (${response.word_count} words)`);
  } catch (error) {
    console.error('[CommentDraft] Failed to regenerate item:', error);
    alert('Failed to regenerate item. Please try again.');
  } finally {
    isRegeneratingItem.value = null;
  }
}

// Session 47: Rebuild full draft from sections
function rebuildDraftFromSections() {
  // Extract intro and closing from current draft
  const lines = draftContent.value.split('\n');
  const introEndIndex = lines.findIndex(line => line.startsWith('**Item'));
  const closingStartIndex = lines.findIndex(line => line.startsWith('Thank you'));

  const intro = lines.slice(0, introEndIndex).join('\n').trim();
  const closing = closingStartIndex >= 0
    ? lines.slice(closingStartIndex).join('\n').trim()
    : 'Thank you for your consideration and service to our community.\n\nSincerely,\n[Your Name]';

  // Rebuild sections
  const sections = itemSections.value.map(s =>
    `**Item ${s.item_ref}: ${s.item_title}**\n\n${s.content}`
  ).join('\n\n');

  draftContent.value = `${intro}\n\n${sections}\n\n${closing}`;
  updateMetrics();
}

// Session 47: Update section content inline (editable content)
function updateSectionContent(itemRef: string, event: Event) {
  const target = event.target as HTMLElement;
  const newContent = target.textContent || '';

  const sectionIndex = itemSections.value.findIndex(s => s.item_ref === itemRef);
  if (sectionIndex !== -1) {
    itemSections.value[sectionIndex].content = newContent;
    itemSections.value[sectionIndex].word_count = newContent.split(/\s+/).length;
  }

  rebuildDraftFromSections();
}

// Watch for content changes to trigger autosave
watch(draftContent, () => {
  updateMetrics();

  // Parse sections if draft contains per-item structure
  if (draftContent.value.includes('**Item')) {
    parseDraftSections(draftContent.value);
  }

  autosave();
});

// Session 45: Keep existing draft (dismiss mismatch banner)
function handleKeepExisting() {
  showMismatchBanner.value = false;
  console.log('[CommentDraft] User chose to keep existing draft');
}

// Session 45: Regenerate for new selection
async function handleRegenerateForNewSelection() {
  showMismatchBanner.value = false;
  await generateDraft();
  console.log('[CommentDraft] Regenerated draft for new selection');
}

// Regenerate with updated personal context
async function handleRegenerate() {
  await generateDraft();
}

// Export actions
async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(draftContent.value);
    alert('Draft copied to clipboard!');
  } catch (error) {
    console.error('Failed to copy to clipboard:', error);
  }
}

function downloadAsTxt() {
  const blob = new Blob([draftContent.value], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `public-comment-${props.event.id}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

async function emailToClerk() {
  if (!clerkEmail.value || !draftId.value) return;

  // Open email client
  const subject = encodeURIComponent(`Public Comment: ${props.event.title}`);
  const body = encodeURIComponent(draftContent.value);
  window.location.href = `mailto:${clerkEmail.value}?subject=${subject}&body=${body}`;

  // Mark as submitted (Session 45)
  try {
    await api.markDraftSubmitted(draftId.value);
    isSubmitted.value = true;
    console.log('[CommentDraft] Marked as submitted:', draftId.value);
  } catch (error) {
    console.error('[CommentDraft] Failed to mark as submitted:', error);
  }
}

// SESSION 46: Handle draft selection from picker
async function handleDraftSelect(targetDraftId: string) {
  console.log('[CommentDraft] User selected draft:', targetDraftId);
  await loadDraftById(targetDraftId);
}

// SESSION 46: Handle new draft creation from picker
async function handleCreateNewDraft() {
  console.log('[CommentDraft] User clicked create new draft');
  showMismatchBanner.value = false;
  await generateDraft();
}

// SESSION 48: Handle draft deletion
function handleDraftDeleted(deletedDraftId: string) {
  console.log('[CommentDraft] Draft deleted:', deletedDraftId);

  // Remove from allDrafts array
  const index = allDrafts.value.findIndex(d => d.draft_id === deletedDraftId);
  if (index !== -1) {
    allDrafts.value.splice(index, 1);
  }

  // If the deleted draft was the current one, clear or load another
  if (draftId.value === deletedDraftId) {
    if (allDrafts.value.length > 0) {
      // Load the most recent remaining draft
      loadDraftById(allDrafts.value[0].draft_id);
    } else {
      // No drafts left, clear state
      draftContent.value = '';
      draftId.value = null;
    }
  }

  showToast('Draft deleted', 'success');
}

// Session 45: Format relative time for save indicator
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const secondsAgo = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (secondsAgo < 10) return 'just now';
  if (secondsAgo < 60) return `${secondsAgo} seconds ago`;

  const minutesAgo = Math.floor(secondsAgo / 60);
  if (minutesAgo < 60) return `${minutesAgo} minute${minutesAgo > 1 ? 's' : ''} ago`;

  const hoursAgo = Math.floor(minutesAgo / 60);
  if (hoursAgo < 24) return `${hoursAgo} hour${hoursAgo > 1 ? 's' : ''} ago`;

  const daysAgo = Math.floor(hoursAgo / 24);
  return `${daysAgo} day${daysAgo > 1 ? 's' : ''} ago`;
}

// SESSION 48: Toast notification system (FIXED: use correct CSS variables)
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

  // Animate in
  setTimeout(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  }, 10);

  // Animate out and remove
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(1rem)';
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

// SESSION 48: Keyboard shortcuts
function handleKeyboard(e: KeyboardEvent) {
  // Cmd/Ctrl + S to save (no toast - autosave indicator already exists)
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault();
    autosave();
  }

  // Cmd/Ctrl + Enter to email
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    if (clerkEmail.value) {
      // TODO: emailDraft() - function moved to DraftWorkspace.vue
      console.log('Email draft keyboard shortcut triggered (not implemented in CommentDraftArtifact)');
    }
  }
}

// Initialize on mount (Session 45: Load or generate)
onMounted(async () => {
  await loadProfile();
  await loadOrGenerateDraft();  // Changed from generateDraft()

  // SESSION 48: Add keyboard shortcuts
  document.addEventListener('keydown', handleKeyboard);
});

// SESSION 48: Cleanup keyboard shortcuts
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyboard);
});
</script>

<template>
  <div class="comment-draft-artifact">
    <!-- Header -->
    <div class="artifact-header">
      <div class="header-content">
        <div class="header-icon">
          <FileText :size="20" />
        </div>
        <div class="header-text">
          <h2 class="artifact-title">Draft Public Comment</h2>
          <p class="event-context">{{ event.title }}</p>
          <p class="meeting-date">{{ formatDateTime(event.when) }}</p>
        </div>
      </div>
      <button class="close-btn" @click="$emit('close')" title="Close">×</button>
    </div>

    <!-- Main Content: Two-column layout -->
    <div class="draft-content">
      <!-- Left: Context Panel (30%) -->
      <aside class="context-panel">
        <div class="context-section">
          <h4>Meeting Context</h4>
          <p class="context-text">{{ event.description || 'No description available' }}</p>
        </div>

        <!-- Selected Agenda Items (if any) -->
        <div v-if="selectedAgendaItems && selectedAgendaItems.length > 0" class="context-section">
          <h4>Selected Items ({{ selectedAgendaItems.length }})</h4>
          <ul class="selected-items-list">
            <li v-for="item in selectedAgendaItems" :key="item.item_ref" class="selected-item">
              <strong>{{ item.item_ref }}:</strong> {{ item.title }}
            </li>
          </ul>
        </div>
        <div v-else class="context-section">
          <h4>Comment Scope</h4>
          <p class="context-text">General comment on meeting (no specific items selected)</p>
        </div>

        <!-- Legislative References (if event has them) -->
        <div v-if="legislativeRefs.length > 0" class="context-section">
          <h4>Related Legislation</h4>
          <ul class="legislative-refs">
            <li v-for="ref in legislativeRefs" :key="ref">{{ ref }}</li>
          </ul>
        </div>

        <!-- Contact Info -->
        <div v-if="event.contact_info" class="context-section">
          <h4>Submit To</h4>
          <p class="contact-info">
            <Mail :size="14" />
            {{ event.contact_info.email }}
          </p>
        </div>
      </aside>

      <!-- Right: Draft Editor (70%) -->
      <main class="editor-panel">
        <!-- SESSION 46: Draft Picker (Multi-Draft System) -->
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
            <!-- Position Badge (only show for clear stances: support/oppose) -->
            <span
              v-if="structuredSummary.position === 'support' || structuredSummary.position === 'oppose'"
              class="position-badge"
              :class="structuredSummary.position"
            >
              {{ structuredSummary.position.charAt(0).toUpperCase() + structuredSummary.position.slice(1) }}
            </span>

            <!-- Key Topics -->
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

        <!-- Session 45: Selection Mismatch Banner -->
        <div v-if="showMismatchBanner" class="mismatch-banner">
          <div class="banner-content">
            <div class="banner-icon">⚠️</div>
            <div class="banner-text">
              <p class="banner-title">Selection mismatch detected</p>
              <p class="banner-description">
                This draft was created for
                <strong>{{ savedAgendaItems.length === 0 ? 'general meeting comment' : `${savedAgendaItems.length} different item(s)` }}</strong>.
                Currently viewing
                <strong>{{ selectedAgendaItems?.length === 0 || !selectedAgendaItems ? 'general meeting' : `${selectedAgendaItems.length} selected item(s)` }}</strong>.
              </p>
            </div>
          </div>
          <div class="banner-actions">
            <button @click="handleKeepExisting" class="btn-secondary">
              Keep Existing Draft
            </button>
            <button @click="handleRegenerateForNewSelection" class="btn-primary">
              Regenerate for Current Selection
            </button>
          </div>
        </div>

        <!-- Draft Display/Editor -->
        <div class="draft-editor">
          <div class="draft-header">
            <div class="header-left">
              <h4>Your Draft</h4>
              <!-- Session 45: Save indicator -->
              <p v-if="isSubmitted" class="save-status submitted">
                ✓ Submitted {{ lastSavedAt ? formatRelativeTime(lastSavedAt) : '' }}
              </p>
              <p v-else-if="lastSavedAt" class="save-status saved">
                ✓ Saved {{ formatRelativeTime(lastSavedAt) }}
              </p>
              <p v-else class="save-status unsaved">
                Unsaved
              </p>
            </div>
            <div class="draft-meta">
              <span>{{ wordCount }} words</span>
              <span>{{ speakingTime }}</span>
            </div>
          </div>
          <div v-if="isLoading" class="loading-indicator">
            <div class="loading-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span class="loading-text">Generating your comment...</span>
          </div>

          <!-- SESSION 47: Organized Sections (per-item display) -->
          <div v-else-if="itemSections.length > 0" class="draft-sections">
            <div
              v-for="section in itemSections"
              :key="section.item_ref"
              class="draft-section"
            >
              <div class="section-header">
                <h4>Item {{ section.item_ref }}: {{ section.item_title }}</h4>
                <div class="section-actions">
                  <span class="word-count">{{ section.word_count }} words</span>
                  <button
                    @click="regenerateItem(section.item_ref)"
                    :disabled="isRegeneratingItem === section.item_ref"
                    class="regenerate-btn"
                    :title="`Regenerate comment for Item ${section.item_ref}`"
                  >
                    <RefreshCw :size="14" :class="{ 'spin': isRegeneratingItem === section.item_ref }" />
                    {{ isRegeneratingItem === section.item_ref ? 'Regenerating...' : 'Regenerate' }}
                  </button>
                </div>
              </div>

              <div
                class="section-content"
                contenteditable
                @blur="updateSectionContent(section.item_ref, $event)"
                v-text="section.content"
              />
            </div>
          </div>

          <!-- Fallback: full draft editor (for backward compatibility or non-organized drafts) -->
          <textarea
            v-else
            v-model="draftContent"
            class="draft-textarea"
            placeholder="Your draft will appear here..."
            @input="updateMetrics"
          ></textarea>
        </div>

        <!-- Collapsible Personal Context (for fine-tuning) -->
        <div class="personal-context-section">
          <button
            class="context-header"
            @click="showPersonalContext = !showPersonalContext"
          >
            <span class="context-label">
              <span>Personal Context</span>
              <span v-if="personalContext.stakes?.length || personalContext.yearsInArea" class="auto-filled-badge">
                Auto-filled
              </span>
            </span>
            <div class="header-actions">
              <button
                v-if="showPersonalContext"
                @click.stop="handleRegenerate"
                :disabled="isLoading"
                class="btn-regenerate"
                title="Regenerate with updated context"
              >
                <RefreshCw :size="14" />
                Regenerate
              </button>
              <ChevronDown
                :size="18"
                :class="['chevron', { expanded: showPersonalContext }]"
              />
            </div>
          </button>

          <transition name="expand">
            <div v-show="showPersonalContext" class="context-content">
              <p class="context-description">
                Edit your personal context below and click "Regenerate" to update the draft.
              </p>
              <PersonalContextForm v-model="personalContext" />
            </div>
          </transition>
        </div>

        <!-- Export Actions -->
        <div class="export-actions">
          <button @click="copyToClipboard" class="btn-export">
            <Copy :size="16" />
            Copy to Clipboard
          </button>
          <button @click="downloadAsTxt" class="btn-export">
            <Download :size="16" />
            Download .txt
          </button>
          <button
            v-if="clerkEmail"
            @click="emailToClerk"
            class="btn-export btn-primary"
          >
            <Mail :size="16" />
            Email to Clerk
          </button>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.comment-draft-artifact {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--base03);
  color: var(--base0);
}

/* Header */
.artifact-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24px;
  border-bottom: 1px solid var(--base02);
  background: var(--base03);
}

.header-content {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.header-icon {
  color: var(--blue);
  margin-top: 4px;
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.artifact-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--base1);
  margin: 0;
}

.event-context {
  font-size: 14px;
  color: var(--base0);
  margin: 0;
}

.meeting-date {
  font-size: 13px;
  color: var(--base01);
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--base01);
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--base02);
  color: var(--base1);
}

/* Main Content Layout */
.draft-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Context Panel (Left 20%) */
.context-panel {
  width: 20%;
  padding: 20px;
  border-right: 1px solid var(--base02);
  overflow-y: auto;
  background: var(--base02);
}

.context-section {
  margin-bottom: 24px;
}

.context-section h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--base01);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 12px 0;
}

.context-text {
  font-size: 14px;
  color: var(--base0);
  line-height: 1.6;
  margin: 0;
}

.selected-items-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.selected-item {
  font-size: 13px;
  color: var(--base0);
  padding: 8px 10px;
  margin-bottom: 6px;
  background: var(--base03);
  border-left: 3px solid var(--primary);
  border-radius: 4px;
  line-height: 1.5;
}

.selected-item:last-child {
  margin-bottom: 0;
}

.selected-item strong {
  color: var(--primary);
  font-weight: 600;
}

.legislative-refs {
  list-style: none;
  padding: 0;
  margin: 0;
}

.legislative-refs li {
  font-size: 14px;
  color: var(--base0);
  padding: 6px 0;
  border-bottom: 1px solid var(--base02);
}

.legislative-refs li:last-child {
  border-bottom: none;
}

.contact-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--base0);
  margin: 0;
}

/* Editor Panel (Right 80%) */
.editor-panel {
  width: 80%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Personal Context Section */
.personal-context-section {
  border-top: 1px solid var(--base02);
  border-bottom: 1px solid var(--base02);
  background: var(--base02);
}

.context-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 16px 24px;
  background: none;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.context-header:hover {
  background: var(--base01-alpha);
}

.context-label {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--base1);
}

.auto-filled-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-regenerate {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--primary);
  border-radius: 4px;
  background: transparent;
  color: var(--primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-regenerate:hover:not(:disabled) {
  background: var(--primary);
  color: var(--base3);
}

.btn-regenerate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chevron {
  color: var(--base01);
  transition: transform 0.2s ease;
}

.chevron.expanded {
  transform: rotate(180deg);
}

.context-content {
  padding: 20px 24px;
  background: var(--base03);
}

.context-description {
  font-size: 13px;
  color: var(--base01);
  margin: 0 0 16px 0;
  font-style: italic;
}

/* Expand Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 600px;
}

/* Draft Editor */
.draft-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--base02);
  min-height: 300px;
}

.draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--base02);
  background: var(--base02);
}

.draft-header .header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.draft-header h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--base1);
  margin: 0;
}

.edit-hint {
  font-size: 12px;
  color: var(--base01);
  margin: 0;
  font-style: italic;
}

/* Session 45: Save indicator styles */
.save-status {
  font-size: 12px;
  margin: 4px 0 0 0;
  font-weight: 500;
}

.save-status.saved {
  color: var(--green);
}

.save-status.unsaved {
  color: var(--orange);
}

.save-status.submitted {
  color: var(--cyan);
  font-weight: 600;
}

/* Session 45: Mismatch banner styles */
.mismatch-banner {
  background: var(--yellow);
  border: 2px solid var(--orange);
  border-radius: 6px;
  padding: 16px;
  margin: 0 8px 16px 8px;
  color: var(--base03);
}

.banner-content {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.banner-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.banner-text {
  flex: 1;
}

.banner-title {
  font-weight: 600;
  font-size: 14px;
  margin: 0 0 6px 0;
  color: var(--base03);
}

.banner-description {
  font-size: 13px;
  margin: 0;
  line-height: 1.5;
  color: var(--base02);
}

.banner-description strong {
  font-weight: 600;
  color: var(--base03);
}

.banner-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn-primary,
.btn-secondary {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-primary {
  background: var(--blue);
  color: var(--base3);
}

.btn-primary:hover {
  background: var(--cyan);
}

.btn-secondary {
  background: transparent;
  color: var(--base02);
  border: 2px solid var(--base02);
}

.btn-secondary:hover {
  background: var(--base02);
  color: var(--yellow);
}

.draft-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: var(--base01);
}

.draft-textarea {
  flex: 1;
  padding: 24px;
  background: var(--base03);
  border: 2px dashed var(--base01);
  border-radius: 4px;
  margin: 8px;
  color: var(--base0);
  font-size: 14px;
  line-height: 1.8;
  font-family: inherit;
  resize: none;
  cursor: text;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.draft-textarea:hover {
  border-color: var(--base00);
  background: var(--base02);
}

.draft-textarea:focus {
  outline: none;
  border: 2px solid var(--blue);
  background: var(--base02);
}

.draft-textarea::placeholder {
  color: var(--base01);
}

/* Session 47: Per-item draft sections */
.draft-sections {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 24px;
  overflow-y: auto;
}

.draft-section {
  border: 1px solid var(--base02);
  border-radius: 8px;
  padding: 1rem;
  background: var(--base03);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  transform: translateY(0);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.draft-section:hover {
  border-color: var(--blue);
  box-shadow: 0 6px 16px rgba(38, 139, 210, 0.2);
  transform: translateY(-4px);
  background: var(--base02);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--base02);
}

.section-header h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--base1);
  font-weight: 600;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.word-count {
  font-size: 0.85rem;
  color: var(--base01);
  font-weight: 500;
}

.regenerate-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  background: var(--base02);
  color: var(--blue);
  border: 1px solid var(--base01);
  border-radius: 4px;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;
}

.regenerate-btn:hover:not(:disabled) {
  background: var(--blue);
  color: var(--base03);
  border-color: var(--blue);
}

.regenerate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.regenerate-btn svg.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.section-content {
  padding: 0.75rem;
  background: var(--base02);
  border-radius: 4px;
  min-height: 80px;
  line-height: 1.6;
  font-size: 0.95rem;
  color: var(--base0);
  cursor: text;
  transition: all 0.2s;
}

.section-content:hover {
  background: var(--base01);
}

.section-content:focus {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
  background: var(--base02);
}

/* Loading Indicator (matches ChatPanel pattern) */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px;
  margin: 8px;
  background: var(--base03);
  border: 2px dashed var(--base01);
  border-radius: 4px;
  color: var(--base01);
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background-color: var(--primary);
  border-radius: 50%;
  animation: pulse 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.loading-text {
  font-size: 14px;
  font-style: italic;
}

/* Structured Summary Card */
.structured-summary-card {
  margin-bottom: 20px;
}

.tldr-section {
  background: var(--background-secondary);
  border: 1px solid var(--base01);
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
}

.tldr-label {
  color: var(--cyan);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: block;
  margin-bottom: 8px;
}

.tldr-text {
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
  margin: 0;
  white-space: pre-line; /* Enable bullet points */
}

.metadata-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.position-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.position-badge.support {
  background: rgba(133, 153, 0, 0.2);
  color: var(--green);
  border: 1px solid var(--green);
}

.position-badge.oppose {
  background: rgba(220, 50, 47, 0.2);
  color: var(--red);
  border: 1px solid var(--red);
}

.position-badge.neutral {
  background: rgba(42, 161, 152, 0.2);
  color: var(--cyan);
  border: 1px solid var(--cyan);
}

.position-badge.questions {
  background: rgba(181, 137, 0, 0.2);
  color: var(--yellow);
  border: 1px solid var(--yellow);
}

.topics-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.topic-pill {
  background: var(--base01);
  color: var(--base1);
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}

/* Export Actions */
.export-actions {
  display: flex;
  gap: 12px;
  padding: 24px;
  background: var(--base02);
}

.btn-export {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: var(--base01);
  border: none;
  border-radius: 4px;
  color: var(--base3);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-export:hover {
  background: var(--base00);
}

.btn-export.btn-primary {
  background: var(--blue);
}

.btn-export.btn-primary:hover {
  background: var(--cyan);
}
</style>

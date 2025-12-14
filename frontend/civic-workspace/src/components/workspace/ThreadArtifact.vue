<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import type { RelatedIssue, CivicEvent } from '@/types/civic';
import { api } from '@/services/api';
import { useWorkspaceStore } from '@/stores/workspace';
import { useContextStore } from '@/stores/context';
import { createThreadContext } from '@/utils/contextHelpers';
import { ArtifactIds } from '@/utils/artifactIds';
import CoordinationChat from './CoordinationChat.vue';
import { Calendar, FileText, Users, MessageCircle, Clock, ArrowRight, AlertTriangle, AlertCircle, ChevronDown, ChevronRight } from 'lucide-vue-next';

interface ThreadInfo {
  thread_id: string;
  focal_type: 'issue' | 'event';
  focal_id: string;
  participant_count: number;
  message_count: number;
  created_at: string;
  last_message_at: string | null;
}

const props = defineProps<{
  threadId: string;
  embedded?: boolean; // When true, hide Related Discussions and optimize for embedded view
}>();

const emit = defineEmits<{
  'close': [];
}>();

// TODO: Replace with actual user ID from auth store
const userId = 'demo_user';
const workspaceStore = useWorkspaceStore();
const contextStore = useContextStore();

// Context registration tracking
const contextId = ref<string>();

// Thread state
const threadInfo = ref<ThreadInfo | null>(null);
const focalPointData = ref<any>(null); // Event or Complaint data
const relatedIssues = ref<RelatedIssue[]>([]); // For event threads
const relatedIssuesForIssue = ref<Array<{ issue_id: string; ai_title: string; short_name: string; description_preview: string; created_at: string; status: string }>>([]);  // For issue threads
const matchedEvents = ref<Array<{ event_id: string; title: string; when: string; match_score: number | null }>>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);

// Reply state (lifted from CoordinationChat to share between message and input instances)
const replyingToMessageId = ref<string | null>(null);

/**
 * Handle reply to message (from messages area)
 */
function handleReplyToMessage(messageId: string) {
  replyingToMessageId.value = messageId;
}

/**
 * Cancel replying to message (from input area)
 */
function handleCancelReply() {
  replyingToMessageId.value = null;
}

/**
 * Handle message sent (from input area) - clear reply state
 */
function handleMessageSent() {
  replyingToMessageId.value = null;
}

// Collapsible section state (default: collapsed)
const matchedEventsExpanded = ref(false);
const relatedIssuesExpanded = ref(false);

// Resizable divider state (for context-area vs messages split)
const DEFAULT_SPLIT_RATIO = 0.20; // 20% top (context), 80% bottom (messages) - fits collapsed Related Discussions
const EMBEDDED_SPLIT_RATIO = 0.12; // 12% top (context), 88% bottom (messages) - for embedded mode (no Related Discussions)
const MIN_TOP_HEIGHT = 150; // Minimum pixels for context area
const MIN_BOTTOM_HEIGHT = 200; // Minimum pixels for messages (input is now separate and always visible)

const splitRatio = ref<number>(props.embedded ? EMBEDDED_SPLIT_RATIO : DEFAULT_SPLIT_RATIO);
const isDragging = ref(false);
const threadContentRef = ref<HTMLElement | null>(null);
const contextAreaRef = ref<HTMLElement | null>(null);
const messagesAreaRef = ref<HTMLElement | null>(null);

// Fetch thread info and focal point data
async function fetchThreadData() {
  isLoading.value = true;
  error.value = null;

  console.log('[ThreadArtifact] Fetching thread data for ID:', props.threadId);

  try {
    // Fetch thread info
    const info = await api.getThreadInfo(props.threadId);
    console.log('[ThreadArtifact] Thread info fetched:', info);
    threadInfo.value = info;

    // Fetch focal point data (event or complaint)
    if (info.focal_type === 'event') {
      // Fetch event data
      const event = await api.getEvent(info.focal_id);
      focalPointData.value = event;

      // Fetch related complaints for event threads
      const messagesResponse = await api.getThreadMessages(props.threadId, userId);
      relatedIssues.value = messagesResponse.related_issues || [];
      console.log('[ThreadArtifact] Related complaints fetched:', relatedIssues.value.length);
    } else if (info.focal_type === 'issue') {
      // Fetch complaint data
      const complaint = await api.getIssue(info.focal_id);
      focalPointData.value = complaint;

      // Fetch matched events for complaint threads
      if (complaint.matched_events && complaint.matched_events.length > 0) {
        // Fetch full event data for each matched event
        const eventPromises = complaint.matched_events.map(async (ref: any) => {
          try {
            const event = await api.getEvent(ref.event_id);
            return {
              event_id: event.id,
              title: event.title,
              when: event.when,
              match_score: ref.match_score
            };
          } catch (err) {
            console.error(`Failed to fetch event ${ref.event_id}:`, err);
            return null;
          }
        });
        const events = await Promise.all(eventPromises);
        matchedEvents.value = events.filter((e): e is NonNullable<typeof e> => e !== null);
        console.log('[ThreadArtifact] Matched events fetched:', matchedEvents.value.length);
      }

      // Fetch related complaints for complaint threads
      if (complaint.related_issues && complaint.related_issues.length > 0) {
        // Fetch full complaint data for each related complaint (excluding current)
        const complaintPromises = complaint.related_issues.slice(0, 5).map(async (issueId: string) => {
          try {
            const relatedIssue = await api.getIssue(issueId);
            return {
              issue_id: relatedIssue.id,
              ai_title: relatedIssue.ai_title || relatedIssue.description.substring(0, 50),
              short_name: relatedIssue.short_name || `Issue #${relatedIssue.id.substring(0, 8)}`,
              description_preview: relatedIssue.description.substring(0, 100) + (relatedIssue.description.length > 100 ? '...' : ''),
              created_at: relatedIssue.created_at,
              status: relatedIssue.status
            };
          } catch (err) {
            console.error(`Failed to fetch related complaint ${issueId}:`, err);
            return null;
          }
        });
        const complaints = await Promise.all(complaintPromises);
        relatedIssuesForIssue.value = complaints.filter((c): c is NonNullable<typeof c> => c !== null);
        console.log('[ThreadArtifact] Related complaints fetched:', relatedIssuesForIssue.value.length);
      }
    }
  } catch (err: any) {
    console.error('Error fetching thread data:', err);
    error.value = err.message || 'Failed to load thread';
  } finally {
    isLoading.value = false;
  }
}

// Format date
function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

// Get focal point title
const focalPointTitle = computed(() => {
  if (!focalPointData.value) return 'Loading...';

  if (threadInfo.value?.focal_type === 'event') {
    return focalPointData.value.title;
  } else if (threadInfo.value?.focal_type === 'issue') {
    // Use ai_title for header display, fallback to truncated description
    // (short_name is used for tab title, but we want the full title in the header)
    return focalPointData.value.ai_title ||
           (focalPointData.value.description?.substring(0, 80) + '...');
  }

  return 'Discussion';
});

// Get focal point subtitle
const focalPointSubtitle = computed(() => {
  if (!focalPointData.value || !threadInfo.value) return '';

  if (threadInfo.value.focal_type === 'event') {
    const event = focalPointData.value as CivicEvent;
    return `${event.jurisdiction.name} • ${formatDate(event.when)}`;
  } else if (threadInfo.value.focal_type === 'issue') {
    const complaint = focalPointData.value;
    return `${complaint.issue_type || 'Issue'} • Filed ${formatDate(complaint.created_at)}`;
  }

  return '';
});

// Open focal point in new tab
function openFocalPoint() {
  if (!threadInfo.value || !focalPointData.value) return;

  // For issues, use short_name for tab title (not the full ai_title)
  let tabTitle = focalPointTitle.value;
  if (threadInfo.value.focal_type === 'issue') {
    tabTitle = focalPointData.value.short_name ||
               focalPointData.value.ai_title ||
               'Issue';
  }

  workspaceStore.openArtifact({
    type: threadInfo.value.focal_type,
    // Centralized ID generation (Session 53.5) - use helper based on type
    id: threadInfo.value.focal_type === 'issue'
      ? ArtifactIds.issue(threadInfo.value.focal_id)
      : ArtifactIds.event(threadInfo.value.focal_id),
    title: tabTitle,
    data: focalPointData.value
  });
}

// Format time ago
function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return '1 day ago';
  return `${diffDays} days ago`;
}

// Open issue in new tab
async function openIssue(issueId: string) {
  try {
    // Fetch full issue data
    const issue = await api.getIssue(issueId);

    const tabTitle = issue.short_name || issue.ai_title || 'Issue';
    console.log('[ThreadArtifact] Opening issue:', {
      id: issue.id,
      short_name: issue.short_name,
      ai_title: issue.ai_title,
      tabTitle: tabTitle
    });

    workspaceStore.openArtifact({
      type: 'issue',
      id: ArtifactIds.issue(issueId), // Centralized ID generation (Session 53.5)
      title: tabTitle,
      data: issue
    });
  } catch (err) {
    console.error('Failed to open issue:', err);
  }
}

// Open event in new tab
async function openEvent(eventId: string) {
  try {
    // Fetch full event data
    const event = await api.getEvent(eventId);

    workspaceStore.openArtifact({
      type: 'event',
      id: ArtifactIds.event(eventId), // Centralized ID generation (Session 53.5)
      title: event.title,
      data: event
    });
  } catch (err) {
    console.error('Failed to open event:', err);
  }
}

// Open discussion thread in new tab
async function openDiscussionThread(focalId: string, focalType: 'event' | 'issue') {
  const stats = discussionThreadStats.value.get(focalId);

  if (!stats?.thread_id) {
    console.error('No thread found for focal point:', focalId);
    return;
  }

  // Fetch the focal point data for the title
  try {
    let title = 'Discussion';
    if (focalType === 'event') {
      const event = await api.getEvent(focalId);
      title = event.title;
    } else if (focalType === 'issue') {
      const issue = await api.getIssue(focalId);
      // Use short_name for issue discussion threads, fallback to ai_title or truncated description
      title = issue.short_name || issue.ai_title || issue.description.substring(0, 40);
    }

    workspaceStore.openArtifact({
      type: 'thread',
      id: ArtifactIds.thread(stats.thread_id), // Centralized ID generation (Session 53.5)
      title: title,
      data: {
        threadId: stats.thread_id,
        focalType: focalType,
        focalId: focalId
      }
    });
  } catch (err) {
    console.error('Failed to open discussion thread:', err);
  }
}

/**
 * Get icon component for discussion type (matches DiscussionsPanel)
 */
function getDiscussionIcon(type: 'event' | 'issue') {
  return type === 'event' ? Calendar : AlertCircle;
}

// Thread stats for related discussions (focal_id -> thread stats + thread_id)
const discussionThreadStats = ref<Map<string, { message_count: number; participant_count: number; last_message_at: string | null; thread_id: string }>>(new Map());

// Unified discussions list (combines events + complaints)
const relatedDiscussions = computed(() => {
  const discussions: Array<{
    id: string;
    type: 'event' | 'issue';
    title: string;
    short_name?: string;
    subtitle: string;
    metadata: string;
    timestamp: Date;
  }> = [];

  // Add matched events as discussions
  matchedEvents.value.forEach(event => {
    discussions.push({
      id: event.event_id,
      type: 'event',
      title: event.title,
      subtitle: formatDate(event.when),
      metadata: event.match_score ? `${event.match_score}% match` : '',
      timestamp: new Date(event.when)
    });
  });

  // Add similar complaints as discussions
  relatedIssuesForIssue.value.forEach(complaint => {
    discussions.push({
      id: complaint.issue_id,
      type: 'issue',
      title: complaint.ai_title || complaint.description_preview, // Use ai_title, fallback to description_preview
      short_name: complaint.short_name, // Include short_name for display
      subtitle: formatTimeAgo(complaint.created_at),
      metadata: '',
      timestamp: new Date(complaint.created_at)
    });
  });

  // Sort by timestamp (most recent first)
  return discussions.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
});

// Fetch thread stats for related discussions
async function fetchDiscussionThreadStats() {
  // Collect all focal points
  const focalPoints = relatedDiscussions.value.map(d => ({ type: d.type, id: d.id }));

  // Fetch thread stats for each focal point
  const statsPromises = focalPoints.map(async ({ type, id }) => {
    try {
      // Get threads and find the one matching this focal point
      const threadsResponse = await api.getThreads({ limit: 100 });
      const thread = threadsResponse.threads.find(t => t.focal_type === type && t.focal_id === id);

      if (thread) {
        return {
          focal_id: id,
          thread_id: thread.thread_id,
          message_count: thread.message_count,
          participant_count: thread.participant_count,
          last_message_at: thread.last_message_at
        };
      }
      return null;
    } catch (err) {
      console.error(`Failed to fetch thread stats for ${type} ${id}:`, err);
      return null;
    }
  });

  const results = await Promise.all(statsPromises);

  // Update the map
  const newMap = new Map();
  results.forEach(result => {
    if (result) {
      newMap.set(result.focal_id, {
        thread_id: result.thread_id,
        message_count: result.message_count,
        participant_count: result.participant_count,
        last_message_at: result.last_message_at
      });
    }
  });

  discussionThreadStats.value = newMap;
}

// Get thread stats for a discussion
function getDiscussionStats(discussionId: string): { message_count: number; participant_count: number; last_message_at: string | null } | null {
  return discussionThreadStats.value.get(discussionId) || null;
}

// Check if a discussion is "hot" (active in last 24 hours)
function isHotDiscussion(discussionId: string): boolean {
  const stats = getDiscussionStats(discussionId);
  if (!stats || !stats.last_message_at) return false;

  const now = new Date();
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const lastActive = new Date(stats.last_message_at);

  return lastActive >= oneDayAgo;
}

// Watch for changes in related discussions and fetch thread stats
watch(relatedDiscussions, async (newDiscussions) => {
  if (newDiscussions.length > 0) {
    await fetchDiscussionThreadStats();
  }
}, { immediate: false });

// Watch for changes in related complaints (for event threads) and fetch thread stats
watch(relatedIssues, async (newComplaints) => {
  if (newComplaints.length > 0) {
    // Fetch thread stats for each complaint
    const statsPromises = newComplaints.map(async (complaint) => {
      try {
        // Get threads and find the one matching this complaint
        const threadsResponse = await api.getThreads({ limit: 100 });
        const thread = threadsResponse.threads.find(t => t.focal_type === 'issue' && t.focal_id === complaint.issue_id);

        if (thread) {
          return {
            focal_id: complaint.issue_id,
            thread_id: thread.thread_id,
            message_count: thread.message_count,
            participant_count: thread.participant_count,
            last_message_at: thread.last_message_at
          };
        }
        return null;
      } catch (err) {
        console.error(`Failed to fetch thread stats for complaint ${complaint.issue_id}:`, err);
        return null;
      }
    });

    const results = await Promise.all(statsPromises);

    // Update the map
    const newMap = new Map(discussionThreadStats.value);
    results.forEach(result => {
      if (result) {
        newMap.set(result.focal_id, {
          thread_id: result.thread_id,
          message_count: result.message_count,
          participant_count: result.participant_count,
          last_message_at: result.last_message_at
        });
      }
    });

    discussionThreadStats.value = newMap;
  }
}, { immediate: false });

// Computed styles for resizable sections (using flex-grow)
const contextAreaStyle = computed(() => ({
  flexGrow: splitRatio.value.toString(),
  flexShrink: '0',
  flexBasis: '0',
  minHeight: `${MIN_TOP_HEIGHT}px`
}));

const messagesAreaStyle = computed(() => ({
  flexGrow: (1 - splitRatio.value).toString(),
  flexShrink: '0',
  flexBasis: '0',
  minHeight: `${MIN_BOTTOM_HEIGHT}px`
}));

/**
 * Start dragging the divider
 */
function startDrag(e: MouseEvent) {
  isDragging.value = true;
  document.body.style.cursor = 'row-resize';
  document.body.style.userSelect = 'none'; // Prevent text selection
  e.preventDefault();
}

/**
 * Handle drag movement
 */
function onDrag(e: MouseEvent) {
  if (!isDragging.value || !threadContentRef.value) return;

  const container = threadContentRef.value;
  const rect = container.getBoundingClientRect();
  const containerHeight = rect.height;
  const mouseY = e.clientY - rect.top;

  // Calculate new ratio
  let newRatio = mouseY / containerHeight;

  // Apply min/max constraints
  const minTopRatio = MIN_TOP_HEIGHT / containerHeight;
  const maxTopRatio = 1 - (MIN_BOTTOM_HEIGHT / containerHeight);
  newRatio = Math.max(minTopRatio, Math.min(maxTopRatio, newRatio));

  splitRatio.value = newRatio;
}

/**
 * Stop dragging and persist preference (manual adjustment only)
 */
function stopDrag() {
  if (!isDragging.value) return;

  isDragging.value = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';

  // Persist manual adjustment to localStorage
  localStorage.setItem('threadArtifact_splitRatio_manual', splitRatio.value.toString());
}

/**
 * Load saved split ratio from localStorage (manual adjustments only)
 * Returns true if a manual adjustment was loaded, false otherwise
 */
function loadSavedSplitRatio(): boolean {
  const saved = localStorage.getItem('threadArtifact_splitRatio_manual');
  if (saved) {
    const ratio = parseFloat(saved);
    if (!isNaN(ratio) && ratio > 0 && ratio < 1) {
      splitRatio.value = ratio;
      return true;
    }
  }
  // No manual adjustment saved
  return false;
}

/**
 * Auto-adjust divider to fit expanded content
 * Called when Related Discussions expands
 *
 * Expands the context area to show ALL Related Discussions items without scrolling,
 * while ensuring messages area never goes below MIN_BOTTOM_HEIGHT (200px).
 * Input box is now separate and always visible at the bottom.
 *
 * @param useRenderedHeight - If true, uses rendered height (for collapsed state). If false, uses scrollHeight (for expanded state).
 */
function autoAdjustDividerForContent(useRenderedHeight = false) {
  if (!threadContentRef.value || !contextAreaRef.value || !messagesAreaRef.value) {
    console.log('[ThreadArtifact] Auto-adjust skipped: refs not ready', {
      threadContent: !!threadContentRef.value,
      contextArea: !!contextAreaRef.value,
      messagesArea: !!messagesAreaRef.value
    });
    return;
  }

  // Wait for DOM to update after expansion
  nextTick(() => {
    // Double nextTick to ensure DOM fully rendered with new content
    nextTick(() => {
      if (!threadContentRef.value || !contextAreaRef.value || !messagesAreaRef.value) return;

      const containerHeight = threadContentRef.value.getBoundingClientRect().height;

      // Calculate actual content height by measuring child elements
      // This gives us the natural height of content, not the flex container's height
      let contentHeight = 0;
      const children = contextAreaRef.value.children;
      for (let i = 0; i < children.length; i++) {
        const child = children[i] as HTMLElement;
        if (useRenderedHeight) {
          // For collapsed state: only count visible elements (respects v-show)
          if (child.offsetHeight > 0) {
            contentHeight += child.offsetHeight;
          }
        } else {
          // For expanded state: use scrollHeight to include all content
          contentHeight += child.scrollHeight || child.offsetHeight;
        }
      }

      const currentMessagesHeight = messagesAreaRef.value.getBoundingClientRect().height; // Current messages height

      console.log('[ThreadArtifact] Auto-adjust measurements:', {
        containerHeight,
        contentHeight,
        currentMessagesHeight,
        currentRatio: splitRatio.value,
        useRenderedHeight,
        childCount: children.length
      });

      // Calculate ideal ratio to fit all content
      let idealRatio = contentHeight / containerHeight;

      // Ensure messages area has minimum usable height
      const maxTopRatioForMinMessages = 1 - (MIN_BOTTOM_HEIGHT / containerHeight);
      idealRatio = Math.min(idealRatio, maxTopRatioForMinMessages);

      // Ensure context has minimum height
      const minTopRatio = MIN_TOP_HEIGHT / containerHeight;
      idealRatio = Math.max(idealRatio, minTopRatio);

      console.log('[ThreadArtifact] Auto-adjust result:', {
        oldRatio: splitRatio.value,
        newRatio: idealRatio,
        idealRatioRaw: contentHeight / containerHeight,
        maxTopForMinMessages: maxTopRatioForMinMessages,
        willShowAllContent: idealRatio >= (contentHeight / containerHeight)
      });

      // Smoothly animate to new ratio (don't save - this is automatic)
      splitRatio.value = idealRatio;
    });
  });
}

/**
 * Reset divider to fit collapsed content
 * Called when Related Discussions collapses
 * Now auto-adjusts to fit collapsed content instead of using fixed default
 */
function resetDividerToDefault() {
  console.log('[ThreadArtifact] Resetting to fit collapsed content:', {
    currentRatio: splitRatio.value
  });

  // Wait for DOM to update (v-show to hide content) before measuring
  // Use rendered height (only visible content) instead of scrollHeight
  nextTick(() => {
    nextTick(() => {
      autoAdjustDividerForContent(true); // true = use rendered height for collapsed state
    });
  });
}

// Watch for Related Discussions expansion/collapse and adjust divider
watch(matchedEventsExpanded, (isExpanded) => {
  console.log('[ThreadArtifact] matchedEventsExpanded changed:', isExpanded);
  if (isExpanded) {
    autoAdjustDividerForContent(false); // false = use scrollHeight to show all expanded content
  } else {
    resetDividerToDefault(); // Move back up to fit collapsed content (flush with bottom)
  }
});

// Watch for Related Complaints expansion/collapse and adjust divider
watch(relatedIssuesExpanded, (isExpanded) => {
  console.log('[ThreadArtifact] relatedIssuesExpanded changed:', isExpanded);
  if (isExpanded) {
    autoAdjustDividerForContent(false); // false = use scrollHeight to show all expanded content
  } else {
    resetDividerToDefault(); // Move back up to fit collapsed content (flush with bottom)
  }
});

onMounted(async () => {
  fetchThreadData();

  // Load saved split ratio (returns true if manual adjustment exists)
  const hasManualAdjustment = loadSavedSplitRatio();

  // Auto-adjust divider to fit initial content (collapsed state)
  // Only if no manual adjustment was saved
  if (!hasManualAdjustment) {
    // Wait for DOM to be fully rendered
    nextTick(() => {
      autoAdjustDividerForContent(true); // true = use rendered height for initial collapsed state
    });
  }

  // Add global drag listeners
  document.addEventListener('mousemove', onDrag);
  document.addEventListener('mouseup', stopDrag);

  // Register context element
  const threadData = {
    id: props.threadId,
    thread_id: props.threadId,
    focal_type: threadInfo.value?.focal_type || 'event',
    focal_id: threadInfo.value?.focal_id || '',
    title: `Discussion Thread`,
    message_count: threadInfo.value?.message_count || 0,
    participant_count: threadInfo.value?.participant_count || 0
  };
  const contextElement = await createThreadContext(
    threadData,
    ArtifactIds.thread(props.threadId), // Centralized ID generation (Session 53.5)
    'secondary'
  );
  contextId.value = contextStore.register(contextElement);
  console.log('[ThreadArtifact] Context registered:', contextId.value);
});

onUnmounted(() => {
  // Cleanup drag listeners
  document.removeEventListener('mousemove', onDrag);
  document.removeEventListener('mouseup', stopDrag);

  // Session 54: Context persists when tab closes (removed context unregister)
  // Context is now only removed via explicit "X" button in ContextIndicator
  // This enables multi-document workflows (e.g., keep thread in context while switching tabs)
});
</script>

<template>
  <div class="thread-artifact">
    <!-- Loading State -->
    <div v-if="isLoading" class="loading-container">
      <div class="loading-spinner"></div>
      <p>Loading discussion...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-container">
      <AlertTriangle :size="48" class="error-icon" />
      <p class="error-message">{{ error }}</p>
      <button @click="fetchThreadData" class="retry-button">Try Again</button>
    </div>

    <!-- Thread Content -->
    <div v-else-if="threadInfo" class="thread-content">
      <!-- Embedded Mode: Simple fixed layout (no divider) -->
      <template v-if="props.embedded">
        <!-- Fixed Stats Header -->
        <div class="embedded-stats-header">
          <span class="stat-item">
            <Users :size="14" class="stat-icon" />
            {{ threadInfo.participant_count }} {{ threadInfo.participant_count === 1 ? 'member' : 'members' }}
          </span>
          <span class="stat-separator">•</span>
          <span class="stat-item">
            <MessageCircle :size="14" class="stat-icon" />
            {{ threadInfo.message_count }} {{ threadInfo.message_count === 1 ? 'message' : 'messages' }}
          </span>
          <span class="stat-separator">•</span>
          <span class="stat-item">
            <Clock :size="14" class="stat-icon" />
            {{ threadInfo.last_message_at ? formatTimeAgo(threadInfo.last_message_at) : 'No activity yet' }}
          </span>
        </div>

        <!-- Messages Area (fills remaining space) -->
        <div class="embedded-messages-area">
          <CoordinationChat
            :threadId="threadInfo.thread_id"
            :focalType="threadInfo.focal_type"
            :focalId="threadInfo.focal_id"
            :alwaysExpanded="true"
            :initialExpanded="true"
            :hideInput="true"
            :replyingToMessageId="replyingToMessageId"
            @reply="handleReplyToMessage"
          />
        </div>

        <!-- Fixed Input Area (always at bottom) -->
        <div class="embedded-input-area">
          <CoordinationChat
            :threadId="threadInfo.thread_id"
            :focalType="threadInfo.focal_type"
            :focalId="threadInfo.focal_id"
            :alwaysExpanded="true"
            :initialExpanded="true"
            :inputOnly="true"
            :replyingToMessageId="replyingToMessageId"
            @cancel-reply="handleCancelReply"
            @message-sent="handleMessageSent"
          />
        </div>
      </template>

      <!-- Standard Mode: Resizable Content (context + divider + messages) -->
      <template v-else>
      <div class="resizable-content" ref="threadContentRef">
        <!-- Scrollable Context Area -->
        <div class="context-area" :style="contextAreaStyle" ref="contextAreaRef">
        <!-- Focal Point Header (hidden when embedded) -->
        <div v-if="!props.embedded" class="focal-point-header">
          <div class="focal-point-link">
            <div class="focal-point-icon">
              <Calendar v-if="threadInfo.focal_type === 'event'" :size="20" />
              <AlertCircle v-else :size="20" />
            </div>
            <div class="focal-point-info">
              <h3 class="focal-point-title">{{ focalPointTitle }}</h3>
              <p class="focal-point-subtitle">
                {{ focalPointSubtitle }}
                <button @click="openFocalPoint" class="view-focal-button">
                  <span v-if="threadInfo.focal_type === 'event'">View Event</span>
                  <span v-else>View Issue</span>
                  <ArrowRight :size="14" class="arrow-icon" />
                </button>
              </p>
            </div>
          </div>
        </div>

        <!-- Thread Stats - Compact Inline (matches sidebar style) -->
        <div class="thread-stats">
          <span class="stat-item">
            <Users :size="14" class="stat-icon" />
            {{ threadInfo.participant_count }} {{ threadInfo.participant_count === 1 ? 'member' : 'members' }}
          </span>
          <span class="stat-separator">•</span>
          <span class="stat-item">
            <MessageCircle :size="14" class="stat-icon" />
            {{ threadInfo.message_count }} {{ threadInfo.message_count === 1 ? 'message' : 'messages' }}
          </span>
          <span class="stat-separator">•</span>
          <span class="stat-item">
            <Clock :size="14" class="stat-icon" />
            {{ threadInfo.last_message_at ? formatTimeAgo(threadInfo.last_message_at) : 'No activity yet' }}
          </span>
        </div>

        <!-- Related Discussions (unified events + complaints) -->
        <div v-if="!props.embedded && relatedDiscussions.length > 0" class="related-discussions-section collapsible-section">
          <button class="section-header" @click="matchedEventsExpanded = !matchedEventsExpanded">
            <span class="chevron-wrapper">
              <ChevronRight v-if="!matchedEventsExpanded" :size="16" />
              <ChevronDown v-else :size="16" />
            </span>
            <MessageCircle :size="14" class="section-icon" />
            <h3 class="section-title">
              Related Discussions ({{ relatedDiscussions.length }})
            </h3>
          </button>

          <div v-show="matchedEventsExpanded" class="section-content">
            <p class="social-proof">
              {{ matchedEvents.length }} {{ matchedEvents.length === 1 ? 'meeting' : 'meetings' }} •
              {{ relatedIssuesForIssue.length }} {{ relatedIssuesForIssue.length === 1 ? 'neighbor' : 'neighbors' }} discussing this issue
            </p>

            <div class="discussion-list">
              <button
                v-for="discussion in relatedDiscussions"
                :key="discussion.id"
                @click="openDiscussionThread(discussion.id, discussion.type)"
                class="discussion-card"
                :class="{ 'hot-thread': isHotDiscussion(discussion.id) }"
              >
                <!-- lucide icon instead of emoji -->
                <component :is="getDiscussionIcon(discussion.type)" :size="16" class="discussion-icon" />
                <div class="discussion-info">
                  <div class="discussion-title-row">
                    <div class="discussion-title">{{ discussion.title }}</div>
                  </div>
                  <!-- Show short_name as secondary text for issue threads (matches DiscussionsPanel) -->
                  <div v-if="discussion.type === 'issue' && discussion.short_name" class="discussion-short-name">
                    {{ discussion.short_name }}
                  </div>
                  <!-- Stats row (matches DiscussionsPanel format) -->
                  <div class="discussion-stats">
                    <template v-if="getDiscussionStats(discussion.id)">
                      <MessageCircle :size="11" />
                      {{ getDiscussionStats(discussion.id)!.message_count }} {{ getDiscussionStats(discussion.id)!.message_count === 1 ? 'message' : 'messages' }}
                      <span class="stat-separator">•</span>
                      {{ getDiscussionStats(discussion.id)!.participant_count }} {{ getDiscussionStats(discussion.id)!.participant_count === 1 ? 'person' : 'people' }}
                      <template v-if="discussion.metadata">
                        <span class="stat-separator">•</span>
                        <span class="match-badge">{{ discussion.metadata }}</span>
                      </template>
                    </template>
                    <template v-else>
                      <MessageCircle :size="11" />
                      {{ discussion.subtitle }}
                      <template v-if="discussion.metadata">
                        <span class="stat-separator">•</span>
                        <span class="match-badge">{{ discussion.metadata }}</span>
                      </template>
                    </template>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- Related Discussions (for event threads - shows related complaints) -->
        <div v-if="!props.embedded && relatedIssues.length > 0" class="related-discussions-section collapsible-section">
          <button class="section-header" @click="relatedIssuesExpanded = !relatedIssuesExpanded">
            <span class="chevron-wrapper">
              <ChevronRight v-if="!relatedIssuesExpanded" :size="16" />
              <ChevronDown v-else :size="16" />
            </span>
            <MessageCircle :size="14" class="section-icon" />
            <h3 class="section-title">
              Related Discussions ({{ relatedIssues.length }})
            </h3>
          </button>

          <div v-show="relatedIssuesExpanded" class="section-content">
            <p class="social-proof">
              {{ relatedIssues.length }} {{ relatedIssues.length === 1 ? 'neighbor' : 'neighbors' }} discussing this issue
            </p>

            <div class="discussion-list">
              <button
                v-for="complaint in relatedIssues"
                :key="complaint.issue_id"
                @click="openDiscussionThread(complaint.issue_id, 'issue')"
                class="discussion-card"
                :class="{ 'hot-thread': isHotDiscussion(complaint.issue_id) }"
              >
                <!-- lucide icon for complaints (matches DiscussionsPanel) -->
                <AlertCircle :size="16" class="discussion-icon" />
                <div class="discussion-info">
                  <div class="discussion-title-row">
                    <div class="discussion-title">{{ complaint.ai_title || complaint.description_preview }}</div>
                  </div>
                  <!-- Show short_name as secondary text for issue threads (matches DiscussionsPanel) -->
                  <div v-if="complaint.short_name" class="discussion-short-name">
                    {{ complaint.short_name }}
                  </div>
                  <!-- Stats row (matches DiscussionsPanel format) -->
                  <div class="discussion-stats">
                    <template v-if="getDiscussionStats(complaint.issue_id)">
                      <MessageCircle :size="11" />
                      {{ getDiscussionStats(complaint.issue_id)!.message_count }} {{ getDiscussionStats(complaint.issue_id)!.message_count === 1 ? 'message' : 'messages' }}
                      <span class="stat-separator">•</span>
                      {{ getDiscussionStats(complaint.issue_id)!.participant_count }} {{ getDiscussionStats(complaint.issue_id)!.participant_count === 1 ? 'person' : 'people' }}
                    </template>
                    <template v-else>
                      <MessageCircle :size="11" />
                      {{ formatTimeAgo(complaint.created_at) }}
                    </template>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div> <!-- Close context-area -->

        <!-- Resizable divider -->
        <div
          class="resize-divider"
          :class="{ 'is-dragging': isDragging }"
          @mousedown="startDrag"
        >
          <div class="resize-handle"></div>
        </div>

        <!-- Messages Area (fills remaining space in resizable content) -->
        <div class="messages-area" :style="messagesAreaStyle" ref="messagesAreaRef">
          <CoordinationChat
            :threadId="threadInfo.thread_id"
            :focalType="threadInfo.focal_type"
            :focalId="threadInfo.focal_id"
            :alwaysExpanded="true"
            :initialExpanded="true"
            :hideInput="true"
            :replyingToMessageId="replyingToMessageId"
            @reply="handleReplyToMessage"
          />
        </div>
      </div> <!-- Close resizable-content -->

      <!-- Fixed Input Area (always at bottom) -->
      <div class="fixed-input-area">
        <CoordinationChat
          :threadId="threadInfo.thread_id"
          :focalType="threadInfo.focal_type"
          :focalId="threadInfo.focal_id"
          :alwaysExpanded="true"
          :initialExpanded="true"
          :inputOnly="true"
          :replyingToMessageId="replyingToMessageId"
          @cancel-reply="handleCancelReply"
          @message-sent="handleMessageSent"
        />
      </div>
      </template> <!-- Close standard mode template -->
    </div> <!-- Close thread-content -->
  </div> <!-- Close thread-artifact -->
</template>

<style scoped>
.thread-artifact {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background);
  overflow: hidden;
}

/* Loading & Error States */
.loading-container,
.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--spacing-lg);
  text-align: center;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  color: var(--orange);
  margin-bottom: var(--spacing-md);
}

.error-message {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-md);
}

.retry-button {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--border-radius);
  cursor: pointer;
  font-weight: 500;
}

.retry-button:hover {
  background: var(--primary-hover);
}

/* Thread Content - Three-section layout */
.thread-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Resizable Content (context + divider + messages) */
.resizable-content {
  flex: 1;
  min-height: 0; /* Important: allows flex children to shrink */
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative; /* For resizable divider */
}

/* Fixed Input Area (always at bottom, never affected by divider) */
.fixed-input-area {
  flex-shrink: 0;
  border-top: 2px solid var(--border); /* Visual separation */
  background: var(--background);
}

/* Scrollable Context Area (header + stats + sections) */
.context-area {
  /* flex properties set via :style binding (flex-grow, flex-shrink, flex-basis, minHeight) */
  overflow-y: auto;
  overflow-x: hidden;
  border-bottom: 1px solid var(--border);
  transition: flex-grow 0.3s ease; /* Smooth animation when auto-adjusting */
}

/* Scrollbar styling for context area - make it visible */
.context-area::-webkit-scrollbar {
  width: 8px;
}

.context-area::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.context-area::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}

.context-area::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}

/* Focal Point Header */
.focal-point-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: var(--background);
  padding: 12px 20px;
}

.focal-point-link {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.view-focal-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  margin-left: 12px;
  background: rgba(38, 139, 210, 0.08);
  color: var(--primary);
  border: 1px solid rgba(38, 139, 210, 0.2);
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  white-space: nowrap;
  transition: all 0.15s ease;
}

.view-focal-button:hover {
  background: rgba(38, 139, 210, 0.15);
  border-color: var(--primary);
  transform: translateX(1px);
}

.view-focal-button .arrow-icon {
  transition: transform 0.15s ease;
}

.view-focal-button:hover .arrow-icon {
  transform: translateX(2px);
}

.focal-point-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  margin-right: 12px;
}

.focal-point-info {
  flex: 1;
  min-width: 0;
}

.focal-point-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.focal-point-subtitle {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

/* Thread Stats - Compact Inline (matches sidebar style) */
.thread-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--background);
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stat-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.stat-separator {
  color: var(--text-tertiary);
  font-weight: 300;
}

/* Related Discussions Section - EXACT match to DiscussionsPanel */
.related-discussions-section {
  /* Matches sidebar minimalism */
}

/* Discussion List - VSCode Minimal Style */
.discussion-list {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tight gaps like sidebar */
}

.discussion-card {
  display: flex;
  align-items: flex-start;
  gap: 10px; /* EXACT match to DiscussionsPanel */
  padding: 6px 0; /* No horizontal padding - parent has it */
  background: transparent;
  border: none;
  border-radius: 0; /* No radius - flush edges */
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
  width: 100%;
}

.discussion-card:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover - EXACT match */
}

/* Hot Thread (active in last 24 hours) - Orange tint like sidebar */
.discussion-card.hot-thread {
  background: rgba(203, 75, 22, 0.04); /* Subtle orange background */
}

.discussion-card.hot-thread:hover {
  background: rgba(203, 75, 22, 0.08); /* Darker orange on hover */
}

.discussion-card.hot-thread .discussion-icon {
  color: var(--accent-orange); /* Orange icon for hot threads */
  opacity: 0.8;
}

.discussion-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.discussion-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px; /* Tighter - EXACT match */
}

.discussion-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.discussion-title {
  font-size: 13px; /* Smaller - EXACT match */
  font-weight: 500; /* Less bold - EXACT match */
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.discussion-short-name {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
  margin-bottom: 2px;
}

.discussion-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 400;
  opacity: 0.8;
}

.stat-separator {
  margin: 0 2px;
  opacity: 0.5;
}

.match-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: var(--primary); /* Darker blue to stand out on light background */
  color: white;
}

/* Social Proof - shared by both sections */
.social-proof {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  line-height: 1.3;
  padding: 0; /* Remove padding since section-content has it */
  font-style: italic;
}

/* Resizable divider */
.resize-divider {
  flex-shrink: 0;
  height: 6px; /* Slightly taller for easier grabbing */
  background: rgba(0, 0, 0, 0.03); /* Very subtle hint that it exists */
  cursor: row-resize;
  position: relative;
  z-index: 10;
  transition: background-color 0.15s ease;
}

.resize-divider:hover {
  background: var(--border);
}

.resize-divider.is-dragging {
  background: var(--primary);
}

/* Visual handle (center line) */
.resize-handle {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 40px;
  height: 2px;
  background: var(--text-secondary);
  opacity: 0;
  transition: opacity 0.15s ease;
  border-radius: 1px;
  pointer-events: none;
}

.resize-divider:hover .resize-handle {
  opacity: 0.4;
}

.resize-divider.is-dragging .resize-handle {
  opacity: 0.8;
  background: var(--primary);
}

/* Messages Area (messages only - within resizable content) */
.messages-area {
  /* flex properties set via :style binding (flex-grow, flex-shrink, flex-basis, minHeight) */
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: flex-grow 0.3s ease; /* Smooth animation when auto-adjusting */
}

/* Collapsible Sections */
.collapsible-section {
  /* Lightweight sections - no heavy borders */
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 20px;
  background: var(--background-secondary); /* Shaded like sidebar headers */
  border: none;
  border-bottom: 1px solid var(--border);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  outline: none; /* Remove blue focus border */
}

.section-header:hover {
  background: var(--hover-bg); /* Darker on hover */
  border-left-color: var(--primary);
}

.section-header:focus {
  outline: none; /* Ensure no blue border on focus */
}

.section-header .section-title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.section-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
}

.chevron-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.section-content {
  padding: 12px var(--space-md);
  background: var(--background); /* Lighter background - content area is white/light */
  border-top: 1px solid var(--border);
}

/* Embedded Mode Styles - Simple fixed layout (no resizable divider) */
.embedded-stats-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--background);
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.embedded-stats-header .stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.embedded-stats-header .stat-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.embedded-stats-header .stat-separator {
  color: var(--text-tertiary);
  font-weight: 300;
}

.embedded-messages-area {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.embedded-input-area {
  flex-shrink: 0;
  border-top: 2px solid var(--border);
  background: var(--background);
}
</style>

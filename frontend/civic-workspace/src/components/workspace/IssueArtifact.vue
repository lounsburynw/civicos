<template>
  <div class="issue-artifact">
    <!-- Header -->
    <div class="artifact-header">
      <div class="header-left">
        <!-- Tab Bar (moved to header) -->
        <div class="header-tabs">
          <button
            class="header-tab-button"
            :class="{ 'active': activeTab === 'details' }"
            @click="switchTab('details')"
          >
            <FileText :size="16" />
            Details
          </button>
          <button
            class="header-tab-button"
            :class="{ 'active': activeTab === 'discussion' }"
            @click="switchTab('discussion')"
          >
            <MessageCircle :size="16" />
            Discussion
          </button>
        </div>
      </div>

      <!-- Follow Button (in header) -->
      <button
        class="follow-btn"
        :class="{ 'is-following': followInfo.your_following }"
        @click="toggleFollow"
      >
        <span v-if="!followInfo.your_following">+ Follow</span>
        <span v-else>Following</span>
      </button>

      <button class="close-btn" @click="$emit('close')" title="Close tab">
        <span class="icon">×</span>
      </button>
    </div>

    <!-- Main Content -->
    <div class="artifact-content" :class="{ 'discussion-mode': activeTab === 'discussion' }">
      <!-- Details Tab Content -->
      <section v-if="activeTab === 'details'" class="issue-section">
        <!-- Short Name + Status Badge + Status Actions (above title) -->
        <div class="issue-header-row">
          <div class="issue-short-name" v-if="!isOperationalIssue && 'short_name' in issue && issue.short_name">
            {{ issue.short_name }}
          </div>

          <!-- Clickable Status Badge with History Indicator -->
          <button
            class="status-badge-jira clickable"
            @click="isStatusHistoryExpanded = !isStatusHistoryExpanded"
            title="Click to view status history"
          >
            <span class="status-label">Status</span>
            <span class="status-value" :class="getStatusBadgeClass(issue.status)">
              {{ formatStatus(issue.status) }}
              <ChevronRight :size="11" class="status-chevron" :class="{ 'is-rotated': isStatusHistoryExpanded }" />
            </span>
          </button>

          <!-- Status Management Actions (inline with status badge) -->
          <div class="status-actions-inline">
            <button
              v-if="issue.status === 'open'"
              class="btn-action btn-status-inline"
              @click="isCloseFormExpanded = !isCloseFormExpanded"
              :disabled="updatingStatus"
              :title="isCloseFormExpanded ? 'Cancel closing' : 'Close this issue'"
            >
              <CheckCircle2 :size="14" />
              {{ isCloseFormExpanded ? 'Cancel' : 'Close' }}
            </button>
            <button
              v-if="issue.status === 'closed'"
              class="btn-action btn-status-inline"
              @click="reopenIssue"
              :disabled="updatingStatus"
              title="Reopen this issue"
            >
              <RotateCcw :size="14" />
              Reopen
            </button>
          </div>
        </div>

        <!-- Closure Context (inline display when closed) -->
        <div v-if="!isOperationalIssue && issue.status === 'closed' && 'closed_reason' in issue && issue.closed_reason" class="closure-context-inline">
          <div class="closure-reason-label">
            Closed as <strong>{{ formatClosedReason(issue.closed_reason) }}</strong>
          </div>
          <p v-if="'closed_note' in issue && issue.closed_note" class="closure-note">
            {{ issue.closed_note }}
          </p>
        </div>

        <!-- Expanded Status History (below header row) -->
        <div v-if="isStatusHistoryExpanded" class="status-history-content-inline">
          <ResponseTimeline ref="statusRef" :issue-id="issue.id" @loaded="handleStatusLoaded" />
        </div>

        <!-- Close Form (inline expansion below header row) -->
        <div v-if="isCloseFormExpanded" class="close-form-inline">
          <h4 class="close-form-title">Why are you closing this issue?</h4>

          <div class="close-reason-options">
            <label class="reason-card" :class="{ 'selected': closeReason === 'resolved' }">
              <input type="radio" v-model="closeReason" value="resolved" />
              <CheckCircle2 :size="20" class="reason-icon" />
              <div class="reason-content">
                <strong class="reason-title">Resolved</strong>
                <p class="reason-description">Issue was fixed</p>
              </div>
            </label>

            <label class="reason-card" :class="{ 'selected': closeReason === 'duplicate' }">
              <input type="radio" v-model="closeReason" value="duplicate" />
              <Copy :size="20" class="reason-icon" />
              <div class="reason-content">
                <strong class="reason-title">Duplicate</strong>
                <p class="reason-description">Merged with another issue</p>
              </div>
            </label>

            <label class="reason-card" :class="{ 'selected': closeReason === 'not-actionable' }">
              <input type="radio" v-model="closeReason" value="not-actionable" />
              <XCircle :size="20" class="reason-icon" />
              <div class="reason-content">
                <strong class="reason-title">Not Actionable</strong>
                <p class="reason-description">Cannot be addressed</p>
              </div>
            </label>

            <label class="reason-card" :class="{ 'selected': closeReason === 'abandoned' }">
              <input type="radio" v-model="closeReason" value="abandoned" />
              <MinusCircle :size="20" class="reason-icon" />
              <div class="reason-content">
                <strong class="reason-title">Abandoned</strong>
                <p class="reason-description">No follow-up needed</p>
              </div>
            </label>
          </div>

          <div class="close-note-section">
            <label for="close-note" class="close-note-label">Optional note</label>
            <textarea
              id="close-note"
              v-model="closeNote"
              class="close-note-textarea"
              placeholder="Add details about closing this issue..."
              rows="3"
            ></textarea>
          </div>

          <div class="close-form-actions">
            <button
              type="button"
              class="btn-secondary"
              @click="cancelCloseForm"
              :disabled="updatingStatus"
            >
              Cancel
            </button>
            <button
              type="button"
              class="btn-primary"
              @click="submitCloseForm"
              :disabled="!closeReason || updatingStatus"
            >
              <span v-if="updatingStatus">Closing...</span>
              <span v-else>Close Issue</span>
            </button>
          </div>
        </div>

        <!-- Operational Issue Header (Session 91) -->
        <div v-if="isOperationalIssue" class="operational-header">
          <div class="operational-badge">
            <span class="icon">🔧</span>
            <span class="badge-text">City tracking via SeeClickFix</span>
          </div>
          <a
            v-if="isOperational(issue) && issue.html_url"
            :href="issue.html_url"
            target="_blank"
            rel="noopener noreferrer"
            class="external-link"
          >
            <span>View on SeeClickFix</span>
            <ExternalLink :size="14" />
          </a>
        </div>

        <!-- AI-Generated Title (h1) -->
        <h1 class="issue-title">
          {{ isOperationalIssue && isOperational(issue) ? issue.title : (!isOperational(issue) && ('ai_title' in issue ? issue.ai_title : issue.description.substring(0, 50) + '...')) }}
        </h1>

        <!-- Metadata (jurisdiction, date, location) -->
        <div class="issue-metadata">
          <span class="metadata-item">
            {{ formatJurisdiction(isOperational(issue) ? 'sanrafael' : issue.jurisdiction_id) }}
          </span>
          <span class="metadata-separator">•</span>
          <span class="metadata-item">
            Filed {{ formatDate(issue.created_at) }}
          </span>
          <span class="metadata-separator" v-if="issue.location">•</span>
          <span class="metadata-item" v-if="issue.location">
            {{ isOperational(issue) ? issue.location.address : issue.location.address }}
          </span>
          <span v-if="isOperationalIssue && isOperational(issue)" class="metadata-separator">•</span>
          <span v-if="isOperationalIssue && isOperational(issue)" class="metadata-item">
            {{ issue.category }}
          </span>
        </div>

        <!-- Issue Tags (above summary, provides category context) -->
        <div class="issue-tags">
          <span class="issue-type-tag">{{ formatIssueType(issue.issue_type) }}</span>
        </div>

        <!-- AI-Generated Summary -->
        <div class="ai-summary" v-if="!isOperationalIssue && 'ai_summary' in issue && issue.ai_summary">
          {{ issue.ai_summary }}
        </div>

        <!-- Collapsible User Description -->
        <div
          class="collapsible-section description-section"
          :class="{ 'is-expanded': isDescriptionExpanded }"
        >
          <button
            class="collapsible-header"
            @click="isDescriptionExpanded = !isDescriptionExpanded"
          >
            <ChevronRight
              :size="16"
              class="collapse-icon"
              :class="{ 'is-rotated': isDescriptionExpanded }"
            />
            <FileText :size="18" class="section-icon" />
            <span class="section-title">User description</span>
          </button>

          <div v-if="isDescriptionExpanded" class="collapsible-content">
            <div class="description-text">
              {{ issue.description }}
            </div>
          </div>
        </div>
      </section>

      <!-- Take Action Section (external escalation only) -->
      <div v-if="activeTab === 'details'" class="primary-actions-section">
        <h3 class="actions-title">Take Action</h3>
        <div class="action-buttons-row">
          <button class="btn-action btn-primary" @click="handleFile311" title="File official 311 report">
            <Phone :size="16" />
            File 311 Report
          </button>
          <button class="btn-action btn-primary" @click="handleEmailDepartment" title="Email relevant city department">
            <Mail :size="16" />
            Email Department
          </button>
        </div>
      </div>

      <!-- Summary Statistics + Follow (combined) -->
      <div v-if="activeTab === 'details'" class="summary-follow-section">
        <div class="summary-stats">
          <div class="summary-stat" v-if="issue.matched_events && issue.matched_events.length > 0">
            <Calendar :size="14" />
            {{ issue.matched_events.length }} {{ issue.matched_events.length === 1 ? 'meeting' : 'meetings' }}
          </div>

          <!-- Always show neighbor count -->
          <div class="summary-stat">
            <Users :size="14" />
            {{ followInfo.follower_count }} {{ followInfo.follower_count === 1 ? 'neighbor' : 'neighbors' }} involved
          </div>

          <div class="summary-stat" v-if="totalActionsTaken > 0">
            <CheckCircle2 :size="14" />
            {{ totalActionsTaken }} {{ totalActionsTaken === 1 ? 'action' : 'actions' }} taken
          </div>
        </div>
      </div>

      <!-- Operational→Policy Matching Section (Session 91) -->
      <div
        v-if="activeTab === 'details' && isOperationalIssue && isOperational(issue) && issue.matched_events && issue.matched_events.length > 0"
        class="collapsible-section matching-section"
        :class="{ 'is-expanded': isMatchingExpanded }"
      >
        <button
          class="collapsible-header"
          @click="isMatchingExpanded = !isMatchingExpanded"
        >
          <ChevronRight
            :size="16"
            class="collapse-icon"
            :class="{ 'is-rotated': isMatchingExpanded }"
          />
          <span class="match-icon">💡</span>
          <span class="section-title">Related Policy Discussions</span>
          <span class="meeting-count">({{ issue.matched_events.length }})</span>
        </button>

        <div v-if="isMatchingExpanded" class="collapsible-content">
          <p class="section-description">
            This operational issue has been matched to policy discussions at city council meetings.
            Attending these meetings or submitting comments can help escalate this concern.
          </p>

          <div class="match-list">
            <div
              v-for="match in issue.matched_events"
              :key="match.event_id"
              class="match-card"
            >
              <div class="match-header">
                <div class="confidence-badge" :class="getConfidenceClass(match.confidence)">
                  {{ match.confidence }}% match
                </div>
                <span class="match-date">{{ match.event ? formatDate(match.event.when) : '' }}</span>
              </div>
              <h4 class="match-title">{{ match.event?.title || match.event_id }}</h4>
              <p class="match-reasoning">{{ match.reasoning }}</p>
              <button
                v-if="match.event"
                @click="openMatchedEvent(match.event)"
                class="btn-view-event"
              >
                <Calendar :size="14" />
                View Meeting
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Matched Events (Phase 3 - redesigned, now collapsible) -->
      <div
        v-if="activeTab === 'details' && !isOperationalIssue && issue.matched_events && issue.matched_events.length > 0"
        class="collapsible-section meetings-section"
        :class="{ 'is-expanded': isMeetingsExpanded }"
      >
        <button
          class="collapsible-header"
          @click="isMeetingsExpanded = !isMeetingsExpanded"
        >
          <ChevronRight
            :size="16"
            class="collapse-icon"
            :class="{ 'is-rotated': isMeetingsExpanded }"
          />
          <Calendar :size="18" class="section-icon" />
          <span class="section-title">Relevant Civic Meetings</span>
          <span class="meeting-count">({{ issue.matched_events.length }})</span>
        </button>

        <div v-if="isMeetingsExpanded" class="collapsible-content">
          <p class="section-description">
            These civic meetings are addressing issues related to your issue. Attending or submitting
            comments can help bring attention to your concerns.
          </p>

          <div class="meeting-list">
            <button
              v-for="eventRef in issue.matched_events"
              :key="eventRef.event_id"
              class="meeting-item"
              @click="openEvent(eventRef.event_id)"
            >
              <Calendar :size="16" class="meeting-icon" />
              <div class="meeting-info">
                <div class="meeting-title">
                  {{ eventData.get(eventRef.event_id)?.title || 'Loading...' }}
                </div>
                <div class="meeting-meta">
                  <span v-if="eventData.get(eventRef.event_id)?.when">
                    {{ formatDate(eventData.get(eventRef.event_id)!.when) }}
                  </span>
                  <span v-if="eventData.get(eventRef.event_id)?.when" class="stat-separator">•</span>
                  <span class="match-badge-small">
                    {{ ('match_score' in eventRef ? (eventRef.match_score !== null ? Math.round(eventRef.match_score * 100) + '% match' : 'Manual link') : ('confidence' in eventRef ? Math.round(eventRef.confidence) + '% match' : 'Unknown')) }}
                  </span>
                </div>
              </div>
              <ArrowRight :size="14" class="meeting-arrow" />
            </button>
          </div>
        </div>
      </div>

      <!-- No Matches Fallback -->
      <section v-if="activeTab === 'details' && issue.matched_events && issue.matched_events.length === 0" class="no-matches-section">
        <h2 class="section-title">No Matching Meetings Yet</h2>
        <p class="section-description">
          Your issue has been recorded. We'll notify you when a relevant civic meeting is scheduled.
          In the meantime, consider connecting with neighbors facing similar issues.
        </p>
      </section>

      <!-- Related Complaints (Phase 4 - redesigned, now collapsible) -->
      <div
        v-if="activeTab === 'details' && !isOperationalIssue && 'related_issues' in issue && issue.related_issues && issue.related_issues.length > 0"
        class="collapsible-section similar-issues-section"
        :class="{ 'is-expanded': isSimilarIssuesExpanded }"
      >
        <button
          class="collapsible-header"
          @click="isSimilarIssuesExpanded = !isSimilarIssuesExpanded"
        >
          <ChevronRight
            :size="16"
            class="collapse-icon"
            :class="{ 'is-rotated': isSimilarIssuesExpanded }"
          />
          <AlertCircle :size="18" class="section-icon" />
          <span class="section-title">Similar Issues from Neighbors</span>
          <span class="issue-count">({{ issue.related_issues.length }})</span>
        </button>

        <div v-if="isSimilarIssuesExpanded" class="collapsible-content">
          <p class="section-description">
            Other residents in your jurisdiction have reported similar concerns. Consider joining
            forces to address this issue collectively.
          </p>

          <div class="similar-issue-cards">
            <button
              v-for="relatedId in issue.related_issues.slice(0, showAllRelated ? undefined : 5)"
              :key="relatedId"
              class="similar-issue-card"
              @click="openComplaint(relatedId)"
            >
              <AlertCircle :size="16" class="issue-icon" />
              <div class="issue-content">
                <div class="issue-title">
                  {{ issueData.get(relatedId)?.ai_title || 'Loading...' }}
                </div>
                <div v-if="issueData.get(relatedId)?.short_name" class="issue-short-name">
                  {{ issueData.get(relatedId)!.short_name }}
                </div>
                <div class="issue-meta">
                  <span v-if="issueData.get(relatedId)?.created_at">
                    Filed {{ formatDate(issueData.get(relatedId)!.created_at) }}
                  </span>
                </div>
              </div>
              <ArrowRight :size="14" class="issue-view-btn" />
            </button>
          </div>

          <button
            v-if="issue.related_issues.length > 5"
            class="show-more-btn"
            @click="showAllRelated = !showAllRelated"
          >
            <template v-if="showAllRelated">
              Show Less
              <ChevronDown :size="16" style="transform: rotate(180deg)" />
            </template>
            <template v-else>
              Show {{ issue.related_issues.length - 5 }} More
              <ChevronDown :size="16" />
            </template>
          </button>
        </div>
      </div>

      <!-- Discussion Group -->
      <section v-if="activeTab === 'details' && !isOperationalIssue && 'discussion_group_id' in issue && issue.discussion_group_id" class="discussion-group-section">
        <div class="section-header">
          <MessageCircle :size="20" class="section-icon" />
          <h3>Community Discussion</h3>
        </div>
        <p class="section-description">
          This issue has an active discussion group. Join to coordinate with neighbors.
        </p>
        <button class="btn-primary">
          <MessageCircle :size="16" />
          Join Discussion Group
        </button>
      </section>

      <!-- AI Analysis (if available) -->
      <section v-if="activeTab === 'details' && !isOperationalIssue && 'ai_analysis' in issue && issue.ai_analysis" class="ai-analysis-section">
        <h2 class="section-title">Recommended Actions</h2>
        <ul class="suggestions-list">
          <li
            v-for="(action, index) in issue.ai_analysis.suggested_actions"
            :key="index"
            class="suggestion-item"
          >
            {{ action }}
          </li>
        </ul>
      </section>

      <!-- Discussion Tab Content -->
      <div v-if="activeTab === 'discussion' && followInfo.thread_id" class="discussion-tab-content">
        <ThreadArtifact :thread-id="followInfo.thread_id" :embedded="true" />
      </div>

    </div>

    <!-- Event Selection Modal (Phase 2 - Task 1) -->
    <EventSelectionModal
      v-if="showEventSelectionModal"
      :issue-id="issue.id"
      :already-linked-event-ids="alreadyLinkedEventIds"
      @close="showEventSelectionModal = false"
      @events-linked="handleEventsLinked"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import type { Issue, OperationalIssue, CivicEvent, FollowInfoResponse } from '@/types/civic';
import { useWorkspaceStore } from '@/stores/workspace';
import { useContextStore } from '@/stores/context';
import { api } from '@/services/api';
import { createIssueContext } from '@/utils/contextHelpers';
import { ArtifactIds } from '@/utils/artifactIds';
import ResponseTimeline from './ResponseTimeline.vue';
import EventSelectionModal from './EventSelectionModal.vue';
import ThreadArtifact from './ThreadArtifact.vue';
import {
  // Status & timeline
  Clock,           // Government Response
  Calendar,        // Relevant Civic Meetings
  FileText,        // Similar Issues (legacy)
  AlertCircle,     // Issue icon (matches TabBar)
  CheckCircle2,    // Filed, Matched, Mark Resolved, Resolved reason
  Link,           // Manually Linked, Link to Meeting
  AlertTriangle,   // Escalate
  Copy,           // Duplicate reason
  XCircle,        // Not actionable reason
  MinusCircle,    // Abandoned reason
  RotateCcw,      // Reopen (undo closure)

  // Actions
  Phone,          // File 311
  Mail,           // Email Department

  // Community
  Users,          // Community stats
  MessageCircle,   // View Discussion

  // UI elements
  ChevronRight,   // Collapse indicator
  ChevronDown,    // Show More
  ArrowRight,     // View buttons
  ExternalLink,   // SeeClickFix external link
} from 'lucide-vue-next';

const props = defineProps<{
  issue: Issue | OperationalIssue;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const workspaceStore = useWorkspaceStore();
const contextStore = useContextStore();
const showAllRelated = ref(false);
const statusRef = ref<InstanceType<typeof ResponseTimeline> | null>(null);
const updatingStatus = ref(false);
const showEventSelectionModal = ref(false);

// Context registration tracking
const contextId = ref<string>();

// Collapsible section state
const isStatusHistoryExpanded = ref(false); // Status history collapsed by default (inline toggle)
const statusItemCount = ref(0);
const isDescriptionExpanded = ref(false); // Description collapsed by default (show AI summary instead)
const isSimilarIssuesExpanded = ref(false); // Similar issues collapsed by default
const isMeetingsExpanded = ref(false); // Meetings collapsed by default
const isMatchingExpanded = ref(false); // Matching section collapsed by default (Session 91)

// Close form state (inline expansion)
const isCloseFormExpanded = ref(false);
const closeReason = ref<'resolved' | 'duplicate' | 'not-actionable' | 'abandoned' | null>(null);
const closeNote = ref('');

// Tab toggle state (details vs discussion)
const activeTab = ref<'details' | 'discussion'>('details');

// TODO: Replace with actual user ID from auth store
const userId = 'demo_user';

// Follow info for coordination chat
const followInfo = ref<FollowInfoResponse>({
  follower_count: 0,
  thread_id: null,
  your_following: false
});

// Mock action counts (TODO: Replace with real data from backend)
const mockActionCounts = ref({
  filed311: Math.floor(Math.random() * 8),  // Random 0-7
  emailed: Math.floor(Math.random() * 6)     // Random 0-5
});

// Local reactive issue data (deep clone to prevent shared references)
const localComplaint = ref<Issue | OperationalIssue>(JSON.parse(JSON.stringify(props.issue)));

// Computed: Make issue reactive and updatable
const issue = computed(() => localComplaint.value);

// Type guard: Check if issue is operational (Session 91 - SeeClickFix Integration)
function isOperational(issue: Issue | OperationalIssue): issue is OperationalIssue {
  return 'source' in issue && issue.source === 'seeclickfix';
}

// Computed: Is this an operational issue?
const isOperationalIssue = computed(() => isOperational(issue.value));

// Computed: Total actions taken
const totalActionsTaken = computed(() => {
  return mockActionCounts.value.filed311 + mockActionCounts.value.emailed;
});

// Watch for prop changes and update local issue
watch(() => props.issue, (newComplaint) => {
  localComplaint.value = JSON.parse(JSON.stringify(newComplaint));

  // DEBUG: Log related issues
  console.log('[ComplaintArtifact] Issue loaded:', {
    id: newComplaint.id,
    issue_type: newComplaint.issue_type,
    related_issues: isOperational(newComplaint) ? undefined : newComplaint.related_issues,
    related_count: isOperational(newComplaint) ? 0 : (newComplaint.related_issues?.length || 0)
  });

  // Reload follow info when issue changes
  loadFollowInfo();
}, { deep: true });

// Computed: Extract already-linked event IDs
const alreadyLinkedEventIds = computed(() => {
  if (!issue.value.matched_events) return [];
  return issue.value.matched_events.map(e => e.event_id);
});

// Formatting helpers
function formatStatus(status: string): string {
  const statusMap: Record<string, string> = {
    open: 'Open',
    closed: 'Closed'
  };
  return statusMap[status] || status;
}

function formatClosedReason(reason: string): string {
  const reasonMap: Record<string, string> = {
    'resolved': 'Resolved',
    'duplicate': 'Duplicate',
    'not-actionable': 'Not Actionable',
    'abandoned': 'Abandoned'
  };
  return reasonMap[reason] || reason;
}

function formatIssueType(type: string | null): string {
  if (!type) return 'General';
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatJurisdiction(jurisdictionId: string): string {
  return jurisdictionId
    .replace('city-', '')
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;

  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

function getMatchScoreClass(score: number): string {
  if (score >= 0.8) return 'match-high';
  if (score >= 0.5) return 'match-medium';
  return 'match-low';
}

// Session 91: Confidence badge styling for operational matching
function getConfidenceClass(confidence: number): string {
  if (confidence >= 80) return 'confidence-high';
  if (confidence >= 60) return 'confidence-medium';
  return 'confidence-low';
}

// Session 91: Open matched event from operational issue
function openMatchedEvent(event: CivicEvent) {
  workspaceStore.openArtifact({
    id: ArtifactIds.event(event),
    type: 'event',
    title: event.title,
    data: event
  });
}

function getStatusBadgeClass(status: string): string {
  const classMap: Record<string, string> = {
    open: 'status-open',
    closed: 'status-closed'
  };
  return classMap[status] || 'status-open';
}

// Cache for fetched data (matches DiscussionsPanel pattern)
const eventData = ref<Map<string, { title: string; when: string }>>(new Map());
const issueData = ref<Map<string, { ai_title: string; short_name: string | undefined; created_at: string }>>(new Map());

// Fetch event data for display (returns object with title and when)
async function fetchEventData() {
  if (!issue.value.matched_events) return;
  const promises = issue.value.matched_events.map(async (eventRef) => {
    if (eventData.value.has(eventRef.event_id)) return;

    try {
      const event = await api.getEvent(eventRef.event_id);
      eventData.value.set(eventRef.event_id, {
        title: event.title,
        when: event.when
      });
    } catch (err) {
      console.error(`Failed to fetch event ${eventRef.event_id}:`, err);
    }
  });

  await Promise.all(promises);
}

// Fetch issue data for display (returns object with titles and date)
async function fetchIssueData() {
  if (isOperationalIssue.value || !('related_issues' in issue.value) || !issue.value.related_issues) return;
  const promises = issue.value.related_issues.slice(0, showAllRelated.value ? undefined : 5).map(async (issueId: string) => {
    if (issueData.value.has(issueId)) return;

    try {
      const relatedIssue = await api.getIssue(issueId);
      issueData.value.set(issueId, {
        ai_title: relatedIssue.ai_title || relatedIssue.description.substring(0, 80) + '...',
        short_name: relatedIssue.short_name,
        created_at: relatedIssue.created_at
      });
    } catch (err) {
      console.error(`Failed to fetch issue ${issueId}:`, err);
    }
  });

  await Promise.all(promises);
}

// Actions
async function openEvent(eventId: string) {
  try {
    // Fetch event from API
    const event: CivicEvent = await api.getEvent(eventId);

    if (!event) {
      alert('Event not found. It may no longer be available.');
      return;
    }

    // Open event as artifact (new tab)
    workspaceStore.openArtifact({
      type: 'event',
      id: ArtifactIds.event(event), // Centralized ID generation (Session 53.5)
      title: event.title,
      data: event
    });
  } catch (error) {
    console.error('[ComplaintArtifact] Failed to open event:', error);
    alert(`Failed to open event. Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

async function openComplaint(issueId: string) {
  try {
    // Fetch issue from API
    const relatedIssue: Issue = await api.getIssue(issueId);

    if (!relatedIssue) {
      alert('Issue not found. It may no longer be available.');
      return;
    }

    // Open issue as artifact (new tab) with short_name as tab title
    const tabTitle = relatedIssue.short_name || relatedIssue.ai_title || relatedIssue.description.substring(0, 50) + '...';
    workspaceStore.openArtifact({
      type: 'issue',
      id: ArtifactIds.issue(relatedIssue.id), // Centralized ID generation (Session 53.5)
      title: tabTitle,
      data: relatedIssue,
      initialTab: 'details' // Open to details tab (not discussion)
    });
  } catch (error) {
    console.error('[IssueArtifact] Failed to open related issue:', error);
    alert(`Failed to open issue. Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

function openFirstMatchedEvent() {
  if (issue.value.matched_events && issue.value.matched_events.length > 0) {
    openEvent(issue.value.matched_events[0].event_id);
  }
}

function linkToEvent() {
  showEventSelectionModal.value = true;
}

async function handleEventsLinked(updatedComplaint: Issue) {
  // Update local issue data with fresh data from API
  localComplaint.value = updatedComplaint;

  // Refresh status to show the manual link entries
  try {
    if (statusRef.value) {
      await statusRef.value.loadTimeline();
    }
  } catch (error) {
    console.error('[IssueArtifact] Failed to refresh status:', error);
  }
}

// Action handlers (stubs for now)
function handleFile311() {
  // TODO: Open 311 filing modal/link with pre-filled information
  alert('311 filing coming soon! You\'ll be able to file an official 311 report for: ' + issue.value.description.substring(0, 50) + '...');
}

function handleEmailDepartment() {
  // TODO: Open email template with relevant department contacts
  alert('Email template coming soon! You\'ll be able to email the relevant city department about your issue.');
}

// Status update actions - Close form handlers
function cancelCloseForm() {
  isCloseFormExpanded.value = false;
  closeReason.value = null;
  closeNote.value = '';
}

async function submitCloseForm() {
  if (!closeReason.value || isOperational(issue.value)) {
    return; // Only policy issues can be closed via this form
  }

  try {
    updatingStatus.value = true;

    await api.updateComplaintStatus(
      issue.value.id,
      'closed',
      closeNote.value || undefined,
      closeReason.value
    );

    // Update local issue status (create new object to ensure reactivity) - policy issue only
    localComplaint.value = {
      ...localComplaint.value,
      status: 'closed',
      closed_reason: closeReason.value,
      closed_at: new Date().toISOString(),
      closed_note: closeNote.value || undefined
    } as Issue;

    // Refresh status
    if (statusRef.value) {
      await statusRef.value.loadTimeline();
    }

    // Reset form
    cancelCloseForm();

    // No alert - UI shows clear visual feedback (status badge changes to "Closed")
  } catch (error) {
    console.error('[IssueArtifact] Error closing issue:', error);
    alert(`Failed to close issue: ${error instanceof Error ? error.message : 'Unknown error'}`);
  } finally {
    updatingStatus.value = false;
  }
}

async function reopenIssue() {
  if (isOperational(issue.value)) {
    return; // Only policy issues can be reopened
  }

  const policyIssue = issue.value as Issue;

  // Build confirmation message with closure context
  let confirmMessage = 'Reopen this issue?\n\n';
  if (policyIssue.closed_reason) {
    confirmMessage += `Previously closed as: ${formatClosedReason(policyIssue.closed_reason)}`;
    if (policyIssue.closed_note) {
      confirmMessage += `\n"${policyIssue.closed_note}"`;
    }
    confirmMessage += '\n\n';
  }
  confirmMessage += 'This will mark the issue as active again.';

  if (!confirm(confirmMessage)) {
    return;
  }

  const note = prompt('(Optional) Add a note about reopening:');

  try {
    updatingStatus.value = true;

    await api.updateComplaintStatus(
      policyIssue.id,
      'open',
      note || undefined
    );

    // Update local issue status (create new object to ensure reactivity) - policy issue only
    localComplaint.value = {
      ...localComplaint.value,
      status: 'open',
      closed_reason: undefined,
      closed_at: undefined,
      closed_note: undefined
    } as Issue;

    // Refresh status
    if (statusRef.value) {
      await statusRef.value.loadTimeline();
    }

    // No alert - UI shows clear visual feedback (status badge changes to "Open")
  } catch (error) {
    console.error('[IssueArtifact] Error reopening issue:', error);
    alert(`Failed to reopen issue: ${error instanceof Error ? error.message : 'Unknown error'}`);
  } finally {
    updatingStatus.value = false;
  }
}

/**
 * Load follow info for coordination chat
 */
async function loadFollowInfo() {
  try {
    const info = await api.getFollowInfo('issue', issue.value.id, userId);
    followInfo.value = info;
  } catch (err) {
    console.error('[IssueArtifact] Failed to load follow info:', err);
  }
}

/**
 * Toggle follow status (corner badge click)
 */
async function toggleFollow() {
  if (followInfo.value.your_following) {
    // Unfollow (no confirmation - social media pattern)
    await unfollowIssue();
  } else {
    // Follow (no confirmation, don't auto-open discussion)
    await followIssue(false);
  }
}

/**
 * Follow this issue (optionally open discussion)
 */
async function followIssue(openDiscussionAfter = true) {
  try {
    const jurisdictionId = isOperational(issue.value) ? 'sanrafael' : issue.value.jurisdiction_id;
    const result = await api.createFollow(
      userId,
      'issue',
      issue.value.id,
      jurisdictionId
    );

    // Update follow info - this triggers badge reactivity
    followInfo.value = {
      follower_count: result.follower_count,
      thread_id: result.thread_id,
      your_following: result.your_following
    };

    // Only open discussion if requested (from button, not badge)
    if (openDiscussionAfter && result.thread_id) {
      openDiscussion();
    }
  } catch (err) {
    console.error('[IssueArtifact] Failed to follow issue:', err);
    alert('Failed to join discussion. Please try again.');
  }
}

/**
 * Unfollow this issue (called by corner badge)
 */
async function unfollowIssue() {
  try {
    const result = await api.deleteFollow(
      userId,
      'issue',
      issue.value.id
    );

    // Update follow info
    followInfo.value = {
      ...followInfo.value,
      follower_count: result.follower_count,
      your_following: result.your_following
    };
  } catch (err) {
    console.error('[IssueArtifact] Failed to unfollow issue:', err);
    alert('Failed to unfollow. Please try again.');
  }
}

/**
 * Open ThreadArtifact for this issue's discussion
 */
function openDiscussion() {
  if (!followInfo.value.thread_id) return;

  // Use short_name for thread tab title, fallback to ai_title or title or truncated description
  const issueTitle = isOperational(issue.value)
    ? issue.value.title
    : (issue.value.short_name || issue.value.ai_title || issue.value.description.substring(0, 40));

  // Open ThreadArtifact in new tab
  workspaceStore.openArtifact({
    type: 'thread',
    id: ArtifactIds.thread(followInfo.value.thread_id), // Centralized ID generation (Session 53.5)
    title: issueTitle,
    data: {
      threadId: followInfo.value.thread_id,
      focalType: 'issue',
      focalId: issue.value.id
    }
  });
}

/**
 * Switch to a specific tab (handles auto-follow for discussion tab)
 */
async function switchTab(tab: 'details' | 'discussion') {
  // If switching to discussion tab and not following, auto-follow first
  if (tab === 'discussion' && !followInfo.value.your_following) {
    await followIssue(false); // false = don't open in new tab, we're switching tabs here
  }
  activeTab.value = tab;
}

/**
 * Handle status loaded event - capture item count
 */
function handleStatusLoaded(count: number) {
  statusItemCount.value = count;
}

// Load follow info on mount
onMounted(async () => {
  // Check if we should open to a specific tab (e.g., 'discussion' from DiscussionsPanel)
  const currentArtifact = workspaceStore.activeArtifact;
  if (currentArtifact?.initialTab && currentArtifact.id === props.issue.id) {
    activeTab.value = currentArtifact.initialTab as 'details' | 'discussion';
  }

  // DEBUG: Log initial issue data
  console.log('[IssueArtifact] Mounted with issue:', {
    id: props.issue.id,
    issue_type: props.issue.issue_type,
    related_issues: !isOperational(props.issue) ? props.issue.related_issues : undefined,
    related_count: !isOperational(props.issue) ? (props.issue.related_issues?.length || 0) : 0
  });

  loadFollowInfo();

  // Fetch event and issue data for display
  if (issue.value.matched_events && issue.value.matched_events.length > 0) {
    fetchEventData();
  }
  if (!isOperational(issue.value) && issue.value.related_issues.length > 0) {
    fetchIssueData();
  }

  // Register context element
  const contextElement = await createIssueContext(
    props.issue,
    ArtifactIds.issue(props.issue.id), // Centralized ID generation (Session 53.5)
    'primary'
  );
  contextId.value = contextStore.register(contextElement);
  console.log('[IssueArtifact] Context registered:', contextId.value);
});

// Session 54: Context persists when tab closes (removed onUnmounted hook)
// Context is now only removed via explicit "X" button in ContextIndicator
// This enables multi-document workflows (e.g., keep issue in context while browsing events)

// Update context when tab changes
watch(activeTab, (newTab) => {
  if (contextId.value) {
    const element = contextStore.get(contextId.value);
    if (element) {
      contextStore.update(contextId.value, {
        accessed_at: new Date()
      });
      console.log('[IssueArtifact] Context updated with tab:', newTab);
    }
  }
});

// Watch for artifact switches to update tab if initialTab is specified
watch(
  () => workspaceStore.activeArtifact,
  (newArtifact) => {
    if (newArtifact?.id === props.issue.id && newArtifact.initialTab) {
      activeTab.value = newArtifact.initialTab as 'details' | 'discussion';
    }
  }
);

// Watch for showAllRelated changes to fetch additional issue data
watch(showAllRelated, async (newValue) => {
  if (newValue && !isOperational(issue.value) && issue.value.related_issues.length > 5) {
    await fetchIssueData();
  }
});
</script>

<style scoped>
.issue-artifact {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--background);
  overflow: hidden;
}

/* Header */
.artifact-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-lg) var(--space-xl);
  background: var(--background);
  border-bottom: 1px solid var(--border);
  gap: var(--space-md);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  flex: 1;
  min-width: 0;
}

.close-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-base);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  transition: all var(--transition-fast);
}

.close-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
}

/* LinkedIn-style Follow Button (in header) */
.follow-btn {
  padding: 6px 16px;
  border-radius: 16px; /* Rounded pill shape like LinkedIn */
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid var(--primary);
  background: transparent;
  color: var(--primary);
  margin-right: var(--space-md);
}

.follow-btn:hover {
  background: rgba(38, 139, 210, 0.08);
}

/* Following state - filled background */
.follow-btn.is-following {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.follow-btn.is-following:hover {
  background: #1c6fa0; /* darker blue */
  border-color: #1c6fa0;
}

.status-group {
  display: flex;
  gap: var(--space-sm);
}

.status-badge,
.issue-type-badge {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-base);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.status-badge {
  background: var(--background-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border);
}

.status-badge.status-open {
  background: var(--cyan-bg);
  color: var(--cyan);
}

.status-badge.status-closed {
  background: var(--base02);
  color: var(--base01);
}

.issue-type-badge {
  background: var(--cyan-bg);
  color: var(--cyan);
}

/* Content */
.artifact-content {
  position: relative;
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xl);
}

/* Discussion Mode - when Discussion tab is active */
.artifact-content.discussion-mode {
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Primary Actions Section (prominent at top) */
.primary-actions-section {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.actions-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

/* Primary Action Buttons Row */
.action-buttons-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.btn-action {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
}

/* Primary Actions - Prominent filled buttons */
.btn-action.btn-primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.btn-action.btn-primary:hover {
  background: var(--primary-hover);
}


/* Summary + Follow Section (combined) */
.summary-follow-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 4px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
}

/* General Sections */
.issue-section,
.no-matches-section,
.discussion-group-section,
.ai-analysis-section {
  margin-bottom: 24px;
}

.discussion-group-section .section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.discussion-group-section .section-icon {
  color: var(--base01, var(--text-secondary));
}

.discussion-group-section .section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--base01, var(--text-secondary));
  margin: 0;
}

.issue-section .section-title,
.no-matches-section .section-title,
.ai-analysis-section .section-title {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-md);
}

.issue-section .section-description,
.no-matches-section .section-description,
.discussion-group-section .section-description,
.ai-analysis-section .section-description {
  font-size: 14px;
  color: var(--base01, var(--text-secondary));
  margin-bottom: 16px;
}

/* Issue Header Row (short name + status badge + status actions) */
.issue-header-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

/* Short Name */
.issue-short-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  opacity: 0.6;
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* JIRA-Style Two-Tone Status Badge */
.status-badge-jira {
  display: inline-flex;
  align-items: stretch;
  overflow: hidden;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  line-height: 1;
  background: transparent;
  border: none;
  padding: 0;
  font-family: inherit;
}

/* Clickable badge hover effect */
.status-badge-jira.clickable {
  cursor: pointer;
  transition: all 0.15s ease;
}

.status-badge-jira.clickable:hover {
  opacity: 0.85;
  transform: translateY(-1px);
}

/* Left side: "Status" label (neutral gray) */
.status-label {
  padding: 5px 8px;
  background: var(--base02, #586e75);
  color: var(--base2, #eee8d5);
  border-right: 1px solid rgba(0, 0, 0, 0.1);
}

/* Right side: Status value (status-specific color) */
.status-value {
  padding: 5px 8px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Chevron inside status badge */
.status-chevron {
  transition: transform 0.2s ease;
  opacity: 0.8;
}

.status-chevron.is-rotated {
  transform: rotate(90deg);
}

/* Status Value Colors (JIRA-style vibrant) */
.status-value.status-open {
  background: #2aa198; /* Solarized cyan - active, distinct from primary blue buttons */
  color: white;
}

.status-value.status-closed {
  background: #586e75; /* Solarized base01 - neutral gray for closed */
  color: white;
}

/* Status Actions Inline (next to status badge) */
.status-actions-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

/* Show status actions on hover */
.issue-header-row:hover .status-actions-inline {
  opacity: 1;
}

/* Inline Status Buttons (compact, JIRA-style) */
.btn-status-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.btn-status-inline:hover {
  background: rgba(38, 139, 210, 0.08);
  border-color: var(--primary);
  color: var(--primary);
}

.btn-status-inline:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Closure Context Inline (always visible when closed) */
.closure-context-inline {
  margin-top: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 6px;
  border-left: 3px solid var(--base01);
}

.closure-reason-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.closure-reason-label strong {
  color: var(--text-primary);
  font-weight: 600;
}

.closure-note {
  font-size: 14px;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.5;
  font-style: italic;
}

/* Status History Content Inline (expanded below header row) */
.status-history-content-inline {
  margin-top: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

/* Close Form Inline (expanded below header row) */
.close-form-inline {
  margin-top: 12px;
  margin-bottom: 16px;
  padding: 16px;
  background: var(--background-secondary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.close-form-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

/* Close Reason Options */
.close-reason-options {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.reason-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--background);
  border: 2px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.reason-card:hover {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.05);
}

.reason-card.selected {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.1);
}

.reason-card input[type="radio"] {
  margin: 0;
  cursor: pointer;
}

.reason-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.reason-card.selected .reason-icon {
  color: var(--primary);
}

.reason-content {
  flex: 1;
  min-width: 0;
}

.reason-title {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.reason-description {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

/* Close Note Section */
.close-note-section {
  margin-bottom: 16px;
}

.close-note-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.close-note-textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  resize: vertical;
  transition: border-color 0.15s ease;
}

.close-note-textarea:focus {
  outline: none;
  border-color: var(--primary);
}

.close-note-textarea::placeholder {
  color: var(--text-secondary);
  opacity: 0.6;
}

/* Close Form Actions */
.close-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.close-form-actions .btn-secondary,
.close-form-actions .btn-primary {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.close-form-actions .btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.close-form-actions .btn-secondary:hover:not(:disabled) {
  background: var(--background-secondary);
  border-color: var(--text-secondary);
}

.close-form-actions .btn-primary {
  background: var(--primary);
  color: white;
  border: none;
}

.close-form-actions .btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.close-form-actions .btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* AI-Generated Title */
.issue-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.3;
}

/* Issue Metadata (jurisdiction, date, location) */
.issue-metadata {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  font-size: 14px;
  color: var(--text-secondary);
}

.metadata-separator {
  opacity: 0.5;
}

/* Issue Tags Container (room for multi-tag) */
.issue-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 0 0 16px 0; /* No left/right margin - flush with title */
  padding: 0; /* No padding - truly flush */
}

/* Issue Type Tag (GitHub-style label) */
.issue-type-tag {
  display: inline-flex;
  padding: 4px 10px;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: capitalize;
  border: 1px solid rgba(0, 0, 0, 0.12); /* Very subtle border */
}

/* AI-Generated Summary (Gemini-style) */
.ai-summary {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--background-secondary);
  border-radius: 8px;
  border: 1px solid var(--base01);
  white-space: pre-line; /* Preserve line breaks for bullet points */
}

/* User Description (inside collapsible section) */
.description-section .collapsible-content {
  padding: 16px 20px;
  background: var(--background-primary);
  border-radius: 0 0 8px 8px;
}

.description-text {
  font-size: 15px;
  color: var(--text-primary);
  line-height: 1.7;
  font-style: italic;
  opacity: 0.9;
}

/* Metadata Grid */
.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-md);
}

.metadata-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.metadata-label {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}

.metadata-value {
  font-size: var(--font-size-base);
  color: var(--text-primary);
  font-weight: 500;
}

/* Summary Statistics (inside summary-follow-section) */
.summary-stats {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.summary-stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.summary-stat svg {
  color: var(--text-secondary);
  opacity: 0.8;
}

/* Meeting List - EXACT match to ThreadArtifact discussion-list */
.meeting-list {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tight gaps like sidebar */
}

.meeting-item {
  display: flex;
  align-items: flex-start;
  gap: 10px; /* EXACT match to ThreadArtifact */
  padding: 6px 0; /* No horizontal padding - parent has it */
  background: transparent;
  border: none;
  border-radius: 0; /* No radius - flush edges */
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
  width: 100%;
}

.meeting-item:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover - EXACT match */
}

.meeting-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.meeting-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px; /* Tighter - EXACT match */
}

.meeting-title {
  font-size: 13px; /* Smaller - EXACT match */
  font-weight: 500; /* Less bold - EXACT match */
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.meeting-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 400;
  opacity: 0.8;
}

.match-badge-small {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: var(--primary); /* Darker blue */
  color: white;
}

.meeting-arrow {
  color: var(--text-secondary);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s ease;
  margin-top: 1px;
}

.meeting-item:hover .meeting-arrow {
  opacity: 1;
}

/* Similar Issues List - EXACT match to ThreadArtifact discussion-list */
.similar-issue-cards {
  display: flex;
  flex-direction: column;
  gap: 2px; /* Tight gaps like sidebar */
}

.similar-issue-card {
  display: flex;
  align-items: flex-start;
  gap: 10px; /* EXACT match to ThreadArtifact */
  padding: 6px 0; /* No horizontal padding - parent has it */
  background: transparent;
  border: none;
  border-radius: 0; /* No radius - flush edges */
  cursor: pointer;
  transition: background-color 0.12s ease;
  text-align: left;
  width: 100%;
}

.similar-issue-card:hover {
  background: rgba(0, 0, 0, 0.04); /* Very subtle hover - EXACT match */
}

.issue-icon {
  color: var(--text-secondary);
  opacity: 0.7;
  flex-shrink: 0;
  margin-top: 1px;
}

.issue-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0px; /* Remove gap to tighten vertical spacing */
}

.issue-content .issue-title {
  font-size: 13px; /* Smaller - EXACT match */
  font-weight: 500; /* Less bold - EXACT match */
  color: var(--text-primary);
  line-height: 1.3; /* Tighter line height to reduce space below title */
  white-space: nowrap; /* Single line like VSCode */
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 0; /* Remove any bottom margin */
}

.issue-content .issue-short-name {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', 'Consolas', monospace;
  letter-spacing: 0.02em;
  opacity: 0.7;
  margin-top: 1px;
  margin-bottom: 2px;
}

.issue-content .issue-meta {
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

.issue-view-btn {
  color: var(--text-secondary);
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s ease;
  margin-top: 1px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
}

.similar-issue-card:hover .issue-view-btn {
  opacity: 1;
}

.show-more-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 8px 16px;
  margin-top: 12px;
  background: transparent;
  color: var(--base01, var(--text-secondary));
  border: 1px solid var(--base02, var(--border));
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.show-more-btn:hover {
  background: var(--base03, var(--background-secondary));
  border-color: var(--base01, var(--text-secondary));
}

/* AI Suggestions */
.suggestions-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.suggestion-item {
  background: var(--background-secondary);
  padding: var(--space-md);
  border-left: 4px solid var(--accent-purple);
  margin-bottom: var(--space-md);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  color: var(--text-primary);
  line-height: 1.6;
}

.icon {
  font-style: normal;
  font-size: 18px;
}

/* Scrollbar */
.artifact-content::-webkit-scrollbar {
  width: 8px;
}

.artifact-content::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.artifact-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-base);
}

.artifact-content::-webkit-scrollbar-thumb:hover {
  background: var(--primary);
}

/* Collapsible Sections - EXACT match to ThreadArtifact */
.collapsible-section {
  /* Lightweight sections - no heavy borders */
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 0;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  outline: none;
}

.collapsible-header:hover .section-title {
  color: var(--primary);
}

.collapsible-header:focus {
  outline: none; /* Ensure no blue border on focus */
}

.collapse-icon {
  color: var(--text-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.collapse-icon.is-rotated {
  transform: rotate(90deg);
}

/* Collapsible section titles (overrides .issue-section .section-title) */
.collapsible-header .section-title {
  margin: 0;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-secondary);
  flex: 1;
  line-height: 1.4;
}

.section-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.issue-count,
.meeting-count {
  color: var(--text-secondary);
  font-size: 13px;
  margin-left: auto;
}

.collapsible-content {
  padding: 12px 20px;
  background: var(--background); /* Lighter background - content area */
  border-top: 1px solid var(--border);
}

.section-description {
  font-size: 14px;
  color: var(--base01, var(--text-secondary));
  margin-bottom: 16px;
}

/* Header Tabs (moved from content area) */
.header-tabs {
  display: flex;
  gap: 2px;
  align-items: flex-end;
}

.header-tab-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-bottom: none;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  border-radius: 6px 6px 0 0; /* Round top corners only */
  position: relative;
  margin-bottom: -1px; /* Overlap with header border */
}

.header-tab-button:hover {
  color: var(--text-primary);
  background: var(--background);
}

.header-tab-button.active {
  color: var(--primary);
  background: var(--background); /* Match content background */
  border-color: var(--border);
  border-bottom: 1px solid var(--background); /* Hide bottom border to connect with content */
  font-weight: 600;
  z-index: 1; /* Appear on top */
}

/* Discussion Tab Content */
.discussion-tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Session 91: Operational Issue Styles */
.operational-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md);
  background: var(--orange-bg);
  border: 1px solid var(--orange);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-lg);
}

.operational-badge {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.operational-badge .icon {
  font-size: var(--font-size-lg);
}

.operational-badge .badge-text {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--orange);
}

.external-link {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--orange);
  border-radius: var(--radius-base);
  background: transparent;
  color: var(--orange);
  text-decoration: none;
  font-size: var(--font-size-sm);
  font-weight: 600;
  transition: all var(--transition-fast);
}

.external-link:hover {
  background: var(--orange);
  color: white;
}

/* Session 91: Matching Section Styles */
.matching-section .match-icon {
  font-size: var(--font-size-lg);
  margin-right: var(--space-xs);
}

.match-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.match-card {
  padding: var(--space-md);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-left: 3px solid var(--cyan);
  border-radius: var(--radius-base);
}

.match-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-sm);
}

.confidence-badge {
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-base);
  font-size: var(--font-size-xs);
  font-weight: 700;
  text-transform: uppercase;
}

.confidence-badge.confidence-high {
  background: var(--green-bg);
  color: var(--green);
}

.confidence-badge.confidence-medium {
  background: var(--yellow-bg);
  color: var(--yellow);
}

.confidence-badge.confidence-low {
  background: var(--orange-bg);
  color: var(--orange);
}

.match-date {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.match-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-sm) 0;
}

.match-reasoning {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-md) 0;
  line-height: 1.5;
}

.btn-view-event {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  border: 1px solid var(--primary);
  border-radius: var(--radius-base);
  background: transparent;
  color: var(--primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-view-event:hover {
  background: var(--primary);
  color: white;
}
</style>

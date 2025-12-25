<template>
  <div class="admin-status-page">
    <!-- Header -->
    <div class="artifact-header">
      <div class="header-left">
        <h2 class="header-title">
          <Activity :size="20" />
          Data Pipeline
        </h2>
        <span v-if="statusData" class="jurisdiction-badge">{{ statusData.jurisdiction }}</span>
      </div>
      <div class="header-right">
        <button class="refresh-btn" @click="loadStatus(false)" :disabled="loading" title="Refresh status">
          <RefreshCw :size="16" :class="{ 'spinning': loading }" />
          Refresh
        </button>
        <button
          v-if="!statusData?.sources"
          class="refresh-btn"
          @click="loadStatus(true)"
          :disabled="loadingSources"
          title="Check source availability (slower)"
        >
          <Download :size="16" :class="{ 'spinning': loadingSources }" />
          Check Sources
        </button>
        <button class="close-btn" @click="$emit('close')" title="Close tab">
          <span class="icon">×</span>
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !statusData" class="loading-state">
      <RefreshCw :size="24" class="spinning" />
      <p>Loading pipeline status...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <AlertCircle :size="24" />
      <p>{{ error }}</p>
      <button class="retry-btn" @click="loadStatus(false)">Retry</button>
    </div>

    <!-- Pipeline Content -->
    <div v-else-if="statusData" class="pipeline-content">
      <!-- Overall Status Banner with Plain Language Summary -->
      <div class="status-banner" :class="statusData.status">
        <div class="status-indicator">
          <CheckCircle v-if="statusData.status === 'healthy'" :size="20" />
          <AlertTriangle v-else-if="statusData.status === 'degraded'" :size="20" />
          <XCircle v-else :size="20" />
        </div>
        <div class="status-text">
          <span class="status-value">{{ formatStatus(statusData.status) }}</span>
          <span class="status-summary">{{ getStatusSummary() }}</span>
        </div>
        <span class="status-timestamp">Updated {{ formatTimeAgo(statusData.timestamp) }}</span>
      </div>

      <!-- Data Cards with Preview (SESSION 358) -->
      <div class="data-cards">
        <!-- Meetings Card -->
        <div class="data-card" :class="getMeetingsCardStatus()">
          <div class="card-header">
            <div class="card-title">
              <Calendar :size="18" />
              <span>Meetings</span>
            </div>
            <span class="card-status-badge" :class="getMeetingsCardStatus()">
              {{ getMeetingsCardStatusLabel() }}
            </span>
          </div>
          <div class="card-stat">
            <span class="stat-number">{{ getStorageMeetingsCount() }}</span>
            <span class="stat-label">tracked</span>
          </div>
          <!-- Meeting samples preview -->
          <div v-if="statusData.samples?.meetings?.length" class="card-preview">
            <div class="preview-label">Recent:</div>
            <div class="preview-table">
              <div
                v-for="meeting in statusData.samples.meetings.slice(0, 3)"
                :key="meeting.id"
                class="preview-row"
              >
                <span class="preview-date">{{ formatPreviewDate(meeting.date) }}</span>
                <span class="preview-title">{{ meeting.title }}</span>
              </div>
            </div>
          </div>
          <div v-else class="card-empty">
            No meetings loaded
          </div>
          <button class="card-action" @click="triggerFetchMeetings" :disabled="!!operationInProgress">
            <RefreshCw :size="14" :class="{ 'spinning': operationInProgress === 'fetch_meetings' }" />
            {{ operationInProgress === 'fetch_meetings' ? 'Fetching...' : 'Fetch New' }}
          </button>
        </div>

        <!-- Search Card -->
        <div class="data-card" :class="getSearchCardStatus()">
          <div class="card-header">
            <div class="card-title">
              <Search :size="18" />
              <span>Search Index</span>
            </div>
            <span class="card-status-badge" :class="getSearchCardStatus()">
              {{ getSearchCardStatusLabel() }}
            </span>
          </div>
          <div class="card-stat">
            <span class="stat-number">{{ getTotalIndexedDocs() }}</span>
            <span class="stat-label">documents indexed</span>
          </div>
          <!-- Search test preview -->
          <div v-if="statusData.samples?.search_test?.results?.length" class="card-preview">
            <div class="preview-label">Test: "{{ statusData.samples.search_test.query }}"</div>
            <div class="preview-table">
              <div
                v-for="(result, idx) in statusData.samples.search_test.results.slice(0, 2)"
                :key="idx"
                class="preview-row"
              >
                <span class="preview-score">{{ (1 - (result.distance || 0)).toFixed(2) }}</span>
                <span class="preview-title">{{ result.preview }}</span>
              </div>
            </div>
          </div>
          <div v-else class="card-empty">
            {{ statusData.chromadb?.status === 'connected' ? 'No search results' : 'Index not available' }}
          </div>
        </div>

        <!-- Issues Card -->
        <div class="data-card" :class="getIssuesCardStatus()">
          <div class="card-header">
            <div class="card-title">
              <AlertCircle :size="18" />
              <span>311 Issues</span>
            </div>
            <span class="card-status-badge" :class="getIssuesCardStatus()">
              {{ getIssuesCardStatusLabel() }}
            </span>
          </div>
          <div class="card-stat">
            <span class="stat-number">{{ getOpenIssuesCount() }}</span>
            <span class="stat-label">open issues</span>
          </div>
          <div class="card-empty">
            {{ statusData.database.issues.count > 0 ? `${statusData.database.issues.count} total from SeeClickFix` : 'Not configured' }}
          </div>
          <button class="card-action" @click="triggerRefreshSeeClickFix" :disabled="!!operationInProgress">
            <RefreshCw :size="14" :class="{ 'spinning': operationInProgress === 'refresh_seeclickfix' }" />
            {{ operationInProgress === 'refresh_seeclickfix' ? 'Fetching...' : 'Refresh' }}
          </button>
        </div>
      </div>

      <!-- Detailed Pipeline View (collapsed by default) -->
      <details class="pipeline-details">
        <summary>
          <Layers :size="16" />
          Pipeline Details
          <span class="help-hint" title="Shows the flow of data through 4 stages: Discovery → Ingestion → Storage → Indexing">
            <HelpCircle :size="12" />
          </span>
        </summary>

        <!-- Pipeline Legend (inside details) -->
        <div class="pipeline-legend">
          <span class="legend-label">Stage health:</span>
          <span class="legend-item"><span class="node fresh"></span> Up to date</span>
          <span class="legend-item"><span class="node has-data"></span> Has data</span>
          <span class="legend-item"><span class="node empty"></span> Empty</span>
        </div>

      <!-- Data Pipelines -->
      <div class="pipelines">
        <!-- Meetings Pipeline -->
        <div class="pipeline-row">
          <div class="pipeline-label">
            <Calendar :size="18" />
            <span>Meetings</span>
          </div>
          <div class="pipeline-stages">
            <!-- Source Coverage -->
            <div class="stage">
              <div class="stage-header">Coverage</div>
              <div
                class="stage-node"
                :class="getSourceNodeClass('meetings')"
                :title="getSourceTooltip('meetings')"
              >
                {{ formatSourceCount('meetings') }}
              </div>
              <div class="stage-meta">{{ getSourceMeta('meetings') }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Ingested -->
            <div class="stage">
              <div class="stage-header">Ingested</div>
              <div
                class="stage-node"
                :class="getNodeClass(statusData.database.meetings.count, statusData.database.meetings.last_updated)"
                :title="`${statusData.database.meetings.count} meetings in database`"
              >
                {{ statusData.database.meetings.count }}
              </div>
              <div class="stage-meta">{{ formatTimeAgo(statusData.database.meetings.last_updated) }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Stored (SESSION 338: 4-stage pipeline) -->
            <div class="stage">
              <div class="stage-header">Stored</div>
              <div
                class="stage-node"
                :class="getStoredNodeClass('meetings')"
                :title="getStoredTooltip('meetings')"
              >
                {{ getStoredCount('meetings') }}
              </div>
              <div class="stage-meta">{{ getStoredMeta('meetings') }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Indexed -->
            <div class="stage">
              <div class="stage-header">Indexed</div>
              <div
                class="stage-node"
                :class="getNodeClass(getCollectionCount('decisions'), null)"
                :title="`${getCollectionCount('decisions')} documents indexed`"
              >
                {{ formatSearchableCount('meetings') }}
              </div>
              <div class="stage-meta">{{ getSearchableMeta('meetings') }}</div>
            </div>
          </div>
        </div>

        <!-- Agenda Items Pipeline -->
        <div class="pipeline-row">
          <div class="pipeline-label">
            <FileText :size="18" />
            <span>Agenda Items</span>
          </div>
          <div class="pipeline-stages">
            <!-- Source (derived from meetings) -->
            <div class="stage">
              <div class="stage-header">Available</div>
              <div class="stage-node derived" title="Derived from meeting agendas">
                —
              </div>
              <div class="stage-meta">from meetings</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Ingested -->
            <div class="stage">
              <div class="stage-header">Ingested</div>
              <div
                class="stage-node"
                :class="getNodeClass(statusData.database.agenda_items.count, statusData.database.agenda_items.last_enriched)"
                :title="`${statusData.database.agenda_items.count} agenda items enriched`"
              >
                {{ statusData.database.agenda_items.count }}
              </div>
              <div class="stage-meta">{{ formatTimeAgo(statusData.database.agenda_items.last_enriched) }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Stored (SESSION 338: 4-stage pipeline) -->
            <div class="stage">
              <div class="stage-header">Stored</div>
              <div
                class="stage-node"
                :class="getStoredNodeClass('agenda_items')"
                :title="getStoredTooltip('agenda_items')"
              >
                {{ getStoredCount('agenda_items') }}
              </div>
              <div class="stage-meta">{{ getStoredMeta('agenda_items') }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Indexed -->
            <div class="stage">
              <div class="stage-header">Indexed</div>
              <div
                class="stage-node"
                :class="getNodeClass(getCollectionCount('chunks'), null)"
                :title="`${getCollectionCount('chunks')} chunks indexed`"
              >
                {{ getCollectionCount('chunks') }}
              </div>
              <div class="stage-meta">chunks</div>
            </div>
          </div>
        </div>

        <!-- Issues Pipeline -->
        <div class="pipeline-row">
          <div class="pipeline-label">
            <AlertCircle :size="18" />
            <span>Issues</span>
          </div>
          <div class="pipeline-stages">
            <!-- Source -->
            <div class="stage">
              <div class="stage-header">Available</div>
              <div class="stage-node unknown" title="SeeClickFix source not configured">
                ?
              </div>
              <div class="stage-meta">SeeClickFix</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Ingested -->
            <div class="stage">
              <div class="stage-header">Ingested</div>
              <div
                class="stage-node"
                :class="getNodeClass(statusData.database.issues.count, statusData.database.issues.last_updated)"
                :title="`${statusData.database.issues.count} issues (${getOpenIssuesCount()} open)`"
              >
                {{ statusData.database.issues.count }}
              </div>
              <div class="stage-meta">{{ getOpenIssuesCount() }} open</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Searchable -->
            <div class="stage">
              <div class="stage-header">Searchable</div>
              <div
                class="stage-node"
                :class="getNodeClass(getCollectionCount('issues'), null)"
                :title="`${getCollectionCount('issues')} issues indexed`"
              >
                {{ getCollectionCount('issues') }}
              </div>
              <div class="stage-meta">indexed</div>
            </div>
          </div>
        </div>

        <!-- Initiatives Pipeline -->
        <div class="pipeline-row">
          <div class="pipeline-label">
            <Users :size="18" />
            <span>Initiatives</span>
          </div>
          <div class="pipeline-stages">
            <!-- Source (user-created) -->
            <div class="stage">
              <div class="stage-header">Available</div>
              <div class="stage-node derived" title="Created by users">
                —
              </div>
              <div class="stage-meta">user-created</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Ingested -->
            <div class="stage">
              <div class="stage-header">Ingested</div>
              <div
                class="stage-node"
                :class="getNodeClass(statusData.database.initiatives.count, statusData.database.initiatives.last_updated)"
                :title="`${statusData.database.initiatives.count} initiatives`"
              >
                {{ statusData.database.initiatives.count }}
              </div>
              <div class="stage-meta">{{ formatTimeAgo(statusData.database.initiatives.last_updated) }}</div>
            </div>

            <div class="stage-arrow">→</div>

            <!-- Searchable -->
            <div class="stage">
              <div class="stage-header">Searchable</div>
              <div class="stage-node empty" title="Not indexed">
                —
              </div>
              <div class="stage-meta">not indexed</div>
            </div>
          </div>
        </div>
      </div>
      </details>

      <!-- Running Operation Indicator (SESSION 309/341) -->
      <div v-if="runningOperation" class="running-operation-banner">
        <div class="running-indicator">
          <RefreshCw :size="18" class="spinning" />
        </div>
        <div class="running-info">
          <span class="running-label">{{ runningOperation.label }}</span>
          <span class="running-timer">
            <Clock :size="12" />
            {{ formatElapsedTime(elapsedSeconds) }}
          </span>
          <!-- Server-side progress (SESSION 341) -->
          <span v-if="currentOperationStatus?.progress?.current_step" class="running-step">
            {{ currentOperationStatus.progress.current_step }}
          </span>
        </div>
      </div>

      <!-- Manual Operations Section -->
      <section class="operations-section">
        <h3 class="section-title">
          <Play :size="16" />
          Manual Operations
        </h3>
        <div class="operations-grid">
          <div class="operation-card">
            <div class="operation-info">
              <Download :size="18" />
              <div class="operation-text">
                <span class="operation-name">Fetch Meetings</span>
                <span class="operation-desc">Scrape ProudCity for new meetings</span>
              </div>
            </div>
            <button
              class="operation-btn"
              @click="triggerFetchMeetings"
              :disabled="!!operationInProgress"
            >
              <RefreshCw v-if="operationInProgress === 'fetch_meetings'" :size="14" class="spinning" />
              <Play v-else :size="14" />
              {{ operationInProgress === 'fetch_meetings' ? 'Running...' : 'Run' }}
            </button>
          </div>
          <div class="operation-card">
            <div class="operation-info">
              <Video :size="18" />
              <div class="operation-text">
                <span class="operation-name">Discover Videos</span>
                <span class="operation-desc">Find YouTube videos for meetings</span>
              </div>
            </div>
            <button
              class="operation-btn"
              @click="triggerDiscoverVideos"
              :disabled="!!operationInProgress"
            >
              <RefreshCw v-if="operationInProgress === 'discover_videos'" :size="14" class="spinning" />
              <Play v-else :size="14" />
              {{ operationInProgress === 'discover_videos' ? 'Running...' : 'Run' }}
            </button>
          </div>
          <div class="operation-card">
            <div class="operation-info">
              <Music :size="18" />
              <div class="operation-text">
                <span class="operation-name">Download Audio</span>
                <span class="operation-desc">Download YouTube audio for transcription</span>
              </div>
            </div>
            <button
              class="operation-btn"
              @click="triggerDownloadAudio"
              :disabled="!!operationInProgress"
            >
              <RefreshCw v-if="operationInProgress === 'download_audio'" :size="14" class="spinning" />
              <Play v-else :size="14" />
              {{ operationInProgress === 'download_audio' ? 'Running...' : 'Run' }}
            </button>
          </div>
          <div class="operation-card">
            <div class="operation-info">
              <Captions :size="18" />
              <div class="operation-text">
                <span class="operation-name">Transcribe Videos</span>
                <span class="operation-desc">Fetch YouTube captions for meeting videos</span>
              </div>
            </div>
            <button
              class="operation-btn"
              @click="triggerTranscribeVideos"
              :disabled="!!operationInProgress"
            >
              <RefreshCw v-if="operationInProgress === 'transcribe_videos'" :size="14" class="spinning" />
              <Play v-else :size="14" />
              {{ operationInProgress === 'transcribe_videos' ? 'Running...' : 'Run' }}
            </button>
          </div>
          <div class="operation-card">
            <div class="operation-info">
              <AlertCircle :size="18" />
              <div class="operation-text">
                <span class="operation-name">Refresh SeeClickFix</span>
                <span class="operation-desc">Fetch latest 311 issues from SeeClickFix</span>
              </div>
            </div>
            <button
              class="operation-btn"
              @click="triggerRefreshSeeClickFix"
              :disabled="!!operationInProgress"
            >
              <RefreshCw v-if="operationInProgress === 'refresh_seeclickfix'" :size="14" class="spinning" />
              <Play v-else :size="14" />
              {{ operationInProgress === 'refresh_seeclickfix' ? 'Running...' : 'Run' }}
            </button>
          </div>
        </div>

        <!-- Operation Result -->
        <div v-if="operationResult" class="operation-result" :class="operationResult.status">
          <div class="result-header">
            <CheckCircle v-if="operationResult.status === 'success'" :size="16" />
            <XCircle v-else :size="16" />
            <span class="result-title">{{ operationResult.operation }}</span>
          </div>
          <div class="result-details">
            <template v-if="operationResult.status === 'success'">
              <!-- fetch_meetings results -->
              <template v-if="operationResult.operation === 'fetch_meetings'">
                <span>Fetched: {{ operationResult.count_fetched }}</span>
                <span>New: {{ operationResult.count_new }}</span>
              </template>
              <!-- discover_videos results -->
              <template v-else-if="operationResult.operation === 'discover_videos'">
                <span>Meetings: {{ operationResult.count_meetings }}</span>
                <span>With Video: {{ operationResult.count_meetings_with_video }}</span>
                <span>Videos: {{ operationResult.count_videos_discovered }}</span>
              </template>
              <!-- download_audio results -->
              <template v-else-if="operationResult.operation === 'download_audio'">
                <span>Pending: {{ operationResult.count_pending }}</span>
                <span>Downloaded: {{ operationResult.count_downloaded }}</span>
                <span>Skipped: {{ operationResult.count_skipped }}</span>
                <span v-if="operationResult.count_errors">Errors: {{ operationResult.count_errors }}</span>
              </template>
              <!-- transcribe_videos results -->
              <template v-else-if="operationResult.operation === 'transcribe_videos'">
                <span>With Video: {{ operationResult.count_with_video }}</span>
                <span>Already Done: {{ operationResult.count_transcribed }}</span>
                <span>Fetched: {{ operationResult.count_fetched }}</span>
                <span v-if="operationResult.count_no_captions">No Captions: {{ operationResult.count_no_captions }}</span>
                <span v-if="operationResult.count_errors">Errors: {{ operationResult.count_errors }}</span>
              </template>
              <!-- refresh_seeclickfix results -->
              <template v-else-if="operationResult.operation === 'refresh_seeclickfix'">
                <span>Fetched: {{ operationResult.count_fetched }}</span>
                <span>New: {{ operationResult.count_new }}</span>
                <span v-if="operationResult.count_updated">Updated: {{ operationResult.count_updated }}</span>
              </template>
              <span>Duration: {{ operationResult.duration_seconds }}s</span>
            </template>
            <template v-else>
              <span class="error-message">{{ operationResult.error }}</span>
            </template>
          </div>
        </div>
      </section>

      <!-- Operation History Table (SESSION 342) -->
      <section v-if="operationHistory.length > 0" class="history-section">
        <h3 class="section-title">
          <History :size="16" />
          Operation History
        </h3>
        <div class="history-table">
          <div class="history-header">
            <span class="col-expand"></span>
            <span class="col-name">Operation</span>
            <span class="col-time">Started</span>
            <span class="col-duration">Duration</span>
            <span class="col-status">Status</span>
          </div>
          <div
            v-for="op in operationHistory"
            :key="op.operation_id"
            class="history-row-wrapper"
          >
            <div
              class="history-row"
              :class="{ expanded: historyExpanded[op.operation_id] }"
              @click="toggleHistoryRow(op.operation_id)"
            >
              <span class="col-expand">
                <ChevronDown v-if="historyExpanded[op.operation_id]" :size="14" />
                <ChevronRight v-else :size="14" />
              </span>
              <span class="col-name">{{ formatOperationName(op.name) }}</span>
              <span class="col-time">{{ formatOperationTime(op.started_at) }}</span>
              <span class="col-duration">{{ op.duration_seconds !== null ? `${op.duration_seconds}s` : '—' }}</span>
              <span class="col-status">
                <span class="status-badge" :class="getStatusBadgeClass(op.status)">
                  {{ op.status }}
                </span>
              </span>
            </div>
            <div v-if="historyExpanded[op.operation_id]" class="history-details">
              <div class="detail-row">
                <span class="detail-label">Operation ID:</span>
                <span class="detail-value monospace">{{ op.operation_id }}</span>
              </div>
              <div v-if="op.completed_at" class="detail-row">
                <span class="detail-label">Completed:</span>
                <span class="detail-value">{{ formatOperationTime(op.completed_at) }}</span>
              </div>
              <div v-if="op.progress_percent !== undefined" class="detail-row">
                <span class="detail-label">Progress:</span>
                <span class="detail-value">{{ op.progress_percent }}%</span>
              </div>
              <div v-if="op.error" class="detail-row error">
                <span class="detail-label">Error:</span>
                <span class="detail-value">{{ op.error }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Storage Details (collapsed by default) -->
      <details class="storage-details">
        <summary>
          <HardDrive :size="16" />
          Storage Details
        </summary>
        <div class="storage-content">
          <div class="storage-row">
            <span>State Database</span>
            <span>{{ formatBytes(statusData.files?.state_db_size_bytes || 0) }}</span>
          </div>
          <div class="storage-row">
            <span>Participation Database</span>
            <span>{{ formatBytes(statusData.files?.participation_db_size_bytes || 0) }}</span>
          </div>
          <div class="storage-row">
            <span>Vector Store</span>
            <span>{{ formatBytes(statusData.chromadb?.size_bytes || 0) }}</span>
          </div>
          <div class="storage-row total">
            <span>Total</span>
            <span>{{ formatBytes(totalStorageBytes) }}</span>
          </div>
        </div>
      </details>

      <!-- Data Browser -->
      <section class="data-browser-section">
        <h3 class="section-title">
          <Search :size="16" />
          Data Browser
        </h3>
        <DataBrowserWidget :jurisdiction="jurisdiction" />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { formatDistanceToNow, differenceInDays } from 'date-fns';
import {
  Activity,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Calendar,
  FileText,
  Users,
  HardDrive,
  Play,
  Download,
  Video,
  Music,
  Captions,
  Clock,
  History,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Layers,
  Search
} from 'lucide-vue-next';
import { api } from '@/services/api';
import DataBrowserWidget from '@/components/shared/DataBrowserWidget.vue';
import type { AdminStatusResponse, AdminTriggerResponse, RunningOperation, OperationStatus, OperationResult, OperationListItem } from '@/types/civic';

const props = defineProps<{
  jurisdiction?: string;
}>();

defineEmits<{
  (e: 'close'): void;
}>();

const loading = ref(false);
const loadingSources = ref(false);
const error = ref<string | null>(null);
const statusData = ref<AdminStatusResponse | null>(null);
const operationInProgress = ref<string | null>(null);
const operationResult = ref<OperationResult | null>(null);

// SESSION 342: Operation history for table display
const operationHistory = ref<OperationListItem[]>([]);
const historyExpanded = ref<Record<string, boolean>>({});

// Running operations with server-side tracking (SESSION 341)
const runningOperation = ref<RunningOperation | null>(null);
const currentOperationStatus = ref<OperationStatus | null>(null);
const elapsedSeconds = ref(0);
let elapsedTimer: ReturnType<typeof setInterval> | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
const POLL_INTERVAL_MS = 2000; // Poll every 2 seconds

const operationLabels: Record<string, string> = {
  'fetch_meetings': 'Fetching meetings from ProudCity',
  'discover_videos': 'Discovering YouTube videos',
  'download_audio': 'Downloading audio files',
  'transcribe_videos': 'Fetching video transcripts',
  'refresh_seeclickfix': 'Refreshing SeeClickFix issues'
};

function startOperationTimer(operationId: string, operation: string) {
  runningOperation.value = {
    operation_id: operationId,
    operation,
    startedAt: new Date(),
    label: operationLabels[operation] || operation
  };
  elapsedSeconds.value = 0;
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value++;
  }, 1000);
}

function stopOperationTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
  runningOperation.value = null;
  elapsedSeconds.value = 0;
}

// SESSION 341: Poll operation status from server
async function pollOperationStatus(operationId: string) {
  try {
    const status = await api.getOperationStatus(operationId);
    currentOperationStatus.value = status;

    if (status.status === 'completed' || status.status === 'failed') {
      // Operation finished - stop polling and update UI
      stopPolling();
      stopOperationTimer();
      operationInProgress.value = null;

      if (status.result) {
        operationResult.value = status.result;
      } else if (status.error) {
        operationResult.value = {
          status: 'error',
          operation: status.name,
          jurisdiction: status.jurisdiction_id.replace('city-', ''),
          timestamp: status.completed_at || new Date().toISOString(),
          error: status.error
        };
      }

      // Refresh status data and history
      if (status.status === 'completed') {
        await loadStatus(false);
      }
      // SESSION 342: Always refresh history when operation finishes
      await loadOperationHistory();
    }
  } catch (e) {
    console.error('Failed to poll operation status:', e);
    // Don't stop polling on transient errors
  }
}

function startPolling(operationId: string) {
  stopPolling(); // Clear any existing poller
  pollTimer = setInterval(() => {
    pollOperationStatus(operationId);
  }, POLL_INTERVAL_MS);
  // Also do an immediate poll
  pollOperationStatus(operationId);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  currentOperationStatus.value = null;
}

// SESSION 341: Check for running operation on mount
async function checkForRunningOperation() {
  try {
    const currentOp = await api.getCurrentOperation(props.jurisdiction || 'san-rafael');
    if (currentOp && (currentOp.status === 'pending' || currentOp.status === 'running')) {
      // Resume tracking this operation
      operationInProgress.value = currentOp.name;
      currentOperationStatus.value = currentOp;

      // Calculate elapsed time from server's started_at
      const startedAt = new Date(currentOp.started_at);
      elapsedSeconds.value = Math.floor((Date.now() - startedAt.getTime()) / 1000);

      startOperationTimer(currentOp.operation_id, currentOp.name);
      startPolling(currentOp.operation_id);
    }
  } catch (e) {
    console.error('Failed to check for running operation:', e);
  }
}

function formatElapsedTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

// SESSION 342: Load operation history
async function loadOperationHistory() {
  try {
    const response = await api.getOperations({
      jurisdiction: props.jurisdiction || 'san-rafael',
      limit: 10
    });
    operationHistory.value = response.operations;
  } catch (e) {
    console.error('Failed to load operation history:', e);
  }
}

function toggleHistoryRow(operationId: string) {
  historyExpanded.value[operationId] = !historyExpanded.value[operationId];
}

function formatOperationTime(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  } catch {
    return timestamp;
  }
}

function getStatusBadgeClass(status: string): string {
  switch (status) {
    case 'completed': return 'success';
    case 'failed': return 'error';
    case 'running': return 'running';
    case 'pending': return 'pending';
    default: return '';
  }
}

function formatOperationName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const totalStorageBytes = computed(() => {
  if (!statusData.value) return 0;
  return (
    (statusData.value.files?.state_db_size_bytes || 0) +
    (statusData.value.files?.participation_db_size_bytes || 0) +
    (statusData.value.chromadb?.size_bytes || 0)
  );
});

async function loadStatus(includeSources: boolean = false) {
  if (includeSources) {
    loadingSources.value = true;
  } else {
    loading.value = true;
  }
  error.value = null;

  try {
    statusData.value = await api.getAdminStatus(
      props.jurisdiction || 'san-rafael',
      { includeSources, includeSamples: true }
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load status';
  } finally {
    loading.value = false;
    loadingSources.value = false;
  }
}

function formatStatus(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatTimeAgo(timestamp: string | null | undefined): string {
  if (!timestamp) return 'Never';
  try {
    return formatDistanceToNow(new Date(timestamp), { addSuffix: true });
  } catch {
    return 'Unknown';
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getNodeClass(count: number | null | undefined, lastUpdated: string | null | undefined): string {
  if (!count || count === 0) return 'empty';
  if (!lastUpdated) return 'has-data';

  const days = differenceInDays(new Date(), new Date(lastUpdated));
  if (days < 7) return 'fresh';
  if (days < 30) return 'has-data';
  return 'stale';
}

function getSourceNodeClass(dataType: string): string {
  if (!statusData.value?.sources) return 'unknown';

  if (dataType === 'meetings') {
    const meetings = statusData.value.sources.meetings;
    const available = meetings?.available;
    if (available === null || available === undefined) return 'unknown';
    if (available === 0) return 'empty';
    // Show warning if coverage gaps exist
    if (meetings?.missing && meetings.missing.length > 0) return 'has-data warning';
    return 'has-data';
  }

  return 'unknown';
}

// SESSION 338: StorageBackend stats helpers for 4-stage pipeline
function getStoredNodeClass(dataType: string): string {
  if (!statusData.value?.storage) return 'unknown';
  if (statusData.value.storage.status !== 'connected') return 'unknown';

  if (dataType === 'meetings') {
    const count = statusData.value.storage.meetings?.count;
    const lastUpdated = statusData.value.storage.meetings?.last_updated;
    if (count === null || count === undefined || count === 0) return 'empty';
    if (!lastUpdated) return 'has-data';

    const days = differenceInDays(new Date(), new Date(lastUpdated));
    if (days < 7) return 'fresh';
    if (days < 30) return 'has-data';
    return 'stale';
  }

  if (dataType === 'agenda_items') {
    const count = statusData.value.storage.agenda_items?.count;
    if (count === null || count === undefined || count === 0) return 'empty';
    return 'has-data';
  }

  return 'unknown';
}

function getStoredCount(dataType: string): string {
  if (!statusData.value?.storage) return '?';
  if (statusData.value.storage.status !== 'connected') return '?';

  if (dataType === 'meetings') {
    const count = statusData.value.storage.meetings?.count;
    return count !== undefined ? String(count) : '?';
  }

  if (dataType === 'agenda_items') {
    const count = statusData.value.storage.agenda_items?.count;
    return count !== undefined ? String(count) : '?';
  }

  return '?';
}

function getStoredTooltip(dataType: string): string {
  if (!statusData.value?.storage) return 'Storage backend not available';
  if (statusData.value.storage.status !== 'connected') {
    return statusData.value.storage.error || 'Storage backend unavailable';
  }

  if (dataType === 'meetings') {
    const meetings = statusData.value.storage.meetings;
    if (!meetings) return 'No stored meetings data';
    return `${meetings.count} meetings in storage backend (SQLite)`;
  }

  if (dataType === 'agenda_items') {
    const agendaItems = statusData.value.storage.agenda_items;
    if (!agendaItems) return 'No stored agenda items data';
    return `${agendaItems.count} agenda items in storage backend`;
  }

  return 'Storage backend';
}

function getStoredMeta(dataType: string): string {
  if (!statusData.value?.storage) return 'SQLite';
  if (statusData.value.storage.status !== 'connected') return 'unavailable';

  if (dataType === 'meetings') {
    const lastUpdated = statusData.value.storage.meetings?.last_updated;
    if (lastUpdated) {
      return formatTimeAgo(lastUpdated);
    }
    return 'SQLite';
  }

  if (dataType === 'agenda_items') {
    return 'SQLite';
  }

  return statusData.value.storage.backend_type || 'SQLite';
}

function formatSourceCount(dataType: string): string {
  if (!statusData.value?.sources) return '?';

  if (dataType === 'meetings') {
    const meetings = statusData.value.sources.meetings;
    const available = meetings?.available;
    if (available === null || available === undefined) return '?';

    // Show coverage format if available: "configured/discovered"
    if (meetings?.configured_count !== undefined && meetings?.discovered_count !== undefined) {
      return `${meetings.configured_count}/${meetings.discovered_count}`;
    }

    return String(available);
  }

  return '?';
}

function getSourceTooltip(dataType: string): string {
  if (!statusData.value?.sources) return 'Click "Check Sources" to load availability';

  if (dataType === 'meetings') {
    const meetings = statusData.value.sources.meetings;
    if (!meetings) return 'No source data';
    if (meetings.error) return meetings.error;

    // Build tooltip with coverage info if available
    const lines: string[] = [`${meetings.available} meetings from ${meetings.configured_count || '?'} configured types`];

    if (meetings.coverage_percent !== undefined) {
      lines.push(`Coverage: ${meetings.coverage_percent}% (${meetings.configured_count}/${meetings.discovered_count} types)`);
    }

    if (meetings.missing && meetings.missing.length > 0) {
      const missingDisplay = meetings.missing.slice(0, 5).map(m => m.replace(/_/g, ' ')).join(', ');
      const suffix = meetings.missing.length > 5 ? ` +${meetings.missing.length - 5} more` : '';
      lines.push(`Missing: ${missingDisplay}${suffix}`);
    }

    return lines.join('\n');
  }

  return 'Unknown';
}

function getSourceMeta(dataType: string): string {
  if (!statusData.value?.sources) return 'ProudCity';

  if (dataType === 'meetings') {
    const meetings = statusData.value.sources.meetings;
    if (!meetings) return 'ProudCity';

    // Show coverage percentage if available
    if (meetings.coverage_percent !== undefined) {
      return `${meetings.coverage_percent}% coverage`;
    }

    if (meetings.last_checked) {
      return formatTimeAgo(meetings.last_checked);
    }
    return meetings.platform || 'ProudCity';
  }

  return '';
}

function getCollectionCount(collectionType: string): number {
  if (!statusData.value?.chromadb?.collections) return 0;
  const collection = statusData.value.chromadb.collections[collectionType];
  return collection?.count || 0;
}

function formatSearchableCount(dataType: string): string {
  if (dataType === 'meetings') {
    const count = getCollectionCount('decisions');
    const ingested = statusData.value?.database.meetings.count || 0;
    if (count === 0 && ingested === 0) return '0';
    if (count === 0) return '0/' + ingested;
    if (ingested === 0) return String(count);
    return `${count}/${ingested}`;
  }
  return '0';
}

function getSearchableMeta(dataType: string): string {
  if (dataType === 'meetings') {
    const count = getCollectionCount('decisions');
    const ingested = statusData.value?.database.meetings.count || 0;
    if (count === 0 && ingested > 0) return 'not indexed';
    if (count === ingested && count > 0) return 'all indexed';
    return 'indexed';
  }
  return '';
}

// SESSION 358: Data card helper functions
function getStorageMeetingsCount(): number {
  return statusData.value?.storage?.meetings?.count || 0;
}

function getMeetingsCardStatus(): string {
  const count = getStorageMeetingsCount();
  if (count === 0) return 'empty';
  const lastUpdated = statusData.value?.storage?.meetings?.last_updated;
  if (lastUpdated) {
    const days = differenceInDays(new Date(), new Date(lastUpdated));
    if (days < 7) return 'healthy';
    if (days < 14) return 'warning';
  }
  return 'stale';
}

function getMeetingsCardStatusLabel(): string {
  const status = getMeetingsCardStatus();
  if (status === 'healthy') return 'Current';
  if (status === 'warning') return 'Aging';
  if (status === 'stale') return 'Stale';
  return 'Empty';
}

function getSearchCardStatus(): string {
  if (statusData.value?.chromadb?.status !== 'connected') return 'empty';
  const total = getTotalIndexedDocs();
  if (total === 0) return 'empty';
  return 'healthy';
}

function getSearchCardStatusLabel(): string {
  if (statusData.value?.chromadb?.status !== 'connected') return 'Unavailable';
  const total = getTotalIndexedDocs();
  if (total === 0) return 'Empty';
  return 'Ready';
}

function getTotalIndexedDocs(): number {
  return statusData.value?.chromadb?.total_documents || 0;
}

function getIssuesCardStatus(): string {
  const count = statusData.value?.database.issues.count || 0;
  if (count === 0) return 'empty';
  return 'healthy';
}

function getIssuesCardStatusLabel(): string {
  const count = statusData.value?.database.issues.count || 0;
  if (count === 0) return 'Not Set Up';
  return 'Active';
}

function formatPreviewDate(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return dateStr.slice(5, 10);
  }
}

function getOpenIssuesCount(): number {
  return statusData.value?.database.issues.by_status?.open ?? 0;
}

// SESSION 358: Plain language summary helpers for improved UX
function getStatusSummary(): string {
  if (!statusData.value) return '';

  const meetingsCount = statusData.value.database.meetings.count;
  const lastUpdated = statusData.value.database.meetings.last_updated;

  if (statusData.value.status === 'healthy') {
    return `${meetingsCount} meetings tracked and up to date`;
  } else if (statusData.value.status === 'degraded') {
    // Check what's degraded
    if (!lastUpdated) return 'Some data sources need attention';
    const days = differenceInDays(new Date(), new Date(lastUpdated));
    if (days > 7) return `Data is ${days} days old - consider refreshing`;
    return 'Some pipeline stages need attention';
  } else {
    return 'Pipeline has errors that need resolution';
  }
}

function getMeetingsTooltip(): string {
  if (!statusData.value) return '';
  const count = statusData.value.database.meetings.count;
  const lastUpdated = statusData.value.database.meetings.last_updated;
  return `${count} meetings in database. Last updated: ${formatTimeAgo(lastUpdated)}`;
}

function getMeetingsFreshness(): string {
  if (!statusData.value?.database.meetings.last_updated) return 'stale';
  const days = differenceInDays(new Date(), new Date(statusData.value.database.meetings.last_updated));
  if (days < 7) return 'fresh';
  if (days < 14) return 'aging';
  return 'stale';
}

function getMeetingsFreshnessLabel(): string {
  const freshness = getMeetingsFreshness();
  if (freshness === 'fresh') return 'current';
  if (freshness === 'aging') return 'aging';
  return 'outdated';
}

function getAgendaTooltip(): string {
  if (!statusData.value) return '';
  const count = statusData.value.database.agenda_items.count;
  const lastEnriched = statusData.value.database.agenda_items.last_enriched;
  return `${count} agenda items extracted from meetings. Last enriched: ${formatTimeAgo(lastEnriched)}`;
}

function getIssuesSummary(): string {
  if (!statusData.value) return '';
  const total = statusData.value.database.issues.count;
  const open = getOpenIssuesCount();
  return `${open} open of ${total} total issues from SeeClickFix`;
}

function getGuidanceTitle(): string {
  if (!statusData.value) return '';
  if (statusData.value.status === 'degraded') return 'Data may be outdated';
  return 'Pipeline needs attention';
}

function getGuidanceAction(): string {
  if (!statusData.value) return '';

  // Check meetings freshness
  const lastUpdated = statusData.value.database.meetings.last_updated;
  if (lastUpdated) {
    const days = differenceInDays(new Date(), new Date(lastUpdated));
    if (days > 7) {
      return 'Run "Fetch Meetings" in Manual Operations below to update data.';
    }
  }

  // Check vector index
  const indexed = getCollectionCount('decisions');
  const stored = statusData.value.database.meetings.count;
  if (indexed < stored) {
    return 'Some meetings are not indexed for search. Check the pipeline details.';
  }

  return 'Expand Pipeline Details below to identify the issue.';
}

// SESSION 341: Generic async operation trigger with polling
async function triggerOperation(
  operation: string,
  triggerFn: () => Promise<AdminTriggerResponse>
) {
  operationInProgress.value = operation;
  operationResult.value = null;

  try {
    const response = await triggerFn();

    if (response.status === 'accepted' && response.operation_id) {
      // Operation started - begin polling
      startOperationTimer(response.operation_id, operation);
      startPolling(response.operation_id);
    } else if (response.status === 'error') {
      // Error starting operation
      operationResult.value = {
        status: 'error',
        operation,
        jurisdiction: props.jurisdiction || 'san-rafael',
        timestamp: new Date().toISOString(),
        error: response.error || 'Failed to start operation'
      };
      operationInProgress.value = null;
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation,
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
    operationInProgress.value = null;
  }
}

async function triggerFetchMeetings() {
  await triggerOperation('fetch_meetings', () =>
    api.triggerFetchMeetings(props.jurisdiction || 'san-rafael')
  );
}

async function triggerDiscoverVideos() {
  await triggerOperation('discover_videos', () =>
    api.triggerDiscoverVideos(props.jurisdiction || 'san-rafael')
  );
}

async function triggerDownloadAudio() {
  await triggerOperation('download_audio', () =>
    api.triggerDownloadAudio(props.jurisdiction || 'san-rafael')
  );
}

async function triggerTranscribeVideos() {
  await triggerOperation('transcribe_videos', () =>
    api.triggerTranscribeVideos(props.jurisdiction || 'san-rafael')
  );
}

async function triggerRefreshSeeClickFix() {
  await triggerOperation('refresh_seeclickfix', () =>
    api.triggerRefreshSeeClickFix(props.jurisdiction || 'san-rafael')
  );
}

onMounted(() => {
  loadStatus(false);
  // SESSION 341: Check for running operation to resume after browser refresh
  checkForRunningOperation();
  // SESSION 342: Load operation history on mount
  loadOperationHistory();
});

onUnmounted(() => {
  stopOperationTimer();
  stopPolling();
});
</script>

<style scoped>
.admin-status-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-primary);
}

/* Header */
.artifact-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.jurisdiction-badge {
  padding: 2px 8px;
  background: var(--color-bg-tertiary);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: none;
  border: none;
  border-radius: 4px;
  font-size: 18px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.close-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* Loading & Error States */
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--color-text-secondary);
}

.error-state {
  color: var(--color-error);
}

.retry-btn {
  padding: 8px 16px;
  background: var(--color-primary);
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
}

/* Pipeline Content */
.pipeline-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.status-banner.healthy {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.status-banner.degraded {
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.3);
}

.status-banner.unhealthy {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.status-banner.healthy .status-indicator { color: #22c55e; }
.status-banner.degraded .status-indicator { color: #eab308; }
.status-banner.unhealthy .status-indicator { color: #ef4444; }

.status-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.status-value {
  font-weight: 600;
  color: var(--color-text-primary);
}

.status-summary {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.status-timestamp {
  font-size: 12px;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

/* Data Cards with Preview (SESSION 358) */
.data-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.data-card {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  transition: border-color 0.15s ease;
}

.data-card.healthy {
  border-color: rgba(34, 197, 94, 0.4);
}

.data-card.warning {
  border-color: rgba(234, 179, 8, 0.4);
}

.data-card.stale, .data-card.empty {
  border-color: var(--color-border);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.card-title svg {
  color: var(--color-text-secondary);
}

.card-status-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.card-status-badge.healthy {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.card-status-badge.warning {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.card-status-badge.stale {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.card-status-badge.empty {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.card-stat {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}

.card-stat .stat-number {
  font-size: 32px;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: 1;
}

.card-stat .stat-label {
  font-size: 14px;
  color: var(--color-text-secondary);
}

.card-preview {
  flex: 1;
  min-height: 80px;
  margin-bottom: 12px;
}

.preview-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.preview-table {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.preview-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px solid var(--color-border);
}

.preview-row:last-child {
  border-bottom: none;
}

.preview-date {
  flex-shrink: 0;
  width: 50px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.preview-score {
  flex-shrink: 0;
  width: 36px;
  font-family: monospace;
  color: #22c55e;
}

.preview-title {
  flex: 1;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-empty {
  flex: 1;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--color-text-secondary);
  opacity: 0.7;
  margin-bottom: 12px;
}

.card-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.card-action:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.card-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Pipeline Details (collapsible, SESSION 358) */
.pipeline-details {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-bottom: 16px;
}

.pipeline-details summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  cursor: pointer;
  list-style: none;
  background: var(--color-bg-secondary);
}

.pipeline-details summary::-webkit-details-marker {
  display: none;
}

.pipeline-details[open] summary {
  border-bottom: 1px solid var(--color-border);
}

.pipeline-details .pipeline-legend {
  margin: 12px 16px;
}

.pipeline-details .pipelines {
  padding: 0 16px 16px;
}

.help-hint {
  margin-left: auto;
  color: var(--color-text-secondary);
  opacity: 0.5;
  cursor: help;
}

.help-hint:hover {
  opacity: 1;
}

/* Pipeline Legend */
.pipeline-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  margin-bottom: 16px;
  background: var(--color-bg-secondary);
  border-radius: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.legend-label {
  font-weight: 500;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-item .node {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.node.empty {
  background: var(--color-bg-tertiary);
  border: 2px solid var(--color-border);
}

.node.has-data {
  background: #eab308;
}

.node.fresh {
  background: #22c55e;
}

.node.stale {
  background: #ef4444;
}

.node.unknown {
  background: var(--color-bg-tertiary);
  border: 2px dashed var(--color-border);
}

.node.derived {
  background: transparent;
  border: 2px dotted var(--color-border);
}

/* Pipelines */
.pipelines {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 24px;
}

.pipeline-row {
  display: flex;
  align-items: center;
  padding: 16px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.pipeline-label {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 140px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.pipeline-stages {
  display: flex;
  align-items: center;
  flex: 1;
  justify-content: space-around;
}

.stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 80px;
}

.stage-header {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stage-node {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  cursor: default;
}

.stage-node.empty {
  background: var(--color-bg-tertiary);
  border: 2px solid var(--color-border);
  color: var(--color-text-secondary);
}

.stage-node.has-data {
  background: rgba(234, 179, 8, 0.15);
  border: 2px solid #eab308;
  color: #eab308;
}

.stage-node.has-data.warning {
  background: rgba(249, 115, 22, 0.15);
  border: 2px solid #f97316;
  color: #f97316;
}

.stage-node.fresh {
  background: rgba(34, 197, 94, 0.15);
  border: 2px solid #22c55e;
  color: #22c55e;
}

.stage-node.stale {
  background: rgba(239, 68, 68, 0.15);
  border: 2px solid #ef4444;
  color: #ef4444;
}

.stage-node.unknown {
  background: var(--color-bg-tertiary);
  border: 2px dashed var(--color-border);
  color: var(--color-text-secondary);
}

.stage-node.derived {
  background: transparent;
  border: 2px dotted var(--color-border);
  color: var(--color-text-secondary);
}

.stage-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.stage-arrow {
  color: var(--color-text-secondary);
  font-size: 18px;
  margin: 0 4px;
}

/* Operations Section */
.operations-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.operations-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.operation-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.operation-info {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--color-text-secondary);
}

.operation-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.operation-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.operation-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.operation-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--color-primary);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
}

.operation-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.operation-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Operation Result */
.operation-result {
  margin-top: 16px;
  padding: 12px 16px;
  border-radius: 8px;
}

.operation-result.success {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.operation-result.error {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.operation-result.success .result-header {
  color: #22c55e;
}

.operation-result.error .result-header {
  color: #ef4444;
}

.result-title {
  font-size: 13px;
  font-weight: 500;
  text-transform: capitalize;
}

.result-details {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.result-details .error-message {
  color: #ef4444;
}

/* Storage Details */
.storage-details {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.storage-details summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-bg-secondary);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  cursor: pointer;
  list-style: none;
}

.storage-details summary::-webkit-details-marker {
  display: none;
}

.storage-details[open] summary {
  border-bottom: 1px solid var(--color-border);
}

.storage-content {
  padding: 12px 16px;
}

.storage-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border-light, var(--color-border));
}

.storage-row:last-child {
  border-bottom: none;
}

.storage-row.total {
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Running Operation Banner (SESSION 309) */
.running-operation-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
}

.running-indicator {
  color: #3b82f6;
}

.running-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.running-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.running-timer {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #3b82f6;
  font-weight: 500;
}

.running-step {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-style: italic;
}

/* Operation History Table (SESSION 342) */
.history-section {
  margin-bottom: 24px;
}

.history-table {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.history-header {
  display: grid;
  grid-template-columns: 24px 1fr 120px 80px 100px;
  gap: 8px;
  padding: 10px 12px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.history-row-wrapper {
  border-bottom: 1px solid var(--color-border);
}

.history-row-wrapper:last-child {
  border-bottom: none;
}

.history-row {
  display: grid;
  grid-template-columns: 24px 1fr 120px 80px 100px;
  gap: 8px;
  padding: 10px 12px;
  align-items: center;
  cursor: pointer;
  transition: background 0.15s ease;
}

.history-row:hover {
  background: var(--color-bg-hover);
}

.history-row.expanded {
  background: var(--color-bg-secondary);
}

.col-expand {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

.col-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.col-time {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.col-duration {
  font-size: 12px;
  color: var(--color-text-secondary);
  text-align: right;
}

.col-status {
  display: flex;
  justify-content: flex-end;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  text-transform: capitalize;
}

.status-badge.success {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.status-badge.error {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.status-badge.running {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.status-badge.pending {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.history-details {
  padding: 8px 12px 12px 44px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border);
}

.detail-row {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}

.detail-label {
  color: var(--color-text-secondary);
  min-width: 100px;
}

.detail-value {
  color: var(--color-text-primary);
}

.detail-value.monospace {
  font-family: monospace;
  font-size: 11px;
}

.detail-row.error .detail-value {
  color: #ef4444;
}

/* Data Browser Section */
.data-browser-section {
  margin-top: 24px;
}
</style>

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
      <!-- Overall Status Banner -->
      <div class="status-banner" :class="statusData.status">
        <div class="status-indicator">
          <CheckCircle v-if="statusData.status === 'healthy'" :size="20" />
          <AlertTriangle v-else-if="statusData.status === 'degraded'" :size="20" />
          <XCircle v-else :size="20" />
        </div>
        <div class="status-text">
          <span class="status-value">{{ formatStatus(statusData.status) }}</span>
          <span class="status-timestamp">Updated {{ formatTimeAgo(statusData.timestamp) }}</span>
        </div>
      </div>

      <!-- Pipeline Legend -->
      <div class="pipeline-legend">
        <span class="legend-label">Pipeline stages:</span>
        <span class="legend-item"><span class="node empty"></span> Empty</span>
        <span class="legend-item"><span class="node has-data"></span> Has data</span>
        <span class="legend-item"><span class="node fresh"></span> Fresh (&lt;7d)</span>
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

            <!-- Searchable -->
            <div class="stage">
              <div class="stage-header">Searchable</div>
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

            <!-- Searchable -->
            <div class="stage">
              <div class="stage-header">Searchable</div>
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
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
  Captions
} from 'lucide-vue-next';
import { api } from '@/services/api';
import type { AdminStatusResponse, AdminTriggerResponse } from '@/types/civic';

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
const operationResult = ref<AdminTriggerResponse | null>(null);

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
      { includeSources }
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

function getOpenIssuesCount(): number {
  return statusData.value?.database.issues.by_status?.open ?? 0;
}

async function triggerFetchMeetings() {
  operationInProgress.value = 'fetch_meetings';
  operationResult.value = null;
  try {
    const result = await api.triggerFetchMeetings(props.jurisdiction || 'san-rafael');
    operationResult.value = result;
    if (result.status === 'success') {
      await loadStatus(false);
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation: 'fetch_meetings',
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
  } finally {
    operationInProgress.value = null;
  }
}

async function triggerDiscoverVideos() {
  operationInProgress.value = 'discover_videos';
  operationResult.value = null;
  try {
    const result = await api.triggerDiscoverVideos(props.jurisdiction || 'san-rafael');
    operationResult.value = result;
    if (result.status === 'success') {
      await loadStatus(false);
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation: 'discover_videos',
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
  } finally {
    operationInProgress.value = null;
  }
}

async function triggerDownloadAudio() {
  operationInProgress.value = 'download_audio';
  operationResult.value = null;
  try {
    const result = await api.triggerDownloadAudio(props.jurisdiction || 'san-rafael');
    operationResult.value = result;
    if (result.status === 'success') {
      await loadStatus(false);
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation: 'download_audio',
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
  } finally {
    operationInProgress.value = null;
  }
}

async function triggerTranscribeVideos() {
  operationInProgress.value = 'transcribe_videos';
  operationResult.value = null;
  try {
    const result = await api.triggerTranscribeVideos(props.jurisdiction || 'san-rafael');
    operationResult.value = result;
    if (result.status === 'success') {
      await loadStatus(false);
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation: 'transcribe_videos',
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
  } finally {
    operationInProgress.value = null;
  }
}

async function triggerRefreshSeeClickFix() {
  operationInProgress.value = 'refresh_seeclickfix';
  operationResult.value = null;
  try {
    const result = await api.triggerRefreshSeeClickFix(props.jurisdiction || 'san-rafael');
    operationResult.value = result;
    if (result.status === 'success') {
      await loadStatus(false);
    }
  } catch (e) {
    operationResult.value = {
      status: 'error',
      operation: 'refresh_seeclickfix',
      jurisdiction: props.jurisdiction || 'san-rafael',
      timestamp: new Date().toISOString(),
      error: e instanceof Error ? e.message : 'Operation failed'
    };
  } finally {
    operationInProgress.value = null;
  }
}

onMounted(() => {
  loadStatus(false);
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
  align-items: center;
  gap: 12px;
}

.status-value {
  font-weight: 600;
  color: var(--color-text-primary);
}

.status-timestamp {
  font-size: 13px;
  color: var(--color-text-secondary);
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
</style>

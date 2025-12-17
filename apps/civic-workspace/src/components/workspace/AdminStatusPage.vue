<template>
  <div class="admin-status-page">
    <!-- Header -->
    <div class="artifact-header">
      <div class="header-left">
        <h2 class="header-title">
          <Activity :size="20" />
          Pipeline Status
        </h2>
        <span v-if="statusData" class="jurisdiction-badge">{{ statusData.jurisdiction }}</span>
      </div>
      <div class="header-right">
        <button class="refresh-btn" @click="loadStatus" :disabled="loading" title="Refresh status">
          <RefreshCw :size="16" :class="{ 'spinning': loading }" />
          Refresh
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
      <button class="retry-btn" @click="loadStatus">Retry</button>
    </div>

    <!-- Status Content -->
    <div v-else-if="statusData" class="status-content">
      <!-- Overall Status Banner -->
      <div class="status-banner" :class="statusData.status">
        <div class="status-indicator">
          <CheckCircle v-if="statusData.status === 'healthy'" :size="24" />
          <AlertTriangle v-else-if="statusData.status === 'degraded'" :size="24" />
          <XCircle v-else :size="24" />
        </div>
        <div class="status-info">
          <span class="status-label">Overall Status</span>
          <span class="status-value">{{ formatStatus(statusData.status) }}</span>
        </div>
        <div class="status-timestamp">
          Updated {{ formatTimeAgo(statusData.timestamp) }}
        </div>
      </div>

      <!-- Database Section -->
      <section class="status-section">
        <div class="section-header" @click="toggleSection('database')">
          <Database :size="18" />
          <h3>Database</h3>
          <span class="connection-status" :class="statusData.database.status">
            {{ statusData.database.status }}
          </span>
          <ChevronDown :size="16" :class="{ 'rotated': !expandedSections.database }" />
        </div>
        <div v-if="expandedSections.database" class="section-content">
          <table class="status-table">
            <thead>
              <tr>
                <th>Table</th>
                <th class="align-right">Count</th>
                <th>Last Updated</th>
                <th>Health</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Meetings</td>
                <td class="align-right">{{ statusData.database.meetings.count.toLocaleString() }}</td>
                <td>{{ formatTimeAgo(statusData.database.meetings.last_updated) }}</td>
                <td><span class="health-dot" :class="getHealthClass(statusData.database.meetings.last_updated)"></span></td>
              </tr>
              <tr>
                <td>Agenda Items</td>
                <td class="align-right">{{ statusData.database.agenda_items.count.toLocaleString() }}</td>
                <td>{{ formatTimeAgo(statusData.database.agenda_items.last_enriched) }}</td>
                <td><span class="health-dot" :class="getHealthClass(statusData.database.agenda_items.last_enriched)"></span></td>
              </tr>
              <tr>
                <td>Issues ({{ statusData.database.issues.by_status.open }} open)</td>
                <td class="align-right">{{ statusData.database.issues.count.toLocaleString() }}</td>
                <td>{{ formatTimeAgo(statusData.database.issues.last_updated) }}</td>
                <td><span class="health-dot" :class="getHealthClass(statusData.database.issues.last_updated)"></span></td>
              </tr>
              <tr>
                <td>Initiatives</td>
                <td class="align-right">{{ statusData.database.initiatives.count.toLocaleString() }}</td>
                <td>{{ formatTimeAgo(statusData.database.initiatives.last_updated) }}</td>
                <td><span class="health-dot" :class="getHealthClass(statusData.database.initiatives.last_updated)"></span></td>
              </tr>
            </tbody>
          </table>
          <div class="section-footer">
            <span class="file-size">Size: {{ formatBytes(statusData.database.size_bytes) }}</span>
          </div>
        </div>
      </section>

      <!-- ChromaDB Section -->
      <section class="status-section">
        <div class="section-header" @click="toggleSection('chromadb')">
          <Layers :size="18" />
          <h3>Vector Store (ChromaDB)</h3>
          <span class="connection-status" :class="statusData.chromadb.status">
            {{ statusData.chromadb.status.replace('_', ' ') }}
          </span>
          <ChevronDown :size="16" :class="{ 'rotated': !expandedSections.chromadb }" />
        </div>
        <div v-if="expandedSections.chromadb" class="section-content">
          <div class="total-documents">
            <span class="total-label">Total Documents:</span>
            <span class="total-value">{{ statusData.chromadb.total_documents.toLocaleString() }}</span>
          </div>
          <table class="status-table">
            <thead>
              <tr>
                <th>Collection</th>
                <th class="align-right">Documents</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(collection, key) in statusData.chromadb.collections" :key="key">
                <td>{{ formatCollectionName(key) }}</td>
                <td class="align-right">{{ collection.count.toLocaleString() }}</td>
                <td>{{ formatTimeAgo(collection.created_at) }}</td>
              </tr>
            </tbody>
          </table>
          <div class="section-footer">
            <span class="file-size">Size: {{ formatBytes(statusData.chromadb.size_bytes) }}</span>
          </div>
        </div>
      </section>

      <!-- Files Section -->
      <section class="status-section">
        <div class="section-header" @click="toggleSection('files')">
          <HardDrive :size="18" />
          <h3>Storage</h3>
          <ChevronDown :size="16" :class="{ 'rotated': !expandedSections.files }" />
        </div>
        <div v-if="expandedSections.files" class="section-content">
          <table class="status-table">
            <thead>
              <tr>
                <th>File</th>
                <th class="align-right">Size</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>State Database</td>
                <td class="align-right">{{ formatBytes(statusData.files.state_db_size_bytes) }}</td>
              </tr>
              <tr>
                <td>Participation Database</td>
                <td class="align-right">{{ formatBytes(statusData.files.participation_db_size_bytes) }}</td>
              </tr>
              <tr>
                <td>Vector Store</td>
                <td class="align-right">{{ formatBytes(statusData.chromadb.size_bytes) }}</td>
              </tr>
              <tr class="total-row">
                <td><strong>Total</strong></td>
                <td class="align-right"><strong>{{ formatBytes(totalStorageBytes) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
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
  Database,
  Layers,
  HardDrive,
  ChevronDown
} from 'lucide-vue-next';
import { api } from '@/services/api';
import type { AdminStatusResponse } from '@/types/civic';

const props = defineProps<{
  jurisdiction?: string;
}>();

defineEmits<{
  (e: 'close'): void;
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const statusData = ref<AdminStatusResponse | null>(null);
const expandedSections = ref({
  database: true,
  chromadb: true,
  files: false
});

const totalStorageBytes = computed(() => {
  if (!statusData.value) return 0;
  return (
    statusData.value.files.state_db_size_bytes +
    statusData.value.files.participation_db_size_bytes +
    statusData.value.chromadb.size_bytes
  );
});

async function loadStatus() {
  loading.value = true;
  error.value = null;
  try {
    statusData.value = await api.getAdminStatus(props.jurisdiction || 'san-rafael');
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load status';
  } finally {
    loading.value = false;
  }
}

function toggleSection(section: 'database' | 'chromadb' | 'files') {
  expandedSections.value[section] = !expandedSections.value[section];
}

function formatStatus(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function formatTimeAgo(timestamp: string | null): string {
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

function formatCollectionName(key: string): string {
  // Convert snake_case to Title Case
  return key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function getHealthClass(timestamp: string | null): string {
  if (!timestamp) return 'health-unknown';
  const days = differenceInDays(new Date(), new Date(timestamp));
  if (days < 7) return 'health-good';
  if (days < 30) return 'health-warning';
  return 'health-critical';
}

onMounted(() => {
  loadStatus();
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

/* Status Content */
.status-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* Status Banner */
.status-banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 8px;
  margin-bottom: 20px;
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

.status-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.status-info .status-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.status-info .status-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.status-timestamp {
  margin-left: auto;
  font-size: 13px;
  color: var(--color-text-secondary);
}

/* Sections */
.status-section {
  margin-bottom: 16px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--color-bg-secondary);
  cursor: pointer;
  transition: background 0.15s ease;
}

.section-header:hover {
  background: var(--color-bg-hover);
}

.section-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-header .connection-status {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.connection-status.connected {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.connection-status.missing,
.connection-status.no_storage {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.connection-status.error,
.connection-status.chromadb_not_installed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.section-header svg:last-child {
  color: var(--color-text-secondary);
  transition: transform 0.2s ease;
}

.section-header svg.rotated {
  transform: rotate(-90deg);
}

.section-content {
  padding: 16px;
}

/* Tables */
.status-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.status-table th {
  padding: 8px 12px;
  text-align: left;
  font-weight: 500;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}

.status-table td {
  padding: 10px 12px;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-light);
}

.status-table tr:last-child td {
  border-bottom: none;
}

.status-table .align-right {
  text-align: right;
}

.status-table .total-row {
  background: var(--color-bg-secondary);
}

/* Health Indicators */
.health-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.health-dot.health-good {
  background: #22c55e;
}

.health-dot.health-warning {
  background: #eab308;
}

.health-dot.health-critical {
  background: #ef4444;
}

.health-dot.health-unknown {
  background: #6b7280;
}

/* Total Documents */
.total-documents {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
  background: var(--color-bg-tertiary);
  border-radius: 6px;
}

.total-label {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.total-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

/* Section Footer */
.section-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid var(--color-border-light);
}

.file-size {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>

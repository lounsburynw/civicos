<template>
  <div class="data-browser-widget">
    <!-- ERD Diagram (replaces tabs) -->
    <ERDDiagram
      :tableStats="tableStats"
      :selectedTable="selectedDataType"
      :vectorStats="vectorStats"
      @table-selected="selectDataType"
    />

    <!-- Header with filter and refresh -->
    <div class="browser-header">
      <div class="header-left">
        <span class="table-label">{{ selectedDataType.replace('_', ' ') }}</span>
        <!-- Active filter indicator -->
        <div v-if="filterColumn" class="filter-badge">
          <span>{{ filterColumn }} = {{ filterValue }}</span>
          <button class="clear-filter-btn" @click="clearFilter" title="Clear filter">
            <X :size="12" />
          </button>
        </div>
      </div>
      <div class="header-meta">
        <span v-if="data" class="record-count">
          {{ data.total }} records
        </span>
        <button class="refresh-btn" @click="loadData" :disabled="loading">
          <RefreshCw :size="14" :class="{ 'spinning': loading }" />
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !data" class="loading-state">
      <RefreshCw :size="20" class="spinning" />
      <span>Loading {{ selectedDataType }}...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <AlertCircle :size="18" />
      <span>{{ error }}</span>
      <button class="retry-btn" @click="loadData">Retry</button>
    </div>

    <!-- Data Table -->
    <div v-else-if="data && data.items.length > 0" class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th class="expand-col"></th>
            <th
              v-for="col in visibleColumns"
              :key="col"
              class="col-header"
              :class="{ primary: isPrimaryColumn(col), fk: isForeignKey(col) }"
            >
              {{ col }}
              <ExternalLink v-if="isForeignKey(col)" :size="10" class="fk-icon" />
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(item, idx) in data.items" :key="item.id || idx">
            <tr
              class="data-row"
              :class="{ expanded: expandedRows[idx] }"
              @click="toggleRow(idx)"
            >
              <td class="expand-col">
                <ChevronDown v-if="expandedRows[idx]" :size="14" />
                <ChevronRight v-else :size="14" />
              </td>
              <td
                v-for="col in visibleColumns"
                :key="col"
                class="data-cell"
                :class="{
                  'null-value': item[col] === null,
                  'fk-cell': isForeignKey(col) && item[col] !== null
                }"
                @click.stop="isForeignKey(col) && item[col] !== null ? navigateToFK(col, item[col]) : toggleRow(idx)"
              >
                <template v-if="isForeignKey(col) && item[col] !== null">
                  <span class="fk-link">{{ formatCellValue(item[col]) }}</span>
                  <ExternalLink :size="10" class="fk-link-icon" />
                </template>
                <template v-else>
                  {{ formatCellValue(item[col]) }}
                </template>
              </td>
            </tr>
            <!-- Expanded Row Detail -->
            <tr v-if="expandedRows[idx]" class="detail-row">
              <td :colspan="visibleColumns.length + 1">
                <div class="detail-content">
                  <div class="detail-header">
                    <div class="view-toggle">
                      <button
                        class="toggle-btn"
                        :class="{ active: viewMode[idx] !== 'json' }"
                        @click.stop="setViewMode(idx, 'formatted')"
                      >
                        Formatted
                      </button>
                      <button
                        class="toggle-btn"
                        :class="{ active: viewMode[idx] === 'json' }"
                        @click.stop="setViewMode(idx, 'json')"
                      >
                        Raw JSON
                      </button>
                    </div>
                  </div>

                  <!-- Formatted View -->
                  <div v-if="viewMode[idx] !== 'json'" class="formatted-view">
                    <div
                      v-for="(value, key) in item"
                      :key="key"
                      class="field-row"
                    >
                      <span class="field-name">{{ key }}</span>
                      <span class="field-type">{{ getValueType(value) }}</span>
                      <span class="field-value" :class="{ 'null-value': value === null }">
                        {{ formatFieldValue(value) }}
                      </span>
                    </div>
                  </div>

                  <!-- JSON View -->
                  <div v-else class="json-view">
                    <pre>{{ JSON.stringify(item, null, 2) }}</pre>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Empty State -->
    <div v-else-if="data && data.items.length === 0" class="empty-state">
      <Database :size="24" />
      <span>No {{ selectedDataType }} records found</span>
      <span v-if="filterColumn" class="note">Filtered by {{ filterColumn }} = {{ filterValue }}</span>
      <span v-else-if="data.note" class="note">{{ data.note }}</span>
    </div>

    <!-- Pagination -->
    <div v-if="data && data.total_pages > 1" class="pagination">
      <button
        class="page-btn"
        :disabled="data.page <= 1"
        @click="goToPage(data.page - 1)"
      >
        <ChevronLeft :size="14" />
        Prev
      </button>
      <span class="page-info">
        Page {{ data.page }} of {{ data.total_pages }}
      </span>
      <button
        class="page-btn"
        :disabled="data.page >= data.total_pages"
        @click="goToPage(data.page + 1)"
      >
        Next
        <ChevronRight :size="14" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import {
  RefreshCw,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Database,
  ExternalLink,
  X
} from 'lucide-vue-next';
import { api } from '@/services/api';
import ERDDiagram from './ERDDiagram.vue';
import type { DataBrowserResponse } from '@/types/civic';

type DataType = 'meetings' | 'agenda_items' | 'decisions' | 'issues';

const props = defineProps<{
  jurisdiction?: string;
  initialDataType?: DataType;
}>();

// Foreign key definitions (static schema)
const foreignKeys: Record<string, { column: string; targetTable: DataType; targetColumn: string }> = {
  agenda_items: { column: 'meeting_id', targetTable: 'meetings', targetColumn: 'id' },
  decisions: { column: 'agenda_item_id', targetTable: 'agenda_items', targetColumn: 'id' },
};

const selectedDataType = ref<DataType>(props.initialDataType || 'meetings');
const loading = ref(false);
const error = ref<string | null>(null);
const data = ref<DataBrowserResponse | null>(null);
const expandedRows = ref<Record<number, boolean>>({});
const viewMode = ref<Record<number, 'formatted' | 'json'>>({});
const currentPage = ref(1);
const perPage = ref(10);

// Filter state for FK navigation
const filterColumn = ref<string | null>(null);
const filterValue = ref<string | null>(null);

// Table stats for ERD (will be populated from individual API calls or cached)
const tableStats = ref({
  meetings: 0,
  agenda_items: 0,
  decisions: 0,
  issues: 0
});

// Vector stats for ERD vector layer
interface VectorCollectionStats {
  vector_count: number;
  source_count: number;
  coverage_percent: number | null;
  source_table: string;
  one_to_one: boolean;
}

interface VectorStats {
  jurisdiction_id: string;
  collections: {
    decisions?: VectorCollectionStats;
    chunks?: VectorCollectionStats;
    issues?: VectorCollectionStats;
    transcripts?: VectorCollectionStats;
  };
  embedding_model: string;
  embedding_dimension: number;
}

const vectorStats = ref<VectorStats | null>(null);

// Primary columns to show in compact table view (schema-faithful)
const primaryColumns: Record<string, string[]> = {
  meetings: ['id', 'meeting_datetime', 'title', 'status', 'source_platform'],
  agenda_items: ['id', 'meeting_id', 'item_number', 'title', 'actionability'],
  decisions: ['id', 'agenda_item_id', 'meeting_date', 'title', 'decision_type'],
  issues: ['id', 'title', 'status', 'category', 'created_at']
};

const visibleColumns = computed(() => {
  if (!data.value?.schema) return [];
  const primary = primaryColumns[selectedDataType.value] || [];
  // Use schema columns, prioritizing primary ones
  const allCols = Object.keys(data.value.schema);
  const ordered = primary.filter(c => allCols.includes(c));
  return ordered.length > 0 ? ordered : allCols.slice(0, 5);
});

function isPrimaryColumn(col: string): boolean {
  return (primaryColumns[selectedDataType.value] || []).includes(col);
}

function isForeignKey(col: string): boolean {
  const fkDef = foreignKeys[selectedDataType.value];
  return fkDef?.column === col;
}

function selectDataType(dt: DataType) {
  selectedDataType.value = dt;
  currentPage.value = 1;
  expandedRows.value = {};
  viewMode.value = {};
  filterColumn.value = null;
  filterValue.value = null;
  loadData();
}

function navigateToFK(col: string, value: any) {
  const fkDef = foreignKeys[selectedDataType.value];
  if (!fkDef || fkDef.column !== col) return;

  // Switch to target table with filter
  selectedDataType.value = fkDef.targetTable;
  filterColumn.value = fkDef.targetColumn;
  filterValue.value = String(value);
  currentPage.value = 1;
  expandedRows.value = {};
  viewMode.value = {};
  loadData();
}

function clearFilter() {
  filterColumn.value = null;
  filterValue.value = null;
  currentPage.value = 1;
  loadData();
}

async function loadData() {
  loading.value = true;
  error.value = null;

  try {
    data.value = await api.getDataBrowser(selectedDataType.value, {
      page: currentPage.value,
      perPage: perPage.value,
      jurisdiction: props.jurisdiction || 'san-rafael',
      filterColumn: filterColumn.value || undefined,
      filterValue: filterValue.value || undefined
    });

    // Update stats for current table
    if (data.value && !filterColumn.value) {
      tableStats.value[selectedDataType.value] = data.value.total;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load data';
  } finally {
    loading.value = false;
  }
}

async function loadAllStats() {
  // Load stats for all tables in parallel
  const tables: DataType[] = ['meetings', 'agenda_items', 'decisions', 'issues'];
  const promises = tables.map(async (table) => {
    try {
      const result = await api.getDataBrowser(table, {
        page: 1,
        perPage: 1,
        jurisdiction: props.jurisdiction || 'san-rafael'
      });
      tableStats.value[table] = result.total;
    } catch {
      tableStats.value[table] = 0;
    }
  });
  await Promise.all(promises);
}

async function loadVectorStats() {
  try {
    const result = await api.getVectorStats(props.jurisdiction || 'san-rafael');
    vectorStats.value = result;
  } catch (e) {
    console.warn('Could not load vector stats:', e);
    vectorStats.value = null;
  }
}

function toggleRow(idx: number) {
  expandedRows.value[idx] = !expandedRows.value[idx];
  if (expandedRows.value[idx] && !viewMode.value[idx]) {
    viewMode.value[idx] = 'formatted';
  }
}

function setViewMode(idx: number, mode: 'formatted' | 'json') {
  viewMode.value[idx] = mode;
}

function goToPage(page: number) {
  currentPage.value = page;
  expandedRows.value = {};
  viewMode.value = {};
  loadData();
}

function formatCellValue(value: any): string {
  if (value === null) return 'null';
  if (value === undefined) return '';
  if (typeof value === 'object') return '[object]';
  if (typeof value === 'string' && value.length > 40) {
    return value.substring(0, 40) + '...';
  }
  return String(value);
}

function formatFieldValue(value: any): string {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function getValueType(value: any): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

onMounted(() => {
  loadAllStats();
  loadVectorStats();
  loadData();
});
</script>

<style scoped>
.data-browser-widget {
  display: flex;
  flex-direction: column;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}

/* Header */
.browser-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.table-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  text-transform: capitalize;
}

.filter-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
  color: #3b82f6;
}

.clear-filter-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 2px;
  color: #3b82f6;
  cursor: pointer;
}

.clear-filter-btn:hover {
  background: rgba(59, 130, 246, 0.2);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.record-count {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* States */
.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px;
  color: var(--color-text-secondary);
}

.error-state {
  color: #ef4444;
}

.retry-btn {
  padding: 6px 12px;
  background: var(--color-primary);
  border: none;
  border-radius: 4px;
  font-size: 12px;
  color: white;
  cursor: pointer;
}

.note {
  font-size: 11px;
  opacity: 0.7;
}

/* Table */
.table-container {
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-family: monospace;
}

.data-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.data-table th {
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  background: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.data-table th.primary {
  color: var(--color-text-primary);
}

.data-table th.fk {
  color: #3b82f6;
}

.fk-icon {
  margin-left: 4px;
  opacity: 0.6;
}

.expand-col {
  width: 24px;
  text-align: center;
  color: var(--color-text-secondary);
}

.data-row {
  cursor: pointer;
  transition: background 0.1s ease;
}

.data-row:hover {
  background: var(--color-bg-hover);
}

.data-row.expanded {
  background: var(--color-bg-secondary);
}

.data-cell {
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.data-cell.null-value {
  color: var(--color-text-secondary);
  font-style: italic;
  opacity: 0.6;
}

.data-cell.fk-cell {
  cursor: pointer;
}

.data-cell.fk-cell:hover {
  background: rgba(59, 130, 246, 0.1);
}

.fk-link {
  color: #3b82f6;
  text-decoration: underline;
  text-decoration-style: dotted;
}

.fk-link-icon {
  margin-left: 4px;
  color: #3b82f6;
  opacity: 0.6;
}

/* Detail Row */
.detail-row {
  background: var(--color-bg-secondary);
}

.detail-row td {
  padding: 0;
  border-bottom: 1px solid var(--color-border);
}

.detail-content {
  padding: 16px;
  max-height: 300px;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.view-toggle {
  display: flex;
  gap: 4px;
  background: var(--color-bg-tertiary);
  border-radius: 4px;
  padding: 2px;
}

.toggle-btn {
  padding: 4px 10px;
  background: transparent;
  border: none;
  border-radius: 3px;
  font-size: 11px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.toggle-btn.active {
  background: white;
  color: var(--color-text-primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

/* Formatted View */
.formatted-view {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-row {
  display: grid;
  grid-template-columns: 180px 60px 1fr;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid var(--color-border);
}

.field-row:last-child {
  border-bottom: none;
}

.field-name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.field-type {
  font-size: 10px;
  color: var(--color-text-secondary);
  opacity: 0.6;
  text-transform: uppercase;
}

.field-value {
  color: var(--color-text-primary);
  word-break: break-all;
  white-space: pre-wrap;
}

.field-value.null-value {
  color: var(--color-text-secondary);
  font-style: italic;
  opacity: 0.6;
}

/* JSON View */
.json-view {
  background: var(--color-bg-tertiary);
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
}

.json-view pre {
  margin: 0;
  font-size: 11px;
  color: var(--color-text-primary);
}

/* Pagination */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  padding: 12px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.page-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.page-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>

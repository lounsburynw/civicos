<template>
  <div class="erd-diagram" :style="{ height: `${diagramHeight}px` }">
    <svg
      ref="svgRef"
      :viewBox="`0 0 ${svgWidth} ${diagramHeight}`"
      class="erd-svg"
      preserveAspectRatio="xMidYMid meet"
      @mousemove="onMouseMove"
      @mouseup="onMouseUp"
      @mouseleave="onMouseUp"
    >
      <!-- SVG Definitions for gradients -->
      <defs>
        <linearGradient id="vectorGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style="stop-color:#f0fdf4;stop-opacity:1" />
          <stop offset="100%" style="stop-color:#dcfce7;stop-opacity:1" />
        </linearGradient>
      </defs>

      <!-- Relationship lines with manual ERD notation (neutral gray) -->

      <!-- meetings (1) -> agenda_items (N) -->
      <!-- Main connector line -->
      <line
        :x1="tablePositions.meetings.x + 150 + 8"
        :y1="tablePositions.meetings.y + 22"
        :x2="tablePositions.agenda_items.x + 75"
        :y2="tablePositions.meetings.y + 22"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.agenda_items.x + 75"
        :y1="tablePositions.meetings.y + 22"
        :x2="tablePositions.agenda_items.x + 75"
        :y2="tablePositions.agenda_items.y - 8"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "One" notation at meetings (single vertical line) -->
      <line
        :x1="tablePositions.meetings.x + 150 + 4"
        :y1="tablePositions.meetings.y + 14"
        :x2="tablePositions.meetings.x + 150 + 4"
        :y2="tablePositions.meetings.y + 30"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "Many" crow's foot at agenda_items -->
      <line
        :x1="tablePositions.agenda_items.x + 75"
        :y1="tablePositions.agenda_items.y - 8"
        :x2="tablePositions.agenda_items.x + 67"
        :y2="tablePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.agenda_items.x + 75"
        :y1="tablePositions.agenda_items.y - 8"
        :x2="tablePositions.agenda_items.x + 75"
        :y2="tablePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.agenda_items.x + 75"
        :y1="tablePositions.agenda_items.y - 8"
        :x2="tablePositions.agenda_items.x + 83"
        :y2="tablePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- FK label -->
      <rect
        :x="tablePositions.agenda_items.x + 80"
        :y="tablePositions.meetings.y + 14"
        width="75"
        height="18"
        rx="4"
        fill="#f1f5f9"
        stroke="#94a3b8"
        stroke-width="1.5"
      />
      <text
        :x="tablePositions.agenda_items.x + 117"
        :y="tablePositions.meetings.y + 27"
        fill="#64748b"
        font-size="10"
        font-weight="600"
        text-anchor="middle"
        font-family="ui-monospace, monospace"
      >meeting_id</text>

      <!-- agenda_items (1) -> decisions (N) -->
      <!-- Main connector line -->
      <line
        :x1="tablePositions.agenda_items.x + 150 + 8"
        :y1="tablePositions.agenda_items.y + 22"
        :x2="tablePositions.decisions.x + 75"
        :y2="tablePositions.agenda_items.y + 22"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.decisions.x + 75"
        :y1="tablePositions.agenda_items.y + 22"
        :x2="tablePositions.decisions.x + 75"
        :y2="tablePositions.decisions.y - 8"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "One" notation at agenda_items (single vertical line) -->
      <line
        :x1="tablePositions.agenda_items.x + 150 + 4"
        :y1="tablePositions.agenda_items.y + 14"
        :x2="tablePositions.agenda_items.x + 150 + 4"
        :y2="tablePositions.agenda_items.y + 30"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "Many" crow's foot at decisions -->
      <line
        :x1="tablePositions.decisions.x + 75"
        :y1="tablePositions.decisions.y - 8"
        :x2="tablePositions.decisions.x + 67"
        :y2="tablePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.decisions.x + 75"
        :y1="tablePositions.decisions.y - 8"
        :x2="tablePositions.decisions.x + 75"
        :y2="tablePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="tablePositions.decisions.x + 75"
        :y1="tablePositions.decisions.y - 8"
        :x2="tablePositions.decisions.x + 83"
        :y2="tablePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- FK label -->
      <rect
        :x="tablePositions.decisions.x + 80"
        :y="tablePositions.agenda_items.y + 14"
        width="95"
        height="18"
        rx="4"
        fill="#f1f5f9"
        stroke="#94a3b8"
        stroke-width="1.5"
      />
      <text
        :x="tablePositions.decisions.x + 127"
        :y="tablePositions.agenda_items.y + 27"
        fill="#64748b"
        font-size="10"
        font-weight="600"
        text-anchor="middle"
        font-family="ui-monospace, monospace"
      >agenda_item_id</text>

      <!-- SESSION 367: Dynamic vector indexing lines - only shown when corpus is linked to SQL -->
      <template v-for="corpus in availableCorpusTypes" :key="`line-${corpus.corpusType}`">
        <line
          v-if="corpus.linkedTable && isLinked(corpus.corpusType) && vectorPositions[`${corpus.corpusType}_vector`]"
          :x1="tablePositions[corpus.linkedTable].x + 150 + 8"
          :y1="tablePositions[corpus.linkedTable].y + 22"
          :x2="vectorPositions[`${corpus.corpusType}_vector`].x - 8"
          :y2="vectorPositions[`${corpus.corpusType}_vector`].y + 27"
          stroke="#16a34a"
          stroke-width="2"
          stroke-dasharray="6 4"
          class="vector-line"
        />
      </template>

      <!-- Table nodes (draggable) -->
      <!-- Meetings -->
      <g
        class="table-node"
        :class="{ selected: selectedTable === 'meetings', dragging: draggingNode === 'meetings' }"
        :transform="`translate(${tablePositions.meetings.x}, ${tablePositions.meetings.y})`"
        @mousedown.prevent="startDrag($event, 'meetings')"
        @click="selectNode('meetings')"
      >
        <rect x="0" y="0" width="150" height="45" rx="8" />
        <text class="table-name" x="75" y="22">meetings</text>
        <text class="table-count" x="75" y="38">{{ tableStats.meetings }} records</text>
        <text class="drag-hint" x="140" y="12">⋮⋮</text>
      </g>

      <!-- Agenda Items -->
      <g
        class="table-node"
        :class="{ selected: selectedTable === 'agenda_items', dragging: draggingNode === 'agenda_items' }"
        :transform="`translate(${tablePositions.agenda_items.x}, ${tablePositions.agenda_items.y})`"
        @mousedown.prevent="startDrag($event, 'agenda_items')"
        @click="selectNode('agenda_items')"
      >
        <rect x="0" y="0" width="150" height="45" rx="8" />
        <text class="table-name" x="75" y="22">agenda_items</text>
        <text class="table-count" x="75" y="38">{{ tableStats.agenda_items }} records</text>
        <text class="drag-hint" x="140" y="12">⋮⋮</text>
      </g>

      <!-- Decisions -->
      <g
        class="table-node"
        :class="{ selected: selectedTable === 'decisions', dragging: draggingNode === 'decisions' }"
        :transform="`translate(${tablePositions.decisions.x}, ${tablePositions.decisions.y})`"
        @mousedown.prevent="startDrag($event, 'decisions')"
        @click="selectNode('decisions')"
      >
        <rect x="0" y="0" width="150" height="45" rx="8" />
        <text class="table-name" x="75" y="22">decisions</text>
        <text class="table-count" x="75" y="38">{{ tableStats.decisions }} records</text>
        <text class="drag-hint" x="140" y="12">⋮⋮</text>
      </g>

      <!-- Issues (standalone) -->
      <g
        class="table-node standalone"
        :class="{ selected: selectedTable === 'issues', dragging: draggingNode === 'issues' }"
        :transform="`translate(${tablePositions.issues.x}, ${tablePositions.issues.y})`"
        @mousedown.prevent="startDrag($event, 'issues')"
        @click="selectNode('issues')"
      >
        <rect x="0" y="0" width="150" height="45" rx="8" />
        <text class="table-name" x="75" y="22">issues</text>
        <text class="table-count" x="75" y="38">{{ tableStats.issues }} records</text>
        <text class="standalone-label" x="75" y="55">SeeClickFix</text>
        <text class="drag-hint" x="140" y="12">⋮⋮</text>
      </g>

      <!-- SESSION 367: Dynamic Vector Collection Nodes -->
      <template v-for="corpus in availableCorpusTypes" :key="`node-${corpus.corpusType}`">
        <g
          v-if="vectorPositions[`${corpus.corpusType}_vector`]"
          class="vector-node"
          :class="{
            dragging: draggingNode === `${corpus.corpusType}_vector`,
            'corpus-only': isCorpusOnly(corpus.corpusType),
            'is-empty': isEmpty(corpus.corpusType)
          }"
          :transform="`translate(${vectorPositions[`${corpus.corpusType}_vector`].x}, ${vectorPositions[`${corpus.corpusType}_vector`].y})`"
          @mousedown.prevent="startDrag($event, `${corpus.corpusType}_vector`)"
        >
          <rect x="0" y="0" width="140" height="55" rx="20" />
          <text class="vector-icon" x="18" y="22">&#9673;</text>
          <text class="vector-name" x="78" y="22">{{ corpus.displayName }}</text>
          <text class="vector-count" x="70" y="38">{{ formatVectorCount(corpus.corpusType) }}</text>
          <text class="vector-status" x="70" y="50">{{ formatCoverage(corpus.corpusType) }}</text>
          <text class="drag-hint" x="130" y="12">⋮⋮</text>
        </g>
      </template>

      <!-- Legend (SESSION 367: Updated to show corpus-only distinction) -->
      <g v-if="vectorStats" class="legend" :transform="`translate(${svgWidth - 180}, 10)`">
        <rect x="0" y="0" width="170" height="68" rx="6" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1" />
        <line x1="10" y1="18" x2="40" y2="18" stroke="#94a3b8" stroke-width="2" />
        <text x="48" y="22" fill="#64748b" font-size="10">FK relationship</text>
        <line x1="10" y1="36" x2="40" y2="36" stroke="#16a34a" stroke-width="2" stroke-dasharray="6 4" />
        <text x="48" y="40" fill="#64748b" font-size="10">SQL→Vector sync</text>
        <rect x="10" y="48" width="30" height="12" rx="6" fill="#fef3c7" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3 2" />
        <text x="48" y="58" fill="#64748b" font-size="10">Corpus only</text>
      </g>
    </svg>
    <!-- Resize handle (bottom-right corner) -->
    <div
      class="resize-handle"
      @mousedown.prevent="startResize"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue';
import type { VectorStatsResponse, VectorCollectionStats } from '@/types/civic';

type TableName = 'meetings' | 'agenda_items' | 'decisions' | 'issues';
type NodeName = TableName | string;  // Vector nodes are dynamic strings like 'decision_vector'

// Canonical corpus types (from API) and their display names
const CORPUS_DISPLAY_NAMES: Record<string, string> = {
  'decision': 'decisions',
  'pdf': 'chunks',
  'issue': 'issues',
  'transcript': 'transcripts',
  'municipal_code': 'municipal code',
  'legislation': 'legislation',
  'programs': 'programs'
};

// Map corpus types to their linked SQL tables (for drawing FK lines)
const CORPUS_TO_TABLE: Record<string, TableName | null> = {
  'decision': 'decisions',
  'pdf': 'agenda_items',
  'issue': 'issues',
  'transcript': null,  // transcript links to meetings but not directly FK'd
  'municipal_code': null,  // corpus-only
  'legislation': null,  // corpus-only
  'programs': null  // corpus-only
};

// Backwards-compatible aliases from API
const ALIAS_TO_CORPUS: Record<string, string> = {
  'decisions': 'decision',
  'chunks': 'pdf',
  'issues': 'issue',
  'transcripts': 'transcript'
};

// SVG sizing
const svgRef = ref<SVGSVGElement | null>(null);
const svgWidth = ref(900);
const diagramHeight = ref(280);
const minHeight = 200;
const maxHeight = 600;

// Resize state
const isResizing = ref(false);
const resizeStartY = ref(0);
const resizeStartHeight = ref(0);

function updateSvgWidth() {
  if (svgRef.value) {
    const rect = svgRef.value.getBoundingClientRect();
    // Use actual width, with minimum of 600
    svgWidth.value = Math.max(600, rect.width);
  }
}

function startResize(event: MouseEvent) {
  isResizing.value = true;
  resizeStartY.value = event.clientY;
  resizeStartHeight.value = diagramHeight.value;
  document.addEventListener('mousemove', onResizeMove);
  document.addEventListener('mouseup', stopResize);
}

function onResizeMove(event: MouseEvent) {
  if (!isResizing.value) return;
  const deltaY = event.clientY - resizeStartY.value;
  const newHeight = Math.max(minHeight, Math.min(maxHeight, resizeStartHeight.value + deltaY));
  diagramHeight.value = newHeight;
}

function stopResize() {
  isResizing.value = false;
  document.removeEventListener('mousemove', onResizeMove);
  document.removeEventListener('mouseup', stopResize);
}

onMounted(() => {
  updateSvgWidth();
  window.addEventListener('resize', updateSvgWidth);
});

onUnmounted(() => {
  window.removeEventListener('resize', updateSvgWidth);
  // Clean up resize listeners if component unmounts during resize
  document.removeEventListener('mousemove', onResizeMove);
  document.removeEventListener('mouseup', stopResize);
});

const props = defineProps<{
  tableStats: {
    meetings: number;
    agenda_items: number;
    decisions: number;
    issues: number;
  };
  selectedTable: TableName | null;
  vectorStats?: VectorStatsResponse | null;
}>();

const emit = defineEmits<{
  (e: 'table-selected', table: TableName): void;
}>();

// SESSION 367: Get canonical corpus types (excluding aliases) that are available
const availableCorpusTypes = computed(() => {
  if (!props.vectorStats?.collections) return [];

  // Get canonical types only (filter out aliases like 'decisions', 'chunks', etc.)
  return Object.entries(props.vectorStats.collections)
    .filter(([key, stats]) => {
      // Skip aliases - they duplicate canonical types
      if (ALIAS_TO_CORPUS[key]) return false;
      // Only include available collections with data
      return stats.available || stats.vector_count > 0;
    })
    .map(([key, stats]) => ({
      corpusType: key,
      stats,
      displayName: CORPUS_DISPLAY_NAMES[key] || key,
      linkedTable: CORPUS_TO_TABLE[key] || null
    }));
});

// Node positions (reactive for dragging)
// SESSION 367: Tables are static, vector positions computed dynamically
const tablePositions = reactive({
  meetings: { x: 20, y: 20 },
  agenda_items: { x: 250, y: 95 },
  decisions: { x: 480, y: 170 },
  issues: { x: 20, y: 170 }
});

// Vector node positions - computed based on available corpus types
const vectorPositions = reactive<Record<string, { x: number; y: number }>>({});

// Compute initial vector positions when corpus types change
watch(availableCorpusTypes, (types) => {
  // Layout vector nodes in a column on the right side of the diagram
  const startX = 680;
  const startY = 20;
  const spacing = 70;  // Vertical spacing between nodes

  types.forEach((type, index) => {
    const nodeKey = `${type.corpusType}_vector`;
    if (!vectorPositions[nodeKey]) {
      vectorPositions[nodeKey] = {
        x: startX,
        y: startY + (index * spacing)
      };
    }
  });
}, { immediate: true });

// Combined node positions for drag operations
const nodePositions = computed(() => ({
  ...tablePositions,
  ...vectorPositions
}));

// Drag state
const draggingNode = ref<NodeName | null>(null);
const dragOffset = ref({ x: 0, y: 0 });

function getNodePosition(node: NodeName): { x: number; y: number } | undefined {
  if (node in tablePositions) {
    return tablePositions[node as TableName];
  }
  return vectorPositions[node];
}

function setNodePosition(node: NodeName, x: number, y: number) {
  if (node in tablePositions) {
    tablePositions[node as TableName].x = x;
    tablePositions[node as TableName].y = y;
  } else if (vectorPositions[node]) {
    vectorPositions[node].x = x;
    vectorPositions[node].y = y;
  }
}

function startDrag(event: MouseEvent, node: NodeName) {
  draggingNode.value = node;
  const svg = (event.target as Element).closest('svg');
  if (!svg) return;

  const pt = svg.createSVGPoint();
  pt.x = event.clientX;
  pt.y = event.clientY;
  const svgP = pt.matrixTransform(svg.getScreenCTM()?.inverse());

  const pos = getNodePosition(node);
  if (!pos) return;

  dragOffset.value = {
    x: svgP.x - pos.x,
    y: svgP.y - pos.y
  };
}

function onMouseMove(event: MouseEvent) {
  if (!draggingNode.value) return;

  const svg = (event.target as Element).closest('svg');
  if (!svg) return;

  const pt = svg.createSVGPoint();
  pt.x = event.clientX;
  pt.y = event.clientY;
  const svgP = pt.matrixTransform(svg.getScreenCTM()?.inverse());

  // Constrain to viewBox bounds (dynamic width x height, minus node size)
  const newX = Math.max(5, Math.min(svgWidth.value - 155, svgP.x - dragOffset.value.x));
  const newY = Math.max(5, Math.min(diagramHeight.value - 60, svgP.y - dragOffset.value.y));

  setNodePosition(draggingNode.value, newX, newY);
}

function onMouseUp() {
  draggingNode.value = null;
}

function selectNode(node: TableName) {
  // Only emit selection if not dragging (or minimal movement)
  if (!draggingNode.value) {
    emit('table-selected', node);
  }
}

// SESSION 367: Check if collection is actually linked to SQL (by corpus type)
function isLinked(corpusType: string): boolean {
  const stats = props.vectorStats?.collections?.[corpusType];
  return stats?.linkage_status === 'linked';
}

// SESSION 367: Check if corpus is corpus-only (no SQL table)
function isCorpusOnly(corpusType: string): boolean {
  const stats = props.vectorStats?.collections?.[corpusType];
  return stats?.linkage_status === 'corpus_only';
}

// SESSION 367: Check if corpus is empty
function isEmpty(corpusType: string): boolean {
  const stats = props.vectorStats?.collections?.[corpusType];
  return !stats || stats.linkage_status === 'empty' || stats.vector_count === 0;
}

// Vector stats formatting - now accepts corpus type
function formatVectorCount(corpusType: string): string {
  const stats = props.vectorStats?.collections?.[corpusType];
  if (!stats) {
    return '0 docs';
  }
  return `${stats.vector_count.toLocaleString()} docs`;
}

// SESSION 367: Updated to show accurate linkage status for any corpus type
function formatCoverage(corpusType: string): string {
  const stats = props.vectorStats?.collections?.[corpusType];
  if (!stats) {
    return 'no data';
  }

  // Show status based on actual linkage
  switch (stats.linkage_status) {
    case 'linked':
      // Show actual linked count vs source count
      if (stats.source_count > 0) {
        return `${stats.linked_count}/${stats.source_count} linked`;
      }
      return `${stats.vector_count} linked`;

    case 'corpus_only':
      // Show corpus source if available
      if (stats.corpus_source) {
        const shortName = stats.corpus_source
          .replace('.json', '')
          .replace(/_/g, ' ')
          .replace(/city-san-rafael/i, '')
          .trim();
        return shortName ? `from ${shortName}` : 'corpus only';
      }
      return 'corpus only';

    case 'not_indexed':
      return 'not indexed';

    case 'empty':
    default:
      return 'no data';
  }
}

// SESSION 367: Get display name for corpus type
function getCorpusDisplayName(corpusType: string): string {
  return CORPUS_DISPLAY_NAMES[corpusType] || corpusType;
}
</script>

<style scoped>
.erd-diagram {
  position: relative;
  padding: 0;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.erd-svg {
  width: 100%;
  height: 100%;
  display: block;
  user-select: none;
}

/* Resize handle - bottom right corner */
.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(
    135deg,
    transparent 30%,
    #cbd5e1 30%,
    #cbd5e1 40%,
    transparent 40%,
    transparent 50%,
    #cbd5e1 50%,
    #cbd5e1 60%,
    transparent 60%,
    transparent 70%,
    #cbd5e1 70%,
    #cbd5e1 80%,
    transparent 80%
  );
  opacity: 0.6;
  transition: opacity 0.15s ease;
}

.resize-handle:hover {
  opacity: 1;
}

/* Table nodes */
.table-node {
  cursor: grab;
}

.table-node:active,
.table-node.dragging {
  cursor: grabbing;
}

.table-node rect {
  fill: #ffffff;
  stroke: #cbd5e1;
  stroke-width: 2;
  transition: fill 0.15s ease, stroke 0.15s ease;
}

.table-node:hover rect {
  fill: #f1f5f9;
  stroke: #94a3b8;
}

.table-node.selected rect {
  stroke: #3b82f6;
  stroke-width: 3;
  fill: #eff6ff;
}

.table-node.dragging rect {
  stroke: #3b82f6;
  stroke-width: 3;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.1));
}

.table-node.standalone rect {
  stroke-dasharray: 4 2;
}

.table-name {
  font-size: 13px;
  font-weight: 600;
  fill: #1e293b;
  text-anchor: middle;
  pointer-events: none;
}

.table-count {
  font-size: 11px;
  fill: #64748b;
  text-anchor: middle;
  pointer-events: none;
}

.standalone-label {
  font-size: 9px;
  fill: #94a3b8;
  text-anchor: middle;
  pointer-events: none;
}

.drag-hint {
  font-size: 10px;
  fill: #cbd5e1;
  text-anchor: middle;
  pointer-events: none;
}

.table-node:hover .drag-hint,
.vector-node:hover .drag-hint {
  fill: #94a3b8;
}

/* Vector nodes */
.vector-node {
  cursor: grab;
}

.vector-node:active,
.vector-node.dragging {
  cursor: grabbing;
}

.vector-node rect {
  fill: url(#vectorGradient);
  stroke: #16a34a;
  stroke-width: 2;
  transition: fill 0.15s ease, stroke 0.15s ease;
}

.vector-node:hover rect {
  stroke: #15803d;
  filter: drop-shadow(0 2px 4px rgba(22, 163, 74, 0.2));
}

.vector-node.dragging rect {
  stroke: #15803d;
  stroke-width: 3;
  filter: drop-shadow(0 4px 6px rgba(22, 163, 74, 0.3));
}

/* SESSION 367: Corpus-only styling (amber/yellow - no SQL linkage) */
.vector-node.corpus-only rect {
  fill: #fef3c7;
  stroke: #f59e0b;
  stroke-dasharray: 4 2;
}

.vector-node.corpus-only:hover rect {
  stroke: #d97706;
  filter: drop-shadow(0 2px 4px rgba(245, 158, 11, 0.2));
}

.vector-node.corpus-only .vector-icon {
  fill: #f59e0b;
}

.vector-node.corpus-only .vector-name {
  fill: #b45309;
}

.vector-node.corpus-only .vector-count {
  fill: #d97706;
}

.vector-node.corpus-only .vector-status {
  fill: #f59e0b;
}

/* SESSION 367: Empty corpus styling (dimmed) */
.vector-node.is-empty rect {
  fill: #f1f5f9;
  stroke: #cbd5e1;
  opacity: 0.6;
}

.vector-node.is-empty .vector-icon,
.vector-node.is-empty .vector-name,
.vector-node.is-empty .vector-count,
.vector-node.is-empty .vector-status {
  fill: #94a3b8;
  opacity: 0.6;
}

.vector-icon {
  font-size: 16px;
  fill: #16a34a;
  pointer-events: none;
}

.vector-name {
  font-size: 12px;
  font-weight: 600;
  fill: #166534;
  text-anchor: middle;
  pointer-events: none;
}

.vector-count {
  font-size: 10px;
  fill: #16a34a;
  text-anchor: middle;
  pointer-events: none;
}

.vector-status {
  font-size: 9px;
  fill: #22c55e;
  text-anchor: middle;
  pointer-events: none;
}

/* Vector connection lines */
.vector-line {
  opacity: 0.7;
  transition: opacity 0.15s ease;
}

.vector-line:hover {
  opacity: 1;
}

/* Legend */
.legend text {
  pointer-events: none;
}
</style>

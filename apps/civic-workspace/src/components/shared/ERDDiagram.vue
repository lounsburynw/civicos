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
        :x1="nodePositions.meetings.x + 150 + 8"
        :y1="nodePositions.meetings.y + 22"
        :x2="nodePositions.agenda_items.x + 75"
        :y2="nodePositions.meetings.y + 22"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.agenda_items.x + 75"
        :y1="nodePositions.meetings.y + 22"
        :x2="nodePositions.agenda_items.x + 75"
        :y2="nodePositions.agenda_items.y - 8"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "One" notation at meetings (single vertical line) -->
      <line
        :x1="nodePositions.meetings.x + 150 + 4"
        :y1="nodePositions.meetings.y + 14"
        :x2="nodePositions.meetings.x + 150 + 4"
        :y2="nodePositions.meetings.y + 30"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "Many" crow's foot at agenda_items -->
      <line
        :x1="nodePositions.agenda_items.x + 75"
        :y1="nodePositions.agenda_items.y - 8"
        :x2="nodePositions.agenda_items.x + 67"
        :y2="nodePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.agenda_items.x + 75"
        :y1="nodePositions.agenda_items.y - 8"
        :x2="nodePositions.agenda_items.x + 75"
        :y2="nodePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.agenda_items.x + 75"
        :y1="nodePositions.agenda_items.y - 8"
        :x2="nodePositions.agenda_items.x + 83"
        :y2="nodePositions.agenda_items.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- FK label -->
      <rect
        :x="nodePositions.agenda_items.x + 80"
        :y="nodePositions.meetings.y + 14"
        width="75"
        height="18"
        rx="4"
        fill="#f1f5f9"
        stroke="#94a3b8"
        stroke-width="1.5"
      />
      <text
        :x="nodePositions.agenda_items.x + 117"
        :y="nodePositions.meetings.y + 27"
        fill="#64748b"
        font-size="10"
        font-weight="600"
        text-anchor="middle"
        font-family="ui-monospace, monospace"
      >meeting_id</text>

      <!-- agenda_items (1) -> decisions (N) -->
      <!-- Main connector line -->
      <line
        :x1="nodePositions.agenda_items.x + 150 + 8"
        :y1="nodePositions.agenda_items.y + 22"
        :x2="nodePositions.decisions.x + 75"
        :y2="nodePositions.agenda_items.y + 22"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.decisions.x + 75"
        :y1="nodePositions.agenda_items.y + 22"
        :x2="nodePositions.decisions.x + 75"
        :y2="nodePositions.decisions.y - 8"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "One" notation at agenda_items (single vertical line) -->
      <line
        :x1="nodePositions.agenda_items.x + 150 + 4"
        :y1="nodePositions.agenda_items.y + 14"
        :x2="nodePositions.agenda_items.x + 150 + 4"
        :y2="nodePositions.agenda_items.y + 30"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- "Many" crow's foot at decisions -->
      <line
        :x1="nodePositions.decisions.x + 75"
        :y1="nodePositions.decisions.y - 8"
        :x2="nodePositions.decisions.x + 67"
        :y2="nodePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.decisions.x + 75"
        :y1="nodePositions.decisions.y - 8"
        :x2="nodePositions.decisions.x + 75"
        :y2="nodePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <line
        :x1="nodePositions.decisions.x + 75"
        :y1="nodePositions.decisions.y - 8"
        :x2="nodePositions.decisions.x + 83"
        :y2="nodePositions.decisions.y"
        stroke="#94a3b8"
        stroke-width="2"
      />
      <!-- FK label -->
      <rect
        :x="nodePositions.decisions.x + 80"
        :y="nodePositions.agenda_items.y + 14"
        width="95"
        height="18"
        rx="4"
        fill="#f1f5f9"
        stroke="#94a3b8"
        stroke-width="1.5"
      />
      <text
        :x="nodePositions.decisions.x + 127"
        :y="nodePositions.agenda_items.y + 27"
        fill="#64748b"
        font-size="10"
        font-weight="600"
        text-anchor="middle"
        font-family="ui-monospace, monospace"
      >agenda_item_id</text>

      <!-- Vector indexing lines (dashed) -->
      <!-- decisions -> decisions_vector -->
      <line
        v-if="vectorStats"
        :x1="nodePositions.decisions.x + 150 + 8"
        :y1="nodePositions.decisions.y + 22"
        :x2="nodePositions.decisions_vector.x - 8"
        :y2="nodePositions.decisions_vector.y + 27"
        stroke="#16a34a"
        stroke-width="2"
        stroke-dasharray="6 4"
        class="vector-line"
      />

      <!-- agenda_items -> chunks_vector -->
      <line
        v-if="vectorStats"
        :x1="nodePositions.agenda_items.x + 150 + 8"
        :y1="nodePositions.agenda_items.y + 35"
        :x2="nodePositions.chunks_vector.x - 8"
        :y2="nodePositions.chunks_vector.y + 27"
        stroke="#16a34a"
        stroke-width="2"
        stroke-dasharray="6 4"
        class="vector-line"
      />

      <!-- issues -> issues_vector -->
      <line
        v-if="vectorStats"
        :x1="nodePositions.issues.x + 150 + 8"
        :y1="nodePositions.issues.y + 22"
        :x2="nodePositions.issues_vector.x - 8"
        :y2="nodePositions.issues_vector.y + 27"
        stroke="#16a34a"
        stroke-width="2"
        stroke-dasharray="6 4"
        class="vector-line"
      />

      <!-- Table nodes (draggable) -->
      <!-- Meetings -->
      <g
        class="table-node"
        :class="{ selected: selectedTable === 'meetings', dragging: draggingNode === 'meetings' }"
        :transform="`translate(${nodePositions.meetings.x}, ${nodePositions.meetings.y})`"
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
        :transform="`translate(${nodePositions.agenda_items.x}, ${nodePositions.agenda_items.y})`"
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
        :transform="`translate(${nodePositions.decisions.x}, ${nodePositions.decisions.y})`"
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
        :transform="`translate(${nodePositions.issues.x}, ${nodePositions.issues.y})`"
        @mousedown.prevent="startDrag($event, 'issues')"
        @click="selectNode('issues')"
      >
        <rect x="0" y="0" width="150" height="45" rx="8" />
        <text class="table-name" x="75" y="22">issues</text>
        <text class="table-count" x="75" y="38">{{ tableStats.issues }} records</text>
        <text class="standalone-label" x="75" y="55">SeeClickFix</text>
        <text class="drag-hint" x="140" y="12">⋮⋮</text>
      </g>

      <!-- Vector Collection Nodes -->
      <!-- Decisions Vector -->
      <g
        v-if="vectorStats"
        class="vector-node"
        :class="{ dragging: draggingNode === 'decisions_vector' }"
        :transform="`translate(${nodePositions.decisions_vector.x}, ${nodePositions.decisions_vector.y})`"
        @mousedown.prevent="startDrag($event, 'decisions_vector')"
      >
        <rect x="0" y="0" width="140" height="55" rx="20" />
        <text class="vector-icon" x="18" y="22">&#9673;</text>
        <text class="vector-name" x="78" y="22">decisions</text>
        <text class="vector-count" x="70" y="38">{{ formatVectorCount('decisions') }}</text>
        <text class="vector-status" x="70" y="50">{{ formatCoverage('decisions') }}</text>
        <text class="drag-hint" x="130" y="12">⋮⋮</text>
      </g>

      <!-- Chunks Vector -->
      <g
        v-if="vectorStats"
        class="vector-node"
        :class="{ dragging: draggingNode === 'chunks_vector' }"
        :transform="`translate(${nodePositions.chunks_vector.x}, ${nodePositions.chunks_vector.y})`"
        @mousedown.prevent="startDrag($event, 'chunks_vector')"
      >
        <rect x="0" y="0" width="140" height="55" rx="20" />
        <text class="vector-icon" x="18" y="22">&#9673;</text>
        <text class="vector-name" x="78" y="22">chunks</text>
        <text class="vector-count" x="70" y="38">{{ formatVectorCount('chunks') }}</text>
        <text class="vector-status" x="70" y="50">{{ formatCoverage('chunks') }}</text>
        <text class="drag-hint" x="130" y="12">⋮⋮</text>
      </g>

      <!-- Issues Vector -->
      <g
        v-if="vectorStats"
        class="vector-node"
        :class="{ dragging: draggingNode === 'issues_vector' }"
        :transform="`translate(${nodePositions.issues_vector.x}, ${nodePositions.issues_vector.y})`"
        @mousedown.prevent="startDrag($event, 'issues_vector')"
      >
        <rect x="0" y="0" width="140" height="55" rx="20" />
        <text class="vector-icon" x="18" y="22">&#9673;</text>
        <text class="vector-name" x="78" y="22">issues</text>
        <text class="vector-count" x="70" y="38">{{ formatVectorCount('issues') }}</text>
        <text class="vector-status" x="70" y="50">{{ formatCoverage('issues') }}</text>
        <text class="drag-hint" x="130" y="12">⋮⋮</text>
      </g>

      <!-- Legend -->
      <g v-if="vectorStats" class="legend" :transform="`translate(${svgWidth - 180}, 10)`">
        <rect x="0" y="0" width="170" height="50" rx="6" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1" />
        <line x1="10" y1="18" x2="40" y2="18" stroke="#94a3b8" stroke-width="2" />
        <text x="48" y="22" fill="#64748b" font-size="10">FK relationship</text>
        <line x1="10" y1="36" x2="40" y2="36" stroke="#16a34a" stroke-width="2" stroke-dasharray="6 4" />
        <text x="48" y="40" fill="#64748b" font-size="10">Vector indexing</text>
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
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue';

type TableName = 'meetings' | 'agenda_items' | 'decisions' | 'issues';
type VectorName = 'decisions_vector' | 'chunks_vector' | 'issues_vector';
type NodeName = TableName | VectorName;

interface VectorCollectionStats {
  vector_count: number;
  source_count: number;
  coverage_percent: number | null;
  source_table: string;
  one_to_one: boolean;
  corpus_source?: string | null;  // e.g., "nov17_chunks.json"
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
  vectorStats?: VectorStats | null;
}>();

const emit = defineEmits<{
  (e: 'table-selected', table: TableName): void;
}>();

// Node positions (reactive for dragging)
const nodePositions = reactive({
  // Tables
  meetings: { x: 20, y: 20 },
  agenda_items: { x: 250, y: 95 },
  decisions: { x: 480, y: 170 },
  issues: { x: 20, y: 170 },
  // Vector collections
  decisions_vector: { x: 680, y: 155 },
  chunks_vector: { x: 450, y: 20 },
  issues_vector: { x: 200, y: 200 }
});

// Drag state
const draggingNode = ref<NodeName | null>(null);
const dragOffset = ref({ x: 0, y: 0 });

function startDrag(event: MouseEvent, node: NodeName) {
  draggingNode.value = node;
  const svg = (event.target as Element).closest('svg');
  if (!svg) return;

  const pt = svg.createSVGPoint();
  pt.x = event.clientX;
  pt.y = event.clientY;
  const svgP = pt.matrixTransform(svg.getScreenCTM()?.inverse());

  dragOffset.value = {
    x: svgP.x - nodePositions[node].x,
    y: svgP.y - nodePositions[node].y
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

  nodePositions[draggingNode.value].x = newX;
  nodePositions[draggingNode.value].y = newY;
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

// Vector stats formatting
function formatVectorCount(collection: 'decisions' | 'chunks' | 'issues'): string {
  if (!props.vectorStats?.collections?.[collection]) {
    return '0 docs';
  }
  const count = props.vectorStats.collections[collection]?.vector_count ?? 0;
  return `${count.toLocaleString()} docs`;
}

function formatCoverage(collection: 'decisions' | 'chunks' | 'issues'): string {
  if (!props.vectorStats?.collections?.[collection]) {
    return 'no data';
  }
  const stats = props.vectorStats.collections[collection]!;

  // If we have a corpus source file, show that
  if (stats.corpus_source) {
    // Shorten filename for display (e.g., "nov17_chunks.json" -> "nov17 corpus")
    const shortName = stats.corpus_source
      .replace('.json', '')
      .replace(/_/g, ' ')
      .replace(/city-san-rafael/i, '')
      .trim();
    return shortName ? `from ${shortName}` : 'from corpus';
  }

  // If we have SQL data with 1:1 mapping, show coverage
  if (stats.one_to_one && stats.source_count > 0) {
    const status = stats.coverage_percent !== null && stats.coverage_percent >= 100 ? '✓' : '⚠';
    return `${stats.vector_count}/${stats.source_count} ${status}`;
  }

  // No data case
  if (stats.vector_count === 0) {
    return 'not indexed';
  }

  return `${stats.vector_count} docs`;
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

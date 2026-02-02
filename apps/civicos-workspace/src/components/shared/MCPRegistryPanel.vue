<template>
  <div class="mcp-registry-panel">
    <div class="panel-header">
      <div class="header-content">
        <Server class="header-icon" :size="18" />
        <h3>MCP Data Sources</h3>
      </div>
      <button
        @click="refreshRegistry(true)"
        :disabled="loading"
        class="refresh-btn"
        title="Check health status"
      >
        <RefreshCw :class="{ spinning: loading }" :size="14" />
      </button>
    </div>

    <div v-if="error" class="error-message">
      {{ error }}
    </div>

    <div v-else-if="loading && !registry" class="loading-state">
      Loading registry...
    </div>

    <div v-else-if="registry" class="operators-list">
      <div
        v-for="operator in registry.operators"
        :key="operator.id"
        class="operator-card"
        :class="{ 'is-active': operator.status === 'active' }"
      >
        <div class="operator-header">
          <div class="operator-name">
            <span class="name">{{ operator.name }}</span>
            <span class="type-badge" :class="operator.type">{{ operator.type }}</span>
          </div>
          <div class="health-indicator" :class="getHealthClass(operator)">
            <span class="health-dot"></span>
            <span class="health-label">{{ getHealthLabel(operator) }}</span>
          </div>
        </div>

        <p v-if="operator.description" class="operator-description">
          {{ operator.description }}
        </p>

        <div class="operator-details">
          <div class="detail-row">
            <MapPin :size="12" />
            <span>{{ formatLocation(operator) }}</span>
          </div>
          <div class="detail-row" v-if="operator.tools_count">
            <Wrench :size="12" />
            <span>{{ operator.tools_count }} tools</span>
          </div>
          <div class="detail-row" v-if="operator.health?.response_time_ms">
            <Zap :size="12" />
            <span>{{ operator.health.response_time_ms }}ms</span>
          </div>
        </div>

        <div class="data-types" v-if="operator.authoritative_for?.length">
          <span
            v-for="dataType in operator.authoritative_for.slice(0, 4)"
            :key="dataType"
            class="data-type-tag"
          >
            {{ dataType }}
          </span>
          <span v-if="operator.authoritative_for.length > 4" class="more-tag">
            +{{ operator.authoritative_for.length - 4 }}
          </span>
        </div>

        <div class="operator-footer">
          <a
            :href="operator.mcp_endpoint"
            target="_blank"
            rel="noopener noreferrer"
            class="endpoint-link"
          >
            <ExternalLink :size="12" />
            <span>{{ formatEndpoint(operator.mcp_endpoint) }}</span>
          </a>
        </div>
      </div>

      <div v-if="registry.operators.length === 0" class="empty-state">
        No MCP servers registered yet.
      </div>
    </div>

    <div class="registry-footer" v-if="registry">
      <div class="registry-meta">
        <span>Registry v{{ registry.version }}</span>
        <span class="separator">|</span>
        <span>Updated {{ formatDate(registry.updated) }}</span>
      </div>
      <a
        v-if="registry.metadata?.documentation_url"
        :href="registry.metadata.documentation_url"
        target="_blank"
        rel="noopener noreferrer"
        class="docs-link"
      >
        <BookOpen :size="12" />
        <span>Docs</span>
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Server, RefreshCw, MapPin, Wrench, Zap, ExternalLink, BookOpen } from 'lucide-vue-next';
import { api } from '@/services/api';
import type { MCPRegistry, MCPOperator } from '@/types/civic';

const registry = ref<MCPRegistry | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function refreshRegistry(checkHealth: boolean = false) {
  loading.value = true;
  error.value = null;

  try {
    registry.value = await api.getMCPRegistry(checkHealth);
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load registry';
  } finally {
    loading.value = false;
  }
}

function getHealthClass(operator: MCPOperator): string {
  if (!operator.health) return 'unknown';
  return operator.health.status;
}

function getHealthLabel(operator: MCPOperator): string {
  if (!operator.health) return 'Unknown';
  switch (operator.health.status) {
    case 'healthy': return 'Online';
    case 'unhealthy': return 'Offline';
    default: return 'Unknown';
  }
}

function formatLocation(operator: MCPOperator): string {
  if (!operator.location) return operator.jurisdiction_id;
  const { city, county, state } = operator.location;
  if (county) return `${city}, ${county} County, ${state}`;
  return `${city}, ${state}`;
}

function formatEndpoint(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname + parsed.pathname;
  } catch {
    return url;
  }
}

function formatDate(isoDate: string): string {
  try {
    const date = new Date(isoDate);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  } catch {
    return isoDate;
  }
}

onMounted(() => {
  refreshRegistry(false);
});
</script>

<style scoped>
.mcp-registry-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--bg-secondary, #f8f9fa);
  border-radius: 8px;
  font-size: 13px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  color: var(--text-secondary, #666);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #333);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary, #666);
  cursor: pointer;
  transition: all 0.15s ease;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-hover, #e9ecef);
  color: var(--text-primary, #333);
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

.error-message {
  padding: 8px 12px;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 6px;
  font-size: 12px;
}

.loading-state {
  padding: 16px;
  text-align: center;
  color: var(--text-secondary, #666);
}

.operators-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.operator-card {
  padding: 12px;
  background: var(--bg-primary, #fff);
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 8px;
  transition: border-color 0.15s ease;
}

.operator-card.is-active {
  border-left: 3px solid var(--accent-color, #3b82f6);
}

.operator-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.operator-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.operator-name .name {
  font-weight: 600;
  color: var(--text-primary, #333);
}

.type-badge {
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  border-radius: 4px;
  letter-spacing: 0.02em;
}

.type-badge.official {
  background: #dbeafe;
  color: #1d4ed8;
}

.type-badge.community {
  background: #dcfce7;
  color: #15803d;
}

.type-badge.experimental {
  background: #fef3c7;
  color: #b45309;
}

.health-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.health-indicator.healthy .health-dot {
  background: #22c55e;
}

.health-indicator.unhealthy .health-dot {
  background: #ef4444;
}

.health-indicator.unknown .health-dot {
  background: #9ca3af;
}

.health-label {
  color: var(--text-secondary, #666);
}

.operator-description {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: var(--text-secondary, #666);
  line-height: 1.4;
}

.operator-details {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-secondary, #666);
}

.data-types {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.data-type-tag {
  padding: 2px 6px;
  font-size: 10px;
  background: var(--bg-tertiary, #f3f4f6);
  color: var(--text-secondary, #666);
  border-radius: 4px;
}

.more-tag {
  padding: 2px 6px;
  font-size: 10px;
  color: var(--text-tertiary, #9ca3af);
}

.operator-footer {
  padding-top: 8px;
  border-top: 1px solid var(--border-light, #f3f4f6);
}

.endpoint-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--link-color, #3b82f6);
  text-decoration: none;
  font-family: monospace;
}

.endpoint-link:hover {
  text-decoration: underline;
}

.empty-state {
  padding: 16px;
  text-align: center;
  color: var(--text-secondary, #666);
}

.registry-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  border-top: 1px solid var(--border-light, #e5e7eb);
}

.registry-meta {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
}

.separator {
  margin: 0 6px;
}

.docs-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--link-color, #3b82f6);
  text-decoration: none;
}

.docs-link:hover {
  text-decoration: underline;
}
</style>

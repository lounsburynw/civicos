<template>
  <div class="chat-mode-selector">
    <div class="mode-buttons">
      <button
        v-for="(config, mode) in CHAT_MODES"
        :key="mode"
        :class="['mode-button', { active: contextStore.activeMode === mode }]"
        :title="`${config.name}: ${config.description}`"
        @click="selectMode(mode as ChatMode)"
      >
        <component :is="getIcon(config.icon)" :size="16" />
        <span class="mode-name">{{ config.name }}</span>
      </button>
    </div>
    <div class="mode-description">
      <p>{{ currentModeConfig.description }}</p>
      <span class="context-limit">
        {{ contextStore.activeContext.length }}/{{ currentModeConfig.maxElements }} active
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useContextStore } from '@/stores/context';
import { CHAT_MODES, type ChatMode } from '@/config/chatModes';
import { Search, ZoomIn, GitCompare } from 'lucide-vue-next';

const contextStore = useContextStore();

const currentModeConfig = computed(() => contextStore.modeConfig);

function selectMode(mode: ChatMode) {
  // Manual mode switching (for testing)
  // TODO Session 56: Replace with LLM-based auto-detection
  contextStore.setMode(mode, 'User manually selected mode');
}

function getIcon(iconName: string) {
  const icons: Record<string, any> = {
    search: Search,
    'zoom-in': ZoomIn,
    'git-compare': GitCompare
  };
  return icons[iconName] || Search;
}
</script>

<style scoped>
.chat-mode-selector {
  padding: 8px 12px;
  border-bottom: 1px solid var(--base01);
  background: var(--base02);
}

.mode-buttons {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.mode-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--base01);
  background: var(--base03);
  color: var(--base0);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.mode-button:hover {
  background: var(--base02);
  border-color: var(--blue);
}

.mode-button.active {
  background: var(--blue);
  color: var(--base03);
  border-color: var(--blue);
  font-weight: 500;
}

.mode-button.active svg {
  color: var(--base03);
}

.mode-name {
  white-space: nowrap;
}

.mode-description {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--base1);
}

.mode-description p {
  margin: 0;
  flex: 1;
}

.context-limit {
  color: var(--base01);
  font-size: 10px;
  padding: 2px 6px;
  background: var(--base03);
  border-radius: 3px;
  white-space: nowrap;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .mode-buttons {
    gap: 2px;
  }

  .mode-button {
    padding: 6px 8px;
    font-size: 11px;
  }

  .mode-name {
    display: none;
  }

  .mode-description {
    font-size: 10px;
  }
}
</style>

<template>
  <div v-if="developerStore.isEnabled" class="model-picker">
    <!-- Trigger Button -->
    <button
      @click="isOpen = !isOpen"
      class="picker-trigger"
      :class="{ 'is-open': isOpen }"
    >
      <span class="trigger-icon" :style="{ color: currentModelColor }">{{ currentModelIcon }}</span>
      <span class="trigger-label">{{ currentModelName }}</span>
      <svg class="trigger-chevron" :class="{ rotated: isOpen }" width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 4L6 8L10 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <!-- Dropdown Menu -->
    <Transition name="dropdown">
      <div v-if="isOpen" class="picker-dropdown">
        <div
          v-for="model in modelOptions"
          :key="model.id"
          @click="selectModel(model.id)"
          class="model-card"
          :class="{ 'is-selected': selectedModel === model.id }"
        >
          <div class="model-header">
            <span class="model-icon" :style="{ backgroundColor: model.color }">{{ model.icon }}</span>
            <div class="model-info">
              <div class="model-name">{{ model.name }}</div>
              <div class="model-description">{{ model.description }}</div>
            </div>
            <span v-if="selectedModel === model.id" class="check-icon">✓</span>
          </div>
          <div class="model-badges">
            <span v-for="badge in model.badges" :key="badge" class="badge" :class="`badge-${badge}`">
              {{ badgeLabels[badge] }}
            </span>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useDeveloperStore } from '../../stores/developer'
import { useChatStore } from '../../stores/chat'

const developerStore = useDeveloperStore()
const chatStore = useChatStore()

// Model selection (stored in developer store)
const selectedModel = ref(developerStore.selectedModel || 'auto')
const isOpen = ref(false)

// Model configuration with icons and badges (using Solarized colors)
const modelOptions = [
  {
    id: 'auto',
    name: 'Auto',
    description: 'Automatically selects the best model for each task',
    icon: 'AI',
    color: '#859900', // Solarized green
    badges: ['recommended']
  },
  {
    id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    description: 'Fast and efficient for most tasks',
    icon: 'GPT',
    color: '#859900', // Solarized green (fast/cheap)
    badges: ['fast', 'cheap']
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    description: 'Balanced performance and capability',
    icon: 'GPT',
    color: '#268bd2', // Solarized blue (balanced)
    badges: ['balanced']
  },
  {
    id: 'claude-sonnet-4',
    name: 'Claude Sonnet 4',
    description: 'Most capable model for complex reasoning',
    icon: 'CL',
    color: '#6c71c4', // Solarized purple (premium)
    badges: ['smart', 'premium']
  },
  {
    id: 'sonar',
    name: 'Perplexity Sonar',
    description: 'Real-time web search and research',
    icon: 'WEB',
    color: '#2aa198', // Solarized cyan (search)
    badges: ['search', 'cheap']
  },
  {
    id: 'gemini-2.0-flash-exp',
    name: 'Gemini 2.0 Flash',
    description: 'Fast multimodal model from Google',
    icon: 'GEM',
    color: '#b58900', // Solarized yellow (fast)
    badges: ['fast', 'cheap']
  },
  {
    id: 'deepseek/deepseek-chat',
    name: 'DeepSeek Chat',
    description: 'Ultra-low cost model for simple tasks',
    icon: 'DS',
    color: '#cb4b16', // Solarized orange (cheap)
    badges: ['cheap']
  }
]

const badgeLabels: Record<string, string> = {
  recommended: 'Recommended',
  smart: 'Most Capable',
  fast: 'Fast',
  cheap: 'Low Cost',
  balanced: 'Balanced',
  search: 'Web Search',
  premium: 'Premium'
}

// Current model display
const currentModelIcon = computed(() => {
  const model = modelOptions.find(m => m.id === selectedModel.value)
  return model?.icon || 'AI'
})

const currentModelColor = computed(() => {
  const model = modelOptions.find(m => m.id === selectedModel.value)
  return model?.color || '#859900'
})

const currentModelName = computed(() => {
  const model = modelOptions.find(m => m.id === selectedModel.value)
  return model?.name || 'Auto'
})

// Sync with store on mount
onMounted(() => {
  selectedModel.value = developerStore.selectedModel || 'auto'
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

// Watch for external changes to store
watch(
  () => developerStore.selectedModel,
  (newModel) => {
    selectedModel.value = newModel || 'auto'
  }
)

// Close dropdown when clicking outside
function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.model-picker')) {
    isOpen.value = false
  }
}

function selectModel(modelId: string) {
  selectedModel.value = modelId
  developerStore.setSelectedModel(modelId)
  isOpen.value = false
  console.log('[ModelPicker] Model changed to:', modelId)
}
</script>

<style scoped>
.model-picker {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--background-secondary);
  border-bottom: 1px solid var(--border);
}

/* Trigger Button */
.picker-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.picker-trigger:hover {
  background: var(--background-secondary);
  border-color: var(--primary);
  box-shadow: 0 2px 6px rgba(108, 113, 196, 0.15);
}

.picker-trigger.is-open {
  border-color: var(--primary);
  background: var(--background-secondary);
}

.trigger-icon {
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.08);
  letter-spacing: 0.5px;
}

.trigger-label {
  flex: 1;
  white-space: nowrap;
}

.trigger-chevron {
  color: var(--text-secondary);
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.trigger-chevron.rotated {
  transform: rotate(180deg);
}

/* Dropdown Menu */
.picker-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 16px;
  min-width: 320px;
  max-height: 480px;
  overflow-y: auto;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  padding: 6px;
}

/* Model Cards */
.model-card {
  padding: 12px;
  margin: 2px 0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid transparent;
}

.model-card:hover {
  background: var(--background-secondary);
  border-color: var(--border);
}

.model-card.is-selected {
  background: rgba(108, 113, 196, 0.08);
  border-color: var(--primary);
}

.model-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
}

.model-icon {
  font-size: 10px;
  line-height: 1;
  font-weight: 700;
  padding: 6px 8px;
  border-radius: 6px;
  color: white;
  flex-shrink: 0;
  letter-spacing: 0.5px;
  min-width: 36px;
  text-align: center;
}

.model-info {
  flex: 1;
  min-width: 0;
}

.model-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.model-description {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.check-icon {
  font-size: 16px;
  color: var(--primary);
  font-weight: bold;
}

/* Badges */
.model-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: 30px;
}

.badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.badge-recommended {
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
}

.badge-smart {
  background: rgba(108, 113, 196, 0.15);
  color: var(--primary);
}

.badge-fast {
  background: rgba(38, 139, 210, 0.15);
  color: var(--accent-blue);
}

.badge-cheap {
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
}

.badge-balanced {
  background: rgba(181, 137, 0, 0.15);
  color: var(--accent-yellow);
}

.badge-search {
  background: rgba(108, 113, 196, 0.15);
  color: var(--primary);
}

.badge-premium {
  background: rgba(203, 75, 22, 0.15);
  color: var(--accent-orange);
}

/* Dropdown Animation */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Scrollbar Styling */
.picker-dropdown::-webkit-scrollbar {
  width: 8px;
}

.picker-dropdown::-webkit-scrollbar-track {
  background: transparent;
}

.picker-dropdown::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}

.picker-dropdown::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

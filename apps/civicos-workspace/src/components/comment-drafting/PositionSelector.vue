<template>
  <div class="position-selector">
    <button
      v-for="option in options"
      :key="option.value"
      :class="['position-btn', option.value, { active: modelValue === option.value }]"
      @click="$emit('update:modelValue', option.value)"
    >
      <component :is="option.icon" :size="20" />
      <span>{{ option.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ThumbsUp, ThumbsDown, CircleDot, HelpCircle } from 'lucide-vue-next'

type Position = 'support' | 'oppose' | 'neutral' | 'questions'

defineProps<{
  modelValue: Position | null
}>()

defineEmits<{
  'update:modelValue': [value: Position]
}>()

const options = [
  {
    value: 'support' as const,
    label: 'Support',
    icon: ThumbsUp
  },
  {
    value: 'oppose' as const,
    label: 'Oppose',
    icon: ThumbsDown
  },
  {
    value: 'neutral' as const,
    label: 'Neutral',
    icon: CircleDot
  },
  {
    value: 'questions' as const,
    label: 'Questions',
    icon: HelpCircle
  }
]
</script>

<style scoped>
.position-selector {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.position-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 24px;
  border: 2px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-default);
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.position-btn:hover {
  border-color: var(--border-default);
  background: var(--surface-hover);
}

.position-btn.active {
  font-weight: 600;
}

/* Support - green */
.position-btn.support.active {
  border-color: var(--accent-green);
  background: rgba(133, 153, 0, 0.1);
  color: var(--accent-green);
}

/* Oppose - red */
.position-btn.oppose.active {
  border-color: var(--accent-red);
  background: rgba(220, 50, 47, 0.1);
  color: var(--accent-red);
}

/* Neutral - gray */
.position-btn.neutral.active {
  border-color: var(--text-secondary);
  background: rgba(147, 161, 161, 0.1);
  color: var(--text-primary);
}

/* Questions - blue */
.position-btn.questions.active {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.1);
  color: var(--primary);
}

/* Keyboard focus */
.position-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
</style>

<template>
  <div class="key-concern-input">
    <textarea
      ref="textareaRef"
      :value="modelValue"
      @input="handleInput"
      :placeholder="placeholder"
      :class="{ invalid: showError }"
      rows="3"
    />
    <div class="input-footer">
      <span v-if="showError" class="error-message">
        {{ errorMessage }}
      </span>
      <span v-else class="helper-text">
        {{ helperText }}
      </span>
      <span :class="['char-count', { warning: isNearMax, error: isOverMax }]">
        {{ charCount }}/{{ maxChars }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    minChars?: number
    maxChars?: number
    placeholder?: string
  }>(),
  {
    minChars: 20,
    maxChars: 300,
    placeholder: "What's your main concern about this item?"
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const textareaRef = ref<HTMLTextAreaElement>()

const charCount = computed(() => props.modelValue.length)
const isNearMax = computed(() => charCount.value > props.maxChars * 0.9)
const isOverMax = computed(() => charCount.value > props.maxChars)
const isTooShort = computed(() => props.modelValue.length > 0 && props.modelValue.length < props.minChars)

const showError = computed(() => isOverMax.value || isTooShort.value)

const errorMessage = computed(() => {
  if (isOverMax.value) {
    return `Too long. Please remove ${charCount.value - props.maxChars} characters.`
  }
  if (isTooShort.value) {
    return `Too short. Please add ${props.minChars - charCount.value} more characters.`
  }
  return ''
})

const helperText = computed(() => {
  if (charCount.value === 0) {
    return 'Express your main concern in 1-2 sentences'
  }
  if (isNearMax.value) {
    return 'Almost at the limit'
  }
  return 'Clear and concise'
})

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
  autoResize()
}

const autoResize = () => {
  nextTick(() => {
    if (textareaRef.value) {
      textareaRef.value.style.height = 'auto'
      textareaRef.value.style.height = textareaRef.value.scrollHeight + 'px'
    }
  })
}

// Auto-resize on mount and when value changes externally
watch(() => props.modelValue, autoResize, { immediate: true })
</script>

<style scoped>
.key-concern-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

textarea {
  width: 100%;
  padding: 12px;
  border: 2px solid var(--border-default);
  border-radius: 6px;
  background: var(--surface-default);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  overflow: hidden;
  transition: all 0.2s ease;
  min-height: 80px;
  max-height: 200px;
}

textarea:focus {
  outline: none;
  border-color: var(--primary);
  background: var(--surface-hover);
}

textarea.invalid {
  border-color: var(--accent-red);
}

textarea::placeholder {
  color: var(--text-tertiary);
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  min-height: 20px;
}

.helper-text {
  color: var(--text-tertiary);
  font-style: italic;
}

.error-message {
  color: var(--accent-red);
  font-weight: 500;
}

.char-count {
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
}

.char-count.warning {
  color: var(--accent-orange);
  font-weight: 500;
}

.char-count.error {
  color: var(--accent-red);
  font-weight: 600;
}
</style>

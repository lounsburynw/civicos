<template>
  <div
    ref="cardRef"
    class="swipe-card"
    :class="{ 'swiping': isDragging }"
    :style="cardStyle"
    @mousedown="handleDragStart"
    @touchstart="handleDragStart"
  >
    <!-- Card Content -->
    <div class="card-content">
      <!-- Icon/Image -->
      <div class="card-icon" :style="{ backgroundColor: card.iconColor }">
        <span class="icon-emoji">{{ card.icon }}</span>
      </div>

      <!-- Title -->
      <h3 class="card-title">{{ card.title }}</h3>

      <!-- Description -->
      <p class="card-description">{{ card.description }}</p>

      <!-- Card Type Badge -->
      <div class="card-badge" :class="`badge-${card.type}`">
        {{ formatCardType(card.type) }}
      </div>
    </div>

    <!-- Swipe Indicators -->
    <div class="swipe-indicator left" :class="{ active: swipeDirection === 'left' }">
      <X class="indicator-icon" :size="48" />
      <span class="indicator-text">Pass</span>
    </div>
    <div class="swipe-indicator right" :class="{ active: swipeDirection === 'right' }">
      <Check class="indicator-icon" :size="48" />
      <span class="indicator-text">Interested</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { X, Check } from 'lucide-vue-next'

export interface SwipeCardData {
  id: string
  type: 'topic' | 'event' | 'issue' | 'jurisdiction'
  title: string
  description: string
  icon: string
  iconColor: string
  metadata?: any // Extra data for backend
}

interface Props {
  card: SwipeCardData
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'swipe-left'): void
  (e: 'swipe-right'): void
}>()

// Card drag state
const cardRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const startX = ref(0)
const startY = ref(0)
const currentX = ref(0)
const currentY = ref(0)

// Swipe threshold (pixels to trigger swipe)
const SWIPE_THRESHOLD = 100

// Computed styles for card transform
const cardStyle = computed(() => {
  if (!isDragging.value && currentX.value === 0) return {}

  const rotate = currentX.value / 20 // Rotate based on drag distance
  const opacity = 1 - Math.abs(currentX.value) / 300

  return {
    transform: `translate(${currentX.value}px, ${currentY.value}px) rotate(${rotate}deg)`,
    opacity: opacity.toString()
  }
})

// Swipe direction indicator
const swipeDirection = computed(() => {
  if (currentX.value > 50) return 'right'
  if (currentX.value < -50) return 'left'
  return null
})

// Drag handlers
function handleDragStart(e: MouseEvent | TouchEvent) {
  isDragging.value = true

  if (e instanceof MouseEvent) {
    startX.value = e.clientX
    startY.value = e.clientY
    document.addEventListener('mousemove', handleDragMove)
    document.addEventListener('mouseup', handleDragEnd)
  } else {
    startX.value = e.touches[0].clientX
    startY.value = e.touches[0].clientY
    document.addEventListener('touchmove', handleDragMove)
    document.addEventListener('touchend', handleDragEnd)
  }
}

function handleDragMove(e: MouseEvent | TouchEvent) {
  if (!isDragging.value) return

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  currentX.value = clientX - startX.value
  currentY.value = clientY - startY.value
}

function handleDragEnd() {
  isDragging.value = false

  // Check if swipe threshold reached
  if (Math.abs(currentX.value) > SWIPE_THRESHOLD) {
    if (currentX.value > 0) {
      // Swipe right (like)
      animateSwipeOut('right')
      setTimeout(() => emit('swipe-right'), 300)
    } else {
      // Swipe left (pass)
      animateSwipeOut('left')
      setTimeout(() => emit('swipe-left'), 300)
    }
  } else {
    // Reset position (snap back)
    currentX.value = 0
    currentY.value = 0
  }

  // Remove event listeners
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
  document.removeEventListener('touchmove', handleDragMove)
  document.removeEventListener('touchend', handleDragEnd)
}

function animateSwipeOut(direction: 'left' | 'right') {
  const distance = direction === 'right' ? 500 : -500
  currentX.value = distance
}

function formatCardType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1)
}

// Cleanup on unmount
onUnmounted(() => {
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
  document.removeEventListener('touchmove', handleDragMove)
  document.removeEventListener('touchend', handleDragEnd)
})
</script>

<style scoped>
.swipe-card {
  position: absolute;
  width: 100%;
  max-width: 400px;
  height: 500px;
  background: var(--background);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  cursor: grab;
  user-select: none;
  transition: transform 0.3s ease, opacity 0.3s ease;
  touch-action: none;
}

.swipe-card.swiping {
  cursor: grabbing;
  transition: none;
}

/* Card Content */
.card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-2xl);
  height: 100%;
  gap: var(--space-lg);
}

.card-icon {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-md);
  box-shadow: var(--shadow);
}

.icon-emoji {
  font-size: 64px;
}

.card-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  text-align: center;
  margin: 0;
  line-height: 1.3;
}

.card-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.6;
  flex: 1;
  margin: 0;
}

.card-badge {
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-topic {
  background: rgba(38, 139, 210, 0.15);
  color: var(--primary);
}

.badge-event {
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
}

.badge-issue {
  background: rgba(220, 50, 47, 0.15);
  color: var(--accent-red);
}

.badge-jurisdiction {
  background: rgba(42, 161, 152, 0.15);
  color: var(--accent-cyan);
}

/* Swipe Indicators */
.swipe-indicator {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-xs);
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.swipe-indicator.active {
  opacity: 1;
}

.swipe-indicator.left {
  left: var(--space-xl);
}

.swipe-indicator.right {
  right: var(--space-xl);
}

.indicator-icon {
  flex-shrink: 0;
}

.swipe-indicator.left .indicator-icon {
  color: var(--accent-red);
}

.swipe-indicator.right .indicator-icon {
  color: var(--accent-green);
}

.indicator-text {
  font-size: var(--font-size-sm);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.swipe-indicator.left .indicator-text {
  color: var(--accent-red);
}

.swipe-indicator.right .indicator-text {
  color: var(--accent-green);
}
</style>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { api } from '@/services/api';
import type { VoiceCountResponse } from '@/types/civic';

const props = withDefaults(defineProps<{
  entity: string;
  compact?: boolean;  // Show just total count
  showZero?: boolean; // Show badge even when counts are zero
}>(), {
  compact: false,
  showZero: false
});

const counts = ref<VoiceCountResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

async function fetchCounts() {
  if (!props.entity) return;

  loading.value = true;
  error.value = null;

  try {
    counts.value = await api.getVoiceCounts(props.entity);
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load';
    // Set zero counts on error
    counts.value = { entity: props.entity, support: 0, oppose: 0, watching: 0, total: 0 };
  } finally {
    loading.value = false;
  }
}

// Fetch on mount and when entity changes
onMounted(fetchCounts);
watch(() => props.entity, fetchCounts);

// Check if we should show the badge
function shouldShow(): boolean {
  if (loading.value) return false;
  if (!counts.value) return false;
  if (props.showZero) return true;
  return counts.value.total > 0;
}
</script>

<template>
  <div v-if="shouldShow()" class="voice-badge" :class="{ compact }">
    <template v-if="compact">
      <!-- Compact: just show total -->
      <span class="voice-icon">👥</span>
      <span class="voice-count">{{ counts?.total }}</span>
    </template>
    <template v-else>
      <!-- Full: show breakdown -->
      <span v-if="counts?.support" class="voice-item support" title="Support">
        <span class="voice-emoji">👍</span>
        <span class="voice-count">{{ counts.support }}</span>
      </span>
      <span v-if="counts?.oppose" class="voice-item oppose" title="Oppose">
        <span class="voice-emoji">👎</span>
        <span class="voice-count">{{ counts.oppose }}</span>
      </span>
      <span v-if="counts?.watching" class="voice-item watching" title="Watching">
        <span class="voice-emoji">👀</span>
        <span class="voice-count">{{ counts.watching }}</span>
      </span>
    </template>
  </div>
</template>

<style scoped>
.voice-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.voice-badge.compact {
  gap: 4px;
  padding: 2px 8px;
}

.voice-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.voice-emoji {
  font-size: 12px;
}

.voice-count {
  font-variant-numeric: tabular-nums;
}

/* Subtle color hints for sentiment */
.voice-item.support {
  color: var(--accent-green, #2da44e);
}

.voice-item.oppose {
  color: var(--accent-orange, #cf222e);
}

.voice-item.watching {
  color: var(--text-secondary);
}
</style>

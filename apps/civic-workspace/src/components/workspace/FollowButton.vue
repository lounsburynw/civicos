<template>
  <div class="follow-button-container">
    <button
      class="follow-button"
      :class="{ following: followInfo.your_following }"
      @click="toggleFollow"
      :disabled="loading"
      :title="followInfo.your_following ? 'Click to unfollow' : 'Join discussion with neighbors'"
    >
      <span v-if="loading" class="loading-spinner">⏳</span>
      <span v-else-if="followInfo.your_following" class="following-text">
        Following ✓
      </span>
      <span v-else class="follow-text">
        <span v-if="showDiscussionLink && followInfo.follower_count > 0">
          Join {{ followInfo.follower_count }} {{ followInfo.follower_count === 1 ? 'neighbor' : 'neighbors' }}
        </span>
        <span v-else>Follow</span>
      </span>
    </button>

    <div v-if="followInfo.follower_count > 0 && !showDiscussionLink" class="follower-count">
      <span class="count-icon">👥</span>
      <span class="count-text">
        {{ followInfo.follower_count }} {{ followInfo.follower_count === 1 ? 'neighbor' : 'neighbors' }} following this
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api } from '@/services/api';
import type { FollowInfoResponse } from '@/types/civic';

const props = defineProps<{
  focalType: 'issue' | 'event';
  focalId: string;
  jurisdictionId?: string;
  showDiscussionLink?: boolean;
}>();

const emit = defineEmits<{
  'follow-changed': [info: FollowInfoResponse];
  'followed': [info: FollowInfoResponse];
}>();

// TODO: Replace with actual user ID from auth store
const userId = 'demo_user';

const followInfo = ref<FollowInfoResponse>({
  follower_count: 0,
  thread_id: null,
  your_following: false
});

const loading = ref(false);
const error = ref<string | null>(null);

/**
 * Load follow info on mount
 */
onMounted(async () => {
  await loadFollowInfo();
});

/**
 * Load follow information from API
 */
async function loadFollowInfo() {
  try {
    const info = await api.getFollowInfo(props.focalType, props.focalId, userId);
    followInfo.value = info;
  } catch (err) {
    console.error('Failed to load follow info:', err);
    error.value = err instanceof Error ? err.message : 'Failed to load follow info';
  }
}

/**
 * Toggle follow/unfollow
 */
async function toggleFollow() {
  if (loading.value) return;

  loading.value = true;
  error.value = null;

  try {
    if (followInfo.value.your_following) {
      // Unfollow
      const result = await api.deleteFollow(userId, props.focalType, props.focalId);
      followInfo.value = {
        ...followInfo.value,
        follower_count: result.follower_count,
        your_following: result.your_following
      };
      // Emit the change to parent
      emit('follow-changed', followInfo.value);
    } else {
      // Follow
      const result = await api.createFollow(
        userId,
        props.focalType,
        props.focalId,
        props.jurisdictionId
      );
      followInfo.value = {
        follower_count: result.follower_count,
        thread_id: result.thread_id,
        your_following: result.your_following
      };
      // Emit the change to parent
      emit('follow-changed', followInfo.value);
      // Emit 'followed' event for auto-opening ThreadArtifact
      emit('followed', followInfo.value);
    }
  } catch (err) {
    console.error('Failed to toggle follow:', err);
    error.value = err instanceof Error ? err.message : 'Failed to toggle follow';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.follow-button-container {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 1rem 0;
  padding: 0.75rem;
  background-color: var(--background-secondary);
  border-radius: var(--radius-sm);
}

.follow-button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  background-color: var(--background);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-fast);
  font-size: 0.875rem;
  font-weight: 500;
}

.follow-button:hover:not(:disabled) {
  background-color: var(--hover-bg);
  border-color: var(--primary);
  color: var(--primary);
}

.follow-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.follow-button.following {
  background-color: var(--blue, var(--primary));
  color: var(--base3, white);
  border-color: var(--blue, var(--primary));
}

.follow-button.following:hover:not(:disabled) {
  background-color: #1c6fa0;
  border-color: #1c6fa0;
}

.follow-button.following:hover:not(:disabled) .following-text::after {
  content: ' (Unfollow)';
  font-size: 0.75rem;
  opacity: 0.8;
}

.loading-spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.follower-count {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

.count-icon {
  font-size: 1rem;
}

.count-text {
  opacity: 0.9;
}
</style>

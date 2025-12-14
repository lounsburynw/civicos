<template>
  <div class="message-container" :class="`depth-${depth}`">
    <!-- Main Message -->
    <div
      class="message"
      :class="{
        'own-message': message.user_id === currentUserId,
        'has-replies': hasReplies,
        'grouped': isGrouped,
        'being-replied-to': isBeingRepliedTo
      }"
      @mouseenter="showActions = true"
      @mouseleave="showActions = false"
    >
      <!-- Avatar (hidden for grouped messages) -->
      <div v-if="!isGrouped" class="message-avatar-container">
        <img
          :src="getAvatarUrl(message.user_id)"
          :alt="formatUserId(message.user_id)"
          class="message-avatar"
        />
      </div>
      <!-- Spacer for grouped messages -->
      <div v-else class="message-avatar-spacer"></div>

      <!-- Message Body -->
      <div class="message-body">
        <!-- Header (hidden for grouped messages) -->
        <div v-if="!isGrouped" class="message-header">
          <span class="message-user">{{ formatUserId(message.user_id) }}</span>
          <span class="message-dot">·</span>
          <span class="message-time">{{ formatTime(message.created_at) }}</span>
        </div>
        <div class="message-content">{{ message.content }}</div>

        <!-- Hover Actions (Reply) -->
        <div v-show="showActions" class="message-actions">
          <button
            @click="handleReplyClick"
            class="action-button"
            :title="`Reply to ${formatUserId(message.user_id)}`"
          >
            <CornerDownRight :size="14" />
            <span>Reply</span>
          </button>
        </div>

        <!-- Reply Count (collapsed indicator) - only show if replies can be displayed (depth < 1) -->
        <button
          v-if="hasReplies && depth < 1"
          @click="toggleCollapsed"
          class="reply-count-button"
        >
          <ChevronRight v-if="collapsed" :size="14" />
          <ChevronDown v-else :size="14" />
          <span>{{ replyCount }} {{ replyCount === 1 ? 'reply' : 'replies' }}</span>
        </button>
      </div>
    </div>

    <!-- Nested Replies (max depth 1, like Slack) -->
    <div v-if="hasReplies && !collapsed && depth < 1" class="nested-replies">
      <MessageBubble
        v-for="(reply, index) in replies"
        :key="reply.message_id"
        :message="reply"
        :current-user-id="currentUserId"
        :depth="depth + 1"
        :is-grouped="index > 0 && replies[index - 1].user_id === reply.user_id"
        :replying-to-id="replyingToId"
        @reply="handleReplyEvent"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { CornerDownRight, ChevronDown, ChevronRight } from 'lucide-vue-next';
import { useAvatars } from '@/composables/useAvatars';
import type { ThreadMessage } from '@/types/civic';

const props = withDefaults(defineProps<{
  message: ThreadMessage;
  currentUserId: string;
  depth?: number;
  isGrouped?: boolean; // True if this message is consecutive from the same user
  replyingToId?: string; // ID of message being replied to (for highlighting)
}>(), {
  depth: 0,
  isGrouped: false,
  replyingToId: undefined
});

const emit = defineEmits<{
  reply: [messageId: string];
}>();

// Avatar composable
const { getAvatarUrl } = useAvatars();

// UI state
const collapsed = ref(false);
const showActions = ref(false);

// Computed
const hasReplies = computed(() => {
  return props.message.replies && props.message.replies.length > 0;
});

const replies = computed(() => {
  return props.message.replies || [];
});

const replyCount = computed(() => {
  return props.message.reply_count || 0;
});

const isBeingRepliedTo = computed(() => {
  return props.replyingToId === props.message.message_id;
});

/**
 * Toggle collapsed state
 */
function toggleCollapsed(): void {
  collapsed.value = !collapsed.value;
}

/**
 * Handle reply button click
 */
function handleReplyClick(): void {
  emit('reply', props.message.message_id);
}

/**
 * Propagate reply event up the tree
 */
function handleReplyEvent(messageId: string): void {
  emit('reply', messageId);
}

/**
 * Format user ID for display
 */
function formatUserId(id: string): string {
  if (id === props.currentUserId) return 'You';
  // Extract first part before underscore or hash
  const parts = id.split(/[_#]/);
  return parts[0] || id;
}

/**
 * Format timestamp for display
 */
function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  // Format as date
  return date.toLocaleDateString();
}
</script>

<style scoped>
/* Message Container with Depth-based Indentation */
.message-container {
  width: 100%;
}

/* Depth-based indentation (max 1 level, like Slack) */
.message-container.depth-1 {
  margin-left: 48px;
  padding-left: 12px;
  border-left: 2px solid rgba(38, 139, 210, 0.2);
  transition: border-color 0.15s ease;
}

.message-container.depth-1 .message {
  padding-right: 8px;
}

.message-container.depth-1:hover {
  border-left-color: rgba(38, 139, 210, 0.35);
}

/* Message Bubble - Slack-style hover presence */
.message {
  display: flex;
  gap: 0.75rem;
  padding: 8px 20px;
  background: transparent;
  border-radius: 0;
  transition: background-color 0.12s ease;
  margin-bottom: 0;
  position: relative;
  border-left: 3px solid transparent;
}

.message:hover {
  background: var(--background-secondary);
  border-left-color: var(--primary);
}

/* Grouped messages (consecutive from same user) - tighter spacing */
.message.grouped {
  padding-top: 2px;
  padding-bottom: 2px;
}

/* Message being replied to - subtle highlight */
.message.being-replied-to {
  background: rgba(38, 139, 210, 0.08);
  border-left-color: var(--primary);
  border-left-width: 4px;
}

.message.being-replied-to:hover {
  background: rgba(38, 139, 210, 0.12);
}

/* Avatar Container */
.message-avatar-container {
  width: 40px;
  flex-shrink: 0;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
}

/* Avatar spacer for grouped messages */
.message-avatar-spacer {
  width: 40px;
  flex-shrink: 0;
}

/* Smaller avatars for nested messages */
.depth-1 .message-avatar,
.depth-2 .message-avatar,
.depth-3 .message-avatar {
  width: 32px;
  height: 32px;
}

/* Message Body */
.message-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

/* Message Header (inline timestamp) */
.message-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.875rem;
}

.message-user {
  font-weight: 600;
  color: var(--blue);
}

.message.own-message .message-user {
  color: var(--green);
}

.message-dot {
  color: var(--base0);
  font-weight: bold;
}

.message-time {
  color: var(--base0);
  font-size: 0.8125rem;
}

/* Message Content */
.message-content {
  color: var(--base1);
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.5;
  font-size: 0.875rem;
}

/* Hover Actions (Reply, React) - Floating Toolbar (Slack-style) */
.message-actions {
  position: absolute;
  top: -4px;
  right: 8px;
  display: flex;
  gap: 2px;
  background: var(--background);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.action-button {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.action-button:hover {
  color: var(--primary);
  background: var(--background-secondary);
}

/* Reply Count Button (collapse/expand indicator) - Solarized Blue */
.reply-count-button {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.65rem;
  margin-top: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--primary);
  background: rgba(38, 139, 210, 0.08); /* Solarized blue tint */
  border: 1px solid rgba(38, 139, 210, 0.25);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s ease;
}

.reply-count-button:hover {
  color: var(--primary);
  background: rgba(38, 139, 210, 0.15);
  border-color: rgba(38, 139, 210, 0.4);
  /* No shadow or lift - keep it smooth */
}

.reply-count-button svg {
  transition: transform 0.2s ease;
}

.reply-count-button:hover svg {
  color: var(--primary);
}

/* Nested Replies */
.nested-replies {
  display: flex;
  flex-direction: column;
}
</style>

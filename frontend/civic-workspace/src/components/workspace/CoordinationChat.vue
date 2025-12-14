<template>
  <div class="coordination-chat" :class="{ 'always-expanded': alwaysExpanded, 'input-only': inputOnly }">
    <!-- Chat Header (collapsible - hidden if alwaysExpanded) -->
    <div v-if="!alwaysExpanded" class="chat-header" @click="toggleExpanded">
      <div class="header-left">
        <span class="chat-icon">💬</span>
        <span class="chat-title">Coordination Chat</span>
        <span v-if="participantCount > 0" class="participant-count">
          ({{ participantCount }} {{ participantCount === 1 ? 'member' : 'members' }})
        </span>
        <span v-if="!expanded && unreadCount > 0" class="unread-badge">
          {{ unreadCount }}
        </span>
      </div>
      <button class="expand-button" :aria-label="expanded ? 'Collapse chat' : 'Expand chat'">
        {{ expanded ? '▲' : '▼' }}
      </button>
    </div>

    <!-- Chat Panel (collapsible or always shown) -->
    <div v-if="expanded || alwaysExpanded" class="chat-panel">
      <!-- Messages Section (hidden if inputOnly) -->
      <template v-if="!inputOnly">
        <!-- Loading State -->
        <div v-if="isLoading" class="loading-state">
          <span>Loading messages...</span>
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="error-state">
          <span>{{ error }}</span>
          <button @click="fetchMessages" class="retry-button">Retry</button>
        </div>

        <!-- Messages -->
        <div v-else class="messages-container" ref="messagesContainer">
          <div v-if="messages.length === 0" class="empty-state">
            <p>No messages yet. Start the conversation!</p>
          </div>

          <!-- Use MessageBubble for nested rendering -->
          <MessageBubble
            v-for="(message, index) in messages"
            :key="message.message_id"
            :message="message"
            :current-user-id="userId"
            :is-grouped="index > 0 && messages[index - 1].user_id === message.user_id"
            :replying-to-id="replyingToMessageId ?? undefined"
            @reply="handleReplyToMessage"
          />

          <!-- Typing Indicator -->
          <div v-if="typingText" class="typing-indicator">
            <span class="typing-text">{{ typingText }}</span>
          </div>
        </div>
      </template>

      <!-- Message Input (hidden if hideInput) -->
      <div v-if="!hideInput" class="message-input-container">
        <!-- Reply Context Indicator -->
        <div v-if="replyingToMessage" class="replying-to">
          <span class="replying-text">
            Replying to <strong>{{ formatUserId(replyingToMessage.user_id) }}</strong>:
            "{{ truncateContent(replyingToMessage.content) }}"
          </span>
          <button @click="cancelReply" class="cancel-reply-button" title="Cancel reply">
            ✕
          </button>
        </div>

        <div class="input-row">
          <textarea
            v-model="messageInput"
            @keydown.enter.exact.prevent="handleSendMessage"
            @input="handleInputChange"
            :placeholder="replyingToMessage ? 'Type reply...' : 'Type message... (Enter to send)'"
            class="message-input"
            :disabled="isSending"
            rows="2"
          ></textarea>
          <button
            @click="handleSendMessage"
            :disabled="!messageInput.trim() || isSending"
            class="send-button"
          >
            {{ isSending ? 'Sending...' : 'Send' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { useCoordinationChat } from '@/composables/useCoordinationChat';
import { useAvatars } from '@/composables/useAvatars';
import MessageBubble from './MessageBubble.vue';
import type { ThreadMessage } from '@/types/civic';

const props = withDefaults(defineProps<{
  threadId: string | null;
  focalType: 'issue' | 'event';
  focalId: string;
  initialExpanded?: boolean;
  alwaysExpanded?: boolean; // If true, hide collapse header entirely
  hideInput?: boolean; // If true, hide input area (messages only)
  inputOnly?: boolean; // If true, show only input area (no messages)
  replyingToMessageId?: string | null; // External reply state (managed by parent)
}>(), {
  initialExpanded: false,
  alwaysExpanded: false,
  hideInput: false,
  inputOnly: false,
  replyingToMessageId: null
});

// Emit definitions
const emit = defineEmits<{
  reply: [messageId: string];
  'cancel-reply': [];
  'message-sent': [];
}>();

// TODO: Replace with actual user ID from auth store
const userId = 'demo_user';

// UI State
const expanded = ref(props.initialExpanded);
const messageInput = ref('');
const messagesContainer = ref<HTMLElement | null>(null);
const typingTimeout = ref<number | null>(null);

// Use coordination chat composable (pass props as refs for reactivity)
const {
  messages,
  participants,
  participantCount,
  typingText,
  unreadCount,
  isLoading,
  error,
  isSending,
  sendMessage,
  handleTyping,
  markAsRead,
  fetchMessages
} = useCoordinationChat(
  () => props.threadId,  // Pass as getter function for reactivity
  userId,
  props.focalType,
  props.focalId
);

// Use avatars composable
const { getAvatarUrl } = useAvatars();

/**
 * Find message by ID in nested structure
 */
function findMessage(msgs: ThreadMessage[], messageId: string): ThreadMessage | null {
  for (const msg of msgs) {
    if (msg.message_id === messageId) return msg;
    if (msg.replies && msg.replies.length > 0) {
      const found = findMessage(msg.replies, messageId);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Compute the replying-to message object from external ID prop
 */
const replyingToMessage = computed<ThreadMessage | null>(() => {
  if (!props.replyingToMessageId) return null;
  return findMessage(messages.value, props.replyingToMessageId);
});

/**
 * Handle reply to specific message - emit event to parent
 */
function handleReplyToMessage(messageId: string): void {
  emit('reply', messageId);
  // Focus on input when replying (for messages-only instances that show input)
  if (!props.hideInput) {
    nextTick(() => {
      const textarea = document.querySelector('.message-input') as HTMLTextAreaElement;
      if (textarea) {
        textarea.focus();
      }
    });
  }
}

/**
 * Cancel replying to message - emit event to parent
 */
function cancelReply(): void {
  emit('cancel-reply');
}

/**
 * Truncate content for reply indicator
 */
function truncateContent(content: string, maxLength: number = 50): string {
  if (content.length <= maxLength) return content;
  return content.substring(0, maxLength) + '...';
}

/**
 * Toggle chat expanded/collapsed
 */
function toggleExpanded(): void {
  expanded.value = !expanded.value;

  // Mark as read when opening chat
  if (expanded.value && unreadCount.value > 0) {
    markAsRead();
  }

  // Scroll to bottom when expanding
  if (expanded.value) {
    nextTick(() => scrollToBottom());
  }
}

/**
 * Send message (with optional parent_message_id for replies)
 */
async function handleSendMessage(): Promise<void> {
  if (!messageInput.value.trim() || isSending.value) return;

  const content = messageInput.value.trim();
  const parentId = replyingToMessage.value?.message_id;

  // Clear input
  messageInput.value = '';

  try {
    await sendMessage(content, parentId);
    // Emit message-sent to clear reply state in parent
    emit('message-sent');
    // Scroll to bottom after sending
    nextTick(() => scrollToBottom());
  } catch (err) {
    // Error already handled by composable
    console.error('Failed to send message:', err);
  }
}

/**
 * Handle input change (typing indicator)
 */
function handleInputChange(): void {
  // Send typing indicator
  handleTyping(true);

  // Clear existing timeout
  if (typingTimeout.value !== null) {
    clearTimeout(typingTimeout.value);
  }

  // Stop typing after 2 seconds of no input
  typingTimeout.value = window.setTimeout(() => {
    handleTyping(false);
    typingTimeout.value = null;
  }, 2000);
}

/**
 * Scroll messages to bottom
 */
function scrollToBottom(): void {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

/**
 * Format user ID for display
 */
function formatUserId(id: string): string {
  if (id === userId) return 'You';
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

// Watch messages and scroll to bottom when new message arrives
watch(() => messages.value.length, () => {
  if (expanded.value) {
    nextTick(() => scrollToBottom());
  }
});

// Mark as read when chat is visible and new messages arrive
watch([() => unreadCount.value, () => expanded.value], ([newUnreadCount, isExpanded]) => {
  if (isExpanded && newUnreadCount > 0) {
    markAsRead();
  }
});
</script>

<style scoped>
.coordination-chat {
  margin-top: 1rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--background);
}

/* Always expanded mode (for ThreadArtifact) */
.coordination-chat.always-expanded {
  margin-top: 0;
  border: none;
  border-radius: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.coordination-chat.always-expanded .chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* Input-only mode (for fixed input area) */
.coordination-chat.input-only .chat-panel {
  border-top: none; /* No top border when showing only input */
}

.coordination-chat.input-only .message-input-container {
  border-top: none; /* Already has border on parent fixed-input-area */
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.chat-header:hover {
  background: var(--base01);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chat-icon {
  font-size: 1.2rem;
}

.chat-title {
  font-weight: 600;
  color: var(--base1);
}

.participant-count {
  color: var(--base0);
  font-size: 0.9rem;
}

.unread-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.5rem;
  padding: 0 0.4rem;
  background: var(--orange);
  color: var(--base03);
  border-radius: 10px;
  font-size: 0.8rem;
  font-weight: 600;
}

.expand-button {
  background: none;
  border: none;
  color: var(--base0);
  font-size: 1rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  transition: color 0.2s;
}

.expand-button:hover {
  color: var(--base1);
}

.chat-panel {
  border-top: 1px solid var(--border);
  background: var(--background);
}

.loading-state,
.error-state {
  padding: 2rem;
  text-align: center;
  color: var(--base01);
}

.retry-button {
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.retry-button:hover {
  background: var(--primary-hover);
}

.messages-container {
  flex: 1; /* Grow to fill available space */
  min-height: 100px; /* Minimum height for usability (input is now separate) */
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 0;
  padding-right: 100px; /* Extra space for action buttons on nested messages */
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--background);
}

.empty-state {
  text-align: center;
  color: var(--base0);
  padding: 2rem 1rem;
}

.typing-indicator {
  padding: 0.5rem;
  font-size: 0.9rem;
  color: var(--base0);
  font-style: italic;
}

.message-input-container {
  display: flex;
  flex-direction: column;
  padding: 12px 20px 24px 20px;
  border-top: 1px solid var(--border);
  background: var(--background);
  flex-shrink: 0; /* Never compress - input must always be visible */
}

.replying-to {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
  background: rgba(38, 139, 210, 0.12);
  border-left: 4px solid var(--primary);
  border-radius: 0;
  font-size: 0.875rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.replying-text {
  color: var(--text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cancel-reply-button {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 1.1rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  min-height: 28px;
}

.cancel-reply-button:hover {
  background: rgba(220, 50, 47, 0.1);
  color: var(--accent-red);
}

.input-row {
  display: flex;
  gap: 0.5rem;
}

.message-input {
  flex: 1;
  padding: 0.5rem;
  background: white;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.9rem;
  resize: vertical;
  min-height: 2.5rem;
  transition: border-color 0.15s ease;
}

.message-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(38, 139, 210, 0.1);
}

.message-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-button {
  padding: 0.5rem 1rem;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.send-button:hover:not(:disabled) {
  background: var(--primary-hover);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Scrollbar styling - subtle like Slack */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

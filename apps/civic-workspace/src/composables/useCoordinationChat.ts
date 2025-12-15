import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { api } from '@/services/api';
import { socketService } from '@/services/socket';
import type { ThreadMessage, ThreadParticipant, SocketMessage, TypingEvent } from '@/types/civic';

/**
 * Coordination Chat Composable
 *
 * Manages real-time messaging for a coordination thread.
 * Handles REST API fetching + Socket.io real-time updates.
 *
 * @param threadIdGetter - Function that returns the coordination thread ID (for reactivity)
 * @param userId - Current user's ID
 * @param focalType - Type of focal point (issue/event)
 * @param focalId - ID of focal point
 */
export function useCoordinationChat(
  threadIdGetter: () => string | null,
  userId: string,
  focalType: 'issue' | 'event',
  focalId: string
) {
  // Reactive thread ID
  const threadId = computed(threadIdGetter);
  // State
  const messages = ref<ThreadMessage[]>([]);
  const participants = ref<ThreadParticipant[]>([]);
  const typingUsers = ref<Set<string>>(new Set());
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const isSending = ref(false);

  // Typing timeout map (to auto-clear typing indicators)
  const typingTimeouts = new Map<string, number>();

  // Computed
  const participantCount = computed(() => participants.value.length);

  const typingUsersList = computed(() => {
    return Array.from(typingUsers.value).filter(id => id !== userId);
  });

  const typingText = computed(() => {
    const count = typingUsersList.value.length;
    if (count === 0) return null;
    if (count === 1) return 'Someone is typing...';
    return `${count} people are typing...`;
  });

  const unreadCount = computed(() => {
    // Find current user's participant record
    const participant = participants.value.find(p => p.user_id === userId);
    if (!participant) return 0;

    // Count messages after last_seen_at
    const lastSeen = new Date(participant.last_seen_at);
    return messages.value.filter(m => {
      return m.user_id !== userId && new Date(m.created_at) > lastSeen;
    }).length;
  });

  /**
   * Fetch initial messages from REST API
   */
  async function fetchMessages(): Promise<void> {
    if (!threadId.value) return;

    isLoading.value = true;
    error.value = null;

    try {
      const response = await api.getThreadMessages(threadId.value, userId);
      messages.value = response.messages || [];
      participants.value = response.participants || [];
    } catch (err) {
      console.error('[Chat] Failed to fetch messages:', err);
      error.value = err instanceof Error ? err.message : 'Failed to load messages';
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Send a message
   * @param content - Message content
   * @param parentMessageId - Optional parent message ID for nested replies
   */
  async function sendMessage(content: string, parentMessageId?: string): Promise<void> {
    if (!content.trim() || !threadId.value) return;

    isSending.value = true;
    error.value = null;

    try {
      // Send via WebSocket (saves to DB and broadcasts to all clients in one operation)
      socketService.sendMessage(content.trim(), parentMessageId);

      // Stop typing indicator
      socketService.sendTypingIndicator(false);

      // Note: The WebSocket server will broadcast the message back to us,
      // and onNewMessage will add it to the messages array
    } catch (err) {
      console.error('[Chat] Failed to send message:', err);
      error.value = err instanceof Error ? err.message : 'Failed to send message';
      throw err; // Re-throw so UI can handle
    } finally {
      isSending.value = false;
    }
  }

  /**
   * Handle typing indicator
   * @param isTyping - Whether user is currently typing
   */
  function handleTyping(isTyping: boolean): void {
    socketService.sendTypingIndicator(isTyping);
  }

  /**
   * Mark thread as read (update last_seen_at)
   */
  async function markAsRead(): Promise<void> {
    try {
      await api.markThreadAsRead(focalType, focalId, userId);

      // Update local participant record
      const participant = participants.value.find(p => p.user_id === userId);
      if (participant) {
        participant.last_seen_at = new Date().toISOString();
      }
    } catch (err) {
      console.error('[Chat] Failed to mark as read:', err);
    }
  }

  /**
   * Socket.io message handler
   */
  function onNewMessage(message: SocketMessage): void {
    // Validate message belongs to current thread (prevent cross-thread contamination)
    if (message.thread_id !== threadId.value) {
      console.warn('[Chat] Ignoring message from different thread:', message.thread_id, 'expected:', threadId.value);
      return;
    }

    // Re-fetch messages to get proper nested structure with replies
    // This ensures collapse buttons appear and parent-child relationships are correct
    fetchMessages();

    // Clear typing indicator for this user
    typingUsers.value.delete(message.user_id);
    const timeout = typingTimeouts.get(message.user_id);
    if (timeout) {
      clearTimeout(timeout);
      typingTimeouts.delete(message.user_id);
    }
  }

  /**
   * Socket.io typing event handler
   */
  function onTypingEvent(event: TypingEvent): void {
    // Ignore own typing events
    if (event.user_id === userId) return;

    if (event.is_typing) {
      // Add to typing users
      typingUsers.value.add(event.user_id);

      // Auto-clear after 3 seconds
      const existingTimeout = typingTimeouts.get(event.user_id);
      if (existingTimeout) {
        clearTimeout(existingTimeout);
      }

      const timeout = window.setTimeout(() => {
        typingUsers.value.delete(event.user_id);
        typingTimeouts.delete(event.user_id);
      }, 3000);

      typingTimeouts.set(event.user_id, timeout);
    } else {
      // Remove from typing users
      typingUsers.value.delete(event.user_id);
      const timeout = typingTimeouts.get(event.user_id);
      if (timeout) {
        clearTimeout(timeout);
        typingTimeouts.delete(event.user_id);
      }
    }
  }

  /**
   * Initialize chat (connect socket, join thread, fetch messages)
   */
  async function init(): Promise<void> {
    if (!threadId.value) return;

    // Connect socket if not already connected
    if (!socketService.isConnected) {
      socketService.connect(userId);
    }

    // Register event handlers
    socketService.onMessage(onNewMessage);
    socketService.onTyping(onTypingEvent);

    // Join thread
    socketService.joinThread(threadId.value);

    // Fetch initial messages
    await fetchMessages();
  }

  /**
   * Cleanup (leave thread, unregister handlers)
   */
  function cleanup(): void {
    const currentThreadId = threadId.value;
    if (!currentThreadId) return;

    // Leave thread
    socketService.leaveThread(currentThreadId);

    // Unregister handlers
    socketService.offMessage(onNewMessage);
    socketService.offTyping(onTypingEvent);

    // Clear typing timeouts
    typingTimeouts.forEach(timeout => clearTimeout(timeout));
    typingTimeouts.clear();
    typingUsers.value.clear();

    // Clear messages and participants when leaving thread
    messages.value = [];
    participants.value = [];
  }

  // Lifecycle hooks
  onMounted(() => {
    init();
  });

  onUnmounted(() => {
    cleanup();
  });

  // Watch threadId changes (in case thread changes while component is mounted)
  watch(threadId, (newThreadId, oldThreadId) => {
    // Only react if thread actually changed
    if (oldThreadId === newThreadId) return;

    // Clean up old thread
    if (oldThreadId) {
      cleanup();
    }

    // Initialize new thread
    if (newThreadId) {
      init();
    }
  });

  return {
    // State
    messages,
    participants,
    participantCount,
    typingUsers: typingUsersList,
    typingText,
    unreadCount,
    isLoading,
    error,
    isSending,

    // Methods
    sendMessage,
    handleTyping,
    markAsRead,
    fetchMessages,
    init,
    cleanup
  };
}

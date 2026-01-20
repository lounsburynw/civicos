import { io, Socket } from 'socket.io-client';
import type { SocketMessage, TypingEvent } from '@/types/civic';

/**
 * Socket.io Client Service
 *
 * Manages WebSocket connection to coordination messaging server.
 * Singleton pattern - one connection shared across the app.
 */
class SocketService {
  private socket: Socket | null = null;
  private userId: string | null = null;
  private activeThreadId: string | null = null;

  /**
   * Initialize Socket.io connection
   * @param userId - Current user's ID (for authentication)
   */
  connect(userId: string): void {
    if (this.socket?.connected) {
      console.log('[Socket] Already connected');
      return;
    }

    this.userId = userId;

    // Connect to WebSocket server (port 8002)
    const socketUrl = import.meta.env.VITE_SOCKET_URL || 'http://localhost:8002';

    this.socket = io(socketUrl, {
      auth: {
        user_id: userId
      },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 5
    });

    // Connection event handlers
    this.socket.on('connect', () => {
      console.log('[Socket] Connected to server');
    });

    this.socket.on('disconnect', (reason) => {
      console.log('[Socket] Disconnected:', reason);
    });

    this.socket.on('connect_error', (error) => {
      console.error('[Socket] Connection error:', error);
    });

    this.socket.on('error', (error) => {
      console.error('[Socket] Socket error:', error);
    });
  }

  /**
   * Disconnect from Socket.io server
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.userId = null;
      this.activeThreadId = null;
      console.log('[Socket] Disconnected');
    }
  }

  /**
   * Join a coordination thread
   * @param threadId - Thread to join
   */
  joinThread(threadId: string): void {
    if (!this.socket || !this.userId) {
      console.warn('[Socket] Cannot join thread - not connected');
      return;
    }

    this.activeThreadId = threadId;
    this.socket.emit('join_thread', {
      thread_id: threadId,
      user_id: this.userId
    });

    console.log('[Socket] Joined thread:', threadId);
  }

  /**
   * Leave a coordination thread
   * @param threadId - Thread to leave
   */
  leaveThread(threadId: string): void {
    if (!this.socket || !this.userId) {
      return;
    }

    this.socket.emit('leave_thread', {
      thread_id: threadId,
      user_id: this.userId
    });

    if (this.activeThreadId === threadId) {
      this.activeThreadId = null;
    }

    console.log('[Socket] Left thread:', threadId);
  }

  /**
   * Send a message to current thread
   * @param content - Message content
   * @param parentMessageId - Optional parent message ID for nested replies
   */
  sendMessage(content: string, parentMessageId?: string): void {
    if (!this.socket || !this.userId || !this.activeThreadId) {
      console.warn('[Socket] Cannot send message - not in a thread');
      return;
    }

    this.socket.emit('new_message', {
      thread_id: this.activeThreadId,
      user_id: this.userId,
      content: content.trim(),
      parent_message_id: parentMessageId || null
    });
  }

  /**
   * Send typing indicator
   * @param isTyping - Whether user is currently typing
   */
  sendTypingIndicator(isTyping: boolean): void {
    if (!this.socket || !this.userId || !this.activeThreadId) {
      return;
    }

    const event = isTyping ? 'typing' : 'stop_typing';
    this.socket.emit(event, {
      thread_id: this.activeThreadId,
      user_id: this.userId
    });
  }

  /**
   * Register callback for new messages
   * @param callback - Function to call when message received
   */
  onMessage(callback: (message: SocketMessage) => void): void {
    if (!this.socket) return;
    this.socket.on('message', callback);
  }

  /**
   * Register callback for typing events
   * @param callback - Function to call when typing event received
   */
  onTyping(callback: (event: TypingEvent) => void): void {
    if (!this.socket) return;
    this.socket.on('user_typing', callback);
  }

  /**
   * Unregister message callback
   */
  offMessage(callback?: (message: SocketMessage) => void): void {
    if (!this.socket) return;
    this.socket.off('message', callback);
  }

  /**
   * Unregister typing callback
   */
  offTyping(callback?: (event: TypingEvent) => void): void {
    if (!this.socket) return;
    this.socket.off('user_typing', callback);
  }

  /**
   * Check if socket is connected
   */
  get isConnected(): boolean {
    return this.socket?.connected || false;
  }

  /**
   * Get current user ID
   */
  get currentUserId(): string | null {
    return this.userId;
  }

  /**
   * Get active thread ID
   */
  get currentThreadId(): string | null {
    return this.activeThreadId;
  }
}

// Export singleton instance
export const socketService = new SocketService();

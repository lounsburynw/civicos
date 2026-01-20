import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { CivicEvent, ConversationRequest } from '../types/civic'
import { api } from '../services/api'
import { useWorkspaceStore } from './workspace'

/**
 * Chat Store
 *
 * Manages conversational interface including:
 * - Conversation messages
 * - Chat panel visibility and height
 * - Context (event, complaint, etc.)
 * - Integration with POST /api/conversation
 * - Context-aware persistence (Option B Phase 1)
 */

export type MessageRole = 'user' | 'assistant' | 'system'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  // Session 68: Developer mode - LLM provider info
  provider_used?: string
  model_used?: string
  usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
  }
}

export interface ChatContext {
  type: 'event' | 'issue' | 'proposal' | 'discussion' | 'legislative' | 'wiki'
  id?: string
  data?: CivicEvent | any
  initialMessage?: string
}

const DEFAULT_PANEL_HEIGHT = 400
const MIN_PANEL_HEIGHT = 200
const MAX_PANEL_HEIGHT = 800

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<ChatMessage[]>([])
  const isVisible = ref(false)
  const panelHeight = ref(DEFAULT_PANEL_HEIGHT)
  const context = ref<ChatContext | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const userId = ref<string>('demo-user') // TODO: Replace with actual user auth

  // Get workspace store for context-aware updates
  const workspaceStore = useWorkspaceStore()

  // Computed
  const hasMessages = computed(() => messages.value.length > 0)
  const lastMessage = computed(() => {
    return messages.value.length > 0
      ? messages.value[messages.value.length - 1]
      : null
  })

  // Actions
  function openChat(chatContext?: ChatContext) {
    isVisible.value = true
    if (chatContext) {
      // If context changed (different event/complaint), add system message
      if (context.value && context.value.id !== chatContext.id) {
        const contextTitle = chatContext.data?.title || chatContext.id || 'new context'
        addMessage({
          role: 'system',
          content: `Context switched to: ${contextTitle}`
        })
      }
      context.value = chatContext
      // If there's an initial message, send it automatically
      if (chatContext.initialMessage) {
        sendMessage(chatContext.initialMessage)
      }
    }
  }

  function closeChat() {
    isVisible.value = false
  }

  function toggleChat() {
    isVisible.value = !isVisible.value
  }

  function setPanelHeight(height: number) {
    panelHeight.value = Math.max(MIN_PANEL_HEIGHT, Math.min(MAX_PANEL_HEIGHT, height))
  }

  function addMessage(message: Omit<ChatMessage, 'id' | 'timestamp'>) {
    const newMessage: ChatMessage = {
      ...message,
      id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: Date.now()
    }
    messages.value.push(newMessage)
    return newMessage
  }

  async function sendMessage(content: string) {
    if (!content.trim()) return

    // Add user message to chat
    const userMessage = addMessage({
      role: 'user',
      content: content.trim()
    })

    // Build request for API based on context
    const requestData: Partial<ConversationRequest> & { message: string } = {
      message: content,
      user_id: userId.value
    }

    // If we have event context, extract jurisdiction and send as city
    if (context.value && context.value.type === 'event' && context.value.data) {
      const event = context.value.data as CivicEvent
      const jurisdiction = event.jurisdiction
      if (jurisdiction) {
        // Extract city name from jurisdiction (e.g., "city-oakland" -> "Oakland")
        const cityName = jurisdiction.name || jurisdiction.id.replace('city-', '').replace(/-/g, ' ')
        requestData.city = cityName

        // Add event-specific prompt enhancement
        requestData.event_context = {
          title: event.title,
          description: event.description,
          when: event.when,
          project_type: event.project_type
        }
      }
    }

    // DEBUG: Log what we're sending
    console.log('[Chat Store] Sending request:', {
      has_context: !!context.value,
      context_type: context.value?.type,
      has_event_data: !!(context.value?.data),
      city: requestData.city,
      has_event_context: !!requestData.event_context,
      event_title: requestData.event_context?.title
    })

    isLoading.value = true
    error.value = null

    try {
      const response = await api.sendMessage(requestData)

      // Add assistant response
      addMessage({
        role: 'assistant',
        content: response.response
      })
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to send message'
      // Add error message to chat
      addMessage({
        role: 'system',
        content: `Error: ${error.value}`
      })
    } finally {
      isLoading.value = false
    }
  }

  function clearMessages() {
    messages.value = []
  }

  function clearContext() {
    context.value = null
  }

  function clearAll() {
    messages.value = []
    context.value = null
    error.value = null
  }

  function setUserId(newUserId: string) {
    userId.value = newUserId
  }

  // Watch for active artifact changes in workspace (auto-sync chat context)
  watch(
    () => workspaceStore.activeArtifact,
    (newArtifact, oldArtifact) => {
      // Skip if chat is not visible
      if (!isVisible.value) {
        return
      }

      // If artifact was closed (null), clear context
      if (!newArtifact) {
        if (context.value) {
          addMessage({
            role: 'system',
            content: 'Chat context cleared - now in general mode'
          })
          context.value = null
        }
        return
      }

      // Skip if artifact didn't actually change
      if (oldArtifact && oldArtifact.id === newArtifact.id) {
        return
      }

      // Map artifact type to chat context type
      let chatContextType: ChatContext['type']
      switch (newArtifact.type) {
        case 'event':
          chatContextType = 'event'
          break
        case 'issue':
          chatContextType = 'issue'
          break
        case 'bill':
          chatContextType = 'legislative'
          break
        case 'program':
          chatContextType = 'legislative'
          break
        default:
          chatContextType = 'event' // fallback
      }

      // Update context
      const previousContext = context.value
      context.value = {
        type: chatContextType,
        id: newArtifact.id,
        data: newArtifact.data
      }

      // Add system message about context change (only if there was a previous context)
      if (previousContext && previousContext.id !== newArtifact.id) {
        addMessage({
          role: 'system',
          content: `Context switched to: ${newArtifact.title}`
        })
      }
    }
  )

  return {
    // State
    messages,
    isVisible,
    panelHeight,
    context,
    isLoading,
    error,
    userId,

    // Computed
    hasMessages,
    lastMessage,

    // Actions
    openChat,
    closeChat,
    toggleChat,
    setPanelHeight,
    addMessage,
    sendMessage,
    clearMessages,
    clearContext,
    clearAll,
    setUserId
  }
})

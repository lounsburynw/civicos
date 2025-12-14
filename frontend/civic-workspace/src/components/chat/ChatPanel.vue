<template>
  <!-- Chat panel fills its container (no mode-specific logic) -->
  <div class="chat-panel-container">
    <!-- Chat Panel -->
    <div class="chat-panel">
      <!-- Header -->
      <div class="chat-header">
        <div class="chat-header-left">
          <span class="chat-title">Civic Assistant</span>
        </div>
        <div class="chat-header-right">
          <!-- Session 50 DEBUG: Test research injection -->
          <button
            @click="addTestResearchMessage"
            class="btn-icon btn-test"
            title="Test: Add sample research message"
          >
            <span class="icon">🧪</span>
          </button>
          <button
            v-if="chatStore.hasMessages"
            @click="handleClearMessages"
            class="btn-icon"
            title="Clear conversation"
          >
            <span class="icon">🗑️</span>
          </button>
        </div>
      </div>

      <!-- Model Picker (Session 88 - Developer Mode) -->
      <ModelPicker />

      <!-- Session 53: Chat Mode Selector - HIDDEN for auto-detection -->
      <!-- TODO Session 55-56: Implement LLM-based mode detection -->
      <!-- <ChatModeSelector /> -->

      <!-- Context Indicator Bar (NEW) -->
      <div v-if="chatStore.context" class="context-indicator-bar">
        <div class="context-info">
          <span class="context-icon">{{ contextIcon }}</span>
          <span class="context-label">{{ contextLabel }}</span>
        </div>
        <button
          @click="handleClearContext"
          class="btn-clear-context"
          title="Clear context and return to general chat"
        >
          Clear Context ✕
        </button>
      </div>

      <!-- NEW: Context Indicator Component (Session 51) -->
      <ContextIndicator />

      <!-- Messages Container -->
      <div ref="messagesContainer" class="messages-container">
        <div v-if="!chatStore.hasMessages" class="empty-state">
          <!-- Welcome Screen -->
          <div class="welcome-screen">
            <h1 class="welcome-title">What can I help you with today?</h1>
            <p class="welcome-subtitle">I can help you participate in local government</p>

            <!-- Input Box (part of welcome screen layout) -->
            <div class="welcome-input-wrapper">
              <textarea
                ref="inputField"
                v-model="messageInput"
                @keydown.enter.exact.prevent="handleSend"
                @keydown.enter.shift.exact="handleNewLine"
                placeholder="Ask me anything about civic participation..."
                class="welcome-message-input"
                rows="1"
              ></textarea>
              <button
                @click="handleSend"
                :disabled="!canSend"
                class="welcome-btn-send"
                title="Send message"
              >
                <span class="icon">↑</span>
              </button>
            </div>

            <!-- Quick Action Cards (below input) -->
            <div class="quick-actions">
              <button
                class="quick-action-card"
                @click="handleQuickAction('Find upcoming meetings in my area')"
              >
                <span class="action-icon">📅</span>
                <span class="action-text">Find upcoming meetings</span>
              </button>
              <button
                class="quick-action-card"
                @click="handleQuickAction('Report a neighborhood issue')"
              >
                <span class="action-icon">🚨</span>
                <span class="action-text">Report an issue</span>
              </button>
              <button
                class="quick-action-card"
                @click="handleQuickAction('Draft a public comment')"
              >
                <span class="action-icon">✉️</span>
                <span class="action-text">Draft a comment</span>
              </button>
              <button
                class="quick-action-card"
                @click="handleQuickAction('Browse local legislation')"
              >
                <span class="action-icon">📜</span>
                <span class="action-text">Browse legislation</span>
              </button>
            </div>
          </div>
        </div>

        <div v-else class="messages-list">
          <MessageBubble
            v-for="message in chatStore.messages"
            :key="message.id"
            :message="message"
            @use-in-draft="handleUseInDraft(message)"
          />
        </div>

        <!-- Loading Indicator -->
        <div v-if="chatStore.isLoading" class="loading-indicator">
          <div class="loading-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <span class="loading-text">Thinking...</span>
        </div>

        <!-- Error Message -->
        <div v-if="chatStore.error" class="error-message">
          <span class="error-icon">⚠️</span>
          <span class="error-text">{{ chatStore.error }}</span>
        </div>
      </div>

      <!-- Input Container (visible when messages exist) -->
      <div class="input-container" v-if="chatStore.hasMessages">
        <textarea
          ref="inputField"
          v-model="messageInput"
          @keydown.enter.exact.prevent="handleSend"
          @keydown.enter.shift.exact="handleNewLine"
          :placeholder="placeholder"
          class="message-input"
          rows="1"
        ></textarea>
        <button
          @click="handleSend"
          :disabled="!canSend"
          class="btn-send"
          title="Send message"
        >
          <span class="icon">↑</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, inject } from 'vue'
import { useChatStore } from '../../stores/chat'
import { useWorkspaceStore } from '../../stores/workspace'
import { useUserStore } from '../../stores/user'
import { useLegislativeStore } from '../../stores/legislative'
import { useSidebarStore } from '../../stores/sidebar'
import { useContextStore } from '../../stores/context'
import { useDeveloperStore } from '../../stores/developer'
import { routeChatMessage, type ChatAction, type ChatContext } from '../../services/chatRouter'
import { api } from '../../services/api'
// Session 60: Removed queryClassifier import - now using unified backend search
import { serializeContextForLLM } from '../../utils/contextHelpers'
import { CHAT_MODES, type ChatMode } from '../../config/chatModes'
import { useVisualEnhancements } from '../../composables/useVisualEnhancements'
import type EventsPanel from '../sidebar/EventsPanel.vue'
import type LegislativePanel from '../sidebar/LegislativePanel.vue'
import type MyIssuesPanel from '../sidebar/MyIssuesPanel.vue'
import MessageBubble from './MessageBubble.vue'
import ContextIndicator from './ContextIndicator.vue'
import ChatModeSelector from './ChatModeSelector.vue'
import ModelPicker from './ModelPicker.vue'

/**
 * ChatPanel Component (Session 31 - Perplexity/Claude.ai style layout)
 *
 * Chat interface that fills its container (side-by-side with artifacts)
 *
 * Features:
 * - Message display with scroll
 * - Input field with send button
 * - Integration with chat store
 * - Context display (event, complaint, etc.)
 * - **Chat routing** with OpenAI function calling (natural language navigation)
 * - **Responsive width** - adapts when artifact pane opens
 */

// No props needed - component adapts to its container

const chatStore = useChatStore()
const workspaceStore = useWorkspaceStore()
const userStore = useUserStore()
const legislativeStore = useLegislativeStore()
const sidebarStore = useSidebarStore()
const contextStore = useContextStore() // Session 55: Context management
const developerStore = useDeveloperStore() // Session 88: Model selection
const { triggerSectionPulse, triggerFilterHighlight } = useVisualEnhancements() // Session 59: Visual enhancements

// Inject EventsPanel ref for programmatic filter control (AI as first-class user)
const eventsPanelRef = inject<typeof EventsPanel | null>('eventsPanelRef', null)

// Inject LegislativePanel ref for programmatic filter control (AI as first-class user)
const legislativePanelRef = inject<typeof LegislativePanel | null>('legislativePanelRef', null)

// Session 61: Inject MyIssuesPanel ref for programmatic filter control
const issuesPanelRef = inject<typeof MyIssuesPanel | null>('issuesPanelRef', null)

// Refs
const messagesContainer = ref<HTMLElement | null>(null)
const inputField = ref<HTMLTextAreaElement | null>(null)
const messageInput = ref('')
const conversationId = ref<string>() // Session 27: Track conversation for chat routing

// Computed
const canSend = computed(() => {
  return messageInput.value.trim().length > 0 && !chatStore.isLoading
})

// Session 27: Build context from current chat state for chat routing
const currentContext = computed<ChatContext>(() => ({
  current_artifact: chatStore.context?.id,
  current_jurisdiction: chatStore.context?.data?.jurisdiction_id,
  current_event: chatStore.context?.type === 'event' ? chatStore.context.id : undefined,
  user_city: userStore.cityName,
  user_jurisdiction_id: userStore.jurisdictionId
}))

const contextIcon = computed(() => {
  if (!chatStore.context) return ''

  switch (chatStore.context.type) {
    case 'event':
      return '📅'
    case 'issue':
      return '📝'
    case 'legislative':
      return '📋'
    case 'proposal':
      return '💡'
    default:
      return '💬'
  }
})

const contextLabel = computed(() => {
  if (!chatStore.context) return ''

  // Get title from context data
  const title = chatStore.context.data?.title || chatStore.context.id || 'Unknown'

  switch (chatStore.context.type) {
    case 'event':
      return `Discussing: ${title}`
    case 'issue':
      return `Issue: ${title}`
    case 'legislative':
      return `Legislation: ${title}`
    case 'proposal':
      return `Proposal: ${title}`
    default:
      return title
  }
})

const placeholder = computed(() => {
  if (!chatStore.context) {
    return "What's happening in your city? (Shift+Enter for new line)"
  }

  switch (chatStore.context.type) {
    case 'event':
      return 'Ask about this meeting... (Shift+Enter for new line)'
    case 'issue':
      return 'Ask about this issue... (Shift+Enter for new line)'
    case 'legislative':
      return 'Ask about this legislation... (Shift+Enter for new line)'
    case 'proposal':
      return 'Ask about this proposal... (Shift+Enter for new line)'
    default:
      return 'Type your message... (Shift+Enter for new line)'
  }
})

// Actions
function handleQuickAction(actionText: string) {
  // Pre-fill the message input with the quick action text
  messageInput.value = actionText
  // Auto-submit the message (one-click flow)
  nextTick(() => {
    handleSend()
  })
}

// Session 27: Chat routing with OpenAI function calling
// Session 55: Enhanced with multi-artifact context awareness
async function handleSend() {
  if (!canSend.value) return

  const message = messageInput.value.trim()
  messageInput.value = ''

  // Reset textarea height
  if (inputField.value) {
    inputField.value.style.height = 'auto'
  }

  // Add user message to chat immediately
  chatStore.addMessage({
    role: 'user',
    content: message
  })

  // Set loading state
  chatStore.isLoading = true
  chatStore.error = null

  try {
    // Session 55: Serialize active context for LLM
    const activeContext = contextStore.activeContext
    const serializedContext = serializeContextForLLM(activeContext)
    const currentMode = contextStore.activeMode

    console.log('[ChatPanel] Sending message with context:', {
      mode: currentMode,
      contextElementCount: activeContext.length,
      serializedPreview: serializedContext.substring(0, 200)
    })

    // Session 88: Get model override if not "auto"
    const modelOverride = developerStore.selectedModel !== 'auto'
      ? developerStore.selectedModel
      : undefined

    // Route message via OpenAI function calling with context
    const action = await routeChatMessage(message, {
      conversationId: conversationId.value,
      context: currentContext.value,
      mode: currentMode,
      serializedContext: serializedContext,
      modelOverride: modelOverride  // Session 88: Manual model selection
    })

    // Store conversation ID for continuity
    conversationId.value = action.conversation_id

    // Session 56: Handle mode changes from backend (silently - modes are deprecated)
    if (action.mode_changed && action.mode) {
      const newMode = action.mode as ChatMode
      contextStore.setMode(newMode, action.mode_reason || 'LLM auto-detection')

      console.log('[ChatPanel] Mode changed:', {
        from: currentMode,
        to: newMode,
        reason: action.mode_reason
      })
    }

    // Dispatch action to UI
    await dispatchAction(action)

    // Only add backend message for conversational responses (not actions that add their own messages)
    if (action.action === 'respond') {
      if (action.message) {
        chatStore.addMessage({
          role: 'assistant',
          content: action.message,
          // Session 68: Capture provider info for developer mode
          provider_used: action.provider_used,
          model_used: action.model_used,
          usage: action.usage
        })
      } else if (action.reasoning) {
        chatStore.addMessage({
          role: 'assistant',
          content: action.reasoning,
          // Session 68: Capture provider info for developer mode
          provider_used: action.provider_used,
          model_used: action.model_used,
          usage: action.usage
        })
      }
    }

  } catch (error) {
    console.error('Chat routing error:', error)
    chatStore.addMessage({
      role: 'assistant',
      content: "I'm sorry, I encountered an error. Please try again."
    })
    chatStore.error = 'Failed to process message'
  } finally {
    chatStore.isLoading = false
  }

  // Scroll to bottom after sending
  await nextTick()
  scrollToBottom()

  // Focus input
  inputField.value?.focus()
}

// Session 27: Dispatch chat routing actions to UI
async function dispatchAction(action: ChatAction) {
  console.log('Dispatching action:', action.action, action.parameters)

  // Session 58: Detect multi-operation queries
  if (action.multi_operation && action.all_operations && action.all_operations.length > 1) {
    await handleMultiOperation(action)
    return
  }

  // Single operation dispatch (existing logic)
  switch (action.action) {
    case 'search_events':
      // Session 68: Pass provider info for developer mode
      await handleSearchEvents(action.parameters, {
        provider_used: action.provider_used,
        model_used: action.model_used,
        usage: action.usage
      })
      break

    case 'file_complaint':
      await handleFileComplaint(action.parameters)
      break

    case 'view_legislative_context':
      // Session 68.5: Pass provider info for developer mode
      await handleLegislativeContext(action.parameters, {
        provider_used: action.provider_used,
        model_used: action.model_used,
        usage: action.usage
      })
      break

    case 'draft_comment':
      await handleDraftComment(action.parameters)
      break

    case 'view_my_complaints':
      await handleViewComplaints(action.parameters)
      break

    case 'explain_event':
      await handleExplainEvent(action.parameters)
      break

    case 'respond':
      // Just conversational - message already added
      break

    default:
      console.warn('Unknown action:', action.action)
  }
}

// Session 58: Handle multi-operation queries (OR logic)
async function handleMultiOperation(action: ChatAction) {
  console.log('[ChatPanel] Multi-operation query:', {
    count: action.operation_count,
    operations: action.all_operations
  })

  // Show visual indicator
  const operationSummary = action.all_operations!
    .map((op, i) => {
      if (op.action === 'search_events') {
        const params = op.parameters || {}
        const jurisdiction = params.jurisdiction || 'unknown'
        const topic = params.topic || 'all topics'
        return `${i + 1}. ${topic} in ${jurisdiction}`
      } else if (op.action === 'view_legislative_context') {
        const params = op.parameters || {}
        const topic = params.topic || 'all topics'
        const level = params.level || 'both'
        return `${i + 1}. ${level} ${topic} legislation`
      } else {
        return `${i + 1}. ${op.action}`
      }
    })
    .join('\n')

  chatStore.addMessage({
    role: 'assistant',
    content: `I found **${action.operation_count} searches** for your query:\n\n${operationSummary}\n\nProcessing each search now...`
  })

  // Session 77: Track result count for query result banner
  let totalResultCount = 0

  // Process each operation sequentially
  for (let i = 0; i < action.all_operations!.length; i++) {
    const op = action.all_operations![i]
    const isFirstOp = i === 0

    console.log(`[ChatPanel] Processing operation ${i + 1}/${action.operation_count}:`, op.action)

    // Add separator message for clarity (Session 59: increased pause for visual breathing room)
    if (i > 0) {
      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 800)) // Session 59: Increased from 500ms to 800ms for better visibility
    }

    // Dispatch individual operation
    switch (op.action) {
      case 'search_events':
        // Session 68: Pass provider info for developer mode
        // NEW: Pass multi-op flags to control filter accumulation behavior
        await handleSearchEvents(
          op.parameters,
          {
            provider_used: op.provider_used,
            model_used: op.model_used,
            usage: op.usage
          },
          {
            isMultiOp: true,
            isFirstInMultiOp: isFirstOp
          }
        )
        // Note: We don't have easy access to result count here, will use filteredEvents.length from EventsPanel
        break
      case 'view_legislative_context':
        await handleLegislativeContext(op.parameters)
        break
      case 'explain_event':
        await handleExplainEvent(op.parameters)
        break
      case 'respond':
        // Skip respond actions in multi-op (they're metadata only)
        break
      default:
        console.warn('[ChatPanel] Unknown multi-op action:', op.action)
    }
  }

  // Session 77: Set active query mode in workspace store
  // Get the current user message from chat history
  const userMessage = chatStore.messages[chatStore.messages.length - 2]?.content || 'Multi-operation query'

  workspaceStore.setActiveQuery({
    rawQuery: userMessage,
    operations: action.all_operations!.map(op => ({
      action: op.action,
      parameters: op.parameters || {}
    })),
    resultCount: 0  // Will be updated by EventsPanel when it loads
  })

  // Summary message after processing all operations
  chatStore.addMessage({
    role: 'assistant',
    content: `Finished processing all **${action.operation_count} searches**. Results are shown in the workspace.`
  })
}

/**
 * Helper function to convert jurisdiction_id to display name
 * Session 60.5: Fix chat display formatting
 */
function getJurisdictionDisplayName(jurisdictionId: string): string {
  // Check if it's "all"
  if (jurisdictionId === 'all') {
    return 'all Bay Area cities'
  }

  // Convert jurisdiction_id to display name
  // Examples: "city-berkeley" → "Berkeley", "county-alameda" → "Alameda County"
  if (jurisdictionId.startsWith('city-')) {
    const cityName = jurisdictionId.replace('city-', '').split('-').map(word =>
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ')
    return cityName
  } else if (jurisdictionId.startsWith('county-')) {
    const countyName = jurisdictionId.replace('county-', '').split('-').map(word =>
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ')
    return `${countyName} County`
  }

  // Fallback: just capitalize the jurisdiction_id
  return jurisdictionId.split('-').map(word =>
    word.charAt(0).toUpperCase() + word.slice(1)
  ).join(' ')
}

// Action handlers (Session 27 + Session 60 - Unified backend search)
async function handleSearchEvents(
  params: any,
  providerInfo?: { provider_used?: string, model_used?: string, usage?: any },
  options?: { isMultiOp?: boolean, isFirstInMultiOp?: boolean }
) {
  console.log('[ChatPanel] Search events:', params)

  // Session 63: Show workspace and expand section FIRST (visual feedback even if query fails)
  if (workspaceStore.viewMode === 'chat-first' && !workspaceStore.workspaceVisible) {
    workspaceStore.toggleWorkspaceVisibility()
  }
  sidebarStore.expandSectionExclusive('events')
  triggerSectionPulse('events')  // Session 59: Visual feedback

  // Session 60: Check if user has set their location (unless searching "all")
  if (!userStore.hasLocation && params.jurisdiction !== 'all') {
    chatStore.addMessage({
      role: 'assistant',
      content: `📍 **Location Required**\n\nTo show you civic meetings in your area, I need to know where you're located.\n\nPlease enter your address in the location prompt to get started. Your full address is never stored—we only keep your city and county.`
    })
    return
  }

  // Session 60: Always call backend search API (unified path - eliminates queryClassifier)
  try {
    const searchParams = {
      jurisdiction: params.jurisdiction || 'all',  // Default to 'all' if not specified
      topic: params.topic,
      query: params.query,  // Keyword search
      dateRange: params.date_range
    }

    console.log('[ChatPanel] Calling backend search:', searchParams)
    const results = await api.searchEvents(searchParams)

    // Determine replace behavior:
    // - Single operation: replace=true (clear previous filters)
    // - Multi-operation, first: replace=true (clear previous unrelated filters)
    // - Multi-operation, subsequent: replace=false (accumulate with previous operations)
    const shouldReplace = !options?.isMultiOp || options?.isFirstInMultiOp

    // Session 77: For multi-operation queries, always use 'all' jurisdiction in sidebar
    // to avoid jurisdiction conflicts (e.g., "housing in Berkeley OR transportation in Oakland")
    // Backend still searches specific jurisdictions, but sidebar shows ALL fetched results
    const effectiveJurisdiction = options?.isMultiOp ? 'all' : (params.jurisdiction || 'all')

    // Update workspace based on result scope
    if (results.jurisdictions_searched.length === 1) {
      // Single jurisdiction → apply filters to EventsPanel (existing UX)
      await nextTick()
      const eventsPanel = eventsPanelRef?.value
      if (eventsPanel && 'applyFilters' in eventsPanel) {
        eventsPanel.applyFilters({
          topic: params.topic,
          dateRange: params.date_range,
          searchQuery: params.query,
          jurisdiction: effectiveJurisdiction,  // Session 77: Use 'all' for multi-op queries
          replace: shouldReplace  // NEW: Control accumulation behavior
        })

        // Session 59: Trigger filter highlight if topic filter applied
        if (params.topic) {
          triggerFilterHighlight('events', params.topic)
        }
      }

      chatStore.addMessage({
        role: 'assistant',
        content: `Found **${results.count} events** in ${getJurisdictionDisplayName(results.jurisdictions_searched[0])}.`,
        // Session 68: Include provider info for developer mode
        ...providerInfo
      })
    } else {
      // Multi-jurisdiction → show all events in sidebar (Session 60.5 fix)
      // TODO Session 60 Phase 4: Create workspace tabs for true multi-jurisdiction support
      console.log('[ChatPanel] Multi-jurisdiction results:', results)

      await nextTick()
      const eventsPanel = eventsPanelRef?.value
      if (eventsPanel && 'applyFilters' in eventsPanel) {
        eventsPanel.applyFilters({
          topic: params.topic,
          dateRange: params.date_range,
          searchQuery: params.query,
          jurisdiction: effectiveJurisdiction,  // Session 77: Use 'all' for multi-op queries
          replace: shouldReplace  // NEW: Control accumulation behavior
        })

        // Trigger filter highlight if topic filter applied
        if (params.topic) {
          triggerFilterHighlight('events', params.topic)
        }
      }

      chatStore.addMessage({
        role: 'assistant',
        content: `Found **${results.count} events** across **${results.jurisdictions_searched.length} jurisdictions**.`,
        // Session 68: Include provider info for developer mode
        ...providerInfo
      })
    }
  } catch (error) {
    console.error('[ChatPanel] Search error:', error)
    chatStore.addMessage({
      role: 'assistant',
      content: `I encountered an error searching for events. Please try again.`
    })
  }
}

async function handleFileComplaint(params: any) {
  console.log('File complaint:', params)

  // Session 62 fix: Ensure workspace is visible before opening form
  if (workspaceStore.viewMode === 'chat-first' && !workspaceStore.workspaceVisible) {
    workspaceStore.toggleWorkspaceVisibility()
  }

  // Open complaint form as an artifact in the right pane
  workspaceStore.openArtifact({
    id: 'new-complaint',
    type: 'issue-form',
    title: 'Report Issue',
    data: {
      initialData: {
        title: params.title,
        description: params.description,
        address: params.address,
        category: params.category
      }
    }
  })

  // Add helpful message
  const hasDetails = params.description || params.title || params.address
  chatStore.addMessage({
    role: 'assistant',
    content: hasDetails
      ? `I've opened an issue form for you with these details pre-filled:\n\n**Your issue:**\n- ${params.description || params.title}\n- Location: ${params.address || 'Not specified'}\n- Category: ${params.category || 'Will be auto-detected'}\n\nPlease review and submit the form in the right pane.`
      : `I've opened the issue form in the right pane. Please describe the issue you'd like to report.`
  })
}

async function handleLegislativeContext(params: any, providerInfo?: any) {
  console.log('View legislative context:', params)

  // Session 64: Map common aliases to canonical topics (matches backend civic_api_integrated.py:5013-5019)
  const topicAliases: Record<string, string> = {
    'cdbg': 'budget',  // CDBG is a federal budget program
    'funding': 'budget',
    'grants': 'budget'
  }
  const normalizedTopic = params.topic ? (topicAliases[params.topic.toLowerCase()] || params.topic) : params.topic

  // Show workspace and switch to Legislative tab
  if (workspaceStore.viewMode === 'chat-first' && !workspaceStore.workspaceVisible) {
    workspaceStore.toggleWorkspaceVisibility()
  }
  workspaceStore.setActiveTab('legislative')

  // Session 50 fix: Expand the Legislative section in the sidebar (collapse others for clarity)
  sidebarStore.expandSectionExclusive('legislative')

  // Apply filters using exposed method (AI as first-class user)
  const legislativePanel = legislativePanelRef?.value
  if (legislativePanel && 'applyFilters' in legislativePanel) {
    legislativePanel.applyFilters({
      topic: normalizedTopic === 'all' ? null : normalizedTopic,
      searchQuery: params.searchQuery, // If user provides a search query
      level: params.level || 'both' // Default to both if not specified
    })
    console.log('[ChatPanel] Applied legislative filters via AI:', { original: params.topic, normalized: normalizedTopic })
  } else {
    // Fallback: Set topic directly in store
    if (normalizedTopic && normalizedTopic !== 'all') {
      legislativeStore.setSelectedTopic(normalizedTopic)
    } else {
      legislativeStore.setSelectedTopic(null)
    }
  }

  const levelText = params.level === 'state' ? 'state bills' :
                    params.level === 'federal' ? 'federal programs' :
                    'state bills and federal programs'

  const topicText = normalizedTopic === 'all' ? 'all topics' : `**${normalizedTopic}**`
  const searchText = params.searchQuery ? ` matching "${params.searchQuery}"` : ''

  chatStore.addMessage({
    role: 'assistant',
    content: `I've opened the Legislative panel to show you ${levelText} for ${topicText}${searchText}.\n\nBrowse the sidebar to explore relevant legislation and programs.`,
    // Session 68.5: Include provider info for developer mode
    provider_used: providerInfo?.provider_used,
    model_used: providerInfo?.model_used,
    usage: providerInfo?.usage
  })
}

async function handleDraftComment(params: any) {
  console.log('Draft comment:', params)

  chatStore.addMessage({
    role: 'assistant',
    content: `I can help you draft a ${params.stance || 'neutral'} comment for this event.\n\n**Note**: Comment drafting will be fully integrated in a future update. For now, you can:\n1. Find the event in the workspace\n2. Click "Draft Comment" on the event card\n3. I'll help you write a persuasive public comment`
  })
}

async function handleViewComplaints(params: any) {
  console.log('[ChatPanel] View my complaints:', params)

  // Session 62: Check if user has set their location
  if (!userStore.hasLocation) {
    chatStore.addMessage({
      role: 'assistant',
      content: `📍 **Location Required**\n\nTo show you your issues, I need to know where you're located.\n\nPlease enter your address in the location prompt to get started.`
    })
    return
  }

  // Show workspace and switch to My Issues tab
  if (workspaceStore.viewMode === 'chat-first' && !workspaceStore.workspaceVisible) {
    workspaceStore.toggleWorkspaceVisibility()
  }
  workspaceStore.setActiveTab('myissues')

  // Expand My Issues section (collapse others)
  sidebarStore.expandSectionExclusive('myIssues')
  triggerSectionPulse('myIssues')  // Session 63: Use camelCase for consistency

  // Session 63: Call backend search API with ownership + status separation
  try {
    const searchParams = {
      user_id: userStore.userId,
      ownership: params.ownership,  // Session 63: Separate from status
      status: params.status,
      category: params.issue_type,  // Backend expects 'category'
      jurisdiction: params.jurisdiction,
      q: params.query
    }

    console.log('[ChatPanel] Calling backend issues search:', searchParams)
    const results = await api.searchIssues(searchParams)

    // Apply filters to sidebar (for visual feedback)
    await nextTick()
    const issuesPanel = issuesPanelRef?.value
    if (issuesPanel && 'applyFilters' in issuesPanel) {
      issuesPanel.applyFilters({
        ownership: params.ownership,
        status: params.status,
        category: params.issue_type,
        jurisdiction: params.jurisdiction,
        searchQuery: params.query
      })
    }

    // Build response message with count and filters (matches events pattern)
    const filters = []
    if (params.ownership && params.ownership !== 'all' && params.ownership !== 'mine') {
      filters.push(params.ownership)  // Only show if not default
    }
    if (params.status && params.status !== 'all') filters.push(params.status)
    if (params.issue_type && params.issue_type !== 'all') filters.push(params.issue_type)
    if (params.jurisdiction && params.jurisdiction !== 'all') {
      filters.push(getJurisdictionDisplayName(params.jurisdiction))
    }
    if (params.query) filters.push(`matching "${params.query}"`)

    const filterText = filters.length > 0 ? ` (${filters.join(', ')})` : ''

    chatStore.addMessage({
      role: 'assistant',
      content: `Found **${results.count} issue${results.count !== 1 ? 's' : ''}**${filterText}.`
    })
  } catch (error) {
    console.error('[ChatPanel] Issues search failed:', error)
    chatStore.addMessage({
      role: 'assistant',
      content: 'Sorry, I encountered an error searching your issues. Please try again.'
    })
  }
}

async function handleExplainEvent(params: any) {
  console.log('Explain event:', params)

  // Session 55: Get event from context store
  const activeContext = contextStore.activeContext
  const eventContext = activeContext.find(el => el.type === 'event')

  if (!eventContext) {
    chatStore.addMessage({
      role: 'assistant',
      content: 'I don\'t have the event details available. Please open an event to see its agenda items.'
    })
    return
  }

  const event = eventContext.data as any

  // Build detailed agenda items message
  const agendaItems = event.agenda_expansion?.actionable_items || []

  if (agendaItems.length === 0) {
    chatStore.addMessage({
      role: 'assistant',
      content: `This meeting (${event.title}) doesn't have detailed agenda items available yet. The agenda may not have been published.`
    })
    return
  }

  // Format agenda items
  const itemsList = agendaItems.map((item: any, index: number) => {
    const num = index + 1
    const title = item.title || 'Untitled Item'
    const actionable = item.actionable ? '✅' : '❌'
    const topics = item.project_types?.join(', ') || 'General'
    return `**${num}. ${title}** ${actionable}\n   Topics: ${topics}`
  }).join('\n\n')

  const message = `## ${event.title}\n**Date**: ${new Date(event.when).toLocaleDateString()}\n**Location**: ${event.jurisdiction.name}\n\n### Agenda Items (${agendaItems.length} total)\n\n${itemsList}\n\n✅ = Actionable (you can comment)\n❌ = Informational only`

  chatStore.addMessage({
    role: 'assistant',
    content: message
  })
}

function handleNewLine() {
  // Allow Shift+Enter to create new line
  // This is handled by not preventing default on Shift+Enter
}

function handleClearMessages() {
  if (confirm('Clear all messages in this conversation?')) {
    chatStore.clearMessages()
  }
}

// Session 50 DEBUG: Add test research message
function addTestResearchMessage() {
  console.log('[ChatPanel] Adding test research message')

  const testResearch = `**SB 9: California Housing Opportunity and More Efficiency (HOME) Act**

SB 9, signed into law in 2021, is a landmark California housing legislation that allows homeowners to:

1. **Split their lot into two parcels** (lot split)
2. **Build up to two units per parcel** (up to 4 units total on a previously single-family lot)

**Key Provisions:**
- Applies to single-family residential zones
- Minimum lot size: 2,400 sq ft per unit
- Cannot be used in high fire hazard zones or coastal zones (unless certified)
- No owner-occupancy requirement (as of 2024)
- Ministerial approval process (cannot be denied by cities if meets objective standards)

**How Residents Can Use SB 9 at Public Hearings:**

1. **Challenge Illegal Denials**: If your city denied an SB 9 application citing subjective design standards, you can cite state law requiring ministerial approval.

2. **Advocate for Objective Standards**: Push your Planning Commission to adopt clear, objective standards for SB 9 projects rather than vague "neighborhood character" requirements.

3. **Support Similar Projects**: When neighbors oppose SB 9 projects, cite the state's priority for housing production and reduced environmental review.

4. **Request Policy Updates**: Ask your city to streamline SB 9 applications and provide clear guidance on compliance.

**Related Legislation:**
- AB 2011 (2022): Requires rezoning near transit for affordable housing
- SB 35 (2017): Streamlined approval for affordable housing projects
- AB 1763 (2019): ADU law reforms

**Federal Connection:**
SB 9 projects may qualify for CDBG funding for infrastructure improvements or HOME Investment Partnerships for affordable units.`

  chatStore.addMessage({
    role: 'assistant',
    content: testResearch
  })

  console.log('[ChatPanel] Test message added - look for "Use this in draft" button below it')
}

function handleClearContext() {
  // Clear the chat context (returns to general chat mode)
  chatStore.clearContext()
  // Note: We don't close the active artifact in workspace
  // User can still see the artifact while chatting generally
}

// Session 50: Handle "Use this in draft" action from chat messages
function handleUseInDraft(message: any) {
  console.log('[ChatPanel] handleUseInDraft called with message:', message)

  const currentArtifact = workspaceStore.activeArtifact
  console.log('[ChatPanel] Current artifact:', currentArtifact)

  // Check if we have an active event artifact
  if (!currentArtifact || currentArtifact.type !== 'event') {
    console.warn('[ChatPanel] No event artifact active')
    showToast('Please open an event first', 'error')
    return
  }

  const currentEvent = currentArtifact.data
  console.log('[ChatPanel] Current event:', currentEvent)

  if (!currentEvent) {
    console.warn('[ChatPanel] No event data found')
    showToast('Please open an event first', 'error')
    return
  }

  // Extract plain text from message (strip markdown formatting)
  const researchContent = stripMarkdown(message.content)
  console.log('[ChatPanel] Research content stripped:', researchContent.substring(0, 100) + '...')

  // Open/switch to event with drafts tab
  console.log('[ChatPanel] Opening artifact with initialTab: drafts')
  workspaceStore.openArtifact({
    id: currentEvent.id,
    type: 'event',
    title: currentEvent.title,
    data: currentEvent,
    initialTab: 'drafts'
  })

  // Store research content for injection (we'll use a new workspace state)
  console.log('[ChatPanel] Setting draft research content')
  workspaceStore.setDraftResearchContent(researchContent)

  showToast('Research added to draft!', 'success')
}

// Helper: Strip markdown formatting to get plain text
function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // Bold
    .replace(/\*([^*]+)\*/g, '$1')      // Italic
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // Links
    .replace(/^#+\s+/gm, '')            // Headers
    .replace(/```[\s\S]*?```/g, '')     // Code blocks
    .trim()
}

// Helper: Show toast notification
function showToast(message: string, type: 'success' | 'error') {
  const toast = document.createElement('div')
  toast.className = `toast toast-${type}`
  toast.textContent = message
  toast.style.cssText = `
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    padding: 1rem 1.5rem;
    background: ${type === 'success' ? '#859900' : '#dc322f'};
    color: #fdf6e3;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    z-index: 10000;
    font-weight: 600;
    font-size: 0.95rem;
    opacity: 0;
    transform: translateY(1rem);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  `
  document.body.appendChild(toast)

  setTimeout(() => {
    toast.style.opacity = '1'
    toast.style.transform = 'translateY(0)'
  }, 10)

  setTimeout(() => {
    toast.style.opacity = '0'
    toast.style.transform = 'translateY(1rem)'
    setTimeout(() => toast.remove(), 300)
  }, 2000)
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// Watch for new messages and scroll to bottom
watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick()
    scrollToBottom()
  }
)

// Auto-resize textarea as user types
watch(messageInput, () => {
  if (inputField.value) {
    inputField.value.style.height = 'auto'
    inputField.value.style.height = `${inputField.value.scrollHeight}px`
  }
})

// Focus input when chat opens
watch(
  () => chatStore.isVisible,
  async (isVisible) => {
    if (isVisible) {
      await nextTick()
      inputField.value?.focus()
      scrollToBottom()
    }
  }
)
</script>

<style scoped>
/* Chat panel fills its container (no fixed positioning) */
.chat-panel-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: var(--chat-bg);
}

.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background-color: var(--chat-bg);
}

/* Header */
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--chat-border);
  background: linear-gradient(180deg, var(--chat-bg-alt) 0%, var(--chat-bg) 100%);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  backdrop-filter: blur(10px);
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.chat-title {
  font-weight: 600;
  font-size: var(--font-size-md);
  color: var(--chat-text-emphasis);
}

.chat-header-right {
  display: flex;
  gap: var(--spacing-xs);
}

.btn-icon {
  background: none;
  border: none;
  color: var(--chat-text-emphasis);
  cursor: pointer;
  padding: var(--spacing-xs);
  border-radius: var(--border-radius);
  transition: all 0.2s;
  font-size: var(--font-size-md);
}

.btn-icon:hover {
  background-color: var(--chat-border);
  color: var(--primary);
}

/* Session 50 DEBUG: Test button styling */
.btn-test {
  background-color: rgba(133, 153, 0, 0.1) !important;
  border: 1px solid var(--accent-green) !important;
}

.btn-test:hover {
  background-color: var(--accent-green) !important;
  color: white !important;
}

/* Back to Chat Button (prominent when workspace is visible) */
.btn-back-to-chat {
  background: var(--primary);
  color: white;
  border: none;
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-md);
  border-radius: var(--border-radius);
  transition: all 0.2s;
  font-size: var(--font-size-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  font-family: var(--font-family);
}

.btn-back-to-chat:hover {
  background: #1f7ab7;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(38, 139, 210, 0.3);
}

.btn-back-to-chat .icon {
  font-size: 16px;
  line-height: 1;
}

.btn-back-to-chat .label {
  font-size: var(--font-size-sm);
  line-height: 1;
}

/* Context Indicator Bar */
.context-indicator-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: linear-gradient(135deg, rgba(38, 139, 210, 0.1), rgba(133, 153, 0, 0.1));
  border-bottom: 1px solid var(--primary);
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.context-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.context-icon {
  font-size: 18px;
  line-height: 1;
}

.context-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--chat-text-emphasis);
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.btn-clear-context {
  background: transparent;
  border: 1px solid var(--chat-border);
  color: var(--chat-text-emphasis);
  cursor: pointer;
  padding: var(--spacing-xs) var(--spacing-sm);
  font-size: var(--font-size-sm);
  border-radius: var(--border-radius);
  transition: all 0.2s;
  font-family: var(--font-family);
}

.btn-clear-context:hover {
  background: var(--chat-border);
  color: var(--primary);
  border-color: var(--primary);
}

/* Messages Container */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-md);
  background-color: var(--chat-bg);
  scroll-behavior: smooth;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--chat-text-emphasis);
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-md);
  opacity: 0.5;
}

.empty-text {
  font-size: var(--font-size-md);
  margin-bottom: var(--spacing-md);
  max-width: 400px;
}

.context-hint {
  font-size: var(--font-size-sm);
  color: var(--primary);
  padding: var(--spacing-sm);
  background-color: var(--chat-bg-alt);
  border-radius: var(--border-radius);
  border: 1px solid var(--primary);
}

.messages-list {
  display: flex;
  flex-direction: column;
}

/* Loading Indicator */
.loading-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  color: var(--chat-text-emphasis);
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background-color: var(--primary);
  border-radius: 50%;
  animation: pulse 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes pulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.loading-text {
  font-size: var(--font-size-sm);
}

/* Error Message */
.error-message {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background-color: var(--chat-bg-alt);
  border: 1px solid var(--accent-red);
  border-radius: var(--border-radius);
  margin: var(--spacing-md);
  color: var(--accent-red);
}

.error-icon {
  font-size: var(--font-size-lg);
}

.error-text {
  font-size: var(--font-size-sm);
}

/* Input Container */
.input-container {
  display: flex;
  gap: 8px;
  padding: 16px 24px 24px 24px;
  background: var(--chat-bg);
  align-items: flex-end;
}


.message-input {
  width: 100%;
  border: 1px solid rgba(0, 0, 0, 0.15);
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.5;
  resize: none;
  background: white; /* White background for text input */
  color: var(--text-primary);
  font-family: var(--font-family);
  min-height: 48px;
  max-height: 200px;
  transition: all 0.15s ease;
}

.message-input:focus {
  outline: none;
  border-color: var(--primary);
  background: white; /* White background for text input */
  box-shadow: 0 0 0 1px var(--primary);
}

.message-input::placeholder {
  color: var(--text-secondary);
}

.btn-send {
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0;
  cursor: pointer;
  font-size: 18px;
  font-weight: 500;
  transition: all 0.15s ease;
  min-width: 48px;
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.btn-send:hover:not(:disabled) {
  background: var(--primary);
  opacity: 0.9;
}

.btn-send:active:not(:disabled) {
  opacity: 0.8;
}

.btn-send:disabled {
  background: rgba(0, 0, 0, 0.1);
  color: rgba(0, 0, 0, 0.3);
  cursor: not-allowed;
}

.btn-send .icon {
  display: inline-block;
  line-height: 1;
}

/* Scrollbar Styling */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: var(--chat-bg);
}

.messages-container::-webkit-scrollbar-thumb {
  background: var(--chat-border);
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: var(--chat-text);
}

/* Welcome Screen */
.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 700px;
  margin: 0 auto;
  padding: 0 24px;
}

.welcome-title {
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
  text-align: center;
  line-height: 1.2;
  letter-spacing: -0.01em;
}

.welcome-subtitle {
  font-size: 15px;
  color: var(--text-secondary);
  margin-bottom: 24px;
  text-align: center;
  font-weight: 400;
  line-height: 1.5;
}

/* Welcome Input Wrapper */
.welcome-input-wrapper {
  width: 100%;
  max-width: 100%; /* Use full width of welcome screen */
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: flex-end;
}

.welcome-message-input {
  flex: 1;
  border: 1px solid rgba(0, 0, 0, 0.15);
  border-radius: 12px;
  padding: 14px 16px;
  font-size: 15px;
  line-height: 1.5;
  resize: none;
  background: white; /* White background for text input */
  color: var(--text-primary);
  font-family: var(--font-family);
  min-height: 52px;
  max-height: 200px;
  transition: all 0.15s ease;
}

.welcome-message-input:focus {
  outline: none;
  border-color: var(--primary);
  background: white; /* White background for text input */
  box-shadow: 0 0 0 1px var(--primary);
}

.welcome-message-input::placeholder {
  color: var(--text-secondary);
}

.welcome-btn-send {
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 10px;
  padding: 0;
  cursor: pointer;
  font-size: 20px;
  font-weight: 500;
  transition: all 0.15s ease;
  min-width: 52px;
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.welcome-btn-send:hover:not(:disabled) {
  background: var(--primary);
  opacity: 0.9;
}

.welcome-btn-send:active:not(:disabled) {
  opacity: 0.8;
}

.welcome-btn-send:disabled {
  background: rgba(0, 0, 0, 0.1);
  color: rgba(0, 0, 0, 0.3);
  cursor: not-allowed;
}

/* Quick Action Cards */
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
  max-width: 100%; /* Match input width for visual consistency */
  justify-content: center;
}

.quick-action-card {
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 16px;
  padding: 8px 14px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: center;
  font-family: var(--font-family);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.quick-action-card:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--primary);
}

.quick-action-card:hover .action-icon {
  opacity: 1;
}

.action-icon {
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.8;
}

.action-text {
  line-height: 1.4;
  font-weight: 500;
  white-space: nowrap;
}

/* Example Queries */
.example-queries {
  text-align: center;
  color: var(--text-secondary);
  width: 100%;
}

.example-label {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--text-secondary);
}

.example-list {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
}

.example-list li {
  opacity: 0.7;
  font-style: italic;
  transition: opacity 0.2s ease;
  color: var(--text-secondary);
}

.example-list li:hover {
  opacity: 1;
  color: var(--primary);
}

/* Smooth transitions */
.chat-panel-container {
  transition: opacity 0.3s ease;
}
</style>

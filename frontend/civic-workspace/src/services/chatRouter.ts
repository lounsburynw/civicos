/**
 * Chat Router Service (Session 27 - Chat-first navigation)
 * Session 55: Enhanced with multi-artifact context awareness
 * Session 56: Added automatic mode detection
 *
 * Routes user chat messages to appropriate functions via backend OpenAI function calling.
 * Enables natural language navigation: "show housing meetings" → search_events() → UI update
 * Now includes context from open artifacts for multi-document analysis.
 */

import type { ChatMode } from '@/config/chatModes'

export interface ChatAction {
  action: 'search_events' | 'file_complaint' | 'view_legislative_context' |
          'draft_comment' | 'view_my_complaints' | 'explain_event' | 'respond'
  parameters?: Record<string, any>
  message?: string
  reasoning?: string
  conversation_id: string
  mode?: string  // Session 56: Detected mode (may differ from input)
  mode_changed?: boolean  // Session 56: True if mode switched
  mode_reason?: string  // Session 56: Why this mode was chosen
  // Session 58: Multi-operation support (OR queries)
  multi_operation?: boolean  // True if this is a multi-operation query
  operation_count?: number  // Total number of operations
  all_operations?: ChatAction[]  // Array of all operation results
  // Session 84: Model routing metadata
  provider_used?: string  // LLM provider used (e.g., 'openai', 'openrouter', 'anthropic')
  model_used?: string  // Specific model used (e.g., 'gpt-4o-mini', 'gemini-2.0-flash-exp')
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  error?: string
}

export interface ChatContext {
  current_artifact?: string
  current_jurisdiction?: string
  current_event?: string
  user_city?: string
  user_jurisdiction_id?: string
}

/**
 * Session 55: Options for chat routing with context awareness
 * Session 88: Added model_override for manual model selection
 */
export interface ChatRouterOptions {
  conversationId?: string
  context?: ChatContext
  mode?: ChatMode
  serializedContext?: string  // LLM-friendly context from serializeContextForLLM()
  modelOverride?: string  // Session 88: Manual model selection (e.g., 'gpt-4o', 'claude-sonnet-4')
}

/**
 * Route a user chat message to the appropriate action via backend OpenAI function calling.
 *
 * @param message - User's chat message (e.g., "Show me housing meetings in Berkeley")
 * @param options - Optional configuration (conversationId, context, mode, serializedContext)
 * @returns Promise resolving to ChatAction with action type and parameters
 *
 * @example
 * // Session 27 style (still supported)
 * const action = await routeChatMessage("Show housing meetings", { conversationId, context })
 *
 * @example
 * // Session 55 style (with multi-artifact context)
 * const action = await routeChatMessage("Compare these bills", {
 *   conversationId,
 *   mode: 'research',
 *   serializedContext: serializeContextForLLM(activeContext)
 * })
 */
export async function routeChatMessage(
  message: string,
  options: ChatRouterOptions = {}
): Promise<ChatAction> {
  const { conversationId, context, mode = 'navigation', serializedContext, modelOverride } = options
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
  const apiKey = import.meta.env.VITE_CIVIC_WEB_KEY || 'dev_key_local'

  const response = await fetch(`${apiUrl}/api/chat/route`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      context,
      mode,  // Session 55: chat mode for mode-specific behavior
      serialized_context: serializedContext,  // Session 55: LLM-friendly context summary
      model_override: modelOverride  // Session 88: Manual model selection
    })
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }))
    throw new Error(`Chat routing failed: ${errorData.error || response.statusText}`)
  }

  return response.json()
}

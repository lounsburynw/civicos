/**
 * AI integration facade — backward-compatible re-exports.
 *
 * The real implementation lives in ai/manager.ts and ai/prompts.ts.
 * This file exists so existing imports from '../lib/ai.js' keep working.
 */

export { composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from './ai/prompts.js';
export { AIManager } from './ai/manager.js';
export type { AIProvider, AITier, AICompletionResult, AIProviderConfig } from './ai/types.js';

import { AIManager } from './ai/manager.js';

// Singleton for use in SidePanel and other contexts
let _manager: AIManager | null = null;

export function getAIManager(): AIManager {
  if (!_manager) {
    _manager = new AIManager();
  }
  return _manager;
}

/**
 * Check if any AI provider is available and ready.
 * Drop-in replacement for the old isAIAvailable().
 */
export async function isAIAvailable(): Promise<boolean> {
  return getAIManager().isAvailable();
}

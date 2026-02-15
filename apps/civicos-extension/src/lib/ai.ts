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
let _storageListenerAttached = false;
const _changeCallbacks: Array<() => void> = [];

function attachStorageListener(): void {
  if (_storageListenerAttached) return;
  if (typeof chrome === 'undefined' || !chrome.storage?.onChanged) return;

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== 'local') return;
    const aiKeyChanged = Object.keys(changes).some(
      k => k.startsWith('civicos-ai-cred-') || k === 'civicos-ai-preferences'
    );
    if (aiKeyChanged) {
      // Destroy old manager so next getAIManager() call creates a fresh one
      if (_manager) {
        _manager.destroy();
        _manager = null;
      }
      for (const cb of _changeCallbacks) cb();
    }
  });
  _storageListenerAttached = true;
}

export function getAIManager(): AIManager {
  attachStorageListener();
  if (!_manager) {
    _manager = new AIManager();
  }
  return _manager;
}

/**
 * Register a callback invoked when AI config changes in chrome.storage.
 * Returns an unsubscribe function.
 */
export function onAIConfigChanged(callback: () => void): () => void {
  _changeCallbacks.push(callback);
  return () => {
    const idx = _changeCallbacks.indexOf(callback);
    if (idx >= 0) _changeCallbacks.splice(idx, 1);
  };
}

/**
 * Check if any AI provider is available and ready.
 * Drop-in replacement for the old isAIAvailable().
 */
export async function isAIAvailable(): Promise<boolean> {
  return getAIManager().isAvailable();
}

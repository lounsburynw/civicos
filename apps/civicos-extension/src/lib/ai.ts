/**
 * AI integration facade — extension singleton with Chrome storage listener.
 *
 * Portable AI types, manager, prompts, and providers live in @civicos/client.
 * This file provides the Chrome-specific singleton and config-change listener.
 */

// Re-export portable API from SDK
export { composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from '@civicos/client';
export { AIManager } from '@civicos/client';
export type { AIProvider, AITier, AICompletionResult, AIProviderConfig } from '@civicos/client';

import { AIManager, ClaudeProvider, OpenAIProvider, GeminiProvider, OllamaProvider, createMcpToolExecutor } from '@civicos/client';
import { ChromeAICredentialStorage } from './adapters/chrome-ai-storage.js';
import { CivicosProxyProvider } from './ai/providers/civicos-proxy.js';
import { ChromeNanoProvider } from './ai/providers/chrome-nano.js';
import { registry } from './client.js';

/**
 * Create an AIManager with Chrome storage and all extension-available providers.
 */
export function createExtensionAIManager(): AIManager {
  const storage = new ChromeAICredentialStorage();
  const manager = new AIManager(storage);

  // Register providers in priority order
  manager.register(new CivicosProxyProvider());
  manager.register(new ClaudeProvider(storage));
  manager.register(new OpenAIProvider(storage));
  manager.register(new GeminiProvider(storage));

  // Ollama with local tool executor for private chat
  const ollama = new OllamaProvider(storage);
  ollama.setToolExecutor(createMcpToolExecutor(() => registry.getMcpUrl()));
  manager.register(ollama);

  manager.register(new ChromeNanoProvider());

  return manager;
}

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
    _manager = createExtensionAIManager();
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
 */
export async function isAIAvailable(): Promise<boolean> {
  return getAIManager().isAvailable();
}

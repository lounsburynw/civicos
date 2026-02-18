/**
 * AI Manager — provider registration, routing, and auto-detection.
 *
 * Platform-agnostic: the host app provides storage and registers providers.
 *
 * Priority: stored preference -> first ready provider in registration order
 */

import type { AIProvider, AICompletionResult } from './types.js';
import type { AICredentialStorage } from './storage.js';

export class AIManager {
  private providers = new Map<string, AIProvider>();
  private activeProvider: AIProvider | null = null;
  private storage: AICredentialStorage;
  private initialized = false;

  constructor(storage: AICredentialStorage) {
    this.storage = storage;
  }

  register(provider: AIProvider): void {
    this.providers.set(provider.id, provider);
  }

  getProvider(id: string): AIProvider | undefined {
    return this.providers.get(id);
  }

  getActiveProvider(): AIProvider | null {
    return this.activeProvider;
  }

  getProviders(): AIProvider[] {
    return Array.from(this.providers.values());
  }

  getStorage(): AICredentialStorage {
    return this.storage;
  }

  /**
   * Initialize: check stored preference, then fall through providers in registration order.
   * Returns true if any provider is ready.
   */
  async initialize(): Promise<boolean> {
    if (this.initialized && this.activeProvider) return true;

    // 1. Check stored user preference
    const prefs = await this.storage.getPreferences();
    if (prefs.activeProviderId) {
      const preferred = this.providers.get(prefs.activeProviderId);
      if (preferred && await preferred.isReady()) {
        this.activeProvider = preferred;
        this.initialized = true;
        return true;
      }
    }

    // 2. Fall through: try each provider in registration order
    for (const provider of this.providers.values()) {
      if (await provider.isReady()) {
        this.activeProvider = provider;
        this.initialized = true;
        return true;
      }
    }

    this.initialized = true;
    return false;
  }

  /**
   * Set the active provider by ID and persist the preference.
   */
  async setActiveProvider(providerId: string): Promise<boolean> {
    const provider = this.providers.get(providerId);
    if (!provider) return false;

    if (await provider.isReady()) {
      this.activeProvider = provider;
      await this.storage.savePreferences({ activeProviderId: providerId });
      return true;
    }
    return false;
  }

  /**
   * Check if any provider is available and ready.
   */
  async isAvailable(): Promise<boolean> {
    if (!this.initialized) await this.initialize();
    return this.activeProvider !== null;
  }

  /**
   * Run a completion against the active provider.
   */
  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    if (!this.initialized) await this.initialize();

    if (!this.activeProvider) {
      return {
        success: false,
        error: 'No AI provider configured. Open extension options to set one up.',
        provider: 'none',
      };
    }

    return this.activeProvider.complete(prompt, systemPrompt);
  }

  /**
   * Get availability/readiness status of all providers.
   */
  async checkStatus(): Promise<Array<{
    id: string;
    name: string;
    tier: string;
    available: boolean;
    ready: boolean;
    active: boolean;
  }>> {
    const results = [];
    for (const provider of this.providers.values()) {
      results.push({
        id: provider.id,
        name: provider.name,
        tier: provider.tier,
        available: await provider.isAvailable(),
        ready: await provider.isReady(),
        active: this.activeProvider?.id === provider.id,
      });
    }
    return results;
  }

  destroy(): void {
    for (const provider of this.providers.values()) {
      provider.destroy();
    }
    this.activeProvider = null;
    this.initialized = false;
  }
}

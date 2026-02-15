/**
 * AI credential storage using chrome.storage APIs.
 *
 * - API keys: chrome.storage.local (persistent)
 * - OAuth tokens: chrome.storage.session (ephemeral, cleared on browser close)
 * - Preferences: chrome.storage.local (persistent)
 */

import type { AIProviderConfig, AIPreferences } from './types.js';

const CRED_PREFIX = 'civicos-ai-cred-';
const OAUTH_PREFIX = 'civicos-ai-oauth-';
const PREFS_KEY = 'civicos-ai-preferences';

export interface AICredentialStorage {
  getConfig(providerId: string): Promise<AIProviderConfig>;
  saveConfig(providerId: string, config: AIProviderConfig): Promise<void>;
  clearConfig(providerId: string): Promise<void>;
  getPreferences(): Promise<AIPreferences>;
  savePreferences(prefs: AIPreferences): Promise<void>;
}

export class ChromeAICredentialStorage implements AICredentialStorage {
  async getConfig(providerId: string): Promise<AIProviderConfig> {
    const config: AIProviderConfig = {};

    // API key from persistent storage
    try {
      const credKey = CRED_PREFIX + providerId;
      const credResult = await chrome.storage.local.get(credKey);
      if (credResult[credKey]) {
        const stored = credResult[credKey] as AIProviderConfig;
        config.apiKey = stored.apiKey;
        config.model = stored.model;
      }
    } catch {
      // Storage unavailable
    }

    // OAuth token from session storage (ephemeral)
    try {
      const oauthKey = OAUTH_PREFIX + providerId;
      const oauthResult = await chrome.storage.session.get(oauthKey);
      if (oauthResult[oauthKey]) {
        config.oauthToken = (oauthResult[oauthKey] as { token: string }).token;
      }
    } catch {
      // Session storage unavailable
    }

    return config;
  }

  async saveConfig(providerId: string, config: AIProviderConfig): Promise<void> {
    // Save API key + model to persistent storage
    if (config.apiKey !== undefined || config.model !== undefined) {
      const credKey = CRED_PREFIX + providerId;
      const existing = await this.getConfig(providerId);
      await chrome.storage.local.set({
        [credKey]: {
          apiKey: config.apiKey ?? existing.apiKey,
          model: config.model ?? existing.model,
        },
      });
    }

    // Save OAuth token to session storage
    if (config.oauthToken !== undefined) {
      const oauthKey = OAUTH_PREFIX + providerId;
      await chrome.storage.session.set({
        [oauthKey]: { token: config.oauthToken },
      });
    }
  }

  async clearConfig(providerId: string): Promise<void> {
    try {
      await chrome.storage.local.remove(CRED_PREFIX + providerId);
    } catch { /* ignore */ }
    try {
      await chrome.storage.session.remove(OAUTH_PREFIX + providerId);
    } catch { /* ignore */ }
  }

  async getPreferences(): Promise<AIPreferences> {
    try {
      const result = await chrome.storage.local.get(PREFS_KEY);
      return (result[PREFS_KEY] as AIPreferences) ?? {};
    } catch {
      return {};
    }
  }

  async savePreferences(prefs: AIPreferences): Promise<void> {
    await chrome.storage.local.set({ [PREFS_KEY]: prefs });
  }
}

export class MemoryAICredentialStorage implements AICredentialStorage {
  private configs = new Map<string, AIProviderConfig>();
  private prefs: AIPreferences = {};

  async getConfig(providerId: string): Promise<AIProviderConfig> {
    return this.configs.get(providerId) ?? {};
  }

  async saveConfig(providerId: string, config: AIProviderConfig): Promise<void> {
    const existing = this.configs.get(providerId) ?? {};
    this.configs.set(providerId, { ...existing, ...config });
  }

  async clearConfig(providerId: string): Promise<void> {
    this.configs.delete(providerId);
  }

  async getPreferences(): Promise<AIPreferences> {
    return this.prefs;
  }

  async savePreferences(prefs: AIPreferences): Promise<void> {
    this.prefs = prefs;
  }
}

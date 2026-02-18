/**
 * AI credential storage interface and portable implementations.
 *
 * Platform-specific implementations (Chrome, localStorage, etc.)
 * live in their respective host apps.
 */

import type { AIProviderConfig, AIPreferences } from './types.js';

export interface AICredentialStorage {
  getConfig(providerId: string): Promise<AIProviderConfig>;
  saveConfig(providerId: string, config: AIProviderConfig): Promise<void>;
  clearConfig(providerId: string): Promise<void>;
  getPreferences(): Promise<AIPreferences>;
  savePreferences(prefs: AIPreferences): Promise<void>;
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

/**
 * OpenAI API provider (cloud-pro tier).
 *
 * API key only. Uses the chat completions endpoint.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult } from '../types.js';
import type { AICredentialStorage } from '../storage.js';

const OPENAI_ENDPOINT = 'https://api.openai.com/v1/chat/completions';
const DEFAULT_MODEL = 'gpt-4o-mini';
const TIMEOUT_MS = 15_000;

export class OpenAIProvider implements AIProvider {
  readonly tier: AITier = 'cloud-pro';
  readonly name = 'OpenAI';
  readonly id = 'openai';
  readonly description = 'OpenAI API. Requires an API key from platform.openai.com.';

  private apiKey: string | null = null;
  private model = DEFAULT_MODEL;

  constructor(private storage: AICredentialStorage) {}

  async isAvailable(): Promise<boolean> {
    return true;
  }

  async isReady(): Promise<boolean> {
    await this.loadConfig();
    return !!this.apiKey;
  }

  private async loadConfig(): Promise<void> {
    const config = await this.storage.getConfig(this.id);
    this.apiKey = config.apiKey ?? null;
    if (config.model) this.model = config.model;
  }

  async configure(config: AIProviderConfig): Promise<void> {
    if (config.apiKey !== undefined) this.apiKey = config.apiKey || null;
    if (config.model) this.model = config.model;
    await this.storage.saveConfig(this.id, config);
  }

  async clearConfig(): Promise<void> {
    this.apiKey = null;
    this.model = DEFAULT_MODEL;
    await this.storage.clearConfig(this.id);
  }

  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    await this.loadConfig();

    if (!this.apiKey) {
      return { success: false, error: 'No API key configured', provider: this.id };
    }

    const messages: Array<{ role: string; content: string }> = [];
    if (systemPrompt) {
      messages.push({ role: 'system', content: systemPrompt });
    }
    messages.push({ role: 'user', content: prompt });

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(OPENAI_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`,
        },
        body: JSON.stringify({ model: this.model, messages }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        const errBody = await resp.text();
        return { success: false, error: `OpenAI API ${resp.status}: ${errBody.slice(0, 200)}`, provider: this.id };
      }

      const data = await resp.json() as {
        choices?: Array<{ message?: { content?: string } }>;
      };
      const text = data.choices?.[0]?.message?.content;
      if (!text) {
        return { success: false, error: 'OpenAI returned empty response', provider: this.id };
      }

      return { success: true, text, provider: this.id };
    } catch (err) {
      const msg = err instanceof Error
        ? (err.name === 'AbortError' ? 'Request timed out' : err.message)
        : 'OpenAI API request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

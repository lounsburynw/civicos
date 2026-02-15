/**
 * Anthropic Claude API provider (cloud-pro tier).
 *
 * API key only (no OAuth). Requires the browser-access header for direct fetch.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult } from '../types.js';
import type { AICredentialStorage } from '../storage.js';

const CLAUDE_ENDPOINT = 'https://api.anthropic.com/v1/messages';
const DEFAULT_MODEL = 'claude-sonnet-4-5-20250929';
const TIMEOUT_MS = 15_000;

export class ClaudeProvider implements AIProvider {
  readonly tier: AITier = 'cloud-pro';
  readonly name = 'Claude';
  readonly id = 'claude';
  readonly description = 'Anthropic Claude API. Requires an API key from console.anthropic.com.';

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

    const body: Record<string, unknown> = {
      model: this.model,
      max_tokens: 1024,
      messages: [{ role: 'user', content: prompt }],
    };
    if (systemPrompt) {
      body.system = systemPrompt;
    }

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(CLAUDE_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': this.apiKey,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        const errBody = await resp.text();
        return { success: false, error: `Claude API ${resp.status}: ${errBody.slice(0, 200)}`, provider: this.id };
      }

      const data = await resp.json() as {
        content?: Array<{ type: string; text?: string }>;
      };
      const text = data.content?.find(b => b.type === 'text')?.text;
      if (!text) {
        return { success: false, error: 'Claude returned empty response', provider: this.id };
      }

      return { success: true, text, provider: this.id };
    } catch (err) {
      const msg = err instanceof Error
        ? (err.name === 'AbortError' ? 'Request timed out' : err.message)
        : 'Claude API request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

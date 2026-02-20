/**
 * Ollama local model provider (device tier).
 *
 * Connects to a locally running Ollama instance (default: localhost:11434).
 * Fully on-device — no queries leave the machine.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult } from '../types.js';
import type { AICredentialStorage } from '../storage.js';

const DEFAULT_BASE_URL = 'http://localhost:11434';
const DEFAULT_MODEL = 'llama3.1:8b';
const TIMEOUT_MS = 30_000;

export class OllamaProvider implements AIProvider {
  readonly tier: AITier = 'device';
  readonly name = 'Ollama (Local)';
  readonly id = 'ollama';
  readonly description = 'Local AI via Ollama. Fully private — no queries leave your machine.';

  private baseUrl = DEFAULT_BASE_URL;
  private model = DEFAULT_MODEL;

  constructor(private storage: AICredentialStorage) {}

  async isAvailable(): Promise<boolean> {
    try {
      await this.loadConfig();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      const resp = await fetch(`${this.baseUrl}/api/tags`, { signal: controller.signal });
      clearTimeout(timeout);
      return resp.ok;
    } catch {
      return false;
    }
  }

  async isReady(): Promise<boolean> {
    try {
      await this.loadConfig();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      const resp = await fetch(`${this.baseUrl}/api/tags`, { signal: controller.signal });
      clearTimeout(timeout);
      if (!resp.ok) return false;
      const data = await resp.json() as { models?: Array<{ name: string }> };
      return data.models?.some(m => m.name === this.model || m.name.startsWith(this.model.split(':')[0])) ?? false;
    } catch {
      return false;
    }
  }

  private async loadConfig(): Promise<void> {
    const config = await this.storage.getConfig(this.id);
    // Store base URL in apiKey field (repurposed — Ollama has no API key)
    if (config.apiKey) this.baseUrl = config.apiKey.replace(/\/$/, '');
    if (config.model) this.model = config.model;
  }

  async configure(config: AIProviderConfig): Promise<void> {
    if (config.apiKey !== undefined) this.baseUrl = (config.apiKey || DEFAULT_BASE_URL).replace(/\/$/, '');
    if (config.model) this.model = config.model;
    await this.storage.saveConfig(this.id, config);
  }

  async clearConfig(): Promise<void> {
    this.baseUrl = DEFAULT_BASE_URL;
    this.model = DEFAULT_MODEL;
    await this.storage.clearConfig(this.id);
  }

  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    await this.loadConfig();

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(`${this.baseUrl}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          prompt,
          system: systemPrompt || undefined,
          stream: false,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        const errBody = await resp.text();
        return { success: false, error: `Ollama ${resp.status}: ${errBody.slice(0, 200)}`, provider: this.id };
      }

      const data = await resp.json() as { response?: string };
      if (!data.response) {
        return { success: false, error: 'Ollama returned empty response', provider: this.id };
      }

      return { success: true, text: data.response, provider: this.id };
    } catch (err) {
      const msg = err instanceof Error
        ? (err.name === 'AbortError' ? 'Request timed out — model may still be loading' : err.message)
        : 'Ollama request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

/**
 * Google Gemini API provider (cloud-free tier).
 *
 * Two auth paths:
 * - API key: free from aistudio.google.com
 * - OAuth: token injected via AICredentialStorage
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult } from '../types.js';
import type { AICredentialStorage } from '../storage.js';

const GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models';
const DEFAULT_MODEL = 'gemini-2.0-flash';
const TIMEOUT_MS = 15_000;

export class GeminiProvider implements AIProvider {
  readonly tier: AITier = 'cloud-free';
  readonly name = 'Google Gemini';
  readonly id = 'gemini';
  readonly description = 'Google Gemini API. Free tier via API key or Google sign-in.';

  private apiKey: string | null = null;
  private oauthToken: string | null = null;
  private model = DEFAULT_MODEL;

  constructor(private storage: AICredentialStorage) {}

  async isAvailable(): Promise<boolean> {
    return true;
  }

  async isReady(): Promise<boolean> {
    await this.loadConfig();
    return !!(this.apiKey || this.oauthToken);
  }

  private async loadConfig(): Promise<void> {
    const config = await this.storage.getConfig(this.id);
    this.apiKey = config.apiKey ?? null;
    this.oauthToken = config.oauthToken ?? null;
    if (config.model) this.model = config.model;
  }

  async configure(config: AIProviderConfig): Promise<void> {
    if (config.apiKey !== undefined) this.apiKey = config.apiKey || null;
    if (config.oauthToken !== undefined) this.oauthToken = config.oauthToken || null;
    if (config.model) this.model = config.model;
    await this.storage.saveConfig(this.id, config);
  }

  async clearConfig(): Promise<void> {
    this.apiKey = null;
    this.oauthToken = null;
    this.model = DEFAULT_MODEL;
    await this.storage.clearConfig(this.id);
  }

  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    await this.loadConfig();

    if (!this.apiKey && !this.oauthToken) {
      return { success: false, error: 'No API key or OAuth token configured', provider: this.id };
    }

    const url = this.apiKey
      ? `${GEMINI_ENDPOINT}/${this.model}:generateContent?key=${this.apiKey}`
      : `${GEMINI_ENDPOINT}/${this.model}:generateContent`;

    const contents: Array<{ role: string; parts: Array<{ text: string }> }> = [];
    if (systemPrompt) {
      contents.push({ role: 'user', parts: [{ text: systemPrompt }] });
      contents.push({ role: 'model', parts: [{ text: 'Understood. I will follow these instructions.' }] });
    }
    contents.push({ role: 'user', parts: [{ text: prompt }] });

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.oauthToken) {
      headers['Authorization'] = `Bearer ${this.oauthToken}`;
    }

    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ contents }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (!resp.ok) {
        const body = await resp.text();
        return { success: false, error: `Gemini API ${resp.status}: ${body.slice(0, 200)}`, provider: this.id };
      }

      const data = await resp.json() as {
        candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
      };
      const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!text) {
        return { success: false, error: 'Gemini returned empty response', provider: this.id };
      }

      return { success: true, text, provider: this.id };
    } catch (err) {
      const msg = err instanceof Error
        ? (err.name === 'AbortError' ? 'Request timed out' : err.message)
        : 'Gemini API request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

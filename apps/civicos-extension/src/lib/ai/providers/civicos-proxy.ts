/**
 * CivicOS Proxy AI provider — zero-config AI drafting.
 *
 * Uses the CivicOS API server as a proxy to Anthropic. Authenticates
 * via Nostr-signed requests (reusing the user's existing identity).
 * No API key needed — works out of the box.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult, AIChatResult } from '@civicos/client';
import { registry } from '../../client.js';

const TIMEOUT_MS = 20_000;

export class CivicosProxyProvider implements AIProvider {
  readonly tier: AITier = 'cloud-pro';
  readonly name = 'CivicOS (Built-in)';
  readonly id = 'civicos';
  readonly description = 'Built-in AI drafting — no API key needed. Uses your CivicOS identity.';

  async isAvailable(): Promise<boolean> {
    return true;
  }

  async isReady(): Promise<boolean> {
    // Ready if user has an identity and it's unlocked (can sign)
    try {
      const response = await chrome.runtime.sendMessage({ type: 'GET_IDENTITY' });
      return response?.success && response.data?.isUnlocked === true;
    } catch {
      return false;
    }
  }

  async configure(_config: AIProviderConfig): Promise<void> {
    // No configuration needed — identity-based auth
  }

  async clearConfig(): Promise<void> {
    // Nothing to clear
  }

  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    // 1. Get signature from service worker
    let sigData: { public_key: string; signature: string; created_at: number };
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SIGN_MESSAGE',
        message: 'ai_draft',
      });
      if (!response?.success) {
        return {
          success: false,
          error: response?.error || 'Failed to sign request — is your identity unlocked?',
          provider: this.id,
        };
      }
      sigData = response.data;
    } catch (err) {
      return {
        success: false,
        error: 'Could not sign request — is your identity unlocked?',
        provider: this.id,
      };
    }

    // 2. POST to CivicOS AI proxy
    try {
      const baseUrl = await registry.getMcpUrl();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);

      const resp = await fetch(`${baseUrl}/api/ai/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          system_prompt: systemPrompt || null,
          public_key: sigData.public_key,
          signature: sigData.signature,
          created_at: sigData.created_at,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (resp.status === 429) {
        const detail = await resp.json().catch(() => ({}));
        return {
          success: false,
          error: detail?.detail || 'Rate limit exceeded — try again later',
          provider: this.id,
        };
      }

      if (resp.status === 401) {
        return {
          success: false,
          error: 'Authentication failed — try unlocking your identity again',
          provider: this.id,
        };
      }

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        return {
          success: false,
          error: detail?.detail || `Server error (${resp.status})`,
          provider: this.id,
        };
      }

      const data: { success: boolean; text?: string; error?: string } = await resp.json();

      if (!data.success) {
        return { success: false, error: data.error || 'AI returned an error', provider: this.id };
      }

      return { success: true, text: data.text, provider: this.id };
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.name === 'AbortError'
            ? 'Request timed out'
            : err.message
          : 'Request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  async chat(question: string, jurisdiction?: string): Promise<AIChatResult> {
    // 1. Get signature from service worker
    let sigData: { public_key: string; signature: string; created_at: number };
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SIGN_MESSAGE',
        message: 'ai_draft',
      });
      if (!response?.success) {
        return {
          success: false,
          error: response?.error || 'Failed to sign request — is your identity unlocked?',
          provider: this.id,
        };
      }
      sigData = response.data;
    } catch {
      return {
        success: false,
        error: 'Could not sign request — is your identity unlocked?',
        provider: this.id,
      };
    }

    // 2. POST to CivicOS AI chat endpoint
    try {
      const baseUrl = await registry.getMcpUrl();
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30_000);

      const resp = await fetch(`${baseUrl}/api/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          jurisdiction: jurisdiction || null,
          public_key: sigData.public_key,
          signature: sigData.signature,
          created_at: sigData.created_at,
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (resp.status === 429) {
        const detail = await resp.json().catch(() => ({}));
        return {
          success: false,
          error: detail?.detail || 'Rate limit exceeded — try again later',
          provider: this.id,
        };
      }

      if (resp.status === 401) {
        return {
          success: false,
          error: 'Authentication failed — try unlocking your identity again',
          provider: this.id,
        };
      }

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        return {
          success: false,
          error: detail?.detail || `Server error (${resp.status})`,
          provider: this.id,
        };
      }

      const data: { success: boolean; text?: string; tool_used?: string; error?: string } = await resp.json();

      if (!data.success) {
        return { success: false, error: data.error || 'AI returned an error', provider: this.id };
      }

      return {
        success: true,
        text: data.text,
        toolUsed: data.tool_used,
        provider: this.id,
      };
    } catch (err) {
      const msg =
        err instanceof Error
          ? err.name === 'AbortError'
            ? 'Request timed out — tool search takes up to 30s'
            : err.message
          : 'Request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

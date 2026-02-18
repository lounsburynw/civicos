/**
 * Chrome Built-in AI (Gemini Nano) provider.
 *
 * Uses the Prompt API available in Chrome 138+.
 * Zero config, on-device, free. Default when available.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult } from '@civicos/client';

// Chrome's Prompt API types (not yet in standard type packages)
interface AILanguageModelCapabilities {
  available: 'readily' | 'after-download' | 'no';
}

interface AILanguageModelCreateOptions {
  systemPrompt?: string;
}

interface AILanguageModel {
  prompt(input: string): Promise<string>;
  destroy(): void;
}

interface AILanguageModelFactory {
  capabilities(): Promise<AILanguageModelCapabilities>;
  create(options?: AILanguageModelCreateOptions): Promise<AILanguageModel>;
}

interface AI {
  languageModel: AILanguageModelFactory;
}

declare global {
  interface WindowOrWorkerGlobalScope {
    ai?: AI;
  }
}

export class ChromeNanoProvider implements AIProvider {
  readonly tier: AITier = 'device';
  readonly name = 'Chrome Built-in AI';
  readonly id = 'chrome-nano';
  readonly description = 'On-device AI via Chrome 138+ (Gemini Nano). No API key needed.';

  private session: AILanguageModel | null = null;
  private lastSystemPrompt: string | undefined;

  async isAvailable(): Promise<boolean> {
    try {
      if (!self.ai?.languageModel) return false;
      const caps = await self.ai.languageModel.capabilities();
      return caps.available === 'readily' || caps.available === 'after-download';
    } catch {
      return false;
    }
  }

  async isReady(): Promise<boolean> {
    return this.isAvailable();
  }

  async configure(_config: AIProviderConfig): Promise<void> {
    // No configuration needed for device provider
  }

  async clearConfig(): Promise<void> {
    // Nothing to clear
  }

  async complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult> {
    try {
      // Recreate session if system prompt changed
      if (this.session && systemPrompt !== this.lastSystemPrompt) {
        this.session.destroy();
        this.session = null;
      }

      if (!this.session) {
        this.session = await self.ai!.languageModel.create({
          systemPrompt,
        });
        this.lastSystemPrompt = systemPrompt;
      }

      const text = await this.session.prompt(prompt);
      return { success: true, text, provider: this.id };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : 'Chrome AI failed',
        provider: this.id,
      };
    }
  }

  destroy(): void {
    if (this.session) {
      this.session.destroy();
      this.session = null;
    }
  }
}

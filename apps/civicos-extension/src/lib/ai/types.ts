/**
 * AI Provider types for the tiered AI stack.
 *
 * Mirrors the SigningProvider pattern from identity providers.
 * Tiers: device (Chrome Nano) -> cloud-free (Gemini) -> cloud-pro (Claude/OpenAI)
 */

export type AITier = 'device' | 'cloud-free' | 'cloud-pro';

export interface AIProviderConfig {
  apiKey?: string;
  oauthToken?: string;
  model?: string;
}

export interface AICompletionResult {
  success: boolean;
  text?: string;
  error?: string;
  provider: string;
}

export interface AIProvider {
  readonly tier: AITier;
  readonly name: string;
  readonly id: string;
  readonly description: string;

  /** Can this provider work in this environment? */
  isAvailable(): Promise<boolean>;

  /** Is it configured and ready to use? */
  isReady(): Promise<boolean>;

  /** Apply configuration (API key, OAuth token, etc.) */
  configure(config: AIProviderConfig): Promise<void>;

  /** Remove stored configuration */
  clearConfig(): Promise<void>;

  /** Run a completion */
  complete(prompt: string, systemPrompt?: string): Promise<AICompletionResult>;

  /** Clean up resources */
  destroy(): void;
}

export interface AIPreferences {
  activeProviderId?: string;
}

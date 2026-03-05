/**
 * AI Provider types for the tiered AI stack.
 *
 * Mirrors the SigningProvider pattern from identity providers.
 */

export type AITier = 'cloud-pro' | 'cloud-free' | 'device';

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

export interface ChatUserContext {
  neighborhood?: string;
  district?: string;
  interests?: string[];
  stakes?: string[];
  expertise?: string;
  yearsInArea?: number;
}

export interface AIChatResult {
  success: boolean;
  text?: string;
  toolUsed?: string;
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

  /** Run a tool-backed civic search (optional — only proxy providers support this) */
  chat?(question: string, jurisdiction?: string, userContext?: ChatUserContext): Promise<AIChatResult>;

  /** Clean up resources */
  destroy(): void;
}

export interface AIPreferences {
  activeProviderId?: string;
  /** When true (default), chat queries use Ollama locally for privacy. When false, use cloud provider. */
  useOllamaForChat?: boolean;
}

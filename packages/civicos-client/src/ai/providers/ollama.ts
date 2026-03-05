/**
 * Ollama local model provider (device tier).
 *
 * Connects to a locally running Ollama instance (default: localhost:11434).
 * Fully on-device — no queries leave the machine.
 */

import type { AIProvider, AITier, AIProviderConfig, AICompletionResult, AIChatResult, ChatUserContext } from '../types.js';
import type { AICredentialStorage } from '../storage.js';
import type { ChatToolExecutor } from '../tools/chat-tools.js';
import { CHAT_TOOL_DEFS } from '../tools/chat-tools.js';

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
  private toolExecutor?: ChatToolExecutor;

  constructor(private storage: AICredentialStorage) {}

  /** Inject a tool executor to enable local chat with tool-backed search. */
  setToolExecutor(executor: ChatToolExecutor): void {
    this.toolExecutor = executor;
  }

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

  async chat(question: string, jurisdiction?: string, userContext?: ChatUserContext): Promise<AIChatResult> {
    if (!this.toolExecutor) {
      return { success: false, error: 'No tool executor configured for local chat', provider: this.id };
    }

    await this.loadConfig();

    let systemPrompt =
      `You are a civic assistant for ${jurisdiction || 'the local community'}. ` +
      'Answer the user\'s question using the available tools to search real civic data. ' +
      'Be concise and factual. Cite specific dates, amounts, or meeting names when available. ' +
      'If no tool is relevant, answer based on your general knowledge and note the limitation.';

    if (userContext?.journalNotes) {
      systemPrompt += ` The user's civic journal: ${userContext.journalNotes}`;
    }

    try {
      // 1. First call: let Ollama select a tool
      const controller1 = new AbortController();
      const timeout1 = setTimeout(() => controller1.abort(), TIMEOUT_MS);

      const resp1 = await fetch(`${this.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: question },
          ],
          tools: CHAT_TOOL_DEFS,
          stream: false,
        }),
        signal: controller1.signal,
      });
      clearTimeout(timeout1);

      if (!resp1.ok) {
        const errBody = await resp1.text();
        return { success: false, error: `Ollama ${resp1.status}: ${errBody.slice(0, 200)}`, provider: this.id };
      }

      const data1 = await resp1.json() as {
        message?: {
          role: string;
          content: string;
          tool_calls?: Array<{ function: { name: string; arguments: Record<string, unknown> } }>;
        };
      };

      const msg1 = data1.message;
      if (!msg1) {
        return { success: false, error: 'Ollama returned empty message', provider: this.id };
      }

      // If no tool call, return the direct answer
      if (!msg1.tool_calls || msg1.tool_calls.length === 0) {
        return {
          success: true,
          text: msg1.content || 'No answer available.',
          provider: this.id,
        };
      }

      // 2. Execute the selected tool via MCP REST API (anonymous)
      const toolCall = msg1.tool_calls[0];
      const toolName = toolCall.function.name;
      const toolArgs = toolCall.function.arguments;

      const toolResult = await this.toolExecutor(toolName, toolArgs);

      // 3. Second call: feed tool result back to Ollama for synthesis
      const controller2 = new AbortController();
      const timeout2 = setTimeout(() => controller2.abort(), TIMEOUT_MS);

      const resp2 = await fetch(`${this.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: this.model,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: question },
            { role: 'assistant', content: '', tool_calls: msg1.tool_calls },
            { role: 'tool', content: toolResult },
          ],
          stream: false,
        }),
        signal: controller2.signal,
      });
      clearTimeout(timeout2);

      if (!resp2.ok) {
        const errBody = await resp2.text();
        return { success: false, error: `Ollama synthesis ${resp2.status}: ${errBody.slice(0, 200)}`, provider: this.id };
      }

      const data2 = await resp2.json() as { message?: { content: string } };
      const finalText = data2.message?.content;

      if (!finalText) {
        return { success: false, error: 'Ollama returned empty synthesis', provider: this.id };
      }

      return {
        success: true,
        text: finalText,
        toolUsed: toolName,
        provider: this.id,
      };
    } catch (err) {
      const msg = err instanceof Error
        ? (err.name === 'AbortError' ? 'Request timed out — model may still be loading' : err.message)
        : 'Ollama chat request failed';
      return { success: false, error: msg, provider: this.id };
    }
  }

  destroy(): void {
    // No persistent resources
  }
}

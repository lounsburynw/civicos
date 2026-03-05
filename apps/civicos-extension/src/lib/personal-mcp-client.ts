/**
 * PersonalMCPClient — thin wrapper around the Personal MCP HTTP server (localhost:8081).
 * Reads/writes profile, preferences, and jurisdictions via JSON-RPC.
 * Falls back gracefully when the server is unavailable.
 */

const DEFAULT_BASE_URL = 'http://localhost:8081';
const HEALTH_CACHE_TTL = 60_000; // 60s

export interface UserProfile {
  name?: string;
  email?: string;
  neighborhood?: string;
  latitude?: number;
  longitude?: number;
  interests: string[];
}

export interface UserPreferences {
  notifications: Record<string, string>;
  display: Record<string, string>;
}

interface ToolResult<T> {
  success: boolean;
  error?: string;
  profile?: T;
  preferences?: T;
  jurisdictions?: string[];
  count?: number;
  message?: string;
}

export class PersonalMCPClient {
  private baseUrl: string;
  private healthCache: { available: boolean; checkedAt: number } | null = null;

  constructor(baseUrl = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /** Check if the Personal MCP server is reachable. Cached for 60s. */
  async isAvailable(): Promise<boolean> {
    if (this.healthCache && Date.now() - this.healthCache.checkedAt < HEALTH_CACHE_TTL) {
      return this.healthCache.available;
    }
    try {
      const resp = await fetch(`${this.baseUrl}/health`, {
        signal: AbortSignal.timeout(500),
      });
      const available = resp.ok;
      this.healthCache = { available, checkedAt: Date.now() };
      return available;
    } catch {
      this.healthCache = { available: false, checkedAt: Date.now() };
      return false;
    }
  }

  /** Invalidate the health cache (e.g., after a failed call). */
  invalidateCache(): void {
    this.healthCache = null;
  }

  /** Call a tool on the Personal MCP server via JSON-RPC. */
  private async callTool<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
    const resp = await fetch(`${this.baseUrl}/mcp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        method: 'tools/call',
        params: { name, arguments: args },
        id: 1,
      }),
      signal: AbortSignal.timeout(5000),
    });

    if (!resp.ok) {
      throw new Error(`Personal MCP HTTP ${resp.status}`);
    }

    const json = await resp.json();

    if (json.error) {
      throw new Error(json.error.message || 'JSON-RPC error');
    }

    // Extract the text content from the MCP response
    const text = json.result?.content?.[0]?.text;
    if (!text) {
      throw new Error('Empty response from Personal MCP');
    }

    return JSON.parse(text) as T;
  }

  // --- Profile ---

  async getProfile(): Promise<UserProfile> {
    const result = await this.callTool<ToolResult<UserProfile>>('get_profile');
    if (!result.success) throw new Error(result.error || 'Failed to get profile');
    return result.profile!;
  }

  async setProfile(updates: Partial<UserProfile>): Promise<UserProfile> {
    const result = await this.callTool<ToolResult<UserProfile>>('set_profile', updates as Record<string, unknown>);
    if (!result.success) throw new Error(result.error || 'Failed to set profile');
    return result.profile!;
  }

  // --- Preferences ---

  async getPreferences(): Promise<UserPreferences> {
    const result = await this.callTool<ToolResult<UserPreferences>>('get_preferences');
    if (!result.success) throw new Error(result.error || 'Failed to get preferences');
    return result.preferences!;
  }

  async setPreferences(updates: Partial<UserPreferences>): Promise<UserPreferences> {
    const result = await this.callTool<ToolResult<UserPreferences>>('set_preferences', updates as Record<string, unknown>);
    if (!result.success) throw new Error(result.error || 'Failed to set preferences');
    return result.preferences!;
  }

  // --- Jurisdictions ---

  async getJurisdictions(): Promise<string[]> {
    const result = await this.callTool<ToolResult<never>>('get_jurisdictions');
    if (!result.success) throw new Error(result.error || 'Failed to get jurisdictions');
    return result.jurisdictions || [];
  }

  async setJurisdictions(jurisdictions: string[]): Promise<string[]> {
    const result = await this.callTool<ToolResult<never>>('set_jurisdictions', { jurisdictions });
    if (!result.success) throw new Error(result.error || 'Failed to set jurisdictions');
    return result.jurisdictions || [];
  }
}

/** Singleton instance for use across the extension. */
export const personalMCP = new PersonalMCPClient();

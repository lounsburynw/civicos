/**
 * Jurisdiction MCP Client
 *
 * HTTP client for querying the Jurisdiction MCP server.
 * Used by personalized query tools to fetch civic data and apply user context.
 */

/**
 * Jurisdiction MCP client configuration.
 */
export interface JurisdictionMCPClientConfig {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
}

/**
 * A civic item returned from Jurisdiction MCP.
 */
export interface CivicItem {
  id: string;
  type: 'decision' | 'meeting' | 'issue' | 'initiative';
  title: string;
  description?: string;
  date?: string;
  topics?: string[];
  location?: string;
  status?: string;
}

/**
 * Response from Jurisdiction MCP tools.
 */
export interface JurisdictionMCPResponse {
  success: boolean;
  data?: unknown;
  error?: string;
}

/**
 * City pulse response structure.
 */
export interface CityPulseResponse {
  upcoming_meetings?: Array<{
    title: string;
    date: string;
    agenda_items?: string[];
  }>;
  recent_decisions?: Array<{
    title: string;
    date: string;
    outcome?: string;
    topics?: string[];
  }>;
  trending_issues?: Array<{
    type: string;
    count: number;
    location?: string;
  }>;
}

/**
 * Meeting history response.
 */
export interface MeetingHistoryResponse {
  decisions?: Array<{
    id: string;
    title: string;
    date: string;
    outcome?: string;
    topics?: string[];
    transcript_excerpt?: string;
  }>;
  meetings?: Array<{
    id: string;
    title: string;
    date: string;
  }>;
}

/**
 * Similar issues response.
 */
export interface SimilarIssuesResponse {
  issues?: Array<{
    id: string;
    type: string;
    summary: string;
    location?: string;
    status?: string;
    created_at?: string;
  }>;
  total?: number;
}

const DEFAULT_BASE_URL = 'http://localhost:8001';
const DEFAULT_TIMEOUT = 30000;

/**
 * Client for querying Jurisdiction MCP server.
 */
export class JurisdictionMCPClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;

  constructor(config: JurisdictionMCPClientConfig = {}) {
    this.baseUrl = config.baseUrl ?? DEFAULT_BASE_URL;
    this.apiKey = config.apiKey;
    this.timeout = config.timeout ?? DEFAULT_TIMEOUT;
  }

  /**
   * Call a Jurisdiction MCP tool.
   */
  async callTool(toolName: string, args: Record<string, unknown> = {}): Promise<JurisdictionMCPResponse> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (this.apiKey) {
        headers['Authorization'] = `Bearer ${this.apiKey}`;
      }

      const response = await fetch(`${this.baseUrl}/mcp`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          jsonrpc: '2.0',
          method: 'tools/call',
          params: {
            name: toolName,
            arguments: args,
          },
          id: Date.now(),
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        return {
          success: false,
          error: `HTTP ${response.status}: ${response.statusText}`,
        };
      }

      const json = await response.json();

      if (json.error) {
        return {
          success: false,
          error: json.error.message ?? 'Unknown error',
        };
      }

      // Parse the tool result content
      if (json.result?.content?.[0]?.text) {
        try {
          const data = JSON.parse(json.result.content[0].text);
          return { success: true, data };
        } catch {
          return { success: true, data: json.result.content[0].text };
        }
      }

      return { success: true, data: json.result };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          return { success: false, error: 'Request timeout' };
        }
        return { success: false, error: error.message };
      }
      return { success: false, error: 'Unknown error' };
    }
  }

  /**
   * Get city pulse (upcoming meetings, recent decisions, trending issues).
   */
  async getCityPulse(daysAhead: number = 7, daysBack: number = 30): Promise<CityPulseResponse | null> {
    const response = await this.callTool('city_pulse', {
      days_ahead: daysAhead,
      days_back: daysBack,
    });
    if (!response.success) return null;
    return response.data as CityPulseResponse;
  }

  /**
   * Search meeting history on a topic.
   */
  async searchMeetingHistory(query: string, limit: number = 10): Promise<MeetingHistoryResponse | null> {
    const response = await this.callTool('search_meeting_history', {
      query,
      include_transcripts: true,
      limit,
    });
    if (!response.success) return null;
    return response.data as MeetingHistoryResponse;
  }

  /**
   * Find similar issues.
   */
  async findSimilarIssues(topic: string, limit: number = 20): Promise<SimilarIssuesResponse | null> {
    const response = await this.callTool('find_similar_issues', {
      topic,
      semantic: true,
      limit,
    });
    if (!response.success) return null;
    return response.data as SimilarIssuesResponse;
  }

  /**
   * Get upcoming meetings.
   */
  async getUpcomingMeetings(days: number = 30): Promise<Array<{title: string; date: string; agenda_items?: string[]}> | null> {
    const response = await this.callTool('get_upcoming_meetings', { days });
    if (!response.success) return null;
    // Response may be wrapped differently
    const data = response.data as Record<string, unknown>;
    return (data?.meetings ?? data) as Array<{title: string; date: string; agenda_items?: string[]}>;
  }

  /**
   * Check if the Jurisdiction MCP server is available.
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}

/**
 * Mock client for testing without a real Jurisdiction MCP server.
 */
export class MockJurisdictionMCPClient extends JurisdictionMCPClient {
  private mockResponses: Map<string, unknown> = new Map();

  setMockResponse(toolName: string, response: unknown): void {
    this.mockResponses.set(toolName, response);
  }

  override async callTool(toolName: string, _args: Record<string, unknown> = {}): Promise<JurisdictionMCPResponse> {
    const mockResponse = this.mockResponses.get(toolName);
    if (mockResponse !== undefined) {
      return { success: true, data: mockResponse };
    }
    // Default mock responses
    switch (toolName) {
      case 'city_pulse':
        return {
          success: true,
          data: {
            upcoming_meetings: [
              {
                title: 'City Council Regular Meeting',
                date: '2026-02-10',
                agenda_items: ['Housing Element Update', 'Traffic Safety Plan'],
              },
            ],
            recent_decisions: [
              {
                title: 'Approve bike lane on 4th Street',
                date: '2026-01-28',
                outcome: 'approved',
                topics: ['transportation', 'traffic safety'],
              },
            ],
            trending_issues: [
              { type: 'pothole', count: 15, location: 'Downtown' },
            ],
          },
        };
      case 'search_meeting_history':
        return {
          success: true,
          data: {
            decisions: [
              {
                id: 'decision:2026-01-15:item-6a',
                title: 'Housing Element Update Discussion',
                date: '2026-01-15',
                outcome: 'continued',
                topics: ['housing', 'planning'],
              },
            ],
          },
        };
      case 'find_similar_issues':
        return {
          success: true,
          data: {
            issues: [
              {
                id: 'issue:12345',
                type: 'pothole',
                summary: 'Large pothole on Main Street',
                location: 'Main St & 1st Ave',
                status: 'open',
              },
            ],
            total: 1,
          },
        };
      case 'get_upcoming_meetings':
        return {
          success: true,
          data: {
            meetings: [
              {
                title: 'Planning Commission Meeting',
                date: '2026-02-15',
                agenda_items: ['ADU Policy Review'],
              },
            ],
          },
        };
      default:
        return { success: false, error: `Unknown tool: ${toolName}` };
    }
  }

  override async healthCheck(): Promise<boolean> {
    return true;
  }
}

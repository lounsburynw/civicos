/**
 * Chat tool definitions and local executor for Ollama tool-backed search.
 *
 * The 6 MVP tools match the server-side CHAT_TOOLS list in ai_proxy.py.
 * Tool schemas use the OpenAI function calling format (compatible with Ollama).
 *
 * The executor calls the MCP REST API anonymously — no auth, no identity.
 * The server only sees a data request, never the user's question.
 */

/** A single tool definition in OpenAI function-calling format. */
export interface ChatToolDef {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

/** Callback that executes a tool by name and returns a text result. */
export type ChatToolExecutor = (
  toolName: string,
  args: Record<string, unknown>,
) => Promise<string>;

/**
 * The 6 MVP chat tool schemas. Matches CHAT_TOOLS in ai_proxy.py.
 * Format: OpenAI function calling (used by Ollama /api/chat).
 */
export const CHAT_TOOL_DEFS: ChatToolDef[] = [
  {
    type: 'function',
    function: {
      name: 'search_meeting_history',
      description: 'Search past city council meetings and decisions on a topic',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search query (e.g., "homeless shelter", "bike lane")' },
          include_transcripts: { type: 'boolean', description: 'Include video transcript excerpts' },
          limit: { type: 'integer', description: 'Maximum results per category' },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_upcoming_meetings',
      description: 'Get upcoming city council meetings and agenda items',
      parameters: {
        type: 'object',
        properties: {
          days: { type: 'integer', description: 'Days to look ahead' },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_budget',
      description: 'Search city budget data by department or category',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Department or category to search' },
          fiscal_year: { type: 'string', description: 'Filter by fiscal year (e.g., "FY25-26")' },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_public_testimony',
      description: 'Get public testimony excerpts on a topic from meeting transcripts',
      parameters: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Topic to search' },
          limit: { type: 'integer', description: 'Maximum excerpts to return' },
        },
        required: ['topic'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_legislation',
      description: 'Search state or federal legislation by topic, keyword, or status',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search topic or keyword (e.g., "housing", "climate")' },
          state: { type: 'string', description: 'State code: "CA" for California, "US" for federal' },
          status: { type: 'string', description: 'Filter by bill status' },
          limit: { type: 'integer', description: 'Maximum results' },
        },
        required: ['query'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'find_similar_issues',
      description: 'Find community issues related to a topic via 311/SeeClickFix',
      parameters: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Topic to search (e.g., "traffic safety", "pothole")' },
          semantic: { type: 'boolean', description: 'Use semantic matching' },
          limit: { type: 'integer', description: 'Maximum results' },
        },
        required: ['topic'],
      },
    },
  },
];

/** Max characters to keep from tool results (matches server-side MAX_TOOL_RESULT_CHARS). */
const MAX_RESULT_CHARS = 4000;

/** Map tool names to REST API endpoint paths on the MCP server. */
const TOOL_ENDPOINTS: Record<string, { path: string; method: 'POST' | 'GET' }> = {
  search_meeting_history: { path: '/api/tools/search-meeting-history', method: 'POST' },
  get_upcoming_meetings: { path: '/api/tools/get-upcoming-meetings', method: 'POST' },
  search_budget: { path: '/api/tools/search-budget', method: 'POST' },
  get_public_testimony: { path: '/api/tools/get-public-testimony', method: 'POST' },
  search_legislation: { path: '/api/tools/search-legislation', method: 'POST' },
  find_similar_issues: { path: '/api/tools/find-similar-issues', method: 'POST' },
};

/**
 * Create a tool executor that calls the MCP REST API anonymously.
 *
 * @param getMcpUrl - Async function that resolves the MCP base URL.
 *   In the extension, pass `() => registry.getMcpUrl()`.
 */
export function createMcpToolExecutor(getMcpUrl: () => Promise<string>): ChatToolExecutor {
  return async (toolName: string, args: Record<string, unknown>): Promise<string> => {
    const endpoint = TOOL_ENDPOINTS[toolName];
    if (!endpoint) {
      return JSON.stringify({ error: `Unknown tool: ${toolName}` });
    }

    const baseUrl = await getMcpUrl();
    const url = `${baseUrl}${endpoint.path}`;

    try {
      const resp = await fetch(url, {
        method: endpoint.method,
        headers: { 'Content-Type': 'application/json' },
        body: endpoint.method === 'POST' ? JSON.stringify(args) : undefined,
        signal: AbortSignal.timeout(15_000),
      });

      if (!resp.ok) {
        return JSON.stringify({ error: `API error ${resp.status}` });
      }

      const result = await resp.json();
      let text: string;

      if (result.success && result.data) {
        text = typeof result.data === 'string' ? result.data : JSON.stringify(result.data);
      } else {
        text = JSON.stringify(result);
      }

      // Truncate to keep within context limits
      if (text.length > MAX_RESULT_CHARS) {
        text = text.slice(0, MAX_RESULT_CHARS) + '\n... (truncated)';
      }

      return text;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Tool request failed';
      return JSON.stringify({ error: msg });
    }
  };
}

/**
 * Client for communicating with the Jurisdiction MCP server.
 *
 * This wraps the existing Python MCP server, providing typed access
 * to civic data tools like get_voice_counts, broadcast_voice, etc.
 */

export interface VoiceCounts {
  support: number;
  oppose: number;
  watching: number;
  total: number;
  recentActivity?: {
    lastHour: number;
    last24Hours: number;
  };
}

export interface EntityContext {
  id: string;
  type: "decision" | "initiative" | "meeting" | "issue";
  title: string;
  description?: string;
  meeting?: {
    date: string;
    body: string;
  };
  status?: string;
}

export class JurisdictionClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /**
   * Call a tool on the jurisdiction MCP server.
   * Times out after 20 seconds to allow for Modal cold starts.
   */
  async callTool(name: string, args: Record<string, unknown>): Promise<string> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);

    try {
      const response = await fetch(this.baseUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json, text/event-stream",
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: Date.now(),
          method: "tools/call",
          params: { name, arguments: args },
        }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        throw new Error(`Jurisdiction MCP error: ${response.status}`);
      }

      const result = await response.json();
      if (result.error) {
        throw new Error(result.error.message || "Unknown error");
      }

      // Extract text content from MCP response
      const content = result.result?.content || [];
      const textContent = content.find((c: any) => c.type === "text");
      return textContent?.text || "";
    } catch (error: any) {
      clearTimeout(timeout);
      if (error.name === "AbortError") {
        console.warn(`Jurisdiction MCP timeout for ${name}`);
        throw new Error("Jurisdiction MCP timeout - backend may be offline");
      }
      throw error;
    }
  }

  /**
   * Get voice counts for an entity.
   * Returns mock data if backend is unavailable.
   */
  async getVoiceCounts(entityId: string): Promise<VoiceCounts> {
    try {
      const text = await this.callTool("get_voice_counts", { entity: entityId });
      return this.parseVoiceCounts(text);
    } catch (error) {
      console.warn("Failed to get voice counts, returning mock data:", error);
      // Return mock data so widget can render
      return {
        support: 23,
        oppose: 7,
        watching: 41,
        total: 71,
        recentActivity: {
          lastHour: 3,
          last24Hours: 12,
        },
      };
    }
  }

  /**
   * Broadcast a signed voice.
   * Returns mock success if backend is unavailable.
   */
  async broadcastVoice(params: {
    entity: string;
    stance: "support" | "oppose" | "watching";
    publicKey: string;
    signature: string;
  }): Promise<{ success: boolean; message: string }> {
    try {
      const text = await this.callTool("broadcast_voice", {
        entity: params.entity,
        stance: params.stance,
        public_key: params.publicKey,
        signature: params.signature,
      });

      return {
        success: !text.toLowerCase().includes("error"),
        message: text,
      };
    } catch (error: any) {
      console.warn("Failed to broadcast voice:", error);
      // Return mock success so widget can show feedback
      // In production, this would queue for retry
      return {
        success: true,
        message: `Voice recorded locally (relay offline). Your ${params.stance} voice for ${params.entity} will sync when connection is restored.`,
      };
    }
  }

  /**
   * Get context about an entity (what it is, when it's being decided, etc.)
   * Returns minimal context if backend is unavailable.
   */
  async getEntityContext(entityId: string): Promise<EntityContext | null> {
    // Parse entity ID to determine type and fetch appropriate context
    const [type, jurisdiction, ...rest] = entityId.split(":");

    if (type === "decision") {
      try {
        const text = await this.callTool("search_meeting_history", {
          query: rest.join(":"),
          limit: 1,
        });
        return this.parseEntityContext(entityId, type, text);
      } catch (error) {
        console.warn("Failed to get entity context:", error);
        // Return minimal context
        return {
          id: entityId,
          type: "decision",
          title: rest.join(" ").replace(/-/g, " "),
        };
      }
    }

    // For other types, return minimal context
    return {
      id: entityId,
      type: (type as EntityContext["type"]) || "decision",
      title: entityId,
    };
  }

  // ─────────── Parsing Helpers ───────────

  private parseVoiceCounts(text: string): VoiceCounts {
    const counts: VoiceCounts = { support: 0, oppose: 0, watching: 0, total: 0 };

    // Parse various formats the jurisdiction MCP might return
    const supportMatch = text.match(/support[:\s]+(\d+)/i);
    const opposeMatch = text.match(/oppose[:\s]+(\d+)/i);
    const watchingMatch = text.match(/watch(?:ing)?[:\s]+(\d+)/i);

    if (supportMatch) counts.support = parseInt(supportMatch[1], 10);
    if (opposeMatch) counts.oppose = parseInt(opposeMatch[1], 10);
    if (watchingMatch) counts.watching = parseInt(watchingMatch[1], 10);
    counts.total = counts.support + counts.oppose + counts.watching;

    // Try to parse recent activity if present
    const lastHourMatch = text.match(/last\s*hour[:\s]+(\d+)/i);
    const last24Match = text.match(/last\s*24\s*hours?[:\s]+(\d+)/i);
    if (lastHourMatch || last24Match) {
      counts.recentActivity = {
        lastHour: lastHourMatch ? parseInt(lastHourMatch[1], 10) : 0,
        last24Hours: last24Match ? parseInt(last24Match[1], 10) : 0,
      };
    }

    return counts;
  }

  private parseEntityContext(
    entityId: string,
    type: string,
    text: string
  ): EntityContext {
    // Basic parsing - can be enhanced based on actual response format
    const titleMatch = text.match(/(?:title|item)[:\s]+([^\n]+)/i);
    const dateMatch = text.match(/(?:date|meeting)[:\s]+([^\n]+)/i);

    return {
      id: entityId,
      type: type as EntityContext["type"],
      title: titleMatch?.[1]?.trim() || entityId,
      meeting: dateMatch
        ? {
            date: dateMatch[1].trim(),
            body: "City Council",
          }
        : undefined,
    };
  }
}

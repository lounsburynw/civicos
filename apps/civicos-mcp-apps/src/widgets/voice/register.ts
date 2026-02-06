/**
 * Voice Widget Registration
 *
 * Registers the voice_interface tool and ui://civicos/voice resource.
 *
 * The voice widget enables real-time civic coordination:
 * - See how many others care about an issue
 * - Cast your own voice (support/oppose/watch)
 * - Watch momentum build in real-time
 */

import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { z } from "zod";
import fs from "node:fs/promises";
import path from "node:path";

import type { JurisdictionClient } from "../../lib/jurisdiction-client.js";

export interface VoiceWidgetConfig {
  jurisdictionClient: JurisdictionClient;
  relayUrl: string;
  widgetsDir: string;
}

export async function registerVoiceWidget(
  server: McpServer,
  config: VoiceWidgetConfig
): Promise<void> {
  const { jurisdictionClient, relayUrl, widgetsDir } = config;

  const resourceUri = "ui://civicos/voice";

  // ─────────── Main Voice Interface Tool ───────────

  registerAppTool(
    server,
    "voice_interface",
    {
      title: "Civic Voice",
      description: `
Open an interactive voice-casting interface for a civic decision, initiative, or issue.

Use this when someone wants to:
- Express support or opposition to a city council decision
- See how the community feels about an issue
- Track a civic matter they care about
- Join others who share their concerns

The interface shows real-time voice counts and enables instant participation.
      `.trim(),
      inputSchema: {
        entity_id: z
          .string()
          .describe(
            "Entity identifier (e.g., 'decision:city-san-rafael:2026-01-15:item-5a', or a natural description)"
          ),
        context: z
          .string()
          .optional()
          .describe("Brief description of what this is about (shown in the widget header)"),
        relevance: z
          .string()
          .optional()
          .describe("Why this might matter to the user (e.g., 'This affects your neighborhood')"),
      },
      _meta: {
        ui: {
          resourceUri,
        },
      },
    },
    async (args) => {
      const entityId = args.entity_id;
      const context = args.context;
      const relevance = args.relevance;

      // Fetch current voice counts
      const counts = await jurisdictionClient.getVoiceCounts(entityId);

      // Fetch entity context if not provided
      let entityContext = context;
      if (!entityContext) {
        const ctx = await jurisdictionClient.getEntityContext(entityId);
        entityContext = ctx?.title || entityId;
      }

      // Build response for widget initialization
      const widgetData = {
        entity_id: entityId,
        context: entityContext,
        relevance: relevance || null,
        counts,
        relay_url: relayUrl,
        timestamp: Date.now(),
      };

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(widgetData),
          },
        ],
      };
    }
  );

  // ─────────── Voice Resource (HTML Widget) ───────────

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      // Each widget is in its own subdirectory, vite preserves src structure
      const htmlPath = path.join(widgetsDir, "voice", "src", "widgets", "voice.html");
      const html = await fs.readFile(htmlPath, "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );

  // ─────────── Broadcast Voice Tool (called by widget) ───────────
  // Use regular server.tool() for non-UI tools called programmatically

  server.tool(
    "broadcast_voice",
    "Submit a cryptographically signed voice to the relay. Called by the voice widget after local signing.",
    {
      entity: z.string().describe("Entity identifier"),
      stance: z.enum(["support", "oppose", "watching"]).describe("Position"),
      public_key: z.string().describe("Hex-encoded public key"),
      signature: z.string().describe("Hex-encoded signature"),
      created_at: z.number().optional().describe("Unix timestamp from signed Nostr event"),
      jurisdiction: z.string().optional().describe("Jurisdiction code from signed event"),
    },
    async (args) => {
      const result = await jurisdictionClient.broadcastVoice({
        entity: args.entity,
        stance: args.stance,
        publicKey: args.public_key,
        signature: args.signature,
        createdAt: args.created_at,
        jurisdiction: args.jurisdiction,
      });

      return {
        content: [{ type: "text", text: JSON.stringify(result) }],
      };
    }
  );

  // ─────────── Refresh Counts Tool (called by widget) ───────────

  server.tool(
    "refresh_voice_counts",
    "Get updated voice counts for an entity. Called by the voice widget for real-time updates.",
    {
      entity: z.string().describe("Entity identifier"),
    },
    async (args) => {
      const counts = await jurisdictionClient.getVoiceCounts(args.entity);
      return {
        content: [{ type: "text", text: JSON.stringify(counts) }],
      };
    }
  );
}

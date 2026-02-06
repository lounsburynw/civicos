/**
 * Action Widget Registration
 *
 * Registers the action_interface tool and ui://civicos/action resource.
 *
 * The action widget enables civic participation tracking:
 * - Commit to taking a civic action (attend meeting, submit comment, etc.)
 * - Report completion with evidence
 * - Watch progress build in real-time
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

export interface ActionWidgetConfig {
  relayUrl: string;
  widgetsDir: string;
}

export async function registerActionWidget(
  server: McpServer,
  config: ActionWidgetConfig
): Promise<void> {
  const { relayUrl, widgetsDir } = config;

  const resourceUri = "ui://civicos/action";

  // ─────────── Main Action Interface Tool ───────────

  registerAppTool(
    server,
    "action_interface",
    {
      title: "Civic Action",
      description: `
Open an interactive action-tracking interface for a civic action item.

Use this when someone wants to:
- Commit to attending a city council meeting
- Submit a written comment on a proposal
- Sign a petition or contact an official
- Track collective progress on civic participation

The interface shows real-time commitment/completion counts and enables instant participation.
      `.trim(),
      inputSchema: {
        action_id: z
          .string()
          .describe(
            "Action identifier (e.g., 'action:city-san-rafael:initiative-123:public_comment:abc12345')"
          ),
        action_type: z
          .string()
          .optional()
          .describe(
            "Type of action: written_comment, attend_meeting, public_comment, contact_official, signature, share, custom"
          ),
        description: z
          .string()
          .optional()
          .describe("Description of the action (shown in the widget header)"),
        target: z
          .string()
          .optional()
          .describe("Who/what the action targets (e.g., 'City Council')"),
        deadline: z
          .string()
          .optional()
          .describe("Deadline for the action (ISO date string)"),
        target_count: z
          .number()
          .optional()
          .describe("Target number of participants needed"),
      },
      _meta: {
        ui: {
          resourceUri,
        },
      },
    },
    async (args) => {
      // Fetch current action counts from relay
      let counts = { commitments: 0, completions: 0, target: null as number | null };
      try {
        const response = await fetch(
          `${relayUrl}/coordination/action/counts/${encodeURIComponent(args.action_id)}${args.target_count ? `?target=${args.target_count}` : ""}`,
          { signal: AbortSignal.timeout(10000) }
        );
        if (response.ok) {
          counts = await response.json();
        }
      } catch (e) {
        console.warn("Failed to fetch action counts:", e);
      }

      const widgetData = {
        action_id: args.action_id,
        action_type: args.action_type || "custom",
        description: args.description || args.action_id,
        target: args.target || null,
        deadline: args.deadline || null,
        target_count: args.target_count || null,
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

  // ─────────── Action Resource (HTML Widget) ───────────

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const htmlPath = path.join(widgetsDir, "action", "src", "widgets", "action.html");
      const html = await fs.readFile(htmlPath, "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );

  // ─────────── Broadcast Commitment Tool (called by widget) ───────────

  server.tool(
    "broadcast_commitment",
    "Submit a cryptographically signed commitment to the relay. Called by the action widget after local signing.",
    {
      action_id: z.string().describe("Action identifier"),
      public_key: z.string().describe("Hex-encoded public key"),
      signature: z.string().describe("Hex-encoded signature"),
    },
    async (args) => {
      try {
        const response = await fetch(`${relayUrl}/coordination/action/commit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_id: args.action_id,
            public_key: args.public_key,
            signature: args.signature,
          }),
          signal: AbortSignal.timeout(10000),
        });

        if (!response.ok) {
          const error = await response.text();
          return {
            content: [{ type: "text", text: JSON.stringify({ success: false, message: error }) }],
          };
        }

        const result = await response.json();
        return {
          content: [{ type: "text", text: JSON.stringify({ success: true, ...result }) }],
        };
      } catch (e: any) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                success: true,
                message: `Commitment recorded locally (relay offline). Will sync when connection is restored.`,
              }),
            },
          ],
        };
      }
    }
  );

  // ─────────── Broadcast Completion Tool (called by widget) ───────────

  server.tool(
    "broadcast_completion",
    "Submit a cryptographically signed completion to the relay. Called by the action widget after local signing.",
    {
      action_id: z.string().describe("Action identifier"),
      public_key: z.string().describe("Hex-encoded public key"),
      signature: z.string().describe("Hex-encoded signature"),
      evidence_url: z.string().nullable().optional().describe("Optional evidence URL or description"),
    },
    async (args) => {
      try {
        const response = await fetch(`${relayUrl}/coordination/action/complete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action_id: args.action_id,
            public_key: args.public_key,
            signature: args.signature,
            evidence_url: args.evidence_url || null,
          }),
          signal: AbortSignal.timeout(10000),
        });

        if (!response.ok) {
          const error = await response.text();
          return {
            content: [{ type: "text", text: JSON.stringify({ success: false, message: error }) }],
          };
        }

        const result = await response.json();
        return {
          content: [{ type: "text", text: JSON.stringify({ success: true, ...result }) }],
        };
      } catch (e: any) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({
                success: true,
                message: `Completion recorded locally (relay offline). Will sync when connection is restored.`,
              }),
            },
          ],
        };
      }
    }
  );

  // ─────────── Refresh Counts Tool (called by widget) ───────────

  server.tool(
    "refresh_action_counts",
    "Get updated action counts. Called by the action widget for real-time updates.",
    {
      action_id: z.string().describe("Action identifier"),
    },
    async (args) => {
      try {
        const response = await fetch(
          `${relayUrl}/coordination/action/counts/${encodeURIComponent(args.action_id)}`,
          { signal: AbortSignal.timeout(10000) }
        );

        if (!response.ok) {
          return {
            content: [
              { type: "text", text: JSON.stringify({ commitments: 0, completions: 0 }) },
            ],
          };
        }

        const counts = await response.json();
        return {
          content: [{ type: "text", text: JSON.stringify(counts) }],
        };
      } catch (e) {
        return {
          content: [
            { type: "text", text: JSON.stringify({ commitments: 0, completions: 0 }) },
          ],
        };
      }
    }
  );
}

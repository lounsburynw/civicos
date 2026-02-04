/**
 * Issue Card Widget Registration
 *
 * Displays local 311 issues (SeeClickFix) with rich context:
 * - Issue details, status, location
 * - Similar issues (momentum indicator)
 * - Related council discussions (if any)
 * - Community support indicators
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

export interface IssueCardWidgetConfig {
  jurisdictionClient: JurisdictionClient;
  widgetsDir: string;
}

export async function registerIssueCardWidget(
  server: McpServer,
  config: IssueCardWidgetConfig
): Promise<void> {
  const { jurisdictionClient, widgetsDir } = config;

  const resourceUri = "ui://civicos/issue-card";

  // ─────────── Issue Card Tool ───────────

  registerAppTool(
    server,
    "issue_card",
    {
      title: "Issue Card",
      description: `
Show a detailed view of a local community issue from 311/SeeClickFix reports.

Use this when someone:
- Asks about a specific local issue or complaint
- Wants to see what issues are in their area
- Asks about potholes, parking, traffic signals, etc.
- Wants to know if others have reported similar problems

The card shows issue details, status, similar reports, and any council discussions.
      `.trim(),
      inputSchema: {
        issue_type: z
          .string()
          .optional()
          .describe("Type of issue (e.g., 'pothole', 'parking', 'traffic_signal', 'graffiti')"),
        address: z
          .string()
          .optional()
          .describe("Address or location to search near"),
        description: z
          .string()
          .optional()
          .describe("Description of the issue to find similar reports"),
      },
      _meta: {
        ui: {
          resourceUri,
        },
      },
    },
    async (args) => {
      // Fetch issue data based on provided criteria
      const issues = await fetchIssues(
        jurisdictionClient,
        args.issue_type,
        args.address,
        args.description
      );

      // Fetch similar issues if we have a description
      let similarIssues: SimilarIssue[] = [];
      if (args.description || (issues.length > 0 && issues[0].description)) {
        const searchDesc = args.description || issues[0].description;
        similarIssues = await fetchSimilarIssues(jurisdictionClient, searchDesc);
      }

      // Fetch analytics for context
      const analytics = await fetchIssueAnalytics(
        jurisdictionClient,
        args.issue_type
      );

      // Build response for widget initialization
      const data = {
        issues,
        similarIssues,
        analytics,
        filter: {
          type: args.issue_type || null,
          address: args.address || null,
        },
        timestamp: Date.now(),
      };

      return {
        content: [{ type: "text", text: JSON.stringify(data) }],
      };
    }
  );

  // ─────────── Issue Card Resource (HTML Widget) ───────────

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const htmlPath = path.join(
        widgetsDir,
        "issue_card",
        "src",
        "widgets",
        "issue_card.html"
      );
      const html = await fs.readFile(htmlPath, "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );

  // ─────────── Find Similar Issues Tool (called by widget) ───────────

  server.tool(
    "search_similar_issues",
    "Find issues similar to a given description. Called by the issue card widget.",
    {
      description: z.string().describe("Description to match against"),
    },
    async (args) => {
      try {
        const text = await jurisdictionClient.callTool("find_similar_issues", {
          issue_description: args.description,
        });
        return {
          content: [{ type: "text", text }],
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ error: "Failed to find similar issues" }),
            },
          ],
        };
      }
    }
  );

  // ─────────── Get Issues Near Address Tool (called by widget) ───────────

  server.tool(
    "get_issues_near_address",
    "Get issues reported near a specific address. Called by the issue card widget.",
    {
      address: z.string().describe("Address to search near"),
      radius: z.number().optional().describe("Radius in meters (default 500)"),
    },
    async (args) => {
      try {
        const text = await jurisdictionClient.callTool("find_issues_near_address", {
          address: args.address,
          radius: args.radius || 500,
        });
        return {
          content: [{ type: "text", text }],
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ error: "Failed to find nearby issues" }),
            },
          ],
        };
      }
    }
  );
}

// ─────────── Types ───────────

interface Issue {
  id: string;
  type: string;
  status: "open" | "acknowledged" | "closed";
  address: string;
  description: string;
  createdAt?: string;
  updatedAt?: string;
}

interface SimilarIssue {
  match: number;
  description: string;
}

interface IssueAnalytics {
  total: number;
  byType: Array<{ type: string; count: number; percentage: number }>;
  byStatus: Array<{ status: string; count: number }>;
}

// ─────────── Data Fetchers ───────────

async function fetchIssues(
  client: JurisdictionClient,
  type?: string,
  address?: string,
  description?: string
): Promise<Issue[]> {
  try {
    // If address is provided, search by location
    if (address) {
      const text = await client.callTool("find_issues_near_address", {
        address,
        radius: 500,
      });
      return parseIssues(text);
    }

    // Otherwise get a sample, optionally filtered by type
    const text = await client.callTool("get_issue_sample", {
      limit: "10",
      ...(type && { type }),
    });
    return parseIssues(text);
  } catch (error) {
    console.warn("Failed to fetch issues:", error);
    return [];
  }
}

async function fetchSimilarIssues(
  client: JurisdictionClient,
  description: string
): Promise<SimilarIssue[]> {
  try {
    const text = await client.callTool("find_similar_issues", {
      issue_description: description,
    });
    return parseSimilarIssues(text);
  } catch (error) {
    console.warn("Failed to fetch similar issues:", error);
    return [];
  }
}

async function fetchIssueAnalytics(
  client: JurisdictionClient,
  type?: string
): Promise<IssueAnalytics> {
  try {
    const text = await client.callTool("get_issue_analytics", {});
    return parseAnalytics(text);
  } catch (error) {
    console.warn("Failed to fetch issue analytics:", error);
    return { total: 0, byType: [], byStatus: [] };
  }
}

// ─────────── Parsers ───────────

function parseIssues(text: string): Issue[] {
  const issues: Issue[] = [];

  // Parse the markdown format from get_issue_sample
  const sections = text.split(/## Issue \d+/);

  for (const section of sections) {
    if (!section.trim()) continue;

    const typeMatch = section.match(/\*\*Type:\*\*\s*(\w+)/i);
    const statusMatch = section.match(/\*\*Status:\*\*\s*(\w+)/i);
    const addressMatch = section.match(/\*\*Address:\*\*\s*(.+?)(?:\n|$)/i);
    const descMatch = section.match(/\*\*Description:\*\*\s*(.+?)(?:\.\.\.|$)/is);

    if (typeMatch || statusMatch || addressMatch) {
      issues.push({
        id: `issue-${issues.length + 1}`,
        type: typeMatch?.[1]?.toLowerCase() || "other",
        status: (statusMatch?.[1]?.toLowerCase() || "open") as Issue["status"],
        address: addressMatch?.[1]?.trim() || "",
        description: descMatch?.[1]?.trim() || "",
      });
    }
  }

  return issues.slice(0, 10);
}

function parseSimilarIssues(text: string): SimilarIssue[] {
  const similar: SimilarIssue[] = [];

  // Parse: "- **[70% match]** Description..."
  const lines = text.split("\n");
  for (const line of lines) {
    const match = line.match(/\*\*\[(\d+)%\s*match\]\*\*\s*(.+)/i);
    if (match) {
      similar.push({
        match: parseInt(match[1], 10),
        description: match[2].trim().slice(0, 100),
      });
    }
  }

  return similar.slice(0, 10);
}

function parseAnalytics(text: string): IssueAnalytics {
  const analytics: IssueAnalytics = {
    total: 0,
    byType: [],
    byStatus: [],
  };

  // Parse total
  const totalMatch = text.match(/Total:\s*(\d+)/i) || text.match(/(\d+)\s*issues/i);
  if (totalMatch) {
    analytics.total = parseInt(totalMatch[1], 10);
  }

  // Parse by type: "- **traffic_signal:** 397 (23.1%)"
  const typeLines = text.split("\n");
  let inByType = false;

  for (const line of typeLines) {
    if (line.includes("## By Type") || line.includes("Results by Type")) {
      inByType = true;
      continue;
    }
    if (inByType && line.startsWith("##")) {
      break;
    }

    if (inByType) {
      const match = line.match(
        /\*\*(\w+):\*\*\s*(\d+)\s*\((\d+\.?\d*)%\)/
      ) || line.match(/-\s*(\w+):\s*(\d+)\s*\((\d+\.?\d*)%\)/);

      if (match) {
        analytics.byType.push({
          type: match[1],
          count: parseInt(match[2], 10),
          percentage: parseFloat(match[3]),
        });
      }
    }
  }

  return analytics;
}

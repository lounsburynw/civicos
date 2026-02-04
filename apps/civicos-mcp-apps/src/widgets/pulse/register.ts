/**
 * City Pulse Widget Registration
 *
 * The "home screen" of civic engagement - shows what's happening in your city
 * and provides pathways to deeper exploration.
 *
 * Surfaces:
 * - Upcoming meetings with hot agenda items
 * - Trending topics by voice activity
 * - Local issue clusters
 * - Personalized topic subscriptions
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

export interface PulseWidgetConfig {
  jurisdictionClient: JurisdictionClient;
  widgetsDir: string;
}

export async function registerPulseWidget(
  server: McpServer,
  config: PulseWidgetConfig
): Promise<void> {
  const { jurisdictionClient, widgetsDir } = config;

  const resourceUri = "ui://civicos/pulse";

  // ─────────── City Pulse Tool ───────────

  registerAppTool(
    server,
    "city_pulse",
    {
      title: "City Pulse",
      description: `
Show an interactive dashboard of what's happening in the city right now.

Use this when someone:
- Asks "what's happening in [city]?"
- Wants to get involved but doesn't know where to start
- Asks about upcoming meetings or decisions
- Wants an overview of civic activity

The dashboard shows upcoming meetings, trending topics, local issues, and personalized subscriptions.
      `.trim(),
      inputSchema: {
        jurisdiction: z
          .string()
          .optional()
          .describe("Jurisdiction ID (e.g., 'city-san-rafael'). Defaults to server's jurisdiction."),
        include_personal: z
          .boolean()
          .optional()
          .describe("Include personalized topics if user context is available"),
      },
      _meta: {
        ui: {
          resourceUri,
        },
      },
    },
    async (args) => {
      const jurisdiction = args.jurisdiction || "city-san-rafael";

      // Fetch data from jurisdiction MCP
      const [pulse, trending, issues] = await Promise.all([
        fetchCityPulse(jurisdictionClient, jurisdiction),
        fetchTrending(jurisdictionClient, jurisdiction),
        fetchIssueClusters(jurisdictionClient, jurisdiction),
      ]);

      // Assemble response
      const data = {
        jurisdiction,
        displayName: pulse.displayName || formatJurisdictionName(jurisdiction),
        timestamp: Date.now(),
        stats: {
          activeVoices: trending.reduce((sum, t) => sum + t.support + t.oppose + t.watching, 0),
          upcomingMeetings: pulse.meetings?.length || 0,
          openIssues: issues.reduce((sum, c) => sum + c.count, 0),
        },
        upcomingMeetings: pulse.meetings || [],
        trending: trending,
        issueClusters: issues,
        yourTopics: [], // TODO: personalization via personal MCP
      };

      return {
        content: [{ type: "text", text: JSON.stringify(data) }],
      };
    }
  );

  // ─────────── Pulse Resource (HTML Widget) ───────────

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const htmlPath = path.join(widgetsDir, "pulse", "src", "widgets", "pulse.html");
      const html = await fs.readFile(htmlPath, "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );
}

// ─────────── Data Fetchers ───────────

async function fetchCityPulse(
  client: JurisdictionClient,
  jurisdiction: string
): Promise<{
  displayName?: string;
  meetings: Array<{
    id: string;
    name: string;
    date: string;
    time: string;
    location?: string;
    hotItems?: Array<{ title: string; hot: boolean }>;
  }>;
}> {
  try {
    // Use get_upcoming_meetings which returns formatted meeting data
    const text = await client.callTool("get_upcoming_meetings", {});
    return {
      displayName: formatJurisdictionName(jurisdiction),
      meetings: parseMeetingsFromText(text),
    };
  } catch (error) {
    console.warn("Failed to fetch city pulse:", error);
    return { displayName: formatJurisdictionName(jurisdiction), meetings: [] };
  }
}

async function fetchTrending(
  client: JurisdictionClient,
  jurisdiction: string
): Promise<
  Array<{
    entityId: string;
    title: string;
    support: number;
    oppose: number;
    watching: number;
    momentum?: number;
  }>
> {
  // Trending topics based on voice activity - not yet implemented in backend
  // Return empty for now; will be populated when relay tracks voice activity
  return [];
}

async function fetchIssueClusters(
  client: JurisdictionClient,
  jurisdiction: string
): Promise<
  Array<{
    category: string;
    label: string;
    icon: string;
    count: number;
    trend?: number;
  }>
> {
  try {
    const text = await client.callTool("get_issue_analytics", {});
    return parseIssueClustersFromText(text);
  } catch (error) {
    console.warn("Failed to fetch issue clusters:", error);
    return [];
  }
}

// ─────────── Parsers ───────────

function parseMeetingsFromText(text: string): Array<{
  id: string;
  name: string;
  date: string;
  time: string;
  location?: string;
  hotItems?: Array<{ title: string; hot: boolean }>;
}> {
  const meetings: Array<{
    id: string;
    name: string;
    date: string;
    time: string;
    location?: string;
  }> = [];

  // Parse markdown format: "- **Meeting Name – Date** - datetime"
  const lines = text.split("\n");
  for (const line of lines) {
    // Match: "- **Meeting Name – Date** - datetime" or "- **Meeting Name** - datetime"
    const match = line.match(/^\s*-\s*\*\*([^*]+)\*\*\s*-?\s*(.+)?$/);
    if (match) {
      const nameAndDate = match[1].trim();
      const datetime = match[2]?.trim() || "";

      // Split on " – " (em dash) or " - " to separate name and date description
      const parts = nameAndDate.split(/\s*[–-]\s*/);
      const name = parts[0].trim();
      const dateStr = parts[1]?.trim() || "";

      // Extract date from datetime (format: "2026-02-04 06:00:00+00:00")
      const dateMatch = datetime.match(/(\d{4}-\d{2}-\d{2})/);
      const date = dateMatch ? dateMatch[1] : dateStr;

      // Extract time
      const timeMatch = datetime.match(/(\d{2}:\d{2})/);
      const time = timeMatch ? formatTime(timeMatch[1]) : "TBD";

      meetings.push({
        id: `meeting-${date}-${name.toLowerCase().replace(/\s+/g, "-").slice(0, 20)}`,
        name,
        date,
        time,
        location: "City Hall",
      });
    }
  }

  return meetings;
}

function formatTime(time24: string): string {
  const [hours, minutes] = time24.split(":").map(Number);
  const period = hours >= 12 ? "PM" : "AM";
  const hours12 = hours % 12 || 12;
  return `${hours12}:${minutes.toString().padStart(2, "0")} ${period}`;
}

function parseIssueClustersFromText(text: string): Array<{
  category: string;
  label: string;
  icon: string;
  count: number;
  trend?: number;
}> {
  const clusters: Array<{
    category: string;
    label: string;
    icon: string;
    count: number;
  }> = [];

  // Map category names to display labels and icons
  const categoryMeta: Record<string, { label: string; icon: string }> = {
    traffic_signal: { label: "Traffic Signals", icon: "🚦" },
    parking: { label: "Parking", icon: "🅿️" },
    illegal_dumping: { label: "Illegal Dumping", icon: "🗑️" },
    trees_vegetation: { label: "Trees & Vegetation", icon: "🌳" },
    operational: { label: "City Operations", icon: "⚙️" },
    stormwater: { label: "Stormwater", icon: "🌧️" },
    pothole: { label: "Potholes", icon: "🕳️" },
    graffiti: { label: "Graffiti", icon: "🎨" },
    parks: { label: "Parks", icon: "🏞️" },
    other: { label: "Other", icon: "📋" },
    roads: { label: "Roads & Sidewalks", icon: "🛣️" },
    safety: { label: "Public Safety", icon: "🚨" },
  };

  // Parse markdown format: "- category_name: count"
  const lines = text.split("\n");
  let inByType = false;

  for (const line of lines) {
    if (line.includes("## By Type")) {
      inByType = true;
      continue;
    }
    if (inByType && line.startsWith("##")) {
      break; // Next section
    }

    if (inByType) {
      const match = line.match(/^\s*-\s*(\w+):\s*(\d+)/);
      if (match) {
        const category = match[1];
        const count = parseInt(match[2], 10);
        const meta = categoryMeta[category] || {
          label: category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
          icon: "📍",
        };

        clusters.push({
          category,
          label: meta.label,
          icon: meta.icon,
          count,
        });
      }
    }
  }

  // Return top 5 by count
  return clusters.sort((a, b) => b.count - a.count).slice(0, 5);
}

function formatJurisdictionName(jurisdiction: string): string {
  // "city-san-rafael" -> "San Rafael"
  const parts = jurisdiction.split("-").slice(1);
  return parts
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

/**
 * Meeting Prep Widget Registration
 *
 * Helps users prepare for upcoming city council meetings by providing:
 * - Agenda overview with key items highlighted
 * - Historical context for agenda items
 * - Related prior decisions
 * - Links to voice interface for items being decided
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

export interface MeetingPrepWidgetConfig {
  jurisdictionClient: JurisdictionClient;
  widgetsDir: string;
}

export async function registerMeetingPrepWidget(
  server: McpServer,
  config: MeetingPrepWidgetConfig
): Promise<void> {
  const { jurisdictionClient, widgetsDir } = config;

  const resourceUri = "ui://civicos/meeting-prep";

  // ─────────── Meeting Prep Tool ───────────

  registerAppTool(
    server,
    "meeting_prep",
    {
      title: "Meeting Prep",
      description: `
Open an interactive meeting preparation interface for an upcoming city council meeting.

Use this when someone:
- Asks about what's on the agenda for an upcoming meeting
- Wants to prepare for a city council meeting
- Asks what decisions are being made
- Wants context on agenda items

The interface shows the meeting agenda, provides historical context for items,
and links to the voice interface for participating in decisions.
      `.trim(),
      inputSchema: {
        meeting_id: z
          .string()
          .optional()
          .describe("Meeting identifier (if known). If not provided, shows the next upcoming meeting."),
        topic: z
          .string()
          .optional()
          .describe("Filter agenda items to those matching this topic"),
      },
      _meta: {
        ui: {
          resourceUri,
        },
      },
    },
    async (args) => {
      // Fetch meeting details
      const meeting = await fetchMeetingDetails(
        jurisdictionClient,
        args.meeting_id
      );

      // Fetch historical context for agenda items
      const context = await fetchMeetingContext(
        jurisdictionClient,
        meeting.agendaItems,
        args.topic
      );

      // Build response for widget initialization
      const data = {
        meeting,
        context,
        topic: args.topic || null,
        timestamp: Date.now(),
      };

      return {
        content: [{ type: "text", text: JSON.stringify(data) }],
      };
    }
  );

  // ─────────── Meeting Prep Resource (HTML Widget) ───────────

  registerAppResource(
    server,
    resourceUri,
    resourceUri,
    { mimeType: RESOURCE_MIME_TYPE },
    async () => {
      const htmlPath = path.join(
        widgetsDir,
        "meeting_prep",
        "src",
        "widgets",
        "meeting_prep.html"
      );
      const html = await fs.readFile(htmlPath, "utf-8");
      return {
        contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }],
      };
    }
  );

  // ─────────── Get Agenda Item Context Tool (called by widget) ───────────

  server.tool(
    "get_agenda_item_context",
    "Get historical context for a specific agenda item. Called by the meeting prep widget.",
    {
      item_title: z.string().describe("Title or description of the agenda item"),
      meeting_id: z.string().optional().describe("Meeting ID for context"),
    },
    async (args) => {
      try {
        const text = await jurisdictionClient.callTool("search_meeting_history", {
          query: args.item_title,
          limit: 5,
        });
        return {
          content: [{ type: "text", text }],
        };
      } catch (error) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ error: "Failed to fetch context" }),
            },
          ],
        };
      }
    }
  );
}

// ─────────── Data Fetchers ───────────

interface Meeting {
  id: string;
  name: string;
  date: string;
  time: string;
  location: string;
  body: string;
  agendaItems: AgendaItem[];
}

interface AgendaItem {
  id: string;
  number: string;
  title: string;
  description?: string;
  type: "consent" | "public_hearing" | "action" | "report" | "other";
  hasVoice: boolean;
  voiceEntityId?: string;
}

interface MeetingContext {
  relatedDecisions: Array<{
    date: string;
    title: string;
    outcome?: string;
  }>;
  publicComments: number;
  keyTopics: string[];
}

async function fetchMeetingDetails(
  client: JurisdictionClient,
  meetingId?: string
): Promise<Meeting> {
  try {
    // If no meeting ID, get the next upcoming meeting
    const text = await client.callTool("get_upcoming_meetings", {});
    const meetings = parseMeetingsFromText(text);

    if (meetings.length === 0) {
      return {
        id: "none",
        name: "No Upcoming Meetings",
        date: "",
        time: "",
        location: "",
        body: "",
        agendaItems: [],
      };
    }

    // If meeting_id provided, find it; otherwise use first
    const meeting = meetingId
      ? meetings.find((m) => m.id === meetingId) || meetings[0]
      : meetings[0];

    // Fetch agenda/context for this meeting
    try {
      const prepText = await client.callTool("prepare_for_meeting", {
        meeting_id: meeting.id,
      });
      meeting.agendaItems = parseAgendaItems(prepText, meeting.id);
    } catch {
      // prepare_for_meeting may not exist or may fail - parse from meeting text
      meeting.agendaItems = [];
    }

    return meeting;
  } catch (error) {
    console.warn("Failed to fetch meeting details:", error);
    return {
      id: "error",
      name: "Error Loading Meeting",
      date: "",
      time: "",
      location: "",
      body: "",
      agendaItems: [],
    };
  }
}

async function fetchMeetingContext(
  client: JurisdictionClient,
  agendaItems: AgendaItem[],
  topic?: string
): Promise<MeetingContext> {
  const context: MeetingContext = {
    relatedDecisions: [],
    publicComments: 0,
    keyTopics: [],
  };

  if (agendaItems.length === 0) {
    return context;
  }

  try {
    // Search for context on the main topics
    const topics = topic
      ? [topic]
      : agendaItems.slice(0, 3).map((item) => item.title);

    context.keyTopics = topics;

    // Fetch related decisions for the first few items
    for (const t of topics.slice(0, 2)) {
      const text = await client.callTool("search_meeting_history", {
        query: t,
        limit: 3,
      });
      const decisions = parseRelatedDecisions(text);
      context.relatedDecisions.push(...decisions);
    }

    // Deduplicate
    context.relatedDecisions = context.relatedDecisions.filter(
      (d, i, arr) => arr.findIndex((x) => x.title === d.title) === i
    );
  } catch (error) {
    console.warn("Failed to fetch meeting context:", error);
  }

  return context;
}

// ─────────── Parsers ───────────

function parseMeetingsFromText(text: string): Meeting[] {
  const meetings: Meeting[] = [];

  // Parse markdown format: "- **Meeting Name – Date** - datetime"
  const lines = text.split("\n");
  for (const line of lines) {
    const match = line.match(/^\s*-\s*\*\*([^*]+)\*\*\s*-?\s*(.+)?$/);
    if (match) {
      const nameAndDate = match[1].trim();
      const datetime = match[2]?.trim() || "";

      const parts = nameAndDate.split(/\s*[–-]\s*/);
      const name = parts[0].trim();

      const dateMatch = datetime.match(/(\d{4}-\d{2}-\d{2})/);
      const date = dateMatch ? dateMatch[1] : "";

      const timeMatch = datetime.match(/(\d{2}:\d{2})/);
      const time = timeMatch ? formatTime(timeMatch[1]) : "TBD";

      meetings.push({
        id: `meeting-${date}-${name.toLowerCase().replace(/\s+/g, "-").slice(0, 20)}`,
        name,
        date,
        time,
        location: "City Hall",
        body: detectBody(name),
        agendaItems: [],
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

function detectBody(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes("council")) return "City Council";
  if (lower.includes("planning")) return "Planning Commission";
  if (lower.includes("library")) return "Library Board";
  if (lower.includes("park")) return "Parks Commission";
  return "City Council";
}

function parseAgendaItems(text: string, meetingId: string): AgendaItem[] {
  const items: AgendaItem[] = [];

  // Parse various agenda formats
  // Format 1: "1. Item title" or "A. Item title"
  // Format 2: "- **Item title**"
  const lines = text.split("\n");
  let itemNumber = 0;

  for (const line of lines) {
    // Match numbered items
    const numberedMatch = line.match(/^\s*(\d+|[A-Z])[.)]\s+(.+)/);
    // Match bullet items with bold
    const bulletMatch = line.match(/^\s*-\s*\*\*([^*]+)\*\*/);

    if (numberedMatch || bulletMatch) {
      itemNumber++;
      const title = numberedMatch ? numberedMatch[2].trim() : bulletMatch![1].trim();
      const number = numberedMatch ? numberedMatch[1] : String(itemNumber);

      items.push({
        id: `${meetingId}-item-${number}`,
        number,
        title: title.slice(0, 100), // Truncate long titles
        type: detectItemType(title),
        hasVoice: detectHasVoice(title),
        voiceEntityId: `decision:city-san-rafael:${meetingId}:item-${number}`,
      });
    }
  }

  // If no items parsed, return placeholder
  if (items.length === 0) {
    items.push({
      id: `${meetingId}-item-1`,
      number: "1",
      title: "Agenda not yet published",
      type: "other",
      hasVoice: false,
    });
  }

  return items;
}

function detectItemType(title: string): AgendaItem["type"] {
  const lower = title.toLowerCase();
  if (lower.includes("consent")) return "consent";
  if (lower.includes("hearing") || lower.includes("public hearing")) return "public_hearing";
  if (lower.includes("resolution") || lower.includes("ordinance") || lower.includes("approve")) return "action";
  if (lower.includes("report") || lower.includes("update")) return "report";
  return "other";
}

function detectHasVoice(title: string): boolean {
  const lower = title.toLowerCase();
  // Items likely to have public input
  return (
    lower.includes("hearing") ||
    lower.includes("resolution") ||
    lower.includes("ordinance") ||
    lower.includes("approve") ||
    lower.includes("adopt") ||
    lower.includes("zone") ||
    lower.includes("permit")
  );
}

function parseRelatedDecisions(text: string): Array<{
  date: string;
  title: string;
  outcome?: string;
}> {
  const decisions: Array<{ date: string; title: string; outcome?: string }> = [];

  // Parse search results format
  const lines = text.split("\n");
  for (const line of lines) {
    const match = line.match(/(\d{4}-\d{2}-\d{2})[:\s]+(.+)/);
    if (match) {
      decisions.push({
        date: match[1],
        title: match[2].slice(0, 80),
      });
    }
  }

  return decisions.slice(0, 5);
}

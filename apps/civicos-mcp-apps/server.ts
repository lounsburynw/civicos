/**
 * CivicOS MCP Apps Server
 *
 * This server provides interactive UI widgets that render directly in AI hosts
 * (Claude.ai, ChatGPT, etc). The key insight: after initial load, the widget
 * communicates directly with this server WITHOUT LLM involvement.
 *
 * This enables:
 * - Real-time voice count updates
 * - Push notifications when others act
 * - Coordination visibility ("3 people joined since you did")
 * - Personal relevance scoring
 *
 * Architecture:
 *   AI Host <-> MCP Apps Server <-> Jurisdiction MCP (civic data)
 *                     |
 *                     +-----------> Personal MCP (relevance, identity)
 *                     |
 *                     +-----------> Relay (real-time events)
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import express from "express";
import cors from "cors";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { JurisdictionClient } from "./src/lib/jurisdiction-client.js";
import { registerVoiceWidget } from "./src/widgets/voice/register.js";
import { registerPulseWidget } from "./src/widgets/pulse/register.js";
import { registerMeetingPrepWidget } from "./src/widgets/meeting_prep/register.js";
import { registerIssueCardWidget } from "./src/widgets/issue_card/register.js";
import { registerActionWidget } from "./src/widgets/action/register.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─────────── Configuration ───────────

const config = {
  port: parseInt(process.env.PORT || "3002", 10),
  jurisdictionMcpUrl:
    process.env.JURISDICTION_MCP_URL ||
    "https://lounsburynw--civicos-san-rafael-mcpserver-mcp-endpoint.modal.run",
  relayUrl: process.env.RELAY_URL || "https://api.civicosproject.org",
  personalMcpUrl: process.env.PERSONAL_MCP_URL, // Optional
};

// ─────────── Server Setup ───────────

const server = new McpServer({
  name: "CivicOS Apps",
  version: "0.1.0",
});

const jurisdictionClient = new JurisdictionClient(config.jurisdictionMcpUrl);

// ─────────── Widget Registration ───────────

// Each widget registers its own tools and resources
// This keeps the server.ts clean and widgets self-contained

await registerVoiceWidget(server, {
  jurisdictionClient,
  relayUrl: config.relayUrl,
  widgetsDir: path.join(__dirname, "dist/widgets"),
});

await registerPulseWidget(server, {
  jurisdictionClient,
  widgetsDir: path.join(__dirname, "dist/widgets"),
});

await registerMeetingPrepWidget(server, {
  jurisdictionClient,
  widgetsDir: path.join(__dirname, "dist/widgets"),
});

await registerIssueCardWidget(server, {
  jurisdictionClient,
  widgetsDir: path.join(__dirname, "dist/widgets"),
});

await registerActionWidget(server, {
  relayUrl: config.relayUrl,
  widgetsDir: path.join(__dirname, "dist/widgets"),
});

// ─────────── HTTP Server ───────────

const app = express();
app.use(cors());
app.use(express.json());

// MCP endpoint
app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

// Health check
app.get("/health", (req, res) => {
  res.json({ status: "ok", widgets: ["voice", "pulse", "meeting_prep", "issue_card", "action"] });
});

// ─────────── Start Server ───────────

app.listen(config.port, () => {
  console.log(`
╭──────────────────────────────────────────────────────╮
│  CivicOS MCP Apps Server                             │
├──────────────────────────────────────────────────────┤
│  MCP Endpoint:  http://localhost:${config.port}/mcp${" ".repeat(Math.max(0, 15 - config.port.toString().length))}│
│  Jurisdiction:  ${config.jurisdictionMcpUrl.slice(0, 35)}...  │
│  Relay:         ${config.relayUrl.slice(0, 35)}...  │
╰──────────────────────────────────────────────────────╯

Test with: npx cloudflared tunnel --url http://localhost:${config.port}
Then add the URL as a custom connector in Claude.ai
`);
});

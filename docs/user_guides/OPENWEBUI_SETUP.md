# Open WebUI Setup Guide

This guide explains how to set up [Open WebUI](https://docs.openwebui.com/) with CivicOS MCP servers, giving you AI-powered access to local civic data and identity/signing tools.

## Overview

> **Developer note:** CivicOS maintains a private Open WebUI fork at `github.com/lounsburynw/civicos-openwebui`. In the monorepo, it's symlinked as `apps/civicos-openwebui-fork/`. Changes to Open WebUI components are committed to that separate repo, not the civicos monorepo. The `/commit` command handles both repos automatically.

Open WebUI is a self-hosted AI chat interface that supports MCP (Model Context Protocol) servers. With this setup, you can:

- Query civic data (meetings, decisions, issues, legislation)
- Create and manage your civic identity
- Sign civic actions (voice support/oppose, commitments)

**Architecture:**

```
Open WebUI (your browser)
    │
    ├── LLM Backend (Claude API or local Ollama)
    │
    ├── Personal MCP (HTTP) ← localhost:8081
    │   └── Identity and signing tools
    │
    └── Jurisdiction MCP (HTTP) ← san-rafael.civicosproject.org/mcp
        └── Read-only civic data (30 tools)
```

---

## Prerequisites

- **Docker** installed ([Get Docker](https://docs.docker.com/get-docker/))
- **Node.js 18+** (for Personal MCP server)
- **LLM API Key** — Claude API (recommended) or OpenAI API

---

## Step 1: Install Open WebUI

Run Open WebUI using Docker:

```bash
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  -e WEBUI_SECRET_KEY=your-secret-key-here \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

**Important:** Set `WEBUI_SECRET_KEY` to a secure random string. This encrypts stored API keys. If you skip this, tool connections may fail after container restarts.

Access Open WebUI at: **http://localhost:3000**

Create an admin account when prompted.

---

## Step 2: Configure LLM Backend

Open WebUI needs an LLM to process queries. We recommend Claude API for best results with civic data.

### Option A: Claude API (Recommended)

1. Get an API key from [console.anthropic.com](https://console.anthropic.com/)
2. In Open WebUI, go to **Settings → Admin Settings → Connections**
3. Under **OpenAI API**, add a new connection:
   - **URL:** `https://api.anthropic.com/v1`
   - **API Key:** Your Anthropic API key
4. Save and select Claude Sonnet or Opus as your model

### Option B: OpenAI API

1. Get an API key from [platform.openai.com](https://platform.openai.com/)
2. In Open WebUI, go to **Settings → Admin Settings → Connections**
3. Add your OpenAI API key
4. Select GPT-4 or GPT-4o as your model

### Option C: Local Ollama

For fully offline use:

1. Install [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull llama3.2`
3. Open WebUI auto-detects local Ollama on port 11434

---

## Step 3: Add Jurisdiction MCP (Read-Only Civic Data)

The Jurisdiction MCP provides read-only access to San Rafael civic data: meetings, decisions, issues, legislation, and more.

> **Note:** Open WebUI's MCP Streamable HTTP support has known issues (see [GitHub #14776](https://github.com/open-webui/open-webui/discussions/14776)). We recommend using **OpenAPI mode** for reliable integration.

### Recommended: OpenAPI Mode

1. Go to **Settings → Admin Settings → External Tools**
2. Click **+ Add Connection**
3. Configure:
   - **Type:** OpenAPI
   - **URL:** `https://lounsburynw--civicos-san-rafael-mcpserver-fastapi-app.modal.run/openapi.json`
   - **Authentication:** None
4. Click **Import**

### Alternative: MCP Mode (may not work reliably)

1. Go to **Settings → Admin Settings → External Tools**
2. Click **+ Add Server**
3. Configure:
   - **Type:** MCP (Streamable HTTP)
   - **URL:** `https://lounsburynw--civicos-san-rafael-mcpserver-fastapi-app.modal.run`
   - **Authentication:** None
4. Click **Save**

**Troubleshooting MCP mode:** If you see "Failed to import", try OpenAPI mode instead. Open WebUI's MCP implementation is actively being improved.

### Test the Connection

In a new chat, try:

> "What meetings are coming up in San Rafael?"

The LLM should call the `get_upcoming_meetings` tool and return scheduled meetings.

### Available Tools (30 total)

| Category | Tools | Example Query |
|----------|-------|---------------|
| Meetings | `get_upcoming_meetings`, `search_meeting_history`, `prepare_for_meeting` | "What's on the agenda for January 21st?" |
| Decisions | `what_happened`, `get_decision_details` | "What did the council decide about housing?" |
| Issues | `find_similar_issues`, `query_issues` | "Show potholes reported on 4th Street" |
| Legislation | `search_regulatory_stack`, `what_applies` | "What laws apply to ADUs in San Rafael?" |
| Overview | `city_pulse`, `get_voice_counts` | "What's the community pulse on the bike lane proposal?" |

---

## Step 4: Set Up Personal MCP (Identity & Signing)

The Personal MCP manages your civic identity and signing keys.

### Option A: Use Hosted Server (Recommended)

For the easiest setup, use the hosted Personal MCP:

1. Go to **Settings → Admin Settings → External Tools**
2. Click **+ Add Server**
3. Configure:
   - **Type:** MCP (Streamable HTTP)
   - **URL:** `https://civicos-personal-mcp--personal-mcp-server-web.modal.run/mcp`
   - **Authentication:** None
4. Click **Save**

### Option B: Run Locally

For development or if you want full control over your keys:

#### Clone and Build

```bash
# Clone the repository
git clone https://github.com/lounsburynw/civicos.git
cd civicos

# Install dependencies
cd apps/civicos-personal-mcp
npm install
npm run build
```

#### Start the Server

```bash
npm run start:http
```

The server runs at **http://localhost:8081**

Verify it's running:

```bash
curl http://localhost:8081/health
# Returns: {"status":"healthy","server":"civicos-personal-mcp",...}
```

#### Add to Open WebUI

1. Go to **Settings → Admin Settings → External Tools**
2. Click **+ Add Server**
3. Configure:
   - **Type:** MCP (Streamable HTTP)
   - **URL:** `http://host.docker.internal:8081/mcp`
   - **Authentication:** None
4. Click **Save**

**Note:** Use `host.docker.internal` instead of `localhost` because Open WebUI runs in Docker and needs to reach your host machine.

### Available Tools (17 total)

**Identity Tools:**

| Tool | Description |
|------|-------------|
| `identity_status` | Check current identity (tier, public key, lock status) |
| `identity_create` | Create identity (Easy: passkey, Private: password + recovery phrase) |
| `identity_import` | Import existing identity |
| `identity_unlock` | Unlock identity (Easy: biometric, Private: password) |
| `identity_lock` | Lock identity (clear keys from memory) |

**Signing Tools:**

| Tool | Description |
|------|-------------|
| `sign_voice` | Sign support/oppose/watching on a decision |
| `sign_commitment` | Sign commitment to take action |
| `sign_completion` | Sign completion report for an action |
| `sign_event` | Sign arbitrary Nostr event |

**Context & Personalization Tools:**

| Tool | Description |
|------|-------------|
| `set_neighborhood` | Set your neighborhood for proximity filtering |
| `set_interests` | Set civic interest topics (housing, transportation, etc.) |
| `follow_item` | Follow a decision, meeting, issue, or topic |
| `unfollow_item` | Stop following an item |
| `get_context` | View your current personalization settings |
| `get_relevant_now` | Get items relevant to you based on interests |
| `get_suggestions` | Get proactive civic recommendations |
| `explain_relevance` | Explain why an item matters to you |

---

## Step 5: Create Your Civic Identity

In a chat with both MCP servers connected:

### Option A: Easy Tier (Recommended for most users)

> "Create an easy identity with my email user@example.com"

Uses TouchID/FaceID via WebAuthn passkeys. No password to remember. Same email + same device passkey = same identity.

### Option B: Private Tier (Full control)

> "Create a private identity with password mypassword123"

The LLM will call `identity_create` and return:

1. Your **public key** (npub format)
2. A **12-word recovery phrase**

**CRITICAL:** Save the recovery phrase securely. It cannot be recovered if lost.

### Unlock to Sign

Before signing actions, unlock your identity:

- **Easy tier:** "Unlock my identity" (triggers biometric prompt)
- **Private tier:** "Unlock my identity with password [your-password]"

---

## Step 6: Test the Full Flow

### Query Civic Data

> "What's happening with the bike lane proposal on 4th Street?"

### Voice Support

> "I want to support the bike lane proposal"

The LLM will:
1. Query the Jurisdiction MCP for the proposal
2. Check your identity status (Personal MCP)
3. Sign a voice event if unlocked
4. Return confirmation with community counts

### Check Community Sentiment

> "How many people support vs oppose the bike lane?"

---

## Troubleshooting

### "Failed to connect to MCP server"

1. Verify the server is running: `curl http://localhost:8081/health`
2. For Docker, use `host.docker.internal` not `localhost`
3. Check authentication is set to "None"

### "Identity not found" or signing fails

1. Create identity: "Create a civic identity"
2. Unlock before signing: "Unlock my identity with password X"

### Tools don't appear in Open WebUI

1. Verify server type is **MCP (Streamable HTTP)** (not OpenAPI)
2. Try adding a single comma `,` to the Function Name Filter List
3. Restart Open WebUI: `docker restart open-webui`

### Personal MCP won't start

```bash
# Check for port conflicts
lsof -i :8081

# Try a different port
PORT=8082 npm run start:http
```

### Connection works but queries fail

1. Check LLM is configured (Step 2)
2. Verify model can use tools (Claude Sonnet/Opus, GPT-4)
3. Check Open WebUI logs: `docker logs open-webui`

---

## Security Notes

### Personal MCP (Local)

- Keys are encrypted with your password (PBKDF2 + AES-256-GCM)
- Keys never leave your machine
- Lock your identity when not in use: "Lock my identity"

### Jurisdiction MCP (Remote)

- Read-only access to public civic data
- No authentication required
- No personal data stored

### Open WebUI

- Set `WEBUI_SECRET_KEY` to protect stored API keys
- Admin account credentials are stored locally
- Consider running behind a reverse proxy for HTTPS

---

## Advanced: Running Both Servers

For development or testing, you can run both MCP servers locally.

### Start Jurisdiction MCP

```bash
cd civicos
source civicos-env/bin/activate
cd apps/civicos-mcp
python server.py --http --port 8080
```

### Update Open WebUI

Change Jurisdiction MCP URL to: `http://host.docker.internal:8080/mcp`

---

## Next Steps

- **[MCP Setup Guide](MCP_SETUP_GUIDE.md)** — Claude Desktop configuration
- **[Getting Started](GETTING_STARTED.md)** — What you can do with CivicOS
- **[Feature Guide](FEATURE_GUIDE.md)** — Detailed feature documentation

---

## Getting Help

- Open WebUI docs: [docs.openwebui.com](https://docs.openwebui.com/)
- MCP protocol: [modelcontextprotocol.io](https://modelcontextprotocol.io/)
- CivicOS issues: [github.com/lounsburynw/civicos/issues](https://github.com/lounsburynw/civicos/issues)

---

## Sources

- [Open WebUI MCP Documentation](https://docs.openwebui.com/features/mcp/)
- [Open WebUI MCP Support](https://docs.openwebui.com/features/plugin/tools/openapi-servers/mcp/)
- [mcpo - MCP-to-OpenAPI Proxy](https://github.com/open-webui/mcpo)

# MCP Server Setup Guide

This guide explains how to connect CivicOS's MCP (Model Context Protocol) server to AI assistants, giving you AI-powered access to local civic data, meeting history, legislation, and community coordination tools.

## What is MCP?

MCP lets AI assistants like Claude and ChatGPT access external tools and data. CivicOS provides a unified MCP server that exposes 25+ tools for querying civic data, drafting public comments, and coordinating community voice.

Once connected, you can ask your AI assistant questions like "What issues have been reported on 5th Avenue?" and it will query live civic data to answer.

---

## Option 1: Remote MCP (No Installation)

Connect directly to the hosted CivicOS MCP server — no local setup required.

=== "Claude (claude.ai or Desktop)"

    1. Go to **Settings > Connectors > Add Connector**
    2. Enter: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What's on the San Rafael city council agenda?"*

=== "ChatGPT (Plus/Team)"

    1. **Settings > Connectors > Enable developer mode**
    2. Add connector: `https://san-rafael.civicosproject.org/mcp`
    3. Ask: *"What has San Rafael decided about housing?"*

---

## Option 2: Local MCP Server

Run the MCP server locally for development or offline use.

### Prerequisites

- **Python 3.10+** installed
- **Git** installed

### Step 1: Clone and Set Up CivicOS

```bash
# Clone the repository
git clone https://github.com/lounsburynw/civicos.git
cd civicos

# Create and activate virtual environment
python3 -m venv civicos-env
source civicos-env/bin/activate

# Install dependencies
pip install -e packages/civicos
pip install -e apps/civicos-mcp
```

### Step 2: Configure Environment

Create or update your `.env` file in the project root:

```bash
# Required for database access
DATABASE_URL=your_postgres_connection_string

# Required for AI-powered features (embeddings, comment drafting)
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### Step 3: Configure Claude Desktop

Claude Desktop reads MCP server configuration from a JSON file.

| OS | Config Location |
|----|-----------------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add the CivicOS MCP server:

```json
{
  "mcpServers": {
    "civicos": {
      "command": "/path/to/civicos/civicos-env/bin/python",
      "args": ["/path/to/civicos/apps/civicos-mcp/server.py"],
      "cwd": "/path/to/civicos",
      "env": {
        "CIVICOS_JURISDICTION": "city-san-rafael"
      }
    }
  }
}
```

**Important:** Replace `/path/to/civicos` with your actual installation path.

### Step 4: Restart Claude Desktop

1. Quit Claude Desktop completely (Cmd+Q on macOS)
2. Reopen Claude Desktop
3. The MCP server will start automatically

### Step 5: Verify the Connection

Try these prompts in Claude Desktop:

> "What meetings are coming up in San Rafael?"

> "What has the council decided about housing?"

> "What does the municipal code say about ADUs?"

---

## Available Tools

Once connected, your AI assistant has access to these capabilities:

### Query Tools

| Tool | Description | Example |
|------|-------------|---------|
| Search meeting history | Past decisions, votes, outcomes | *"What happened with the bike lane proposal?"* |
| Get upcoming meetings | Future meetings and agendas | *"What's on the agenda this month?"* |
| Search transcripts | What was said in meetings | *"What did residents say about traffic?"* |
| Search legislation | Municipal code, state/federal law | *"What laws apply to ADUs?"* |
| Search issues | SeeClickFix/311 complaints | *"What issues are on Lincoln Ave?"* |
| Search budget | City budget by department | *"How much is spent on public safety?"* |
| Search agenda packets | Full-text PDF search | *"Find staff reports about Downtown Precise Plan"* |

### 311 Analytics Tools

| Tool | Description |
|------|-------------|
| Aggregate stats | Issue counts, types, status breakdown |
| Geographic search | Issues near a specific address |
| Trend analysis | Issue types increasing or decreasing |
| Resolution tracking | How fast issues get resolved |
| Neighborhood reports | Full report for a zip code |

### Action Tools

| Tool | Description |
|------|-------------|
| Draft public comment | Generate a comment grounded in civic data |
| Prepare for meeting | Background context, talking points, logistics |

---

## REST API Access (No MCP Required)

Query civic data programmatically via the REST API. No local installation required.

### Get an API Key

```bash
curl -X POST https://san-rafael.civicosproject.org/api/keys/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Your Name", "email": "you@example.com"}'
```

Save the returned `raw_key` — it's shown once and cannot be retrieved again.

### Make Requests

```bash
# Search meeting history
curl -X POST https://san-rafael.civicosproject.org/api/tools/search-meeting-history \
  -H "Authorization: Bearer cvk_live_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing"}'

# List all available tools
curl https://san-rafael.civicosproject.org/api/tools/
```

### Rate Limits

| Access | Rate Limit |
|--------|-----------|
| No API key (public) | 60 requests/min per IP |
| Free tier key | 60 requests/min per key |

Full OpenAPI spec: `https://san-rafael.civicosproject.org/openapi.json`

---

## Troubleshooting

### Claude doesn't show MCP tools

1. **Check config syntax** — Ensure your JSON is valid (no trailing commas)
2. **Verify paths** — Use absolute paths, not relative ones like `~/`
3. **Check Python path** — Use the full path to the Python in your virtual environment
4. **Restart Claude** — Quit completely and reopen

### Tools work but return no data

1. **Check environment** — Verify `DATABASE_URL` is set in your `.env`
2. **Check jurisdiction** — The server defaults to `city-san-rafael`

### Server crashes on startup

Test the server directly:

```bash
cd /path/to/civicos
source civicos-env/bin/activate
python apps/civicos-mcp/server.py
```

---

## Next Steps

- **[Getting Started](GETTING_STARTED.md)** — Learn what you can do with CivicOS
- **[Admin Setup Guide](ADMIN_SETUP_GUIDE.md)** — Set up CivicOS for a new jurisdiction

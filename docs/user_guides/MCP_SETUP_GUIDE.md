# MCP Server Setup Guide

This guide explains how to connect Civic's MCP (Model Context Protocol) servers to Claude Desktop, giving you AI-powered access to local civic data and public comment drafting tools.

## What is MCP?

MCP lets AI assistants like Claude access external tools and data. Civic provides two MCP servers:

1. **civic-issues** — Query local civic complaints and issues (SeeClickFix data)
2. **civicos-server** — Draft public comments for city council meetings

Once connected, you can ask Claude questions like "What issues have been reported on 5th Avenue?" and it will query live civic data to answer.

---

## Prerequisites

- **Claude Desktop** (download from [claude.ai/download](https://claude.ai/download))
- **Python 3.10+** installed
- **Git** installed
- **OpenAI API key** (optional, for AI-powered comment drafting)

---

## Step 1: Clone and Set Up Civic

If you haven't already installed Civic:

```bash
# Clone the repository
git clone https://github.com/your-org/civic.git
cd civic

# Create and activate virtual environment
python3 -m venv civic-env
source civic-env/bin/activate

# Install dependencies
pip install -e packages/civic
pip install -e apps/civic-mcp
```

If you already have Civic installed, activate the environment:

```bash
cd civic
source civic-env/bin/activate
```

---

## Step 2: Configure Environment Variables

Create or update your `.env` file in the project root:

```bash
# Required for AI-powered comment generation (optional)
OPENAI_API_KEY=sk-your-openai-api-key-here
```

Without an OpenAI key, the `compose_public_comment` tool will use template-based comments instead of AI-generated ones. The `civic-issues` server works without any API keys.

---

## Step 3: Find Your Civic Path

You'll need the absolute path to your Civic installation:

```bash
# From the civic directory, get the full path
pwd
```

Note this path (e.g., `/Users/yourname/projects/civic`). You'll use it in the next step.

---

## Step 4: Configure Claude Desktop

Claude Desktop reads MCP server configuration from a JSON file. The location depends on your operating system.

### Find Your Config File

| OS | Config Location |
|----|-----------------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Create or Edit the Config

If the file doesn't exist, create it. Add the Civic MCP servers:

```json
{
  "mcpServers": {
    "civic-issues": {
      "command": "/path/to/civic/civic-env/bin/python",
      "args": ["/path/to/civic/apps/civic-mcp/civic_issues.py"],
      "cwd": "/path/to/civic"
    },
    "civicos-server": {
      "command": "/path/to/civic/civic-env/bin/python",
      "args": ["/path/to/civic/apps/civic-mcp/civic_server.py"],
      "cwd": "/path/to/civic",
      "env": {
        "OPENAI_API_KEY": "sk-your-openai-api-key-here"
      }
    }
  }
}
```

**Important:** Replace `/path/to/civic` with your actual path from Step 3.

### Example (macOS)

If your Civic installation is at `/Users/jane/projects/civic`:

```json
{
  "mcpServers": {
    "civic-issues": {
      "command": "/Users/jane/projects/civic/civic-env/bin/python",
      "args": ["/Users/jane/projects/civic/apps/civic-mcp/civic_issues.py"],
      "cwd": "/Users/jane/projects/civic"
    },
    "civicos-server": {
      "command": "/Users/jane/projects/civic/civic-env/bin/python",
      "args": ["/Users/jane/projects/civic/apps/civic-mcp/civic_server.py"],
      "cwd": "/Users/jane/projects/civic",
      "env": {
        "OPENAI_API_KEY": "sk-proj-abc123..."
      }
    }
  }
}
```

---

## Step 5: Restart Claude Desktop

After saving the config file:

1. Quit Claude Desktop completely (Cmd+Q on macOS, or exit from system tray)
2. Reopen Claude Desktop
3. The MCP servers will start automatically

---

## Step 6: Verify the Connection

In Claude Desktop, you should see MCP tools available. Try these prompts:

### Test civic-issues

> "List the jurisdictions with civic issue data"

Claude should call `list_jurisdictions()` and show you available cities.

### Test with a query

> "What pothole issues have been reported in San Rafael?"

Claude should call `query_issues()` and return actual civic complaint data.

### Test civicos-server

> "Help me draft a public comment supporting the bike lane proposal"

Claude should call `compose_public_comment()` and generate a draft.

---

## Available Tools

Once connected, Claude has access to these tools:

### civic-issues Server

| Tool | Description | Example Use |
|------|-------------|-------------|
| `query_issues` | Search civic complaints by location, type, or status | "What issues are on Lincoln Ave?" |
| `get_issue_stats` | Get aggregate statistics for a jurisdiction | "How many open issues in San Rafael?" |
| `get_street_issues_summary` | Analyze issues for a specific street | "Summarize 5th Avenue problems" |
| `list_jurisdictions` | List all available jurisdictions | "What cities have data?" |

### civicos-server Server

| Tool | Description | Example Use |
|------|-------------|-------------|
| `compose_public_comment` | Draft a public comment for an agenda item | "Help me write a comment about the housing proposal" |
| `get_comment_guidelines` | Get submission rules for public comments | "How do I submit a comment in San Rafael?" |

---

## Example Prompts

Here are prompts that work well with the Civic MCP servers:

**Finding Issues**
- "What issues have neighbors reported on my street?"
- "Show me open pothole complaints in San Rafael"
- "What are the most common issue types in the city?"

**Analyzing Patterns**
- "Which streets have the most complaints?"
- "How many issues are open vs closed?"
- "What's the issue breakdown by type?"

**Preparing to Participate**
- "Help me write a public comment opposing the development on 4th Street"
- "Draft a letter supporting the new bike lanes"
- "What are the guidelines for speaking at city council?"

---

## Troubleshooting

### Claude doesn't show MCP tools

1. **Check config syntax** — Ensure your JSON is valid (no trailing commas, proper quotes)
2. **Verify paths** — Use absolute paths, not relative ones like `~/`
3. **Check Python path** — Use the full path to the Python in your virtual environment
4. **Restart Claude** — Quit completely and reopen

### "Command not found" or path errors

Make sure you're using the Python from your virtual environment:
```bash
# Correct: full path to venv Python
"/Users/jane/projects/civic/civic-env/bin/python"

# Wrong: system Python
"python3"
```

### Tools work but return no data

1. **Check database** — Verify `data/civic_state.db` exists
2. **Refresh data** — Run the data extraction scripts if database is empty
3. **Check jurisdiction** — Use `list_jurisdictions()` to see available data

### AI comments say "template fallback"

This means the OpenAI key isn't configured:
1. Check `OPENAI_API_KEY` in your config's `env` section
2. Verify the key is valid
3. Template comments still work, just less personalized

### Server crashes on startup

Check the logs:
```bash
# Test the server directly
cd /path/to/civic
source civic-env/bin/activate
python apps/civic-mcp/civic_issues.py
```

If it runs without errors, the issue is in Claude's configuration.

---

## Advanced: HTTP Mode

For integration with LangGraph or other systems, run the servers in HTTP mode:

```bash
# civic-issues on port 8080
python apps/civic-mcp/civic_issues.py --http --port 8080

# civicos-server on port 8081
python apps/civic-mcp/civic_server.py --http --port 8081
```

Connect your MCP client to `http://localhost:8080` or `http://localhost:8081`.

---

## Next Steps

- **[Getting Started](GETTING_STARTED.md)** — Learn what you can do with Civic
- **[Admin Setup Guide](ADMIN_SETUP_GUIDE.md)** — Set up Civic for a new jurisdiction

---

## Getting Help

Having trouble?

- Check the [MCP documentation](https://modelcontextprotocol.io/docs)
- Report issues at the Civic repository
- Contact your local Civic administrator

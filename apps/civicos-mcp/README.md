# MCP CivicOS Engagement Server

Production MCP (Model Context Protocol) server exposing the full CivicOS API for AI-assisted civic engagement. Enables users of Claude, ChatGPT, and other AI assistants to query San Rafael civic data.

## Overview

**Current State**: 22 MCP primitives (15 tools + 5 resources + 2 prompts) covering:
- Meeting search, upcoming events, agenda packets
- Decision history, voting records, public testimony
- Budget queries, federal/state funding flows
- SeeClickFix issues, municipal code, legislation
- Meeting preparation workflows

**Distribution Channels**:
| Platform | Method | Status |
|----------|--------|--------|
| Claude Desktop | Local MCP (stdio) | Working |
| Claude.ai web | Remote MCP (OAuth) | Ready to deploy |
| Claude Mobile | Remote MCP (same) | Ready to deploy |
| ChatGPT | Custom GPT + Actions | Planned |

## Quick Start

### Local (Claude Desktop)

```bash
# Activate virtual environment
source civic-env/bin/activate

# Run the server
python civicos_server.py

# Configure Claude Desktop (~/.config/claude/config.json on macOS)
```

**Claude Desktop config**:
```json
{
  "mcpServers": {
    "civic-san-rafael": {
      "command": "python",
      "args": ["/path/to/civic/apps/civicos-mcp/civicos_server.py"]
    }
  }
}
```

### Remote (Claude.ai Web + Mobile)

Deploy the MCP server remotely to enable Claude.ai web and mobile access.

**Requirements**:
1. Host publicly (Railway, Fly.io, Render, Vercel)
2. Implement OAuth 2.0 authentication
3. Support SSE or Streamable HTTP transport
4. Configure Claude.ai connector URL

**OAuth callback**: `https://claude.ai/api/mcp/auth_callback`

**User setup** (after deployment):
1. Open Claude.ai > Settings > Connectors
2. Add connector URL
3. Authorize via OAuth
4. Tools appear in Claude conversations

See [Building Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers) for details.

## Distribution Strategy

### MCP Registry Listing

Register on official and community directories for discoverability:

| Directory | URL | Priority |
|-----------|-----|----------|
| Official MCP Registry | [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/) | High |
| MCP.so | [mcp.so](https://mcp.so/) | High |
| MCPServers.org | [mcpservers.org](https://mcpservers.org/) | Medium |

### ChatGPT Custom GPT

Build "CivicOS San Rafael" GPT with Actions calling the REST API:

```
Custom GPT Structure:
- Name: CivicOS San Rafael
- System prompt: San Rafael civic engagement assistant
- Actions: OpenAPI spec -> civic-services REST API
  - /api/meetings (whats_next)
  - /api/decisions (what_happened)
  - /api/issues (whos_with_me)
  - /api/search (multi-corpus)
- Conversation starters:
  - "What's on the city council agenda this week?"
  - "What decisions have been made about housing?"
  - "Are there complaints about traffic on 4th Street?"
```

### Linkbacks to Web App

All AI responses include deep links to the main web app:

```
Found 3 decisions about "housing permits"...

View full details: https://civic.example.com/decisions/dec-123
Browse all: https://civic.example.com/search?q=housing+permits
```

## MCP Primitives

### Tools (15)

| Tool | Description |
|------|-------------|
| `compose_public_comment` | Generate draft public comment for agenda item |
| `get_comment_template` | Get comment template by stance |
| `get_comment_guidelines` | Get submission guidelines for jurisdiction |
| `get_meeting_opportunities` | Get upcoming civic engagement opportunities |
| `search_regulatory_stack` | Search municipal code + legislation |
| `search_meeting_history` | Search past decisions via `what_happened()` |
| `find_similar_issues` | Find related SeeClickFix issues via `whos_with_me()` |
| `search_agenda_packets` | Search PDF chunks from agenda packets |
| `search_budget` | Query budget by department or keyword |
| `get_upcoming_meetings` | Get meetings via `whats_next()` |
| `get_voting_record` | Get official's voting history |
| `get_decision_context` | Get context around a specific decision |
| `get_public_testimony` | Get public testimony from transcripts |
| `get_funding_flow` | Trace federal/state funding to local programs |
| `prepare_for_meeting` | Generate meeting prep via `prepare()` |

### Resources (5)

| Resource | Description |
|----------|-------------|
| `civicos://meetings` | Browsable list of recent meetings |
| `civicos://budget/departments` | Budget department listing |
| `civicos://issues/stats` | Issue statistics summary |
| `civicos://corpus/stats` | Data corpus coverage stats |
| `civicos://jurisdiction/info` | Jurisdiction metadata |

### Prompts (2)

| Prompt | Description |
|--------|-------------|
| `meeting-prep` | Guided meeting preparation workflow |
| `research-topic` | Multi-tool topic research workflow |

## Development Status

### Completed
- Full MCP server with 22 primitives (`civicos_server.py`)
- Integration with CivicOS API (PostgreSQL + pgvector)
- Input validation (`civic_input_validator.py`)
- Local Claude Desktop testing

### In Progress
- Remote deployment for Claude.ai web access
- MCP Registry listing
- ChatGPT Custom GPT build

### Planned
- OAuth authentication for remote access
- Desktop Extensions (.mcpb) packaging
- OpenAI Apps SDK integration (when mature)

## Testing

```bash
# Test with MCP Inspector
npx @anthropic-ai/mcp-inspector

# Connect to: python apps/civicos-mcp/civicos_server.py
# Test tools interactively
```

## Dependencies

See `pyproject.toml` for full dependency list. Key requirements:
- `mcp[cli]>=1.13.1` - Model Context Protocol framework
- `httpx` - Async HTTP client for API integration
- `python>=3.10` - Required for MCP SDK

## Development Guidelines

### Code Style
- Use async functions for all external API calls
- Include comprehensive docstrings with parameter descriptions
- Log to stderr only (stdout reserved for MCP protocol)
- Use type hints for all function parameters and returns

### MCP Best Practices
- Tools should be stateless and focused on single actions
- Resources should provide read-only data access
- Error handling should be graceful with informative messages
- All external API calls must be async with proper timeout handling

### Security Considerations
- Never log sensitive user data (email addresses, personal information)
- Validate all input parameters before processing
- Use domain allowlists for email submission endpoints
- Implement proper authentication for production deployment

## Success Metrics

| Metric | Target |
|--------|--------|
| MCP tool usage from Claude users | 5-10% of queries |
| Linkback clicks to web app | 20% of tool responses |
| ChatGPT Custom GPT conversations | 100/week post-launch |

## Related Documentation

- [MCP Integration Strategy](../../docs/critical/MCP_INTEGRATION_STRATEGY.md) - Full distribution strategy
- [Remote MCP docs](https://modelcontextprotocol.io/docs/develop/connect-remote-servers)
- [Building Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)

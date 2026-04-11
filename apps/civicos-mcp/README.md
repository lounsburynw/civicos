# MCP CivicOS Engagement Server

Production MCP (Model Context Protocol) server exposing the full CivicOS API for AI-assisted civic engagement. Enables users of Claude, ChatGPT, and other AI assistants to query San Rafael civic data.

## Overview

**Current State**: 32 MCP primitives (25 tools + 5 resources + 2 prompts) covering:
- Meeting search, upcoming events, agenda packets
- Decision history, voting records, public testimony
- Budget queries, federal/state funding flows
- **311 issue analytics** - aggregate stats, drill-down analysis, pattern discovery
- SeeClickFix semantic search, municipal code, legislation
- Meeting preparation workflows

**Distribution Channels**:
| Platform | Method | Status |
|----------|--------|--------|
| Claude Desktop | Local MCP (stdio) | Working |
| Claude.ai web | Remote MCP (OAuth 2.1) | Working |
| Claude Mobile | Remote MCP (OAuth 2.1) | Working |
| ChatGPT | Custom GPT + Actions | Planned |

## Quick Start

### Local (Claude Desktop)

```bash
# Activate virtual environment
source civicos-env/bin/activate

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

### Production (Modal - Recommended)

Modal provides serverless deployment with automatic scaling and no cold starts.

**Production URL**: `https://san-rafael.civicosproject.org/mcp`

```bash
# Install Modal CLI
pip install modal

# Authenticate
modal token new

# Create secrets
modal secret create civicos-env \
    DATABASE_URL="postgresql://..." \
    RELAY_DATABASE_URL="postgresql://..." \
    CIVICOS_JURISDICTION="city-san-rafael"

# Deploy
modal deploy apps/civicos-mcp/modal_app.py

# Test locally first
modal serve apps/civicos-mcp/modal_app.py
```

### Docker Container

For self-hosted deployments on Docker, Fly.io, or any container platform.

```bash
# Build (from repo root)
docker build -f apps/civicos-mcp/Dockerfile.mcp -t civicos-mcp .

# Run
docker run -p 8080:8080 \
  -e DATABASE_URL="postgresql://..." \
  -e CIVICOS_JURISDICTION="city-san-rafael" \
  civicos-mcp
```

**Endpoints**:
- MCP: `http://localhost:8080/mcp`
- Health: `http://localhost:8080/health`

### Remote (Claude.ai Web + Mobile)

The deployed MCP server supports OAuth 2.1 for Claude.ai Connectors.

**Connect in 2 steps**:
1. Open Claude.ai > Settings > Connectors
2. Add connector URL: `https://san-rafael.civicosproject.org/mcp`
3. Click "Allow" on the CivicOS consent page
4. Tools appear in Claude conversations

**How it works**:
- Claude.ai discovers OAuth metadata via `/.well-known/oauth-protected-resource`
- Dynamic Client Registration creates a session automatically
- PKCE-protected authorization code flow with no password required
- Free tier: public civic data with rate limiting (60 req/min)
- Existing API keys (`cvk_live_*`) continue to work alongside OAuth

**OAuth endpoints** (auto-provisioned on all deployed servers):
- `GET /.well-known/oauth-authorization-server` — Discovery metadata
- `GET /.well-known/oauth-protected-resource` — Resource metadata
- `POST /register` — Dynamic Client Registration
- `GET /authorize` — Consent page
- `POST /token` — Token exchange (authorization_code, refresh_token)

**Other jurisdictions**: Replace `san-rafael` with any deployed jurisdiction
(e.g., `california.civicosproject.org/mcp`, `federal.civicosproject.org/mcp`).

See [Building Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers) for details.

## Architecture

The MCP server uses a modular architecture with shared tool definitions:

```
apps/civicos-mcp/
├── tools/                   # Shared tool definitions
│   ├── __init__.py
│   ├── registry.py         # Tool metadata and registry
│   └── handlers.py         # Tool handler implementations
├── modal_app.py            # Modal deployment (~300 lines)
├── server.py               # Container deployment (FastAPI)
├── civicos_server.py       # Local FastMCP server
├── Dockerfile.mcp          # Container build file
└── requirements-mcp.txt    # Dependencies
```

This design enables:
- **Single source of truth**: Tool definitions in `tools/registry.py`
- **Portable handlers**: Same logic works across all deployment methods
- **Easy extension**: Add tools once, available everywhere

### Tool scope policy

**Before adding a new tool, read
[docs/public/decisions/tool_scope_and_federation.md](../../docs/public/decisions/tool_scope_and_federation.md).**
Every tool must declare a scope policy that answers:

- **Default scope** — what jurisdictions does it query if no scope
  parameter is given? (primary only, primary + parents, primary +
  siblings, or region)
- **Expandable scope** — what optional widening does it accept?
- **Maximum scope** — what ceiling refuses further expansion?

The ADR contains the authoritative scope table for every currently
bound tool. Read-side tools may expand vertically (parent jurisdictions)
and horizontally (sibling jurisdictions / regions) automatically with
results labeled by source. Write-side tools (`compose_public_comment`,
`broadcast_voice`, `broadcast_initiative`, etc.) are **strictly scoped
to the primary jurisdiction** of the server — they refuse
cross-jurisdiction operation because they route to specific clerks,
portals, and relays keyed to one authoritative operator.

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
- Actions: OpenAPI spec -> civicos-services REST API
  - /api/meetings (whats_next)
  - /api/decisions (what_happened)
  - /api/issues (issue search)
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

### Tools (25)

| Tool | Description |
|------|-------------|
| `compose_public_comment` | Generate draft public comment for agenda item |
| `get_comment_template` | Get comment template by stance |
| `get_comment_guidelines` | Get submission guidelines for jurisdiction |
| `get_meeting_opportunities` | Get upcoming civic engagement opportunities |
| `search_regulatory_stack` | Search municipal code + legislation |
| `search_meeting_history` | Search past decisions via `what_happened()` |
| `find_similar_issues` | Find related SeeClickFix issues |
| `get_issue_analytics` | **311 analytics**: aggregate stats by type/status/location/time |
| `query_issue_data` | **311 drill-down**: group/filter with custom parameters |
| `get_issue_sample` | **311 patterns**: raw issue records for content analysis |
| `get_issue_resolution_stats` | **311 accountability**: resolution rates, time to fix |
| `find_issues_near_address` | **311 geo**: issues within radius of address |
| `detect_trends` | **311 trends**: what's increasing/decreasing |
| `find_repeat_issues` | **311 accountability**: recurring problems at same location |
| `get_seasonal_patterns` | **311 patterns**: monthly distribution analysis |
| `generate_neighborhood_report` | **311 report**: comprehensive zip code summary |
| `compare_zip_codes` | **311 comparison**: analyze multiple neighborhoods |
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
- Full MCP server with 32 primitives (`civicos_server.py`)
- Integration with CivicOS API (PostgreSQL + pgvector)
- 311 analysis suite (10 tools): analytics, trends, geo-search, accountability, reports
- Input validation (`civicos_input_validator.py`)
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

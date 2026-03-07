# MCP CivicOS Engagement Server

Production MCP (Model Context Protocol) server exposing the full CivicOS API for AI-assisted civic engagement. Enables users of Claude, ChatGPT, and other AI assistants to query San Rafael civic data.

## Overview

**Current State**: 49 MCP tools covering:
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
| Claude.ai web | Remote MCP (OAuth) | Ready to deploy |
| Claude Mobile | Remote MCP (same) | Ready to deploy |
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

Deploy the MCP server remotely to enable Claude.ai web and mobile access.

**Requirements**:
1. Host publicly (Modal, Docker, or container platform)
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

## MCP Tools (49)

### Core Civic Data

| Tool | Description |
|------|-------------|
| `get_started` | Welcome overview for new users |
| `city_pulse` | Structured city activity data (meetings, decisions, issues) |
| `get_upcoming_meetings` | Upcoming meetings via `whats_next()` |
| `search_meeting_history` | Past decisions via `what_happened()` |
| `search_regulatory_stack` | Municipal code + state/federal legislation |
| `get_public_testimony` | Transcript excerpts on a topic |
| `search_agenda_packets` | PDF chunks from agenda packets |
| `get_voting_record` | Official's voting history |
| `get_decision_context` | Context around a specific decision |
| `decision_detail` | Structured decision detail with testimony |
| `get_item_context` | Comprehensive context assembly for any civic item |

### Public Comment

| Tool | Description |
|------|-------------|
| `compose_public_comment` | Draft public comment for agenda item |
| `get_comment_template` | Fill-in-the-blank template by stance |
| `get_comment_guidelines` | Submission guidelines for jurisdiction |
| `prepare_for_meeting` | Meeting prep via `prepare()` |

### 311 / SeeClickFix Analytics (12 tools)

| Tool | Description |
|------|-------------|
| `find_similar_issues` | Related issues via `whos_with_me()` |
| `get_issue_analytics` | Aggregate stats by type/status/location/time |
| `get_issue_trends` | Issue trends over time |
| `query_issue_data` | Flexible group/filter queries |
| `get_issue_sample` | Raw issue records for analysis |
| `get_issue_resolution_stats` | Resolution rates, time to fix |
| `find_issues_near_address` | Issues within radius of address |
| `geo_search_issues` | Geographic area search |
| `detect_trends` | Significant trend detection |
| `find_repeat_issues` | Recurring problems at same location |
| `get_seasonal_patterns` | Monthly distribution analysis |
| `compare_zip_codes` | Multi-neighborhood comparison |
| `neighborhood_report` | Comprehensive zip code summary |

### Legislation & Federal Data

| Tool | Description |
|------|-------------|
| `search_legislation` | State/federal bill search |
| `get_bill_detail` | Full bill detail with sponsors and leverage points |
| `get_leverage_points` | Bills where citizens can take action |
| `search_executive_orders` | Executive order search |
| `get_recent_executive_orders` | Recently signed orders |
| `get_open_comment_periods` | Federal rules with open comment periods |
| `search_federal_rules` | Federal rulemaking document search |
| `get_upcoming_hearings` | Legislative committee hearings |
| `get_governors_desk` | Bills awaiting governor's signature |

### Budget & Finance

| Tool | Description |
|------|-------------|
| `search_budget` | Budget by department or keyword |
| `get_funding_flow` | Federal → state → city funding trace |
| `get_federal_expenditures` | Single Audit (FAC) expenditure data |
| `get_intergovernmental_revenue` | CA State Controller revenue data |

### Coordination (Relay)

| Tool | Description |
|------|-------------|
| `get_voice_counts` | Community voice counts for an entity |
| `prepare_voice` | Prepare voice payload for signing |
| `broadcast_voice` | Submit signed voice to relay |
| `subscribe_to_topic` | Subscribe to topic notifications via relay |
| `prepare_initiative` | Prepare initiative for signing |
| `broadcast_initiative` | Submit signed initiative to relay |
| `list_initiatives` | List community-created initiatives |
| `list_relays` | List known relay nodes |

## Development Status

### Completed
- 49 MCP tools covering civic data, legislation, 311, budget, and coordination
- Integration with CivicOS API (PostgreSQL + pgvector)
- Remote MCP deployment on Modal (Claude.ai + ChatGPT connector)
- 311 analysis suite (12 tools)
- Legislation suite (9 tools) including leverage points and comment periods
- Relay coordination tools (8 tools)

### Planned
- MCP Registry listing
- Desktop Extensions (.mcpb) packaging

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

# MCP Server Setup

The CivicOS MCP server exposes 40+ civic data tools for AI assistants like Claude and ChatGPT.

## Connect to Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "civicos": {
      "url": "https://<deployment-url>/mcp/"
    }
  }
}
```

## Available Tools

### Core Civic (10 tools)
- `search_meeting_history` — Past meetings and decisions with transcripts
- `get_upcoming_meetings` — Upcoming council meetings
- `find_similar_issues` — Community issues via 311/SeeClickFix
- `search_regulatory_stack` — Local, state, and federal laws on a topic
- `compose_public_comment` — Context for writing public comments
- `city_pulse` — Structured city activity snapshot (meetings, decisions, issues)
- `get_issue_analytics` — 311 aggregate statistics
- `get_issue_trends` — Issue trends over time
- `search_budget` — City budget by department
- `get_public_testimony` — Transcript excerpts on a topic

### 311 Analysis (9 tools)
- `query_issue_data` — Flexible 311 query with grouping and filtering
- `get_issue_resolution_stats` — Response time and resolution rates
- `detect_trends` — Significant pattern changes
- `get_issue_sample` — Raw issue samples
- `find_issues_near_address` — Geo-based issue search
- `find_repeat_issues` — Locations with recurring problems
- `get_seasonal_patterns` — Seasonal issue patterns
- `compare_zip_codes` — Cross-zip-code analysis
- `neighborhood_report` — Comprehensive neighborhood report

### Council & Voting (3 tools)
- `get_voting_record` — Official voting history
- `get_decision_context` — Decisions with transcript excerpts
- `decision_detail` — Detailed decision with testimony

### Legislation (5 tools)
- `search_legislation` — State/federal bills by topic
- `get_bill_detail` — Full bill text, sponsors, status
- `get_leverage_points` — Bills with citizen action opportunities
- `search_executive_orders` — Executive order search
- `get_recent_executive_orders` — Recent executive orders

### Financial (3 tools)
- `get_funding_flow` — Intergovernmental revenue tracing
- `get_federal_expenditures` — Federal spending data
- `search_budget` — City budget search

### Coordination (5 tools)
- `get_voice_counts` — Voice aggregation by entity
- `subscribe_to_topic` — Topic subscription
- `prepare_voice` — Voice composition and signing
- `broadcast_voice` — Submit voice
- `list_relays` — Available relays

### Initiatives (3 tools)
- `prepare_initiative` — Initiative composition
- `broadcast_initiative` — Submit initiative
- `list_initiatives` — List initiatives

### Engagement (3 tools)
- `get_started` — Welcome overview for new users
- `get_comment_guidelines` — Jurisdiction-specific public comment guidelines
- `get_comment_template` — Comment templates

## Deployment

The MCP server runs on Modal (serverless Python):

```bash
modal deploy apps/civicos-mcp/modal_mcp.py
```

It exposes:
- `/mcp/` — MCP Streamable HTTP (for Claude, ChatGPT)
- `/health` — Health check
- `/api/tools/*` — REST fallback (for Open WebUI)

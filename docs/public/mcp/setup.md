# MCP Server Setup

The CivicOS MCP server exposes 50+ read-only civic data tools for AI assistants like Claude and ChatGPT. Write operations (voices, initiatives, comments) are not available through MCP — they go through the [relay](../relay/overview.md) directly and require Nostr-signed requests.

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

### Core Civic (7 tools)
- `search_meeting_history` — Past meetings and decisions with transcripts
- `get_upcoming_meetings` — Upcoming council meetings
- `find_similar_issues` — Community issues via 311/SeeClickFix
- `search_regulatory_stack` — Local, state, and federal laws on a topic
- `compose_public_comment` — Context for writing public comments
- `city_pulse` — Structured city activity snapshot (meetings, decisions, issues)
- `get_started` — Welcome overview for new users

### 311 Analysis (12 tools)
- `get_issue_analytics` — 311 aggregate statistics
- `get_issue_trends` — Issue trends over time
- `query_issue_data` — Flexible 311 query with grouping and filtering
- `get_issue_resolution_stats` — Response time and resolution rates
- `detect_trends` — Significant pattern changes
- `get_issue_sample` — Raw issue samples
- `find_issues_near_address` — Geo-based issue search
- `find_repeat_issues` — Locations with recurring problems
- `get_seasonal_patterns` — Seasonal issue patterns
- `compare_zip_codes` — Cross-zip-code analysis
- `neighborhood_report` — Comprehensive neighborhood report
- `geo_search_issues` — Geographic issue search by area

### Council & Voting (3 tools)
- `get_voting_record` — Official voting history
- `get_decision_context` — Decisions with transcript excerpts
- `decision_detail` — Detailed decision with testimony

### Legislation & Federal (7 tools)
- `search_legislation` — State/federal bills by topic
- `get_bill_detail` — Full bill text, sponsors, status
- `get_leverage_points` — Bills with citizen action opportunities
- `search_executive_orders` — Executive order search
- `get_recent_executive_orders` — Recent executive orders
- `get_upcoming_hearings` — Congressional hearing schedule
- `get_governors_desk` — Bills awaiting governor signature

### Federal Participation (2 tools)
- `get_open_comment_periods` — Open federal rulemaking comment periods
- `search_federal_rules` — Federal rules and regulations

### Financial (4 tools)
- `search_budget` — City budget search
- `get_funding_flow` — Intergovernmental revenue tracing
- `get_federal_expenditures` — Federal spending data
- `get_intergovernmental_revenue` — Federal/state/county revenue

### Coordination (3 tools, read-only)
- `get_voice_counts` — Voice aggregation by entity
- `list_relays` — Available relays
- `list_initiatives` — List initiatives

### Participation (5 tools)
- `get_public_testimony` — Transcript excerpts on a topic
- `search_agenda_packets` — Agenda packet PDF search
- `prepare_for_meeting` — Meeting preparation context
- `get_comment_guidelines` — Jurisdiction-specific public comment guidelines
- `get_comment_template` — Comment templates

### Context Assembly (1 tool)
- `get_item_context` — Rich context bundle for any civic item

### Admin (6 tools) — requires `_admin_token`
- `admin_data_status` — Corpus counts, vector coverage, indexing gaps
- `admin_vector_coverage` — Embedding coverage by corpus type
- `admin_system_health` — Backend connectivity status
- `admin_cost_dashboard` — Operating costs by service/time
- `manage_api_keys` — Create, list, revoke API keys
- `query_feedback` — Query user feedback by type/jurisdiction

Admin tools require an `_admin_token` argument validated against the server's `CIVICOS_ADMIN_TOKEN` environment variable. These tools are available at all jurisdiction levels (federal, state, county, city).

### Tool Access by API Tier

Tools are gated by API key tier. Each tier includes all tools from lower tiers (cumulative):

| Tier | Rate Limit | Additional Tools |
|------|-----------|-----------------|
| **open** | 30/min | `city_pulse`, `get_started`, `get_voice_counts`, `list_relays`, `list_initiatives`, `data_provenance` |
| **free** | 60/min | + All read-only civic data (meetings, legislation, budget, issues, voting, executive orders, federal participation) |
| **builder** | 300/min | + Participation tools (`get_public_testimony`, `search_agenda_packets`, `compose_public_comment`, `get_decision_context`, `prepare_for_meeting`, `neighborhood_report`, `get_item_context`) |
| **organization** | 300/min | Same as builder |
| **city** | 600/min | Same as builder |
| **admin** | 1,000/min | + Admin tools (`admin_data_status`, `admin_vector_coverage`, `admin_system_health`, `admin_cost_dashboard`, `manage_api_keys`) |

## Federation

The MCP server is one of two independent services in CivicOS's [federation model](../decisions/federation_domain_architecture.md). Operators can run either or both:

| Component | Direction | Purpose |
|-----------|-----------|---------|
| **MCP Server** | Read-only | Serves civic data queries — meetings, decisions, legislation |
| **[Relay](../relay/overview.md)** | Bidirectional | Coordinates civic participation — voices, actions, subscriptions |

A city government might run only an MCP server to publish authoritative civic data. A neighborhood group might run only a relay to coordinate community voices. A full operator runs both.

When multiple operators serve the same jurisdiction, each can run an MCP server. Clients discover available operators via the [registry](../decisions/federation_domain_architecture.md#discovery-via-registry). Authoritative civic data (meetings, decisions, municipal code) flows outward from the official operator's MCP server; community-generated data (voices, subscriptions) flows between operators via [relay peering](../relay/federation.md).

## Deployment

The MCP server runs on Modal (serverless Python):

```bash
modal deploy apps/civicos-mcp/modal_mcp.py
```

It exposes:
- `/mcp/` — MCP Streamable HTTP (for Claude, ChatGPT)
- `/health` — Health check
- `/api/tools/*` — REST fallback (for Open WebUI)

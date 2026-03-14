# MCP Server Setup

The CivicOS MCP server provides read-only civic data tools for AI assistants like Claude and ChatGPT. Write operations (voices, initiatives, comments) go through the [relay](../relay/overview.md) directly and require Nostr-signed requests.

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

## v2 Query Interface (Recommended)

The v2 interface consolidates civic queries into 5 verbs with server-side composition. Instead of calling 5 separate tools to answer a question, one `civic.search` call fans out across multiple corpora and jurisdictions.

| Verb | Endpoint | Purpose |
|------|----------|---------|
| `civic.search` | `POST /api/v2/civic/search` | Multi-corpus search with cross-jurisdiction support |
| `civic.upcoming` | `POST /api/v2/civic/upcoming` | Upcoming meetings, hearings, comment periods |
| `civic.context` | `POST /api/v2/civic/context` | Deep item context or civic jargon lookup |
| `civic.act` | `POST /api/v2/civic/act` | Participation actions (comment drafting, meeting prep) |
| `civic.explore` | `POST /api/v2/civic/explore` | Discover jurisdictions, corpora, capabilities |

**Cross-jurisdiction queries:** Set `include_parents: true` to include county, state, and federal results. Set `include_siblings: true` to include neighboring cities in the same county.

See [API Reference — v2 Query Interface](../api.md#v2-query-interface-recommended) for full request/response schemas.

## Legacy Tools (v1)

> The following individual tools are still available but are superseded by the v2 query interface. New integrations should use v2 verbs instead.

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

Admin tools require an `_admin_token` argument validated against the server's `CIVICOS_ADMIN_TOKEN` environment variable.

### API Key Rate Limiting

MCP connections are rate-limited per API key (or per IP without a key):

| Tier | Rate Limit |
|------|-----------|
| No key (public) | 60 req/min |
| **open** | 30 req/min |
| **free** | 60 req/min |
| **builder** | 300 req/min |
| **organization** | 300 req/min |
| **city** | 600 req/min |
| **admin** | 1,000 req/min |

Rate limits use a sliding 60-second window, tracked in-memory (resets on server restart).

### Tool Access by API Tier

Tools are assigned to tiers cumulatively — each tier includes all tools from lower tiers:

| Tier | Additional Tools |
|------|-----------------|
| **open** | `city_pulse`, `get_started`, `get_voice_counts`, `list_relays`, `list_initiatives`, `data_provenance` |
| **free** | + All read-only civic data (meetings, legislation, budget, issues, voting, executive orders, federal participation) |
| **builder** | + Participation tools (`get_public_testimony`, `search_agenda_packets`, `compose_public_comment`, `get_decision_context`, `prepare_for_meeting`, `neighborhood_report`, `get_item_context`) |
| **organization** | Same as builder |
| **city** | Same as builder |
| **admin** | + Admin tools (`admin_data_status`, `admin_vector_coverage`, `admin_system_health`, `admin_cost_dashboard`, `manage_api_keys`) |

> **Note:** Tool-level tier enforcement is defined but not yet active at the MCP endpoint level. Currently all authenticated users can access all non-admin tools. Per-tool gating is planned.

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

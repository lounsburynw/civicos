# Quick Start for Builders

Get from zero to querying civic data in under 10 minutes. Three options depending on how you want to consume the data.

## What You'll Build

By the end of this guide, you'll be able to query upcoming meetings, search past decisions, find relevant legislation, and check community voice counts for the San Rafael pilot.

## Option A: REST API

No setup required. Curl against the live API.

**Base URL:** `https://san-rafael.civicosproject.org`

The recommended path is the v2 query interface (see Option C below). Legacy tool endpoints are also available at `/api/tools/{tool_name}`.

```bash
BASE=https://san-rafael.civicosproject.org

# v2: Multi-corpus search (recommended)
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing", "corpus": ["decisions", "legislation", "meetings"]}'

# v2: Upcoming events
curl -X POST "$BASE/api/v2/civic/upcoming" \
  -H "Content-Type: application/json" \
  -d '{"types": ["meetings"], "days": 30}'

# City pulse (open tier — no auth required)
curl "$BASE/api/tools/city-pulse"

# Voice counts (open tier — no auth required)
curl -X POST "$BASE/api/tools/get-voice-counts" \
  -H "Content-Type: application/json" \
  -d '{"entity": "city-san-rafael:mtg-2026-03-10-cc:item-5"}'

# Interactive API docs (Swagger UI)
open "$BASE/docs"
```

### Getting an API Key

A few discovery endpoints work without a key (open tier, 30 req/min). For full access:

| Tier | Rate Limit | How to Get |
|------|-----------|------------|
| **open** | 30 req/min | No key needed |
| **free** | 60 req/min | Contact via GitHub Issues |
| **builder** | 300 req/min | `POST /api/billing/checkout` with `{"tier": "builder", "email": "..."}` |

Key format: `cvk_live_` followed by 32 hex characters. Pass as `Authorization: Bearer <key>`.

## Option B: MCP (Claude Desktop / ChatGPT)

Connect your AI assistant directly to civic data.

**Claude Desktop:** Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "civicos-san-rafael": {
      "url": "https://san-rafael.civicosproject.org/mcp/"
    }
  }
}
```

Restart Claude Desktop. You now have civic data tools including the v2 query interface. Try these prompts:

- "What meetings are coming up in San Rafael?"
- "What has the city council decided about housing?"
- "Show me state legislation related to transportation"
- "What are people saying about the downtown parking proposal?"

For other jurisdictions, add additional MCP server entries pointing at their domains (e.g., `california.civicosproject.org/mcp/`, `federal.civicosproject.org/mcp/`).

See [MCP Server Setup](mcp/setup.md) for the full tool inventory and ChatGPT configuration.

## Option C: v2 Query API

The v2 interface provides server-side composition — one request searches across multiple corpora and jurisdictions.

```bash
# Multi-corpus search (decisions + legislation + meetings in one call)
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KEY" \
  -d '{"query": "housing", "corpus": ["decisions", "legislation", "meetings"]}'

# Cross-jurisdiction search (include county + state results)
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $KEY" \
  -d '{"query": "housing", "corpus": ["decisions"], "include_parents": true}'

# Upcoming events
curl -X POST "$BASE/api/v2/civic/upcoming" \
  -H "Content-Type: application/json" \
  -d '{"types": ["meetings"], "days": 14}'

# Deep context for a specific item (using ref from search results)
curl -X POST "$BASE/api/v2/civic/context" \
  -H "Content-Type: application/json" \
  -d '{"ref": "decision:city-san-rafael:dec-123"}'

# Discover available corpora and capabilities
curl -X POST "$BASE/api/v2/civic/explore" \
  -H "Content-Type: application/json" \
  -d '{"what": "corpora"}'
```

The v2 API returns a stable two-level result structure: an envelope (`type`, `ref`, `title`, `date`, `summary`, `relevance`) plus type-specific `details`. See [API Reference — v2 Query Interface](api.md#v2-query-interface-recommended) for full field documentation.

## Next Steps

- [API Reference](api.md) — full endpoint documentation, return types, error codes
- [MCP Server Setup](mcp/setup.md) — complete tool inventory, tier access, federation
- [Data Dictionary](data-dictionary.md) — field-level schemas for all data types
- [Operator Guide](operator-guide.md) — run your own CivicOS instance for your jurisdiction
- [Nostr Event Schemas](relay/nostr-events.md) — build CivicOS clients in any language

## Rate Limits

REST API: 30-600 req/min depending on tier, 10,000 req/hour ceiling. LLM-powered endpoints limited to 30 req/min. Rate limit headers (`X-RateLimit-*`) are included in every response. See [API Reference — Rate Limiting](api.md#rate-limiting) for details.

# Quick Start for Builders

Get from zero to querying civic data in under 10 minutes. Three options depending on how you want to consume the data.

## What You'll Build

By the end of this guide, you'll be able to query upcoming meetings, search past decisions, find relevant legislation, and check community voice counts for the San Rafael pilot.

## Option A: REST API

No setup required. Curl against the live API.

**Base URL:** `https://san-rafael.civicosproject.org`

All REST endpoints use the `/api/tools/{tool_name}` pattern, which wraps the MCP tools as HTTP POST endpoints.

```bash
BASE=https://san-rafael.civicosproject.org

# What's happening this month? (open tier — no auth required)
curl "$BASE/api/tools/city-pulse"

# Search upcoming meetings
curl -X POST "$BASE/api/tools/get-upcoming-meetings" \
  -H "Content-Type: application/json" \
  -d '{"topics": "housing", "days": 30}'

# Past decisions about housing
curl -X POST "$BASE/api/tools/search-meeting-history" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing"}'

# State legislation on housing
curl -X POST "$BASE/api/tools/search-legislation" \
  -H "Content-Type: application/json" \
  -d '{"topic": "housing", "level": "state", "limit": 5}'

# Voice counts on an entity (open tier — no auth required)
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

Restart Claude Desktop. You now have 40+ civic data tools. Try these prompts:

- "What meetings are coming up in San Rafael?"
- "What has the city council decided about housing?"
- "Show me state legislation related to transportation"
- "What are people saying about the downtown parking proposal?"

For other jurisdictions, add additional MCP server entries pointing at their domains (e.g., `california.civicosproject.org/mcp/`, `federal.civicosproject.org/mcp/`).

See [MCP Server Setup](mcp/setup.md) for the full tool inventory and ChatGPT configuration.

## Option C: Python SDK

Direct access, no HTTP overhead.

```bash
pip install civicos python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()  # Loads DATABASE_URL from .env

from civicos import CivicOS
c = CivicOS("city-san-rafael")

# Upcoming meetings
for m in c.whats_next(days=14):
    print(m.title, m.date)

# Past decisions
for d in c.what_happened("housing"):
    print(d.title, d.outcome)

# Relevant legislation
regs = c.what_applies("housing")
print(f"{len(regs.federal)} federal, {len(regs.state)} state, {len(regs.local)} local")

# Meeting transcript search
for excerpt in c.what_was_said("parking", top_k=3):
    print(f"{excerpt.speaker}: {excerpt.text[:100]}...")
```

The Python SDK requires `DATABASE_URL` pointing to a PostgreSQL instance with civic data. For local development without a database, it falls back to SQLite with sample data.

## Next Steps

- [API Reference](api.md) — full endpoint documentation, return types, error codes
- [MCP Server Setup](mcp/setup.md) — complete tool inventory, tier access, federation
- [Data Dictionary](data-dictionary.md) — field-level schemas for all data types
- [Operator Guide](operator-guide.md) — run your own CivicOS instance for your jurisdiction
- [Nostr Event Schemas](relay/nostr-events.md) — build CivicOS clients in any language

## Rate Limits

REST API: 30-600 req/min depending on tier, 10,000 req/hour ceiling. LLM-powered endpoints limited to 30 req/min. Rate limit headers (`X-RateLimit-*`) are included in every response. See [API Reference — Rate Limiting](api.md#rate-limiting) for details.

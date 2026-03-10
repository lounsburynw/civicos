# CivicOS Operator Guide

An **operator** is anyone who runs CivicOS services for a jurisdiction — a city IT department, civic organization, or community group. This guide walks you from zero to a running instance.

## Choose Your Configuration

| Configuration | Services | Use Case |
|--------------|----------|----------|
| **MCP only** | MCP server | Publish civic data for AI assistants and developers |
| **Relay only** | Relay | Coordinate community voices and actions |
| **MCP + relay** | Both | Full civic data + coordination |
| **Full stack** | MCP + relay + signer | Full stack with your own attestation authority |

Start with what you need. Each service is independently deployable.

## Prerequisites

- **PostgreSQL** — one database for MCP, a separate one for relay (if running relay). Free options: [Supabase](https://supabase.com), [Neon](https://neon.tech), [Fly.io](https://fly.io/docs/postgres).
- **Python 3.11+** — for direct deployment. Or use [Modal](https://modal.com) for serverless.
- **Jurisdiction code** — a canonical ID like `city-berkeley` or `county-alameda`. Check `config/registry.json` for existing codes.
- **OpenAI API key** — required for the MCP server (embeddings and AI features).

## Register Your Jurisdiction

If your jurisdiction isn't in `config/registry.json`, add it via PR:

```json
{
  "city-berkeley": {
    "domain": "berkeley.civicosproject.org",
    "display_name": "Berkeley",
    "modal_app_name": "civicos-berkeley",
    "parent_jurisdictions": ["state-california", "country-united-states"]
  }
}
```

The `parent_jurisdictions` field defines the attestation rollup hierarchy — a Berkeley attestation is valid for Alameda County, California, and federal entities. See [Federation — Attestation Rollup](relay/federation.md#attestation-rollup).

## Database Setup

### MCP Server Database

The MCP server needs a PostgreSQL database with civic data (meetings, decisions, legislation, vectors).

```bash
# Set in your environment or .env file
export DATABASE_URL=postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres
```

Enable pgvector for semantic search:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Relay Database (if running relay)

The relay uses a **separate** database for coordination data. This is a deliberate architectural boundary.

```bash
export RELAY_DATABASE_URL=postgresql://postgres:password@db.yyyyy.supabase.co:5432/postgres

# Apply the relay schema
psql $RELAY_DATABASE_URL -f packages/civicos-relay/schema.sql
```

See [Environment Variable Reference](operator-env-reference.md) for all configuration options.

## Deploy Services

### Option A: Modal (Serverless)

Modal handles scaling, HTTPS, and container management.

**MCP Server:**
```bash
# Default jurisdiction (city-san-rafael)
modal deploy apps/civicos-mcp/modal_mcp.py

# Custom jurisdiction
CIVICOS_JURISDICTION=city-berkeley modal deploy apps/civicos-mcp/modal_mcp.py
```

Configure Modal Secrets with your env vars:
```bash
modal secret create civicos-env \
  DATABASE_URL=postgresql://... \
  OPENAI_API_KEY=sk-... \
  CIVICOS_JURISDICTION=city-berkeley
```

**Relay:**
```bash
modal deploy apps/civicos-relay/modal_relay.py
```

Relay requires three Modal Secrets: `civicos-env`, `civicos-attestation`, `civic-anthropic`. See [env reference](operator-env-reference.md#relay-on-modal).

### Option B: Direct Python

Run services directly with uvicorn for self-hosted deployments.

**MCP Server:**
```bash
pip install -r requirements.txt
uvicorn civicos_services.servers.api:create_app --host 0.0.0.0 --port 8001
```

**Relay:**
```bash
pip install -e packages/civicos-relay
uvicorn civicos_relay.server.app:create_app --host 0.0.0.0 --port 8003
```

**Signer** (if running full stack):
```bash
pip install civicos-signer[server]
civicos-signer keygen --jurisdiction city-berkeley --organization "Berkeley Civic"
civicos-signer serve  # Reads .env.signer by default
```

Then register the signer with your relay — see [civicos-signer docs](packages/civicos-signer.md).

## Verify

After deployment, check that each service is healthy:

```bash
# MCP Server
curl https://your-domain/health
# Expected: {"status": "healthy", "service": "civicos-mcp", "jurisdiction": "city-berkeley", ...}

# Relay
curl https://your-relay-domain/health
# Expected: {"status": "healthy", "service": "civicos-relay", "relay_db_configured": true, ...}

# Signer (if running)
curl http://localhost:8850/health
# Expected: {"status": "healthy", "issuer_pubkey": "...", "jurisdiction": "city-berkeley", ...}
```

## Connect Clients

### Browser Extension

Users configure the extension to point at your MCP server:
1. Install the extension ([setup guide](extension/setup.md))
2. Open extension settings
3. Set the API URL to your MCP server's domain

### Claude Desktop (MCP)

Add to Claude Desktop's config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "civicos": {
      "url": "https://your-domain/mcp/"
    }
  }
}
```

### REST API

Interactive docs are available at `https://your-domain/docs` (Swagger UI). See [API reference](api.md) for endpoint details.

## Data Ingestion

An empty database returns empty results. CivicOS includes platform parsers for common civic data sources (Legistar, ProudCity, Granicus, SeeClickFix, LegiScan, Municode), but ingestion is jurisdiction-specific and requires configuration for your city's data sources.

See `docs/internal/ingestion.md` for the ingestion pipeline. Data ingestion is a significant operational task — plan for it as a separate workstream.

## Federation

If other operators already serve your jurisdiction, you can peer with them to sync voices and coordinate data. See [Federation Setup](operator-federation.md).

## Anti-patterns

- **Don't share databases** between MCP and relay. They have different data models and federation boundaries.
- **Don't skip RLS.** Enable Row Level Security on production databases (`scripts/sql/enable_rls.sql`).
- **Don't run the signer without a relay.** The signer signs attestations on behalf of the relay — it needs a relay to call it.
- **Don't disable signature verification.** Setting `CIVICOS_ALLOW_UNSIGNED=true` in production defeats the trust model.

## Further Reading

- [Environment Variable Reference](operator-env-reference.md) — all operator-relevant env vars
- [Federation Setup](operator-federation.md) — peer with other operators
- [Relay Overview](relay/overview.md) — full endpoint reference and trust model
- [MCP Server Setup](mcp/setup.md) — tool inventory and client configuration
- [civicos-signer](packages/civicos-signer.md) — attestation signing service
- [Quick Start for Builders](quickstart-api.md) — consuming the API as a developer

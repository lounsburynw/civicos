# Building Agents on CivicOS

How to build AI agents and applications that read civic data, participate in coordination, and interact with residents — using CivicOS as the data and coordination layer.

## Architecture Overview

CivicOS has two independent services. Your agent will interact with one or both depending on what it does.

```
Your Agent
    │
    ├──► MCP Server (read)     — meetings, decisions, legislation, budgets, transcripts
    │    GET /api/tools/*       — REST endpoints
    │    POST /mcp/             — MCP Streamable HTTP
    │
    └──► Relay (read + write)  — voices, actions, initiatives, AI drafting
         GET  /coordination/*   — read counts, list voices
         POST /coordination/*   — cast voices, create initiatives (Nostr-signed)
         POST /api/ai/*         — AI proxy (draft, chat)
```

**Reads** are unauthenticated or API-key authenticated. **Writes** require secp256k1 Schnorr signatures (Nostr-compatible).

## Choose Your Integration Path

| Path | Best For | Auth | Language |
|------|----------|------|----------|
| **MCP** | AI assistants (Claude, ChatGPT) | Optional API key | Any (JSON-RPC over HTTP) |
| **REST API** | Custom apps, dashboards, bots | API key | Any |
| **Python SDK** | Backend services, data pipelines | Database access | Python |
| **TypeScript client** | Browser apps, extensions | API key | TypeScript/JavaScript |

Most agents should use the **REST API** or **MCP** path. The Python SDK requires direct database access and is better suited for operators than external builders.

## Reading Civic Data

### Via REST (recommended for agents)

All MCP tools are available as REST endpoints at `/api/tools/{tool-name}`:

```python
import httpx

BASE = "https://san-rafael.civicosproject.org"

# Upcoming meetings
resp = httpx.post(f"{BASE}/api/tools/get-upcoming-meetings",
    json={"topics": "housing", "days": 30})
meetings = resp.json()

# Past decisions
resp = httpx.post(f"{BASE}/api/tools/search-meeting-history",
    json={"query": "housing zoning"})
decisions = resp.json()

# Legislation
resp = httpx.post(f"{BASE}/api/tools/search-legislation",
    json={"topic": "housing", "level": "state", "limit": 10})

# City pulse (no auth required — open tier)
resp = httpx.get(f"{BASE}/api/tools/city-pulse")

# Voice counts (no auth required — open tier)
resp = httpx.post(f"{BASE}/api/tools/get-voice-counts",
    json={"entity": "city-san-rafael:mtg-2026-03-10-cc:item-5"})
```

For higher rate limits, pass an API key:
```python
headers = {"Authorization": "Bearer cvk_live_your_key_here"}
resp = httpx.post(f"{BASE}/api/tools/search-meeting-history",
    json={"query": "housing"}, headers=headers)
```

See [API Reference](api.md) for rate limits and tier access. See [MCP Setup — Tool Access by Tier](mcp/setup.md#tool-access-by-api-tier) for which tools are available at each tier.

### Via MCP (for AI assistants)

If your agent framework supports MCP (Claude Desktop, OpenAI agents, LangChain, etc.), connect directly:

```json
{
  "mcpServers": {
    "civicos": {
      "url": "https://san-rafael.civicosproject.org/mcp/"
    }
  }
}
```

The MCP server exposes 50+ tools. Your agent can call them like any MCP tool. See [MCP Setup](mcp/setup.md) for the full tool inventory.

### Multi-Jurisdiction Queries

Each jurisdiction has its own MCP server. Query multiple jurisdictions by hitting different endpoints:

| Jurisdiction | Endpoint |
|-------------|----------|
| San Rafael | `san-rafael.civicosproject.org` |
| California | `california.civicosproject.org` |
| Federal | `federal.civicosproject.org` |

The jurisdiction registry (`config/registry.json`) lists all available jurisdictions and their domains.

### Via TypeScript Client

For browser-based agents or Node.js services:

```typescript
import { ApiClient, RegistryClient } from '@civicos/client';

const registry = new RegistryClient();
const servers = await registry.getRegistryServers();

const api = new ApiClient('https://san-rafael.civicosproject.org');
const counts = await api.getVoiceCountsBatch(
  ['city-san-rafael:mtg-2026-03-10-cc:item-5'],
  'city-san-rafael'
);
```

See [civicos-client](packages/civicos-client.md) for all available classes and types.

## Writing to the Relay

Write operations (casting voices, creating initiatives, submitting comments) go through the relay and require **Nostr-signed request bodies**. This is the key difference from reads — writes prove identity cryptographically.

### Signing Overview

Every write is a Nostr event signed with a secp256k1 Schnorr key (BIP-340):

1. Generate a keypair (once, store the private key securely)
2. Construct the event (kind, tags, content)
3. Serialize: `[0, pubkey, created_at, kind, tags, content]`
4. SHA-256 hash the serialization
5. Sign the hash with Schnorr
6. POST the signed event to the relay

### Example: Cast a Voice

```python
import json
import hashlib
import time
from coincurve import PrivateKey

# Your keypair (generate once, store securely)
private_key = PrivateKey(bytes.fromhex("your_private_key_hex"))
public_key = private_key.public_key_xonly.hex()

# Construct the voice event (kind 30800)
created_at = int(time.time())
tags = [
    ["d", "decision:city-san-rafael:2026-03-10:item-5"],
    ["j", "city-san-rafael"],
    ["stance", "support"]
]
content = ""

# Serialize and sign (NIP-01)
serialized = json.dumps([0, public_key, created_at, 30800, tags, content],
                         separators=(',', ':'))
event_hash = hashlib.sha256(serialized.encode()).digest()
signature = private_key.sign_schnorr(event_hash).hex()

# POST to relay
import httpx
relay_url = "https://san-rafael.civicosproject.org/relay"
resp = httpx.post(f"{relay_url}/coordination/voice", json={
    "id": event_hash.hex(),
    "pubkey": public_key,
    "created_at": created_at,
    "kind": 30800,
    "tags": tags,
    "content": content,
    "sig": signature
})
```

### Acceptance Policy

The relay enforces rate limits on writes. Without attestation, default limits apply:

| Event Type | Daily Limit |
|------------|-------------|
| voice | 50 |
| comment | 20 |
| initiative | 5 |

Exceeding limits returns HTTP 402. For unlimited writes, the key must have an attestation proof. See [Relay — Acceptance Policy](relay/overview.md#acceptance-policy).

### Nostr Event Reference

Full tag structures for all event kinds:

| Kind | Event | Purpose |
|------|-------|---------|
| 30800 | Voice | Stance on a civic entity |
| 30803 | Comment | Public comment on an entity |
| 30810 | Civic Action | Define an action for others to commit to |
| 30811 | Commitment | Commit to a civic action |
| 30812 | Completion | Record completing an action |

See [Nostr Event Schemas](relay/nostr-events.md) for complete tag structures and content formats for all event kinds.

## Using the AI Proxy

The relay includes an AI proxy that provides Claude-powered civic Q&A and drafting, grounded in real local data via MCP tool calls. Your agent can use this instead of running its own LLM.

```python
import time, json, hashlib
from coincurve import PrivateKey

# Sign the request (same pattern as voice casting)
private_key = PrivateKey(bytes.fromhex("your_key"))
public_key = private_key.public_key_xonly.hex()
created_at = int(time.time())

# Kind 24242 = auth event
auth_serialized = json.dumps([0, public_key, created_at, 24242, [], ""],
                              separators=(',', ':'))
auth_hash = hashlib.sha256(auth_serialized.encode()).digest()
signature = private_key.sign_schnorr(auth_hash).hex()

# Chat with civic data context
resp = httpx.post(f"{relay_url}/api/ai/chat", json={
    "question": "What happened with the downtown parking proposal?",
    "jurisdiction": "city-san-rafael",
    "public_key": public_key,
    "signature": signature,
    "created_at": created_at
})
# Response includes Claude's answer grounded in meeting records, decisions, testimony
```

The AI proxy requires attestation and is rate-limited to 20 requests/day per pubkey. See [AI Proxy](relay/ai-proxy.md) for privacy architecture and endpoint details.

## Agent Patterns

### Meeting Monitor

Watches for new meetings and alerts when relevant topics appear.

```
Poll get_upcoming_meetings (every hour)
  → Filter by topics of interest
  → For each new meeting: get_item_context for full background
  → Notify user with context summary
```

### Legislative Tracker

Tracks state/federal legislation and surfaces local impact.

```
Poll search_legislation (daily, by topic)
  → For each bill: get_bill_detail, get_leverage_points
  → Cross-reference with local decisions: search_meeting_history
  → Generate impact summary
```

### Community Dashboard

Real-time participation dashboard for a jurisdiction.

```
city_pulse → overall activity snapshot
get_voice_counts (per active entity) → participation levels
list_initiatives → active community campaigns
get_issue_analytics → 311 service request trends
```

### Testimony Assistant

Helps residents prepare for public comment.

```
User provides: meeting ID + topic
  → prepare_for_meeting → agenda, background, prior decisions
  → get_public_testimony → what others have said
  → search_regulatory_stack → relevant laws
  → compose_public_comment → drafting context
  → (Optional) POST /api/ai/draft via relay → AI-assisted draft
```

## Key Constraints

- **Reads are free, writes require signing.** Any agent can query civic data. Only agents with secp256k1 keys can cast voices or create initiatives.
- **Rate limits apply.** Open tier: 30 req/min. Builder tier: 300 req/min. See [API Reference — Rate Limiting](api.md#rate-limiting).
- **Attestation gates participation.** Unlimited voice casting requires an attestation proof (kind 30850) demonstrating residency. Without it, rate limits apply.
- **Data freshness varies.** Meetings/agendas update daily, legislation weekly, budget data per fiscal year. Check `data_provenance` for current coverage.
- **Write tools are relay-only.** The MCP server is read-only. All writes go through the relay's `/coordination/*` endpoints with signed Nostr events.

## Further Reading

- [Quick Start](quickstart-api.md) — 10-minute onramp for builders
- [API Reference](api.md) — full REST endpoint docs, return types, error codes
- [MCP Setup](mcp/setup.md) — complete tool inventory and tier access
- [Nostr Event Schemas](relay/nostr-events.md) — build CivicOS clients in any language
- [Relay Overview](relay/overview.md) — coordination endpoints, acceptance policy
- [AI Proxy](relay/ai-proxy.md) — privacy-preserving AI access for residents
- [civicos-client](packages/civicos-client.md) — TypeScript client library
- [Operator Guide](operator-guide.md) — run your own CivicOS instance

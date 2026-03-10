# CivicOS

AI-enabled infrastructure for local self-organization and governance.

CivicOS indexes public civic data — meetings, agendas, decisions, budgets, legislation, community issues — and makes it searchable, understandable, and actionable through a browser extension, MCP server, and REST API.

**Pilot city:** San Rafael, CA

## How It Works

A resident installs the browser extension. It shows them what's happening in their city: upcoming meetings, recent decisions, budget breakdowns, community issues on a map, and relevant state/federal legislation. They can express a stance on agenda items (support, oppose, watching), draft public comments with AI assistance, and track how officials vote.

Identity is local-first, built on Nostr (secp256k1 Schnorr signatures). Private keys never leave the device.

## Surfaces

| Surface | What it does | Who it's for |
|---------|-------------|--------------|
| [Browser extension](extension/setup.md) | Primary UI — civic dashboard, voice, identity | Residents |
| [MCP server](mcp/setup.md) | 50+ read-only civic data tools for AI assistants | Claude, ChatGPT users |
| REST API | Programmatic access to civic data | Developers |

## Architecture

```
Browser Extension (Svelte 5)
    ├── civicos-components (Svelte UI)
    └── civicos-client (TypeScript)
              |
    ┌─────────┼─────────┐
    v         v         v
REST API  MCP Server  Relay API
(FastAPI) (JSON-RPC)  (FastAPI)
    |         |         |
    v         v         v
    CivicOS (core)   civicos-relay
    (Python query)   (coordination)
         |                |
         v                v
    PostgreSQL        Relay DB
    + pgvector        (Supabase)
    (Supabase)
         ^
         |
    civicos-extraction
    (platform parsers)
```

### Federation

Operators can independently run an **MCP server** (read-only civic data), a **relay** (bidirectional coordination), or both. Multiple operators per jurisdiction [peer via the relay protocol](relay/federation.md) and are discoverable through a [central registry](decisions/federation_domain_architecture.md).

```
       Operator A (Government)       Operator B (Civic Org)
    ┌──────────┬──────────┐     ┌──────────┬──────────┐
    │MCP Server│  Relay   │◄───►│  Relay   │MCP Server│
    │(civic    │(voices,  │peer │(community│(mirrors  │
    │ data)    │ actions) │sync │ voices)  │ data)    │
    └──────────┴──────────┘     └──────────┴──────────┘
```

**Packages:**

| Package | Purpose |
|---------|---------|
| [`civicos`](packages/civicos.md) | Core query API — `what_happened()`, `whats_next()`, `what_applies()` |
| [`civicos-services`](packages/civicos-services.md) | REST API server (FastAPI, 15 routers, 50+ endpoints) |
| [`civicos-relay`](packages/civicos-relay.md) | Coordination — voice casting, subscriptions, relay sync |
| [`civicos-signer`](packages/civicos-signer.md) | Portable attestation signing — lets organizations hold their own issuer keys |
| [`civicos-extraction`](packages/civicos-extraction.md) | Platform parsers — Legistar, CivicClerk, ProudCity, Granicus, SeeClickFix, LegiScan, and more |
| [`civicos-client`](packages/civicos-client.md) | TypeScript client — API wrapper, identity, AI provider management |
| [`civicos-components`](packages/civicos-components.md) | Svelte UI components — meetings, decisions, budgets, maps |

## Data (San Rafael Pilot, as of March 2026)

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | ProudCity (city website) |
| Decisions | ~44 | Minutes extraction |
| Transcripts | ~19 | YouTube + AssemblyAI |
| Agenda packets (PDF chunks) | ~5,084 | City agenda PDFs |
| Municipal code | ~16,175 | Municode |
| Community issues | ~1,730 | SeeClickFix (311) |
| Budget items | ~58 | FY25-26 budget PDF |
| Legislation | ~17,719 | LegiScan (CA + federal) |

All data is semantically indexed (~16,786 vector embeddings) for natural language search.

## Quick Start (Developers)

```bash
# Python core
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(c.whats_next())
"

# Browser extension
cd apps/civicos-extension
npm install && npm run dev
# Load unpacked from dist/ in chrome://extensions (developer mode)
```

## Links

- [Extension setup](extension/setup.md)
- [Extension development](extension/development.md)
- [MCP server setup](mcp/setup.md)
- [Core API reference](api.md)
- [Data dictionary](data-dictionary.md)
- [Relay — attestation, trust, coordination](relay/overview.md)
- [Nostr event schemas — build CivicOS clients in any language](relay/nostr-events.md)
- [Federation — how relays and MCP servers peer across operators](relay/federation.md)
- [Architecture decisions](decisions/vector_storage.md)
- [Learning series](learning/README.md) — cryptographic foundations, Nostr, attestation

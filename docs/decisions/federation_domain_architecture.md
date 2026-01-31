# ADR: Federation Domain Architecture

**Status:** Accepted
**Date:** 2026-01-30
**Context:** Domain strategy for multi-operator, multi-jurisdiction federation

## Decision

Adopt a **Registry + Bring Your Own Domain (BYOD)** model for federation. `civicos.io` serves as a registry and optional hosting provider, while operators can run instances at their own domains and peer via the relay protocol.

## Context

CivicOS is designed for federation across:
- **Multiple jurisdictions**: San Rafael, Novato, Mill Valley, etc.
- **Multiple operators per jurisdiction**: City government, civic orgs, neighborhood groups

A centralized hosting model (all instances at civicos.io) doesn't align with:
- Foundation funding thesis (cities are partners, not tenants)
- Political viability (cities want sovereignty over civic infrastructure)
- Resilience (no single point of failure)
- Open source ethos (anyone can run an instance)

## Architecture

### Federation Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              civicos.io                                      │
│                         (Registry + Protocol)                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • Operator directory (who runs what, where)                         │   │
│  │  • Protocol specification                                            │   │
│  │  • Reference implementation                                          │   │
│  │  • Optional hosted instances (for operators who want it)            │   │
│  │  • Cross-jurisdiction aggregation queries (future)                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
        ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
        │  San Rafael   │  │    Novato     │  │  Mill Valley  │
        │  Jurisdiction │  │  Jurisdiction │  │  Jurisdiction │
        └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
                │                  │                  │
    ┌───────────┼───────────┐     ...               ...
    ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐
│  City  │ │  LWV   │ │ Canal  │
│Official│ │Chapter │ │Neighbor│
└────────┘ └────────┘ └────────┘
    │           │           │
    └─────────┬─┴───────────┘
              │
      Relay peering
      (voices, events)
```

### Operator Types

| Operator Type | Example | Role |
|---------------|---------|------|
| **Official** | City of San Rafael | Authoritative civic data (meetings, decisions, code) |
| **Civic org** | League of Women Voters | Community voices, voter education |
| **Neighborhood** | Canal Alliance | Hyperlocal issues, community voices |
| **Media** | Marin IJ | Public interest, transparency |

### What Each Component Provides

| Component | Data Ownership | Federation Role |
|-----------|----------------|-----------------|
| **MCP Server** | Queries civic data | Serves AI clients (Claude.ai, ChatGPT) |
| **Relay** | Voices, subscriptions | Peers with other relays for sync |
| **Authoritative source** | Official records | City's instance is source of truth for civic data |

## Domain Structure

### Pattern: Jurisdiction-First with Operator Subdomains

```
civicosproject.org                      ← Registry, protocol, optional hosting
├── registry.civicosproject.org         ← Operator directory API (future)

san-rafael.civicosproject.org           ← Default/hosted instance (LIVE)
├── /mcp                                ← MCP endpoint
├── /health                             ← Health check
└── /relay                              ← Relay peering endpoint (future)

Operators using civicosproject.org hosting:
├── city.san-rafael.civicosproject.org  ← City's hosted instance
├── lwv.san-rafael.civicosproject.org   ← LWV's hosted instance
└── canal.san-rafael.civicosproject.org ← Neighborhood instance

Operators with own domains (BYOD):
├── civic.cityofsanrafael.gov           ← City's own infrastructure
├── sanrafael.marinlwv.org              ← LWV's own infrastructure
└── civicdata.marinij.com               ← Media org's infrastructure
```

### Discovery via Registry

```json
GET registry.civicos.io/jurisdictions/city-san-rafael/operators

{
  "jurisdiction": "city-san-rafael",
  "operators": [
    {
      "id": "city-official",
      "name": "City of San Rafael",
      "type": "official",
      "authoritative_for": ["meetings", "decisions", "municipal_code"],
      "mcp_endpoint": "https://civic.cityofsanrafael.gov/mcp",
      "relay_endpoint": "https://civic.cityofsanrafael.gov/relay",
      "domain_type": "byod"
    },
    {
      "id": "lwv-marin",
      "name": "League of Women Voters - Marin",
      "type": "civic_org",
      "authoritative_for": [],
      "mcp_endpoint": "https://lwv.san-rafael.civicos.io/mcp",
      "relay_endpoint": "https://lwv.san-rafael.civicos.io/relay",
      "domain_type": "hosted"
    }
  ]
}
```

## Data Sovereignty Model

### What Federates vs. What's Authoritative

| Data Type | Source | Federation Model |
|-----------|--------|------------------|
| Meetings, agendas | Official operator | Mirror/cache from authoritative source |
| Decisions, votes | Official operator | Mirror/cache from authoritative source |
| Municipal code | Official operator | Mirror/cache from authoritative source |
| **Voices** | All operators | Peer-to-peer relay sync |
| **Subscriptions** | Per operator | Managed by originating operator |
| Issues (311) | Official operator | Mirror from authoritative source |
| Community discussions | All operators | Peer-to-peer or operator-specific |

### Authoritative Data Flow

```
City's Official Instance              Other Operators
┌─────────────────────┐              ┌─────────────────────┐
│ Authoritative for:  │              │ Mirror/cache:       │
│ • meetings          │─────────────►│ • meetings          │
│ • decisions         │  sync/pull   │ • decisions         │
│ • municipal_code    │              │ • municipal_code    │
│ • budget            │              │ • budget            │
└─────────────────────┘              └─────────────────────┘

All operators contribute voices, which federate peer-to-peer:
┌─────────────────────┐              ┌─────────────────────┐
│ City voices         │◄────────────►│ LWV voices          │
│ (e.g., city staff)  │  relay sync  │ (e.g., members)     │
└─────────────────────┘              └─────────────────────┘
```

## Protocol Requirements

### Relay Peering Across Domains

The relay protocol must support cross-domain peering:

```python
# Relay discovery via registry
async def discover_peers(jurisdiction_id: str) -> List[RelayPeer]:
    """Find all relay endpoints for a jurisdiction."""
    operators = await registry.get_operators(jurisdiction_id)
    return [
        RelayPeer(
            operator_id=op["id"],
            relay_url=op["relay_endpoint"],
            public_key=op["public_key"],
        )
        for op in operators
        if op.get("relay_endpoint")
    ]

# Peering handshake
async def peer_with(relay_url: str, our_identity: RelayIdentity):
    """Establish peering relationship with another relay."""
    # 1. Exchange identity (public keys)
    # 2. Verify signatures
    # 3. Negotiate sync scope (which event types to share)
    # 4. Begin incremental sync
```

### MCP Discovery

AI clients can discover MCP servers via registry:

```
User: "What's happening in San Rafael?"

AI Client:
1. Query registry.civicos.io for San Rafael operators
2. Select appropriate operator (official for authoritative data)
3. Connect to MCP endpoint
4. Execute tools
```

## Implementation

### Pilot (Jan 2026) - COMPLETE

Single operator, civicosproject.org hosting with Cloudflare proxy to Modal:

```
san-rafael.civicosproject.org           ← LIVE
├── /mcp     → Cloudflare Worker → Modal MCP endpoint
├── /health  → Cloudflare Worker → Modal health endpoint
└── /relay   → Supabase relay database (future)
```

Infrastructure:
- Domain: `civicosproject.org` (Cloudflare Registrar)
- DNS: Cloudflare (proxied)
- Proxy: Cloudflare Worker (`civicos-mcp-proxy`)
- Compute: Modal (`civicos-mcp` app)
- Storage: Supabase PostgreSQL + pgvector

### Post-Pilot: Multi-Operator

When second operator joins San Rafael:

1. Register operator in directory
2. Establish relay peering
3. Configure data sync (authoritative sources)

### Post-Pilot: Multi-Jurisdiction

When Novato joins:

1. Create `novato.civicos.io` (or operator uses BYOD)
2. Register in directory
3. Cross-jurisdiction relay peering (optional)

## What civicos.io Provides

| Service | Description | Who Uses It |
|---------|-------------|-------------|
| **Registry** | Operator directory, discovery API | AI clients, operators |
| **Protocol spec** | Relay peering, MCP extensions | Operators implementing protocol |
| **Reference impl** | Open source packages | Operators building instances |
| **Hosted instances** | Optional hosting at civicos.io subdomains | Operators who don't want to self-host |
| **Aggregation** | Cross-jurisdiction queries (future) | AI clients querying multiple cities |

## Rationale

### Why Not Centralized Multi-Tenant?

| Concern | Centralized | Registry + BYOD |
|---------|-------------|-----------------|
| Single point of failure | Yes | No |
| City sovereignty | Limited | Full |
| Scaling costs | Central | Distributed |
| Foundation funding alignment | Weak | Strong |
| Open source ethos | Partial | Full |

### Why Not Fully Decentralized (No Registry)?

| Concern | No Registry | With Registry |
|---------|-------------|---------------|
| Discovery | Hard | Easy |
| Aggregated queries | Impossible | Possible |
| Onboarding | Complex | Guided |
| Protocol evolution | Fragmented | Coordinated |

## Migration Path

### Phase 1: Pilot Domain - COMPLETE (Jan 2026)

- [x] Register `civicosproject.org` (Cloudflare)
- [x] Create Cloudflare Worker proxy to Modal
- [x] Configure `san-rafael.civicosproject.org` subdomain
- [x] Verify MCP endpoint: `https://san-rafael.civicosproject.org/mcp`
- [x] Verify health endpoint: `https://san-rafael.civicosproject.org/health`
- [x] Update MCP_INTEGRATION_STRATEGY.md with production URL
- [x] Update HOSTING_DECISION.md with production URL

### Phase 2: Registry MVP

- [ ] Implement registry.civicos.io (simple JSON/API)
- [ ] Register pilot operator
- [ ] Document operator registration process

### Phase 3: Multi-Operator

- [ ] Relay cross-domain peering
- [ ] BYOD operator onboarding
- [ ] Authoritative data sync protocol

### Phase 4: Multi-Jurisdiction

- [ ] Cross-jurisdiction federation
- [ ] Aggregated query routing
- [ ] Regional directories (e.g., marin.civicos.io)

## Related Documents

- `COORDINATION_PROTOCOL.md` - Relay protocol details
- `MCP_INTEGRATION_STRATEGY.md` - MCP deployment
- `data_source_federation.md` - DataSource protocol for queries
- `FOUNDATION_FUNDING_THESIS.md` - Partnership model alignment

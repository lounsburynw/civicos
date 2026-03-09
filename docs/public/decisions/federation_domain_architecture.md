# ADR: Federation Domain Architecture

**Status:** Accepted
**Date:** 2026-01-30

## Decision

Adopt a **Registry + Bring Your Own Domain (BYOD)** model for federation. `civicosproject.org` serves as a registry and optional hosting provider, while operators can run instances at their own domains and peer via the relay protocol.

## Context

CivicOS is designed for federation across multiple jurisdictions and multiple operators per jurisdiction. A centralized hosting model doesn't align with:

- **City sovereignty** — Cities want control over civic infrastructure
- **Resilience** — No single point of failure
- **Foundation funding model** — Cities are partners, not tenants
- **Open source ethos** — Anyone can run an instance

## Architecture

### Federation Topology

```
┌──────────────────────────────────────────────────────────────┐
│                      civicosproject.org                       │
│                   (Registry + Protocol)                       │
│                                                              │
│  • Operator directory (who runs what, where)                 │
│  • Protocol specification                                    │
│  • Reference implementation                                  │
│  • Optional hosted instances                                 │
│  • Cross-jurisdiction aggregation (future)                   │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
    │  San Rafael   │ │    Novato     │ │  Mill Valley  │
    │  Jurisdiction │ │  Jurisdiction │ │  Jurisdiction │
    └───────┬───────┘ └───────────────┘ └───────────────┘
            │
  ┌─────────┼─────────┐
  ▼         ▼         ▼
┌──────────┐┌──────────┐┌──────────┐
│Government││ Civic Org││Community │
│MCP+Relay ││MCP+Relay ││  Relay   │
└──────────┘└──────────┘└──────────┘
      └─────────┬──────────┘
   Relay peering (voices, events)
   MCP publishing (civic data)
```

### Operator Types

| Type | Example | Role |
|------|---------|------|
| **Official** | City of San Rafael | Authoritative civic data (meetings, decisions, code) |
| **Civic org** | League of Women Voters | Community voices, voter education |
| **Neighborhood** | Canal Alliance | Hyperlocal issues, community voices |
| **Media** | Marin IJ | Public interest, transparency |

## Components

Operators can run either or both of two independent services:

| Component | Protocol | Direction | Purpose |
|-----------|----------|-----------|---------|
| **MCP Server** | MCP (JSON-RPC) | Read-only | Serves civic data queries — AI clients and apps ask "what happened at the last council meeting?" |
| **Relay** | WebSocket | Bidirectional | Syncs coordination data between operators — voices, subscriptions, and events peer across instances |

The two are independent. A city government might run only an MCP server to publish authoritative civic data. A neighborhood group might run only a relay to coordinate community voices. An operator running both can serve queries *and* participate in peer-to-peer sync.

This split reflects the data sovereignty model: authoritative civic data (meetings, decisions, code) flows *outward* via MCP as a read API, while community-generated data (voices, subscriptions) flows *between* operators via relay peering.

## Domain Structure

### Jurisdiction-first with operator subdomains

```
civicosproject.org                       ← Registry, protocol, docs
├── registry.civicosproject.org          ← Operator directory API

san-rafael.civicosproject.org            ← Default hosted instance
├── /mcp                                 ← MCP protocol endpoint
└── /relay                               ← Relay peering endpoint

Hosted operators:
├── city.san-rafael.civicosproject.org   ← City's hosted instance
├── lwv.san-rafael.civicosproject.org    ← LWV's hosted instance

BYOD operators:
├── civic.cityofsanrafael.gov            ← City's own infrastructure
├── sanrafael.marinlwv.org               ← LWV's own infrastructure
```

### Discovery via Registry

```json
GET registry.civicosproject.org/jurisdictions/city-san-rafael/operators

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
      "mcp_endpoint": "https://lwv.san-rafael.civicosproject.org/mcp",
      "relay_endpoint": "https://lwv.san-rafael.civicosproject.org/relay",
      "domain_type": "hosted"
    }
  ]
}
```

## Data Sovereignty

### What federates vs. what's authoritative

| Data Type | Source | Federation Model |
|-----------|--------|------------------|
| Meetings, agendas | Official operator | Mirror/cache from authoritative source |
| Decisions, votes | Official operator | Mirror/cache from authoritative source |
| Municipal code | Official operator | Mirror/cache from authoritative source |
| **Voices** | All operators | Peer-to-peer relay sync |
| **Subscriptions** | Per operator | Managed by originating operator |
| Issues (311) | Official operator | Mirror from authoritative source |

### Data flow

```
Official Instance                    Other Operators
┌─────────────────────┐              ┌─────────────────────┐
│ Authoritative for:  │              │ Mirror/cache:       │
│ • meetings          │─────────────►│ • meetings          │
│ • decisions         │  sync/pull   │ • decisions         │
│ • municipal_code    │              │ • municipal_code    │
└─────────────────────┘              └─────────────────────┘

All operators contribute voices, which federate peer-to-peer:
┌─────────────────────┐              ┌─────────────────────┐
│ City voices         │◄────────────►│ LWV voices          │
└─────────────────────┘  relay sync  └─────────────────────┘
```

## Registry Services

| Service | Description |
|---------|-------------|
| **Operator directory** | Discovery API — who runs what, where |
| **Protocol spec** | Relay peering and MCP extension standards |
| **Reference implementation** | Open source packages for running an instance |
| **Hosted instances** | Optional hosting for operators who don't want to self-host |
| **Aggregation** | Cross-jurisdiction queries (future) |

## Rationale

### Why not centralized multi-tenant?

| Concern | Centralized | Registry + BYOD |
|---------|-------------|-----------------|
| Single point of failure | Yes | No |
| City sovereignty | Limited | Full |
| Scaling costs | Central operator bears all | Distributed |
| Open source ethos | Partial | Full |

### Why not fully decentralized (no registry)?

| Concern | No Registry | With Registry |
|---------|-------------|---------------|
| Discovery | Hard | Easy |
| Aggregated queries | Impossible | Possible |
| Onboarding | Complex | Guided |
| Protocol evolution | Fragmented | Coordinated |

## References

- [DataSource Protocol](data_source_federation.md) — Query abstraction for local and federated data
- [Entity ID Namespacing](entity_id_namespace.md) — Global ID uniqueness across jurisdictions
- [civicos-relay package](../packages/civicos-relay.md) — Relay protocol implementation

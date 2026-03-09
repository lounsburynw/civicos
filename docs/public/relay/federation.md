# Relay Federation

How relays peer across operators and jurisdictions, how attestation works across government levels, and how data sovereignty is maintained.

> **Note:** Federation applies to both CivicOS services — **relays** and **MCP servers**. Relays federate coordination data (voices, actions) via peer-to-peer sync. MCP servers federate civic data (meetings, decisions, legislation) as read-only APIs. This document covers relay federation. For the full two-service model, see [Federation Domain Architecture](../decisions/federation_domain_architecture.md). For MCP federation, see [MCP Server Setup](../mcp/setup.md#federation).

## Multi-Operator Peering

Multiple operators can run relays for the same jurisdiction. When they do, voices and events sync between them via the relay protocol:

```
City of San Rafael          League of Women Voters
┌─────────────────────┐     ┌─────────────────────┐
│ Relay A              │◄──►│ Relay B              │
│ (official operator)  │    │ (civic org operator) │
│                      │    │                      │
│ City voices          │    │ LWV member voices    │
│ Official entities    │    │ Community entities   │
└─────────────────────┘     └─────────────────────┘
```

Each relay independently verifies all incoming voices — signatures, attestation proofs, the full six-check verification. No relay trusts another relay's word; every relay trusts the math.

## Data Sovereignty

Not all data federates the same way:

| Data Type | Source | Federation Model |
|-----------|--------|------------------|
| Meetings, agendas, decisions | Official operator | Mirror/cache from authoritative source |
| Municipal code, budget | Official operator | Mirror/cache from authoritative source |
| **Voices** | All operators | Peer-to-peer relay sync |
| **Actions** | All operators | Peer-to-peer relay sync |
| **Subscriptions** | Per operator | Managed by originating operator |

Authoritative civic data (what happened at the meeting) flows outward from the official operator via their MCP server. Community-generated data (who supports what) flows between operators via relay peering.

## Attestation Rollup

Attestation is scoped to a jurisdiction. When a San Rafael resident wants to voice on a county-level entity, what happens?

### Upward rollup

City attestation is valid at city, county, state, and federal levels — because being a San Rafael resident necessarily makes you a Marin County resident, a California resident, and a U.S. resident.

```
city-san-rafael attestation → valid for:
  city-san-rafael entities        ✓ (exact match)
  marin-county entities           ✓ (San Rafael is in Marin)
  california entities             ✓ (Marin is in California)
  us-federal entities             ✓ (California is in the US)
```

Rollup goes up, not down or sideways. A county attestation doesn't prove you live in a specific city. A San Rafael attestation doesn't let you voice on Novato entities.

### Jurisdiction hierarchy

The relay checks attestation validity by walking a jurisdiction tree:

```json
{
  "city-san-rafael": { "parent": "marin-county", "type": "city" },
  "city-novato": { "parent": "marin-county", "type": "city" },
  "marin-county": { "parent": "california", "type": "county" },
  "california": { "parent": "us-federal", "type": "state" },
  "us-federal": { "parent": null, "type": "federal" }
}
```

To verify: walk from the attestation jurisdiction up the tree. If you reach the entity's jurisdiction, the attestation is valid.

### Special districts

U.S. governance doesn't fit a clean tree. School districts, water districts, and transit authorities overlap city boundaries. CivicOS handles this pragmatically:

- Special districts declare which jurisdictions they accept attestation from
- The agent layer provides context about standing ("this district covers parts of San Rafael, San Anselmo, and Fairfax")
- The relay keeps its acceptance logic simple; nuance lives at the edge

## Cross-Relay Verification

When multiple relays serve the same entities, they can cross-check automatically using commitment logs (see [Trust Model](trust.md)):

- **Consistent:** Both relays report the same voice count and merkle root for an entity. High confidence both are serving identical data.
- **Inconsistent:** Different counts or roots. Any client can pull the full voice lists from both relays, verify all signatures independently, and determine which is correct.

The critical property: resolving disagreements doesn't require trusting either relay. The voices themselves carry the proof.

## Further Reading

- [Federation Domain Architecture](../decisions/federation_domain_architecture.md) — Domain strategy, operator types, registry model
- [DataSource Protocol](../decisions/data_source_federation.md) — Query abstraction for local and federated data
- [Entity ID Namespacing](../decisions/entity_id_namespace.md) — How namespaced IDs enable federation

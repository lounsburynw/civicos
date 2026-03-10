# Operator Federation Setup

Practical guide for peering your relay with other CivicOS operators. For the theory behind federation, see [Relay Federation](relay/federation.md).

## When You Need This

Federation matters when **multiple operators serve the same jurisdiction**. For example, a city government and a civic organization both running relays for Berkeley. Without peering, each relay only has voices from its own users. With peering, voices sync bidirectionally so all operators serve the complete picture.

If you're the only operator for your jurisdiction, you don't need federation yet.

## Prerequisites

- A running relay with `RELAY_DATABASE_URL` configured (see [Operator Guide](operator-guide.md))
- The URL of the peer relay you want to sync with
- Both relays serving the same or overlapping jurisdictions

## Configure Peering

Set `RELAY_PEERS` in your relay's environment to a comma-separated list of peer relay URLs:

```bash
# Single peer
RELAY_PEERS=https://san-rafael.civicosproject.org/relay

# Multiple peers
RELAY_PEERS=https://san-rafael.civicosproject.org/relay,https://civic-org.example.com/relay
```

Each peer URL should point to the relay's base URL (the health endpoint should be reachable at `{url}/health`).

Peering is configured independently on each side. Both operators must add each other as peers for bidirectional sync.

## Verify Peering

After configuring and restarting your relay:

```bash
# Check your relay's health (should show relay_db_configured: true)
curl https://your-relay/health

# Check the peer's sync endpoint (should return voices)
curl https://peer-relay/coordination/sync/voices?limit=10

# Verify your relay can reach the peer
curl https://your-relay/health
# Look for peer connectivity in the response
```

## How Sync Works

Voices sync bidirectionally between peers. Each relay independently verifies every voice it receives — checking the Nostr signature, attestation proof, and entity namespace. No relay trusts another relay's verification; every relay trusts the cryptographic proof.

Subscriptions do **not** sync. Each operator manages their own notification routing. Civic data (meetings, decisions, legislation) comes from MCP servers, not relays — it doesn't participate in relay sync.

Sync runs on a configurable interval (default: 300 seconds) and processes voices in batches.

## Jurisdiction Hierarchy

Jurisdictions form a hierarchy defined in `config/registry.json`:

```json
{
  "city-san-rafael": {
    "parent_jurisdictions": ["county-marin", "state-california", "country-united-states"]
  }
}
```

Attestation rolls upward: a San Rafael attestation is valid for Marin County, California, and federal entities. It does **not** roll sideways — a San Rafael attestation is not valid for Novato entities, even though both are in Marin County.

When peering with a relay that serves a parent or child jurisdiction, namespace filtering ensures only relevant voices sync. Configure `RELAY_NAMESPACES` to control which entity namespaces your relay hosts (default: `*` for all).

## Troubleshooting

**Peer returns 404 on sync endpoint**
The peer may not be running a relay, or may have sync disabled. Check that `RELAY_SYNC_ENABLED=true` on the peer.

**Voices don't appear after sync**
Your relay independently verifies every incoming voice. If verification fails (bad signature, invalid attestation, wrong namespace), voices are silently dropped. Check relay logs for verification failures.

**Sync interval too slow**
The default sync interval is 300 seconds (5 minutes). For faster sync during testing, this is configurable in the relay YAML config but not currently exposed as an env var.

**One-directional sync**
Peering must be configured on both sides. If you added the peer but they haven't added you, sync only flows in one direction.

## Further Reading

- [Relay Federation](relay/federation.md) — theory, data sovereignty, attestation rollup, cross-relay verification
- [Operator Guide](operator-guide.md) — initial setup and deployment
- [Relay Overview](relay/overview.md) — full endpoint reference
- [Environment Variable Reference](operator-env-reference.md) — all relay env vars

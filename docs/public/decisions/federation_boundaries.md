# ADR: Federation Boundaries

**Status:** Accepted
**Date:** 2026-04-12

## Decision

CivicOS federation is structured around three independent boundary
types — **protocol**, **data**, and **trust** — with each boundary
determining what is shared globally, what is shared between peers,
and what stays local to an operator. The boundaries are designed
so that a second independent operator can join the network without
changes to the protocol, without merging databases, and without
coordinating trust decisions with existing operators.

1. **Protocol boundaries are global and frozen per version.**
   The Nostr event kinds (30800-30899), tag vocabulary (`d`, `j`,
   `stance`, `type`), entity ID format
   (`{type}:{jurisdiction}:{source}:{id}`), signature scheme
   (BIP-340 Schnorr on secp256k1), and sync wire format
   (`civicos:sync:v1:...`) are shared across all operators.
   Changing any of these requires a protocol version bump.

2. **Data boundaries follow the read/write split.** Civic data
   (meetings, decisions, legislation, municipal code) is
   *authoritative per jurisdiction* and flows outward via read-only
   MCP queries. Coordination data (voices, actions, comments,
   initiatives) is *authored per user* and federates between
   operators via relay sync. Neither data type merges into a single
   global store.

3. **Trust boundaries are per-operator and per-jurisdiction.**
   Each relay independently decides which attestation issuers it
   trusts, which peer relays it syncs with, and what acceptance
   policy it enforces. Trust decisions are configuration, not
   protocol — two operators for the same jurisdiction can have
   different issuer registries and still interoperate on the
   protocol layer.

## Context

CivicOS has five existing Architecture Decision Records that each
address a slice of federation:

- [Entity ID Namespace](entity_id_namespace.md) — global ID
  uniqueness via `{type}:{jurisdiction}:{source}:{id}`
- [DataSource Protocol](data_source_federation.md) — read-only
  `DataSource` abstraction over local and federated backends
- [Federation Domain Architecture](federation_domain_architecture.md)
  — Registry + BYOD model, operator types, domain structure
- [Query Interface](query_interface.md) — v2 query layer with
  `include_parents` / `include_siblings`
- [Tool Scope and Federation](tool_scope_and_federation.md) —
  read/write split, scope policies for 65+ MCP tools

These decisions were made during single-operator pilot, when the
questions they answered were somewhat theoretical. As the system
approaches multi-operator deployment, concrete boundary questions
arise:

- When a third-party operator deploys a relay, **what exactly do
  they need to match** in order to peer with existing relays?
- When a query fans out across jurisdictions, **where does data
  come from** and what happens when a jurisdiction is unreachable?
- When a user attested at Relay A submits a voice to Relay B,
  **what does B verify** and what does it take on trust?

This ADR answers these questions by documenting the three boundary
types, the concrete protocols at each boundary, and the failure
modes at each seam.

## Protocol boundaries: what every operator must share

The protocol boundary is the minimum compatibility surface. An
operator that conforms to this boundary can interoperate with any
other conforming operator, regardless of how different their
deployment, configuration, or organizational structure.

### Shared globally (breaking changes require version bump)

| Component | Specification | Location |
|-----------|--------------|----------|
| Event kinds | 30800 (voice), 30801 (entity), 30802 (subscription), 30803 (comment), 30850 (attestation), 30810-30812 (actions), 10800 (provenance), 1800-1804 (vouch, notification, key-link, feedback) | `civicos_relay/nostr/kinds.py` |
| Tag vocabulary | `d`, `j`, `stance`, `type`, `title`, `p`, `t`, `threshold` | `civicos_relay/nostr/kinds.py` |
| Signature scheme | BIP-340 Schnorr on secp256k1 (NOT P-256 ECDSA) | `civicos_relay/voice/crypto.py` |
| Event ID computation | `SHA256(json([0, pubkey, created_at, kind, tags, content]))` | NIP-01, `crypto.py:35-44` |
| Entity ID format | `{entity_type}:{jurisdiction_id}:{source}:{identifier}` | [Entity ID Namespace](entity_id_namespace.md) |
| Sync wire format | `civicos:sync:v1:{relay_id}:{data_hash}:{cursor}` | `civicos_relay/sync/protocol.py` |
| Attestation format | Kind-30850, d-tag `attest:{jurisdiction}:{subject_pubkey}`, content `civicos:attestation:v1:{jurisdiction}:{type}:{created_at}` | `nostr/kinds.py:90-105` |
| Verification checks | 6-check sequence: kind, issuer, d-tag, required tags, event ID hash, Schnorr signature | `voice/crypto.py` |

### Not shared (operator configuration)

| Component | Per-operator | Notes |
|-----------|-------------|-------|
| Trusted issuer pubkeys | Yes | Each relay maintains its own issuer registry |
| Acceptance policy (rate limits, PoW difficulty) | Yes | Config-driven via `relay_policies.json` |
| Peer relay list | Yes | Which relays to sync with |
| Storage backend | Yes | Postgres connection, schema identical but data independent |
| Domain/URL | Yes | BYOD or hosted on `civicosproject.org` |
| Token issuance keys | Yes | Blind signature issuer keypair per operator |

### Version negotiation

The sync protocol includes a version prefix
(`civicos:sync:v1:...`). If a future version changes the event
structure, kind semantics, or verification rules, relays that
speak different versions will see the version mismatch in the
sync handshake and can degrade gracefully (refuse sync rather
than silently corrupt data).

No backwards-compatible negotiation is planned for v1. Version
changes are breaking — both sides must be on the same version to
sync. This is a deliberate simplicity choice: the federation
network is small enough that coordinated upgrades are cheaper than
version negotiation machinery.

## Data boundaries: what lives where

### Civic data (authoritative, read-only)

Civic data — meetings, decisions, legislation, municipal code,
budget, issues — has a canonical source per jurisdiction: the
official operator (typically the city government or a
civicosproject.org-hosted instance running the extraction
pipeline).

```
Authoritative Source              Querying Instance
┌─────────────────────┐           ┌─────────────────────┐
│ city-san-rafael      │           │ bay-area regional    │
│ MCP server           │           │ MCP server           │
│                      │           │                      │
│ Meetings: 98         │◄──query──│ "What's on the       │
│ Decisions: 44        │           │  agenda in SR?"      │
│ Transcripts: 19      │──result─►│                      │
│ Legislation: 17,719  │           │ Labels result as     │
│                      │           │ jurisdiction:        │
└─────────────────────┘           │   city-san-rafael    │
                                  └─────────────────────┘
```

**Today:** All civic data lives in a single Supabase instance.
Cross-jurisdiction queries are local database queries with
jurisdiction-filtered WHERE clauses. `walk_scope()` resolves the
scope to a list of jurisdiction IDs and fans the storage call
across them — fast, reliable, no network hops.

**Federated future:** When a jurisdiction's data moves to a
separate operator, the `DataSource` protocol
([data_source_federation.md](data_source_federation.md)) switches
from `LocalDataSource` (direct DB query) to `FederatedDataSource`
(MCP query to the remote operator). The tool handler, the scope
walker, and the result labeling all remain identical. The only
change is which `DataSource` implementation the factory returns.

**Failure mode:** If a federated jurisdiction is unreachable
during a scope walk, `walk_scope()` catches the exception, logs
the failure, and continues with results from reachable
jurisdictions. The caller sees partial results clearly labeled
by source — a gap in jurisdiction labels is the signal that a
source was unavailable. This is the existing behavior for local
query failures and extends naturally to network failures.

**Caching:** Not specified by this ADR. A regional server that
frequently queries a federated jurisdiction's MCP server may
cache results locally with a TTL. The cache is an operator
decision, not a protocol requirement. Cache invalidation is
the operator's problem — the registry can publish data freshness
hints, but the protocol doesn't enforce them.

### Coordination data (peer-to-peer, replicated)

Coordination data — voices, actions, comments, initiatives —
federates between relays via the sync protocol. Every relay that
syncs a voice independently verifies it (six-check verification)
before accepting it into local storage.

```
Relay A                           Relay B
┌─────────────────────┐           ┌─────────────────────┐
│ 42 voices for        │           │ 38 voices for        │
│ entity X             │           │ entity X             │
│                      │ GET       │                      │
│ /sync/voices?        │◄─────────│ "Give me voices      │
│   since=2026-04-01   │           │  since April 1"      │
│                      │──────────►│                      │
│ [{voice1}, {voice2}  │  signed   │ Verify each voice:   │
│  ...]                │  response │ ✓ kind, ✓ issuer,    │
│                      │           │ ✓ d-tag, ✓ tags,     │
│                      │           │ ✓ event ID, ✓ sig    │
│                      │           │                      │
│                      │           │ Accept: 4 new        │
│                      │           │ Reject: 0            │
│                      │           │ Duplicate: 34        │
│                      │           │ Now: 42 voices       │
└─────────────────────┘           └─────────────────────┘
```

**Key property:** Relay A doesn't vouch for the voices it
sends — it transmits raw Nostr events with embedded proofs.
Relay B verifies each one from scratch. A compromised Relay A
cannot inject a forged voice because the math would fail at
Relay B's verification step.

**Namespace filtering:** Sync requests support a `namespace`
parameter that filters by entity ID prefix. A regional relay
syncing with a city relay can request only voices for entities
in that city's namespace (`decision:city-san-rafael:*`). This
prevents a full-network sync from pulling every voice on every
relay — operators choose what scope of data they want to
replicate.

**Conflict resolution:** Voices are idempotent — same
`kind:pubkey:d-tag` resolves to one voice per entity per user.
If a user revokes and re-casts a voice, the later event
(by `created_at` timestamp) wins. No merge logic, no
coordination needed.

### Subscriptions (local, not federated)

Subscriptions are per-operator. A user's notification preferences
on Relay A are not visible to Relay B. This is intentional:

- Subscriptions contain encrypted delivery configuration
  (webhook URLs, push notification endpoints) that should not
  leak between operators
- A relay has no obligation to notify users of another relay's
  operator about events it observes
- Cross-relay notification would require a forwarding mechanism
  that creates coupling between operators' availability

If a user wants notifications from voices on Relay B, they
subscribe directly to Relay B. The browser extension manages
subscriptions across multiple relays on the user's behalf.

## Trust boundaries: what each operator decides independently

### Attestation issuer trust

Each relay maintains its own registry of trusted attestation
issuers — organizations authorized to sign kind-30850
attestation events for a jurisdiction. The registry is managed
through admin endpoints:

```
POST /coordination/issuers/register    Register issuer (starts unverified)
POST /coordination/admin/issuer/{id}/verify    Mark as trusted
POST /coordination/admin/issuer/{id}/revoke    Revoke trust
GET  /coordination/issuers/{jurisdiction}      List trusted issuers
```

**Cross-operator attestation works when operators share issuers.**
If the League of Women Voters is a trusted issuer on both the
city-run relay and the civicosproject.org relay, an attestation
from LWV is accepted by both. No coordination is needed between
relay operators — both independently trust the same signer's
public key.

**Cross-operator attestation fails when issuers differ.** If
Relay A trusts LWV but Relay B doesn't, a voice carrying an
LWV attestation will be accepted by A but rate-limited on B.
This is the correct behavior: trust is an operator decision,
and disagreement between operators about who is trustworthy is
a feature, not a bug.

**Issuer key distribution is out of band.** The protocol does
not specify how operators learn about issuer pubkeys. In
practice, trusted organizations register their signers via the
admin API, and the relay operator verifies the registration.
The civicosproject.org registry can publish a directory of
known issuers as a convenience, but operators are not required
to import from it.

### Attestation rollup across government levels

A city-level attestation is valid for entities at every
government level above the city in the jurisdiction hierarchy:

```
city-san-rafael attestation →
  city-san-rafael entities     ✓ (exact match)
  county-marin entities        ✓ (San Rafael ∈ Marin)
  state-california entities    ✓ (Marin ∈ California)
  country-united-states entities ✓ (California ∈ US)

city-san-rafael attestation →
  city-novato entities         ✗ (San Rafael ≠ Novato)
  city-mill-valley entities    ✗ (sideways, not upward)
```

Rollup walks the `parent_jurisdictions` chain from
`config/registry.json`. If the attestation's jurisdiction is an
ancestor-or-equal of the entity's jurisdiction, the attestation
is valid. No sideways rollup — a San Rafael attestation does
not grant standing in Novato, even though both are in Marin.

### Token issuance trust

Blind signature tokens for payment-tier acceptance are issued
per operator. Each operator generates its own token issuer
keypair and publishes the public key via
`GET /coordination/tokens/info`.

**Cross-operator token acceptance** is possible if operators
include each other's issuer pubkeys in their
`TOKEN_ISSUER_PUBKEYS` configuration. A token purchased from
Relay A can be spent on Relay B if B trusts A's issuer key.
This is opt-in and unilateral — B decides whether to trust A's
tokens, A doesn't need to know or agree.

**Double-spend protection** is per-operator. Each relay
maintains its own `SpentTokenStorage`. A token spent on Relay A
can theoretically be replayed on Relay B. This is acceptable
because:

- Token purchase is cheap (rate-limit bypass, not monetary value)
- Cross-operator token trust is rare in early federation
- A shared double-spend log would require coordinated writes
  across operators, creating a central dependency

If cross-operator token abuse becomes a problem, operators can
share spent-token lists via a simple pub/sub mechanism (publish
spent hashes, subscribe to peers' spent lists). This is a future
optimization, not a launch requirement.

### Acceptance policy

Each relay configures its own acceptance policy: rate limits per
event type, proof-of-work difficulty, attestation validity period.
The policy is loaded from `config/relay_policies.json` with
per-jurisdiction overrides.

**No global policy coordination.** Relay A's rate limit of
50 voices/day is independent of Relay B's limit of 100/day. A
user who hits the limit on A can still write to B. This means
aggregate write capacity scales with the number of relays a
user is connected to — a feature of the multi-operator model,
not a loophole. Rate limits prevent individual-relay abuse, not
network-wide throttling.

## Cross-jurisdiction query execution

### Read path: scope walking

When an MCP tool runs, it resolves its declared scope policy to
a list of jurisdiction IDs and fans the storage call across them.
The execution flow:

```
Tool handler
    │
    ▼
resolve_requested_scope(policy, args)
    │ Decide which scope to walk (default or caller-expanded)
    ▼
resolve_scope_to_jurisdictions(scope, primary)
    │ Expand scope enum to concrete jurisdiction IDs:
    │   PRIMARY → ["city-san-rafael"]
    │   PRIMARY_PLUS_SIBLINGS → ["city-san-rafael", "city-novato", ...]
    │   PRIMARY_PLUS_ALL_PARENTS → ["city-san-rafael", "county-marin",
    │                                "state-california", "country-united-states"]
    │   REGION → ["city-san-rafael", "city-novato", "city-mill-valley", ...]
    │
    │ Cap at MAX_SCOPE_FANOUT (25 jurisdictions)
    ▼
walk_scope(policy, primary, storage_call)
    │ For each jurisdiction:
    │   1. Call storage_call(jurisdiction_id)
    │   2. If call fails, log and continue (partial results)
    │   3. Stamp each result row with jurisdiction label
    │
    ▼
Deduplicated, labeled results → tool handler → AI caller
```

**Today:** `storage_call` is a closure over `StorageBackend`
methods. All jurisdictions hit the same Postgres database.
Latency is ~O(N * single-query-time) where N is the number of
jurisdictions in the scope (typically 1-15).

**Federated future:** `storage_call` becomes a closure over
`DataSource` methods. For jurisdictions hosted by the same
operator, it remains a local query. For jurisdictions hosted by
a remote operator, it becomes an MCP query to the remote
server. `walk_scope()` does not change — the closure hides the
data source.

**Latency implications:** Federated queries add network RTT for
each remote jurisdiction. With MAX_SCOPE_FANOUT of 25 and
serial execution, worst-case latency is 25 * remote_RTT. If
this becomes problematic, the walker can be made concurrent
(parallel queries to remote jurisdictions). The protocol does
not require serial execution — the current implementation is
serial for simplicity.

### Write path: strict routing

Write-side tools (voice, comment, initiative, action) are
strictly scoped to the primary jurisdiction of the MCP server
they run on. A user connected to `san-rafael.civicosproject.org`
cannot submit a voice on a Novato entity through that server.

```
Tool handler checks:
  target jurisdiction == server primary jurisdiction?
    Yes → proceed to relay endpoint
    No  → return error: "Connect to the Novato instance"
```

The relay endpoint that receives the signed event also checks:
the event's `j` tag must match the relay's configured
jurisdiction (or be a descendant in the hierarchy, for
upward-rollup entities like federal legislation). Cross-
jurisdiction writes fail at two independent checkpoints.

**Federated write routing** (not yet needed): If a regional MCP
server wants to accept writes for any jurisdiction in its region,
it would need to proxy the signed event to the authoritative
relay for that jurisdiction. The event signature is preserved —
the proxy doesn't re-sign, just forwards. The authoritative relay
verifies the signature and accepts or rejects. This is a
straightforward extension of the existing architecture but is not
implemented because no regional MCP server needs write support
yet.

## What changes when the first third-party operator joins

This section enumerates the concrete steps for a new operator to
join the federation network. Nothing below requires protocol
changes — it's all configuration.

### Minimum viable federation

1. **Deploy a relay.** Use the reference implementation
   (`civicos-relay`). Configure `RELAY_DATABASE_URL` to a
   Postgres instance. Set `RELAY_JURISDICTION` to the target
   jurisdiction.

2. **Configure peer sync.** Add existing relay URLs to the peer
   list. Trigger initial sync via
   `POST /coordination/sync/trigger`. Verify imported voice
   counts match.

3. **Register issuers.** Add trusted attestation issuer pubkeys
   via the admin API. At minimum, trust the same issuers the
   existing relay trusts for the target jurisdiction.

4. **Register with the registry.** Submit operator metadata
   (name, type, jurisdiction, endpoints) to the
   civicosproject.org registry so clients can discover the new
   relay.

5. **Optionally deploy an MCP server.** If the operator wants to
   serve civic data queries, deploy `civicos-mcp` pointed at
   their own data source. If they're running a relay only (e.g.,
   a civic org coordinating community voices), no MCP server is
   needed.

### What doesn't change

- Event structure and kinds
- Verification algorithm
- Entity ID format
- Scope walking logic
- Tool API signatures
- Browser extension communication protocol

### What the new operator configures

- Issuer trust decisions (which organizations to trust for
  attestation)
- Peer relay list (which relays to sync with)
- Acceptance policy (rate limits, PoW requirements)
- Domain and deployment infrastructure
- Token issuance keys (if accepting paid-tier writes)

## Consequences

1. **Protocol stability enables independent deployment.** Because
   the protocol boundary is frozen per version, operators can
   deploy at their own pace without coordinating release schedules.
   A relay running the reference implementation at commit A is
   compatible with one at commit B, as long as both are v1.

2. **Trust is composable, not transitive.** Relay B trusting
   Relay A does not mean B trusts everyone A trusts. Trust
   relationships are configured independently per operator. This
   prevents trust creep: an operator's security posture is
   determined by their own decisions, not by the weakest link in
   a trust chain.

3. **Data sovereignty is maintained by default.** No operator is
   required to replicate data they don't want. A civic org relay
   can sync only voices (not civic data). A city government can
   publish civic data (via MCP) without accepting voices from
   external relays. The boundary defaults are sovereignty-
   preserving.

4. **Partial federation is valid.** Not all operators need to
   peer with all others. A city relay that syncs with
   civicosproject.org but not with a newspaper's relay is still a
   valid federation participant. Users who want the union of all
   voices connect to multiple relays. The browser extension
   handles multi-relay aggregation.

5. **Commitment logs become load-bearing at Tier 2.** The jump
   from single operator (Tier 1) to operator-plus-auditor
   (Tier 2) is when commitment logs go from "nice to have" to
   "the mechanism that makes federation credible." An auditor
   pulling voices from a relay and comparing merkle roots is the
   minimum verification that catches silent censorship. This ADR
   does not specify the commitment log format — that is a future
   ADR — but identifies it as the critical next protocol
   extension after the first third-party operator joins.

## Non-goals

- **This ADR does not define the commitment log protocol.** The
  merkle root format, publication schedule, and cross-relay
  comparison mechanism are deferred to a future ADR. The trust
  model ([trust.md](../relay/trust.md)) describes the concept;
  the protocol specification is a separate, later decision.

- **This ADR does not specify operator discovery.** How clients
  find which operators serve a jurisdiction is covered by the
  registry model in
  [federation_domain_architecture.md](federation_domain_architecture.md).
  The registry API specification is a separate concern.

- **This ADR does not address cross-operator subscription
  forwarding.** Subscriptions are per-operator by design. If a
  future use case requires cross-relay notification forwarding,
  that is a new protocol extension, not a change to these
  boundaries.

- **This ADR does not mandate federation.** Single-operator
  deployments remain valid. A city running one relay and one MCP
  server with no peering is a complete CivicOS deployment. The
  boundaries documented here are for when operators *choose* to
  federate.

## Related decisions

- [Entity ID Namespace](entity_id_namespace.md) — global ID
  uniqueness across jurisdictions
- [DataSource Protocol](data_source_federation.md) — query
  abstraction for local and federated data
- [Federation Domain Architecture](federation_domain_architecture.md)
  — Registry + BYOD model, operator types
- [Query Interface](query_interface.md) — v2 query layer with
  cross-jurisdiction support
- [Tool Scope and Federation](tool_scope_and_federation.md) —
  read/write split, per-tool scope policies

## Implementation references

- `packages/civicos-relay/src/civicos_relay/nostr/kinds.py` —
  Nostr kind constants and tag vocabulary
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py` —
  Six-check verification, BIP-340 signatures
- `packages/civicos-relay/src/civicos_relay/voice/blind.py` —
  Blind signature token issuance
- `packages/civicos-relay/src/civicos_relay/server/acceptance.py`
  — Tiered acceptance policy
- `packages/civicos-relay/src/civicos_relay/sync/protocol.py` —
  Sync wire format and protocol constants
- `apps/civicos-mcp/tools/scope_walk.py` — Scope resolution and
  fan-out
- `apps/civicos-mcp/tools/scope.py` — Per-tool scope policy table
- `config/registry.json` — Jurisdiction hierarchy, parent chains,
  regions

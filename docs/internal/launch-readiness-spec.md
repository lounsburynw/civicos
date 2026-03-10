# Launch Readiness Spec

**Status:** Draft
**Date:** 2026-03-09

CivicOS is approaching launch readiness for San Rafael. This spec addresses three interlocking capabilities needed to go from single-city pilot to multi-city, multi-operator platform: city onboarding, relay federation, and developer/operator experience.

## Design Principle: MCP-Native Administration

CivicOS is AI-enabled civic infrastructure. Its administrative interface should be too.

Today, platform operations run through Claude Code slash commands (`/onboard`, `/ingest`, `/data-status`, `/vectors`). These commands call the same Python functions that power the REST admin router and MCP server. The gap isn't capability — it's exposure. The admin operations exist but are only accessible to someone with repo access and Claude Code.

**This spec treats MCP as the universal interface.** The same tools that serve civic data to AI assistants should serve operational capabilities to operators. Claude Code commands become the reference implementation; MCP tools become the product.

This means:
- A city IT director onboards their city by talking to Claude (or ChatGPT, or any MCP client)
- A civic org founder spins up their own MCP server the same way
- A developer queries the API through the same tool interface
- The platform operator (us) uses Claude Code for power-user workflows, which wrap the same MCP tools

### Why Not Later

The REST admin router already implements most operational endpoints. The MCP server is deployed on Modal with the same backend access. The slash commands document the workflows. Wiring admin tools into MCP is incremental — roughly 5-7 new tool definitions that delegate to existing code. There is no architectural blocker; just registration.

---

## 1. City Onboarding Pipeline

### Current State

The `/onboard` CLI wizard handles:
1. Platform auto-detection (Legistar, CivicClerk, ProudCity)
2. Jurisdiction YAML config generation
3. Archive discovery (meeting URLs)
4. Config validation

Post-onboard, separate commands handle ingestion (`/ingest`), vector indexing (`/vectors`), and monitoring (`/data-status`).

### What Works

- **Platform detection** covers Legistar (Berkeley, Oakland, SF, Santa Rosa, Hayward, Napa), CivicClerk (Richmond, El Cerrito, Daly City, Milpitas), ProudCity (San Rafael)
- **Base client architecture** (`BaseExtractor`) with `health()`, `validate()`, `get_events()` is generic
- **Checkpoint-based ingestion** handles incremental updates
- **Config schema** (`data/jurisdictions/schema.yaml`) is well-defined

### Gaps

| Gap | Impact | Effort |
|-----|--------|--------|
| No Granicus auto-detection | Misses ~30% of US cities | Medium — requires subdomain + view ID discovery |
| HUD grantee lookup is manual | Slows onboarding | Small — HUD Exchange API integration |
| Zip codes/neighborhoods manual | Tedious per-city work | Small — Census geocoder API |
| No post-onboard health dashboard | Admins can't see what populated | Small — `/data-status` exists, needs MCP exposure |
| Vector indexing is a separate step | Easy to forget, city seems "empty" | Small — add to onboard completion checklist or auto-trigger |
| Each city may need 1 custom parser | Expected, not eliminable | Varies — framework makes this manageable |

### Target: City #2 Acceptance Criteria

- Onboarded in a single session (operator-assisted or self-serve via MCP)
- Platform auto-detected or manually specified
- Config generated, validated, and written
- Initial ingestion completes (meetings, issues, legislation)
- Vector embeddings generated
- `/data-status` confirms all corpora populated
- Civic data queryable via MCP within 24 hours of onboard start

### Jurisdiction #2: Marin County

**Decision:** Onboard Marin County (`county-marin`) as the second jurisdiction, not a second city.

**Rationale:**
- **Extraction config already exists** (`data/extraction/county-marin.json`) with Granicus platform details, 1,622 historical meetings, view IDs, and URL patterns
- **Forces Granicus parser** — the platform covering ~30% of US jurisdictions. Building it now unblocks dozens of future cities
- **Directly tests jurisdiction hierarchy** — San Rafael residents voicing on Board of Supervisors items validates upward attestation rollup
- **Shared county data** — housing authority, HUD programs, flood control district are county-level entities that San Rafael residents interact with
- **Multiple meeting bodies** — BOS, Planning Commission, Housing Authority, Marin Transit, Open Space District = rich test of multi-body extraction

A second city (Berkeley, Novato) comes third, after county-level federation is proven.

### MCP Tools to Add

```
onboard_city(city_name, url, state, county?, platform?)
  → Runs platform detection, generates config, validates
  → Returns: config preview, detected platform, TODO list

check_onboard_status(jurisdiction)
  → Returns: config completeness, ingestion status per corpus, vector coverage
  → Wraps DataStatus + VectorCoverage

trigger_ingestion(jurisdiction, sources?)
  → Triggers Modal ingestion for specified sources (or all)
  → Returns: operation ID for status polling

get_ingestion_status(operation_id)
  → Returns: progress, errors, checkpoint state
```

---

## 2. Relay Federation

### Current State (60% Ready)

**Working:**
- Voice casting with secp256k1 Schnorr signatures (Nostr-correct)
- Relay-to-relay sync (export/import, pagination, dedup)
- Peer health checking with auto-disable
- Multi-issuer attestation (code batch → redemption → kind-30850 proof)
- Event emission with topic/type/entity/geographic subscription matching
- 18 test files

**Not working:**

| Gap | Severity | Effort |
|-----|----------|--------|
| Sync response signature verification is a `TODO` | **Critical** — peers can send modified data | Small |
| Jurisdiction hierarchy rollup not implemented | **High** — blocks cross-level voicing | Medium |
| Subscription federation missing | Medium — subscribers only see local events | Large |
| Peer health state not persisted | Medium — lost on restart | Small |
| Namespace filtering not enforced in sync | Medium — peers sync everything | Medium |
| Merkle root commitment logs | Low (launch) — needed for trust tier 2 | Large |

### Implementation Sequence

**Phase A: Security baseline** (pre-launch)
1. Implement sync response signature verification (`sync/service.py:154`)
2. Persist peer health state to `coordination_peer_health` table

**Phase B: Multi-jurisdiction** (city #2)
3. Implement jurisdiction hierarchy tree (config-driven, walk parent chain)
4. Wire attestation rollup into voice verification
5. Enforce namespace filtering in sync

**Phase C: Trust infrastructure** (post-launch)
6. Commitment logs with merkle roots
7. Cross-relay consistency verification
8. Subscription federation

### Acceptance Criteria

- Two relays (CivicOS + civic org) sync voices for San Rafael
- San Rafael attestation validates for Marin County entities (upward rollup)
- Peer health survives relay restart
- Invalid sync responses are rejected (signature verification)

---

## 3. Operator & Developer Experience

### The Authorization Question

CivicOS has four operator types (per [Federation Domain Architecture ADR](../public/decisions/federation_domain_architecture.md)):

| Type | Example | Runs | Authority |
|------|---------|------|-----------|
| **Official** | City of San Rafael | MCP + Relay | Authoritative for civic data |
| **Civic org** | League of Women Voters | MCP + Relay | Community voices, curated data |
| **Neighborhood** | Canal Alliance | Relay only | Hyperlocal coordination |
| **Media** | Marin IJ | MCP only | Transparency, public interest |

Plus two additional personas:

| Persona | Tool | Needs |
|---------|------|-------|
| **Platform operator** | Claude Code | Full access — deploy, debug, schema changes |
| **Developer** | API / MCP | Read civic data, build apps, subscribe to events |

### Authorization Model

The key insight: **publishing an MCP server is permissionless. Claiming authority is not.**

Anyone can run an MCP server that serves civic data for any jurisdiction. This is by design — it's open source, the data is public, and restricting it would contradict the federation model. What differs is **what the registry says about you** and **what operations you can perform**.

Three authorization layers:

#### Layer 1: Data Access (API Keys)

Read-only access to civic data. Tiered by rate limit and capability.

| Tier | Rate | Access | Audience |
|------|------|--------|----------|
| **Open** | 30 req/min | Status, provenance, voice counts, Nostr directory | Anyone, no key |
| **Free** | 60 req/min | + events, issues, legislation, budget | Devs exploring |
| **Builder** | 300 req/min | + transcripts, testimony, context assembly, MCP tools | Devs building apps |
| **Organization** | 300 req/min | + bulk exports, webhooks, coordination write | Civic orgs |

Self-serve registration: `POST /api/register` → returns API key. No approval gate for Free/Builder tiers. Organization tier requires email verification.

#### Layer 2: Coordination (Nostr Signatures)

Write operations on coordination data. No API key needed — identity is the signature.

| Operation | Auth | Requirement |
|-----------|------|-------------|
| Cast voice | Nostr signature + attestation proof | Must be attested resident |
| Submit comment | Nostr signature | Any key holder |
| Create initiative | Nostr signature + attestation proof | Must be attested resident |
| Subscribe | Nostr signature | Any key holder |

This layer is already implemented. Attestation codes are distributed at in-person civic events. The relay verifies signatures and attestation proofs cryptographically — no trust in the relay required.

**Attestation issuance is permissionless.** Any organization can run `civicos-signer` and distribute their own attestation codes. The issuer's pubkey is embedded in every attestation event (kind-30850), making provenance transparent. Trust decisions happen at two levels:

- **Relay level:** Operators configure which issuers they accept for gated operations (voicing). A city's official relay might honor city-issued and recognized civic org attestations. A community relay might accept any valid attestation.
- **Client level:** The browser extension and AI agents display issuer identity alongside voice counts (e.g., "47 voices: 32 via City of San Rafael, 12 via LWV Marin, 3 via Bob's Burgers"). Users decide how much weight to give each issuer.

This mirrors how public testimony works: anyone can show up and speak. The audience decides how much to trust the speaker. The relay's job is to verify the signature is real, not to judge whether the issuer is worthy.

#### Layer 3: Operations (Jurisdiction-Scoped Admin)

Administrative operations on infrastructure. This is the new layer.

| Operation | Who | Auth Mechanism |
|-----------|-----|----------------|
| Trigger ingestion | Jurisdiction admin | API key (city/org tier) + jurisdiction scope |
| Reset checkpoint | Jurisdiction admin | API key (city/org tier) + jurisdiction scope |
| Manage attestation codes | Attestation issuer | Issuer registry + bearer token |
| Register as operator | Anyone | Self-serve, registry validates domain |
| Claim "official" status | City government | Manual verification (domain + contact) |
| Platform deploy/debug | Platform operator | Claude Code (repo access) |

**The edge case: civic org founder who wants their own MCP.**

This is not an edge case — it's operator type #2. The flow:

1. Founder runs `onboard_city` MCP tool (or uses Claude Code) to generate jurisdiction config
2. If jurisdiction already exists in registry, config references existing data sources
3. Founder deploys their own MCP server (Modal, self-hosted, whatever)
4. Founder registers in the operator registry: `POST registry.civicosproject.org/operators`
5. Registry lists them as a `civic_org` operator for that jurisdiction
6. Their MCP server serves the same public civic data (mirrored from authoritative source) plus any community-curated additions
7. If they also run a relay, voices federate with other relays via peer sync

**What they CAN do without permission:**
- Run an MCP server serving public civic data
- Run a relay accepting voices
- Register in the operator directory
- Distribute their own attestation codes (via `civicos-signer`)

**What they CANNOT do:**
- Claim "official" status in the registry (requires domain verification)
- Trigger ingestion on someone else's infrastructure
- Modify authoritative civic data (meetings, decisions) — they can only mirror it
- Issue attestation codes on behalf of another organization

**What they get from the platform:**
- `civicos-signer` package to run their own attestation signing service
- Reference MCP server implementation to fork/customize
- Registry listing for discoverability
- Relay peering for voice federation

### MCP Admin Tools to Add

```
admin_data_status(jurisdiction)
  → Corpus counts, vector coverage, gaps
  → Wraps existing DataStatus class

admin_system_health()
  → Storage backend, vector backend, API key validity
  → Wraps existing admin router /status

admin_vector_coverage(jurisdiction, corpus_type?)
  → Embedding counts vs storage counts
  → Wraps existing VectorCoverage class

admin_cost_dashboard()
  → Operating costs by service and time period
  → Wraps existing admin router /cost-dashboard

trigger_vector_index(jurisdiction, corpus_type?)
  → Triggers Modal GPU job for embeddings
  → Returns operation ID

manage_api_keys(action, key_id?, tier?, jurisdictions?)
  → Create, list, revoke API keys
  → Wraps existing admin router /keys
```

### Developer Experience

**What a dev needs to build an app on CivicOS:**

1. **API key** — self-serve, free tier, immediate
2. **Working example** — "What's my city council voting on?" widget (< 100 lines)
3. **TypeScript client** — `civicos-client` already exists, needs npm publish
4. **MCP tool access** — for AI-native apps, connect to the MCP server directly
5. **Webhook subscriptions** — "notify me when a new decision is made about housing"

**Lead example: AI Civic Assistant**

The primary developer example is a minimal autonomous agent that connects to the CivicOS MCP server. This is what developers want to build right now, and it naturally demonstrates the full platform:

- Python or TypeScript, < 50 lines of agent code
- Connects to CivicOS MCP endpoint with a free-tier API key
- Uses Claude, OpenAI, or any LLM as the reasoning layer
- Can answer "what's my city council voting on?", "what did residents say about the bike lane?", "draft me a public comment for the housing item"
- README shows how to swap in any jurisdiction's MCP endpoint

Additional examples (lower priority):

| App | Complexity | Demonstrates |
|-----|-----------|-------------|
| Legislative alert bot | Medium | Subscriptions, webhook delivery, topic filtering |
| Meeting widget | Simple | API queries, upcoming meetings, embed in any site |
| Neighborhood dashboard | Medium | Issue data, geographic filtering, voice counts |

### Public API Gaps to Close

| Gap | Current State | Action |
|-----|---------------|--------|
| No self-serve key registration | Keys manually provisioned | Add `POST /api/register` |
| Stripe → key provisioning incomplete | Checkout endpoint exists, flow unfinished | Complete `payment_intent.succeeded` → key creation |
| Jurisdiction scoping not enforced | `AuthContext.jurisdictions` defined, not checked | Add middleware validation |
| MCP server has no auth | Open endpoint | Add optional Bearer token for admin tools (see below) |
| CORS is wildcard | `Access-Control-Allow-Origin: *` | Restrict to known origins + configurable allowlist |
| Usage not persisted for billing | Fire-and-forget logging | Complete `api_usage_logs` table flow |
| `civicos-client` not on npm | Package exists, not published | `npm publish` |

---

## 4. Sequencing & Dependencies

### Dependency Chain

```
Fix sync signature verification (security baseline)
    ↓
Pick city #2, run onboard (validates extraction generality)
    ↓
Wire admin tools into MCP (enables self-serve monitoring)
    ↓
Implement jurisdiction hierarchy (enables cross-level voicing)
    ↓
Ship free-tier API keys + example app (enables developer ecosystem)
    ↓
Register civic org operator for SR (validates multi-operator federation)
    ↓
Publish civicos-client to npm (enables frontend devs)
```

### Session Breakdown (Estimated)

| Session | Work | Depends On |
|---------|------|------------|
| **S1** | Sync signature verification + peer health persistence | Nothing |
| **S2** | MCP admin tools (data_status, system_health, vector_coverage) | Nothing |
| **S3** | Granicus parser (multi-body) + Marin County BOS ingestion | S1 (security baseline) |
| **S4** | Self-serve API key registration + tier enforcement | Nothing |
| **S5** | Jurisdiction hierarchy + attestation rollup | S3 (needs county jurisdiction) |
| **S6** | AI civic assistant example + civicos-client npm publish | S4 (needs API keys) |
| **S7** | Multi-operator test (civic org relay for SR) | S1, S5 |

Sessions S1, S2, and S4 have no dependencies and can run in parallel.

### What's NOT In This Spec

- Commitment logs / merkle roots (post-launch trust infrastructure)
- Subscription federation (post-launch, after multi-operator is proven)
- Traditional admin web UI (MCP-native admin is the strategy)
- Special district jurisdiction handling (pragmatic approach per existing ADR)
- Second city onboarding (comes after county-level federation is proven)

### MCP Authentication

MCP auth is early in the ecosystem. The spec supports an optional `Authorization` header on HTTP transport, and major clients (Claude Desktop, ChatGPT, Cursor) support passing bearer tokens in server config. There is no standardized OAuth flow in MCP yet (OAuth 2.1 is drafted but not ratified).

**CivicOS approach:** Same API key system for both REST and MCP. Three tiers of tool access:

```
No auth required (public civic data):
  search_meeting_history, get_upcoming_meetings, city_pulse,
  find_similar_issues, search_regulatory_stack, etc.

Bearer token required (admin/operational tools):
  admin_data_status, trigger_ingestion, manage_api_keys,
  admin_cost_dashboard, trigger_vector_index, etc.

Nostr signature required (coordination writes — relay only, not MCP):
  Writes go through relay acceptance policy (not exposed in MCP).
```

MCP client configuration:
```json
{
  "mcpServers": {
    "civicos-san-rafael": {
      "url": "https://san-rafael.civicosproject.org/mcp",
      "headers": {
        "Authorization": "Bearer cvk_free_abc123"
      }
    }
  }
}
```

Implementation: Check `Authorization` header in MCP HTTP handler. If tool requires auth and no valid key present, return error. If tool is public, proceed without auth. Per-tool auth scoping is handled in the tool handler based on key tier.

When MCP OAuth 2.1 is ratified, add it as an alternative auth method. Bearer tokens remain supported.

---

## Decisions (Resolved)

1. **Jurisdiction #2:** Marin County. Extraction config exists, forces Granicus parser, tests jurisdiction hierarchy directly with San Rafael. A second city comes third.

2. **Attestation issuance:** Permissionless from day one. Any organization can run `civicos-signer` and distribute codes. Trust is layered: relays configure which issuers they accept for gated operations; clients display issuer provenance so users decide. This matches how public testimony works — anyone can speak, the audience decides trust.

3. **Registry:** Build the API now. The federation domain architecture ADR already specifies the registry endpoints and operator schema. A static `registry.json` doesn't support self-serve operator registration, which is core to the permissionless model. Registry writes live on the relay (operator registration is infrequent). Registry data is also published as a cacheable static manifest for high-availability reads — clients hit the manifest first, fall back to the API. This decouples read availability from relay uptime.

4. **MCP auth:** Optional Bearer token. Public civic data tools require no auth (the data is public). Admin and operational tools require a valid API key. Coordination writes require Nostr signatures (already implemented). This is backward-compatible — existing MCP clients with no auth configured continue to work for civic data queries.

5. **Granicus parser scope:** Build the parser to handle any meeting body generically (multi-body from day one). Validate against BOS, Planning Commission, Housing Authority, and Marin Transit — the four most structurally different bodies. Ingest BOS first (largest, most important for federation testing), remaining bodies follow automatically. This prioritizes portable ingestion infrastructure (goal b) while still shipping county content quickly (goal a).

6. **Lead example app:** AI civic assistant. Autonomous agents are what developers want to build now, and CivicOS MCP is the ideal substrate. A < 50 line agent script that connects to the MCP endpoint demonstrates the full platform value. Meeting widget and alert bot are secondary examples.

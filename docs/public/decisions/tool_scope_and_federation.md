# ADR: Tool Scope and the Read/Write Federation Boundary

**Status:** Accepted
**Date:** 2026-04-11

## Decision

Tool scope in the MCP server is governed by three independent axes —
**vertical** (city ↔ county ↔ state ↔ federal), **horizontal**
(sibling jurisdictions within a common parent or region), and
**ownership** (who is canonical for a given jurisdiction's data) — and
by the **read/write distinction** between tools that retrieve civic
data and tools that initiate civic actions.

1. **Scope lives on tools, not on deployments.** A server's deployment
   scope (`CIVICOS_JURISDICTION`, Modal app name, Cloudflare subdomain)
   is an *operational* boundary, not a *data* boundary. The actual data
   scope of any individual query is decided by the tool being called,
   based on a per-tool scope policy.

2. **Read-side tools expand scope freely along the vertical and
   horizontal axes, with results labeled by source jurisdiction.** A
   `search_legislation` call automatically includes parent-jurisdiction
   results (county code, state bills, federal rules) regardless of
   which server it runs on. A regional server's `get_upcoming_meetings`
   automatically aggregates across sibling jurisdictions in the region.
   Callers get scope expansion by default; narrowing is opt-in via
   explicit parameters.

3. **Write-side tools are strictly scoped to the primary jurisdiction
   of the server they run on.** A tool that submits a public comment,
   broadcasts a voice, creates an initiative, or takes any other action
   routes to a specific clerk, portal, or relay keyed to one
   jurisdiction. These tools refuse cross-jurisdiction operation and
   require the caller to be connected to the authoritative server for
   the target jurisdiction.

4. **Federation is a data-plane concern, not a tool-surface concern.**
   Whether the data underlying a read comes from local Postgres, a
   shared Supabase, or a peer instance queried via the relay network
   does not change the tool API, the scope policy, or the user
   experience. Federation is resolved inside the data access layer
   when a tool runs, not inside the connector URL or the tool
   signature.

## Context

CivicOS exposes civic data through MCP servers. Prior to this decision,
each MCP server was bound to exactly one jurisdiction via
`CIVICOS_JURISDICTION`, and every tool on that server operated on that
jurisdiction alone. This worked well for the single-pilot case
(San Rafael) but created three friction points as the system grew:

1. **Jurisdictional naïveté in tool results.** A user connected to
   `san-rafael.civicosproject.org/mcp` and asking "what housing
   legislation affects me?" received only San Rafael municipal code
   results, despite the CivicOS database already containing California
   state bills and federal HUD rules that clearly affect them. The data
   was available; the tool boundary hid it.

2. **Connector proliferation for regional users.** Someone wanting to
   track "what's happening in Marin" would need to install connectors
   for San Rafael, Mill Valley, Novato, Tiburon, Sausalito, Fairfax,
   San Anselmo, Corte Madera, Larkspur, Belvedere, Ross, and
   Marin County — twelve connectors to answer one question. Realistic
   users give up after about three.

3. **Federation coupling to deployment.** The instinct to solve (1)
   and (2) by adjusting deployment topology (more servers, fewer
   servers, regional servers) conflated operational boundaries with
   data scope and made the real federation question ("who is canonical
   for this jurisdiction's data?") much harder, because it got tangled
   up with "which Cloudflare subdomain serves this user?" The two
   questions are independent and should stay that way.

## The three axes of scope

### Vertical scope: city → county → state → federal

This is the government hierarchy, already encoded in
`parent_jurisdictions` in `config/registry.json`. A San Rafael resident
lives inside Marin County inside California inside the United States,
and laws at every level affect them. The v2 query layer
(`civicos-services/query/`) already supports `include_parents=true` on
search requests, which walks this chain.

Vertical scope is always available on any server. A city-scoped
deployment can walk up to federal; a regional deployment can do the
same. The only question is whether a given tool *should* expand
vertically by default — answered by the scope policy table below.

### Horizontal scope: siblings and regions

This is the peer-sibling relationship — cities that share a common
parent (Mill Valley and Larkspur both in Marin County) or regions
defined by operational geography (the Bay Area, the North Bay, SoCal).
The v2 query layer supports `include_siblings=true` bounded by a
common parent.

Horizontal scope beyond the direct sibling relationship requires a
**region** concept — a named set of jurisdiction IDs that does not
correspond to a single `parent_jurisdictions` entry. Regions can be
nested (Marin ⊆ Bay Area), overlap is allowed, and a region can
include jurisdictions at different hierarchy levels (e.g., a region
might explicitly include both `county-marin` and its constituent
cities). Region definitions live in `config/registry.json` under a
`regions` key.

### Ownership scope: canonical authority

This is the federation axis. Today, all civic data lives in a single
Supabase instance operated by civicosproject.org, and every deployed
MCP server is a facade over the same database. In the federated
target architecture (see
[federation_domain_architecture.md](federation_domain_architecture.md)),
each jurisdiction or region can have an *authoritative* operator that
runs the canonical instance, and other instances querying that
jurisdiction's data must resolve to the authoritative peer.

The key property of the scope model in this ADR: **ownership is
invisible to the tool surface.** A tool call for San Rafael data on
`bay-area.civicosproject.org/mcp` has the same signature and the same
result shape whether the data comes from local Postgres, a peer
instance, or a cached federation response. The data access layer
resolves canonical authority at query time; the tool layer doesn't
see it.

## The read/write split

Read-side and write-side tools have fundamentally different scope
semantics and should be treated differently.

### Read-side tools

Read-side tools retrieve civic data — meetings, decisions,
legislation, issues, budgets, testimony, voting records. They have
these properties:

- **Idempotent.** Running the same query twice returns the same data
  (modulo freshness).
- **Result shape is uniform across jurisdictions.** A decision from
  Mill Valley and a decision from San Rafael can be returned in the
  same list, clearly labeled by source.
- **No external side effects.** Running a search doesn't mutate
  government records, send messages, or obligate anyone.
- **Failure modes are graceful.** A query that can't reach one
  jurisdiction in a multi-jurisdiction result set can return partial
  results with a clear indication of what was missed.

Because of these properties, read-side tools can safely expand scope
automatically along vertical and horizontal axes. The default scope of
a read-side tool is determined by what's semantically useful for the
question being asked, not by the server's deployment jurisdiction.

### Write-side tools

Write-side tools initiate civic actions — submitting public comments,
broadcasting voices, creating initiatives, subscribing to topics,
drafting federal rule comments. They have these properties:

- **Non-idempotent.** Submitting a public comment twice creates two
  comments (or worse, an error and a silent duplicate).
- **Routing-sensitive.** Each action targets a specific clerk, portal,
  relay, or API endpoint owned by a specific jurisdiction.
- **External side effects.** The action changes state in systems that
  CivicOS doesn't own and can't undo.
- **Authority-bound.** Federated instances trust the canonical
  operator for a jurisdiction to correctly handle write operations for
  that jurisdiction. Routing a write through the wrong operator breaks
  the trust model.

Because of these properties, write-side tools must be strictly scoped.
They run against the primary jurisdiction of the server they live on
and refuse to operate on any other. A user who wants to submit a
public comment to Mill Valley's Planning Commission must be connected
to the Mill Valley authoritative instance, not to a regional facade.

This is the read/write boundary for federation: **reads go anywhere,
writes go to the canonical owner.**

## Scope policy table

Every tool declares its scope policy in one place
(`apps/civicos-mcp/tools/scope.py`), enumerating:

- **Default scope** — what runs if no scope parameter is given
- **Expandable scope** — what the tool accepts as optional widening
- **Maximum scope** — the ceiling beyond which the tool refuses

The table below is the authoritative starting point. Any new tool
added to the server must declare its scope row before it's bound.

### Read-side tools

| Tool | Default | Expandable | Max | Notes |
|---|---|---|---|---|
| `get_upcoming_meetings` | primary + siblings | +region | region | Regional view is the user's natural question |
| `search_meeting_history` | primary | — | primary | History is jurisdiction-specific; cross-pollinating is noise |
| `search_legislation` | primary + all parents | — | federal | Local + county + state + federal all affect the caller |
| `search_executive_orders` | federal | — | federal | Always federal |
| `search_federal_rules` | federal | — | federal | Always federal |
| `get_recent_executive_orders` | federal | — | federal | Always federal |
| `get_congressional_votes` | federal | — | federal | Always federal |
| `get_congressional_hearings` | federal | — | federal | Always federal |
| `get_open_comment_periods` | federal | — | federal | Federal regulatory comment periods |
| `search_regulatory_stack` | primary + all parents | — | federal | Stack means: municipal + county + state + federal code |
| `search_agenda_packets` | primary | — | primary | Packets are meeting-scoped |
| `get_public_testimony` | primary | — | primary | Testimony is attached to specific meetings |
| `search_budget` | primary | — | primary | Budgets don't compose across levels |
| `get_funding_flow` | primary + direct parent | +all parents | federal | Intergov transfers are inherently cross-level |
| `get_federal_expenditures` | federal | — | federal | Always federal |
| `get_intergovernmental_revenue` | primary + direct parent | — | state | Revenue flows from parents |
| `query_issue_data` | primary | — | primary | 311 is scoped to the responding jurisdiction |
| `get_issue_analytics` | primary | — | primary | Analytics don't aggregate meaningfully across jurisdictions |
| `get_issue_trends` | primary | — | primary | Trend timeseries tied to one 311 system |
| `geo_search_issues` | primary | — | primary | Geographic search bounded to one jurisdiction |
| `get_issue_resolution_stats` | primary | — | primary | Resolution is by local crews |
| `detect_trends` | primary | — | primary | Trend detection is jurisdiction-specific |
| `get_issue_sample` | primary | — | primary | Sampling from one jurisdiction |
| `find_issues_near_address` | primary | — | primary | Address geocoded to one jurisdiction |
| `find_repeat_issues` | primary | — | primary | Repeats only meaningful within one 311 system |
| `get_seasonal_patterns` | primary | — | primary | Jurisdiction-specific climate/usage patterns |
| `compare_zip_codes` | primary | — | primary | Within-jurisdiction ZIP comparison |
| `neighborhood_report` | primary | — | primary | Single-jurisdiction neighborhood summary |
| `find_similar_issues` | primary + siblings | +region | region | "Has Mill Valley dealt with this?" is a real query |
| `city_pulse` | primary | — | primary | Health snapshot of one city |
| `get_voting_record` | primary | — | primary | Local councilmembers; Congress has its own tool |
| `get_decision_context` | primary | — | primary | Context for a specific decision |
| `decision_detail` | primary | — | primary | Detail for a specific decision |
| `get_item_context` | primary | — | primary | Assembled context for one item |
| `get_leverage_points` | primary + all parents | — | federal | Leverage points live wherever a bill is legislated; matches `search_legislation` |
| `get_bill_detail` | federal | — | federal | Bill detail (federal congress); state/local have their own |
| `get_started` | primary + all parents | — | federal | Onboarding overview should show the full stack |

### Write-side tools (strictly scoped to primary)

| Tool | Scope | Reason |
|---|---|---|
| `compose_public_comment` | primary only | Comments route to a specific clerk/portal |
| `get_comment_guidelines` | primary only | Guidelines are jurisdiction-specific |
| `get_comment_template` | primary only | Templates are jurisdiction-specific |
| `prepare_for_meeting` | primary only | Meeting prep targets a specific agenda |
| `prepare_voice` | primary only | Voices are signed for a specific jurisdiction's relay |
| `broadcast_voice` | primary only | Broadcast routes to the authoritative relay |
| `prepare_initiative` | primary only | Initiatives are jurisdiction-scoped |
| `broadcast_initiative` | primary only | Initiatives routed to the authoritative relay |
| `list_initiatives` | primary + siblings | *Read* operation in disguise — safe to expand |
| `list_relays` | primary only | Relays are not jurisdictional — fan-out is a no-op |
| `get_voice_counts` | primary | Counts are per-jurisdiction |
| `subscribe_to_topic` | primary only | Subscription routes to specific relay |
| `draft_federal_comment` | federal only | Routes to regulations.gov, not a local portal |
| `prepare_federal_comment` | federal only | Federal comment preparation |

### Admin tools

| Tool | Scope | Notes |
|---|---|---|
| `admin_data_status` | primary | Server operator sees their own data |
| `admin_vector_coverage` | primary | Server operator sees their own indexing |
| `admin_system_health` | primary | Server health |
| `admin_cost_dashboard` | primary | Operator cost view |
| `manage_api_keys` | primary | Operator key management |
| `query_feedback` | primary | Operator feedback review |

Admin tools stay strictly scoped — an operator of the San Rafael
instance should not be able to inspect or mutate the state of another
operator's instance through their own admin tools.

### Implementation status (as of 2026-04-11)

The scope policy table above is the authoritative declaration. Actual
handler wiring ships in stages — this sub-section tracks how much of
the declared scope is actually enforced at runtime.

**Wired through `walk_scope`** (scope is load-bearing):

- `search_legislation` — vertical walk to state + federal
- `search_regulatory_stack` — vertical walk to state + federal
- `get_started` — vertical walk (Governance Stack section)
- `get_upcoming_meetings` — horizontal walk to siblings (+ optional region via `args["scope"]`)
- `find_similar_issues` — horizontal walk to siblings (+ optional region)
- `get_leverage_points` — vertical walk to state + federal (scope widened from `primary+direct parent` to `primary+all parents` when the handler was wired, because the legacy code path already pulled both CA and US bills and the narrower scope would have degenerated to empty)
- `list_initiatives` — horizontal walk to siblings (per-jurisdiction relay calls against the same relay URL)

**Declared scope is a no-op** (handler data source is jurisdiction-agnostic):

- `list_relays` — returns the static `KNOWN_RELAYS` list regardless of jurisdiction. Policy demoted to `primary only` to match reality.
- All 10 federal-default handlers (`search_executive_orders`, `search_federal_rules`, `get_recent_executive_orders`, `get_congressional_votes`, `get_congressional_hearings`, `get_open_comment_periods`, `get_federal_expenditures`, `get_bill_detail`, `draft_federal_comment`, `prepare_federal_comment`) — their storage methods pull federal data directly; walk_scope would only re-visit `country-united-states` once.

**Naturally strict** (default scope is `primary`):

All remaining read and write tools declare `primary only` and need no wiring — the handler's own jurisdiction-bound data path already honors the scope by construction.

## Consequences

1. **New tool development must declare scope first.** The scope policy
   table is the authoritative reference. Adding a tool to the server
   without a scope entry is a blocker. The scope entry determines how
   the tool wrapper walks the v2 query layer, whether cross-jurisdiction
   results are labeled, and whether the tool is eligible to run on a
   regional server.

2. **Regional servers become viable without redesigning the tool
   surface.** A `bay-area.civicosproject.org/mcp` deployment is the
   same codebase with a different primary jurisdiction and a `region`
   assignment. Tools that expand horizontally automatically cover the
   region; tools that don't stay narrowly scoped. No per-region tool
   forking.

3. **Federation can be deferred without blocking regional deployments.**
   Today, "the data plane" is a shared Supabase and the canonical
   operator question is moot. When the first third-party CivicOS
   instance appears, the federation work lives in the data access
   layer, not the tool layer or the deployment layer.

4. **Write-side safety is a first-class property.** A user on a
   regional connector cannot accidentally submit a public comment to
   the wrong jurisdiction, because write-side tools refuse to run if
   the caller isn't on the authoritative instance for the target.
   Regional connectors surface a clear "connect to the Mill Valley
   instance to submit this comment" message instead.

5. **Open-tier access is further constrained.** Because write-side
   tools require authority anchoring, the already-tight open-tier
   access to write operations is formally closed. Open tier remains
   valid only for a narrow set of read operations that don't require
   user identity (primarily `get_started`).

## Non-goals

- **This ADR does not define the federation protocol itself.** How a
  regional server discovers the canonical operator for a jurisdiction,
  how results are cached across instances, and how operator trust is
  established are all data-plane concerns covered by
  [federation_domain_architecture.md](federation_domain_architecture.md)
  and future federation ADRs.

- **This ADR does not specify regional boundaries.** The question of
  which jurisdictions belong to "bay-area" vs. "marin" vs. "north-bay"
  is a configuration decision, not an architectural one. Regions are
  defined in `config/registry.json` and can be adjusted without code
  changes.

- **This ADR does not mandate regional servers.** Per-city deployments
  remain valid and useful for residents who want narrow scope and
  predictable costs. Regional deployments are an additional option,
  not a replacement.

## Related decisions

- [Unified Civic Query Interface](query_interface.md) — the v2 query
  layer this ADR builds on
- [Federation Domain Architecture](federation_domain_architecture.md)
  — the Registry + BYOD model this ADR's federation axis defers to
- [Distribution Pivot](distribution_pivot.md) — the strategic context
  for why regional coverage matters for launch
- [Entity ID Namespace](entity_id_namespace.md) — jurisdiction-prefixed
  entity IDs that make cross-jurisdiction result labeling possible

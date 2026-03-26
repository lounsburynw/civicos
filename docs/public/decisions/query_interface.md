# ADR: Unified Civic Query Interface

**Status:** Proposed
**Date:** 2026-03-13

## Decision

Replace the 50+ individual MCP/API tool surface with 5 semantic verbs (`civic.search`, `civic.upcoming`, `civic.context`, `civic.act`, `civic.explore`) backed by a server-side query plan layer that maps domain vocabulary to internal storage queries, insulating callers from database schema changes.

## Context

CivicOS exposes civic data (meetings, decisions, legislation, public testimony, 311 issues, budgets) to AI agents and developers through MCP and REST APIs. The current surface has 50+ individually-defined tools, each mapping roughly to a specific query pattern against PostgreSQL/pgvector.

This creates three problems:

1. **Composition burden (primary).** The most valuable civic queries are inherently cross-corpus: "What's the full story on the downtown rezoning?" touches meetings, decisions, testimony, legislation, issues, and budget. The current surface forces the caller to orchestrate multiple tools and stitch results in its own context window — expensive, lossy, and repeated every session. The server already has composition logic (`assemble_context`, `what_happened_full_context`) but it's buried behind single-purpose endpoints.

2. **Schema coupling.** Tools like `query_issue_data` expose structural concepts (`group_by: "type, status, street"`, `filter_status`) that mirror internal table schemas. Schema changes propagate to every consumer.

3. **Agent cognitive load.** AI agents must select among 50+ tools before each call. Note: LLMs are reasonably good at selecting from large tool sets when descriptions are clear. The bigger issue is not selection accuracy but the round-trip cost — an agent making 5 sequential calls to compose a cross-cutting answer spends 5x the latency and token budget of a single composed call.

### Motivation

A [design analysis](https://github.com/anthropics/claude-code/issues) of CLI-vs-function-calling agent architectures surfaced a key insight: CivicOS tools aren't composable Unix primitives, but they *are* wrappers around composable SQL/vector primitives. The composition should happen server-side, not in the agent's context window.

Additionally, agents are first-class API consumers with pricing tiers (open/free/builder/organization/city). The $500/mo builder tier should get an interface that makes agents *powerful*, not one that forces them to spend half their token budget navigating a tool catalog.

## Architecture

### The 5 Verbs

#### `civic.search` — "What do you know about X?"

Unified search across corpora. Replaces `search_meeting_history`, `find_similar_issues`, `search_regulatory_stack`, `search_legislation`, `search_executive_orders`, `search_budget`, `get_public_testimony`, `search_agenda_packets`, `search_federal_rules`, `get_voting_record`, `get_decision_context`, `get_bill_detail`, and related tools.

```json
{
  "query": "housing density near downtown",
  "corpus": ["decisions", "legislation", "testimony"],
  "jurisdiction": "city-san-rafael",
  "since": "2025-01",
  "location": "downtown",
  "limit": 10,
  "depth": "standard",
  "mode": "search",
  "cursor": null
}
```

**Parameters:**
- `query` (string, required): Natural language search query
- `corpus` (array of strings, required): Which data types to search. See corpus vocabulary below. Requiring this avoids the intent-classification problem of auto-detection — agents use `civic.explore` to discover available corpora.
- `jurisdiction` (string): Jurisdiction filter (e.g., `city-san-rafael`, `state-CA`)
- `since` / `until` (string): Date range filters, translated per-corpus by the query plan layer
- `location` (string): Geographic filter — address, intersection, or neighborhood. First-class parameter because civic data is inherently spatial.
- `limit` (integer): Max results (across all corpora)
- `depth` (enum): `minimal` (IDs + titles), `standard` (+ summaries), `deep` (+ inline details)
- `mode` (enum): `search` (find matching items), `aggregate` (counts/statistics), `trend` (temporal patterns). Defaults to `search`.
- `cursor` (string): Opaque pagination cursor from a previous response

**Corpus vocabulary** (domain terms, not table names):

| Corpus | Internal mapping | Description |
|--------|-----------------|-------------|
| `decisions` | decisions table + decision vectors | Council votes and outcomes |
| `testimony` | transcript vectors | What was said at meetings |
| `testimony:public` | transcript vectors, `is_public_comment=true` | Public comment only |
| `testimony:council` | transcript vectors, `speaker_role=council` | Council discussion only |
| `testimony:staff` | transcript vectors, `speaker_role=staff` | Staff presentation only |
| `legislation` | legislation table + legislation vectors | State and federal bills |
| `issues` | issues table + issue vectors | 311/SeeClickFix reports |
| `budget` | budget_items table | City budget data |
| `meetings` | meetings + agenda_items | Meeting records and agendas |
| `rules` | federal rules | Federal rulemaking (regulations.gov) |
| `orders` | executive orders | Presidential executive orders |
| `municipal_code` | municipal_code vectors | Local ordinances and code |
| `packets` | chunks (PDF vectors) | Agenda packets and staff reports |

Corpus terms are **additive-only**: new terms may be added, existing terms are never removed or renamed. If a corpus needs to split, the original term becomes an alias. For example, if `testimony` splits, the original term returns the union of its sub-corpora.

Sub-corpus qualifiers (e.g., `testimony:public`) allow filtering without the agent needing to post-process results.

**Response format — two-level result structure:**

```json
{
  "results": [
    {
      "type": "decision",
      "ref": "decision:city-san-rafael:proudcity-city-san-rafael-city-council-november-17-2025-monday:05",
      "title": "Approve ADU ordinance update",
      "date": "2025-11-15",
      "summary": "Council approved updates to ADU regulations allowing...",
      "relevance": 0.87,
      "details": {
        "outcome": "Approved 4-1",
        "votes": {"yes": 4, "no": 1},
        "body": "City Council"
      }
    },
    {
      "type": "legislation",
      "ref": "legislation:ca-sb9",
      "title": "SB-9 Housing Development",
      "date": "2021-09-16",
      "summary": "Allows lot splits and duplexes on single-family zoned parcels...",
      "relevance": 0.72,
      "details": {
        "bill_number": "SB-9",
        "status": "Enacted",
        "state": "CA",
        "leverage_point": "Local implementation — city ADU ordinance"
      }
    }
  ],
  "meta": {
    "corpora_searched": ["decisions", "legislation", "testimony"],
    "corpus_counts": {"decisions": 3, "legislation": 5, "testimony": 2},
    "corpus_times_ms": {"decisions": 120, "legislation": 340, "testimony": 89},
    "total_results": 42,
    "cursor": "eyJvZmZzZXQiOjEwfQ==",
    "query_time_ms": 380,
    "schema_version": "2025.1"
  }
}
```

- **Top level** (stable envelope): `type`, `ref`, `title`, `date`, `summary`, `relevance` — always present, same fields across all corpus types. Agents can process results generically.
- **`details`** (type-specific essential metadata): Each corpus type includes a small set of fields that answer the most common follow-up question without requiring a `civic.context` call. These are documented per corpus via `civic.explore(what="corpus_schema:decisions")` and may evolve — agents relying on specific detail fields should check `schema_version`.

Essential detail fields per corpus type:

| Corpus | Essential details | Answers without follow-up |
|--------|------------------|--------------------------|
| `decisions` | `outcome`, `vote_summary`, `body` | "How did they vote?" |
| `legislation` | `bill_number`, `status`, `state` | "Is this active? Where?" |
| `testimony` | `speaker`, `speaker_role`, `video_url` | "Who said it? Where's the clip?" |
| `meetings` | `agenda_item_count`, `has_transcript`, `location` | "Is there a recording?" |
| `issues` | `status`, `category`, `address` | "Is it resolved? Where?" |
| `budget` | `amount`, `department`, `fiscal_year` | "How much? Which department?" |
| `municipal_code` | `section_number`, `chapter` | "Which code section?" |
- **`ref`**: Opaque identifier. Agents pass refs to `civic.context` and `civic.act` without constructing them. Format may change between schema versions.
- **`meta`**: Per-corpus timing and counts for observability. `cursor` for pagination.

#### `civic.upcoming` — "What's happening next?"

Temporal queries. Replaces `get_upcoming_meetings`, `city_pulse`, `get_open_comment_periods`, `get_upcoming_hearings`, `get_governors_desk`.

```json
{
  "types": ["meetings", "hearings", "comment_periods"],
  "jurisdiction": "city-san-rafael",
  "days": 14,
  "actionable_only": true
}
```

`actionable_only: true` filters to items where civic participation is possible — comment-eligible agenda items, open NPRM comment periods, bills at hearing stage. This is the "Meeting Monitor" agent pattern in one call.

#### `civic.context` — "Tell me everything about this item"

Deep context for a specific item. Wraps the existing `assemble_context` engine. Replaces `get_item_context`, `decision_detail`, `neighborhood_report`.

```json
{
  "ref": "decision:city-san-rafael:proudcity-city-san-rafael-city-council-november-17-2025-monday:05",
  "depth": "deep",
  "sections": ["history", "testimony", "regulatory", "financial", "participation"]
}
```

Returns the existing `ContextBundle` structure: item details, related decisions, regulatory stack, community context, financial data, testimony excerpts, and participation options. Each section is independently failable — partial results are returned with degradation notices in metadata.

#### `civic.act` — "Help me participate"

Participation actions. Replaces `compose_public_comment`, `get_comment_template`, `get_comment_guidelines`, `prepare_for_meeting`, `prepare_voice`, `broadcast_voice`, `prepare_initiative`, `broadcast_initiative`, `subscribe_to_topic`.

```json
{
  "action": "prepare_comment",
  "ref": "agenda_item:city-san-rafael:2025-12-01:item-3b",
  "stance": "support",
  "key_points": ["pedestrian safety", "school zone proximity"]
}
```

Actions: `prepare_comment`, `comment_template`, `comment_guidelines`, `prepare_meeting`, `prepare_voice`, `broadcast_voice`, `prepare_initiative`, `broadcast_initiative`, `subscribe`.

Write operations (voice, initiative) remain relay-backed and require Nostr signatures. The verb consolidates the surface but doesn't change the trust model.

#### `civic.explore` — "What can I ask you?"

Progressive discovery. The `--help` equivalent for agents.

```json
{
  "what": "corpora",
  "jurisdiction": "city-san-rafael"
}
```

`what` values:
- `jurisdictions` — available jurisdictions with levels and data ranges
- `corpora` — available corpus types with counts and date ranges
- `corpus_schema:{name}` — field documentation for a corpus's `details` shape
- `actions` — available participation actions
- `capabilities` — full capability summary (for agent system prompts)
- `schema_version` — current API schema version

This replaces `get_started` and `list_relays`, and provides the metadata agents need to make informed `civic.search` calls.

### The Query Plan Layer

Between the verbs and the existing CivicOS API, a **deterministic rules engine** translates requests into query plans:

```
civic.search(query, corpus, filters)
  → QueryPlanner.plan(query, corpus, filters)
    → QueryPlan {
        corpus_queries: [
          CorpusQuery(corpus="decisions", method="what_happened", params={...}),
          CorpusQuery(corpus="legislation", method="what_applies", params={...}),
        ],
        merge_strategy: "interleave",
        timeout_ms: 10000,
      }
    → Parallel execution
    → ResultMerger.merge(results, strategy)
      → Normalized, ranked, paginated response
```

Key design decisions:

1. **No LLM in the query path.** The plan layer is a deterministic rules engine — a match/switch on corpus type, each branch knowing how to translate common filters into corpus-specific API calls. This keeps latency low and behavior predictable.

2. **Filter translation via per-corpus adapters.** The `since` parameter means different things per corpus — `meeting_datetime` for decisions, `introduced_date` or `last_action_date` for legislation, `created_at` for issues. Each corpus registers an adapter that declares which filters it supports and how to translate them. The query plan layer can then report partial matches: "searched decisions and meetings for your date range; legislation does not support spatial filtering and was searched without that constraint." Schema changes (e.g., renaming `meeting_datetime`) only affect the relevant adapter, not callers.

    The filter vocabulary is explicitly defined as a schema. Each corpus adapter declares supported filters, preventing silent failures when a filter doesn't apply. The test surface is `|filters| × |corpora|` — gaps must be explicitly tracked.

3. **Cross-corpus ranking via reciprocal rank fusion.** Vector similarity scores from different corpora are not directly comparable. Rather than raw score interleaving, results are ranked within each corpus first, then merged by reciprocal rank. This is well-understood, requires no calibration, and degrades gracefully.

4. **Per-corpus timeouts with partial results.** Each corpus query has a 10-second timeout (matching `assemble_context` precedent). If one corpus times out, results from completed corpora are returned with a degradation notice in `meta.corpus_status`.

5. **The existing handler code doesn't change.** The query plan layer orchestrates existing API methods (`what_happened`, `what_applies`, `what_was_said`, etc.). The 50 tools become internal implementation; the 5 verbs are the public surface.

### Versioning

- **URL versioning**: The 5-verb surface ships as `/api/v2/civic/{verb}`. The existing 50-tool surface is effectively v1 (`/api/tools/{name}`).
- **Schema version in responses**: Every response includes `meta.schema_version` (e.g., `"2025.1"`). Agents can detect and adapt to schema evolution.
- **Additive-only corpus vocabulary**: New corpus terms may be added. Existing terms are never removed — only aliased if semantics change.
- **Both surfaces run in parallel** during migration. v1 tools remain available for existing integrations.

### Rate Limiting

Multi-corpus queries consume more backend resources than single-tool calls. Rate limiting accounts for this:

- **Request-level limits** remain (per tier: open 30/min, free 60/min, builder 300/min)
- **Query cost weighting**: A `civic.search` with 5 corpora counts as 5 "query units" against a per-minute query budget. This prevents a single multi-corpus search from being cheaper than the equivalent individual calls.
- **Per-corpus `max_results`**: Callers can limit per-corpus result counts to control cost. Default: `limit / len(corpus)` per corpus, minimum 5.

## Rationale

### Why 5 verbs over 50 tools

The primary win is **server-side composition**, not tool count reduction. The most valuable civic queries cross corpus boundaries — "What's happening with housing?" touches decisions, legislation, testimony, and issues simultaneously. With 50 tools, the agent orchestrates this fan-out itself (5 round trips, stitching in-context). With 5 verbs, a single `civic.search` call fans out server-side in parallel and returns merged results — faster, cheaper, and no stitching.

The secondary win is that the 50-tool surface leaks internal taxonomy. An agent building a housing tracker shouldn't need to distinguish `search_meeting_history` from `get_decision_context` from `what_happened`. These are implementation distinctions, not user distinctions.

### Why require corpus (not auto-detect)

Auto-detection means intent classification — either an LLM call (adding cost and latency to every request) or heuristics (brittle). Requiring `corpus` keeps behavior deterministic and lets agents be explicit about what they want. The `civic.explore` verb provides discovery for agents that don't know which corpora to search.

### Why domain vocabulary over SQL/DSL exposure

Exposing a query DSL or raw SQL would give agents maximum flexibility but zero schema insulation. When we rename a column or split a table, every agent integration breaks. Domain vocabulary (`"decisions"`, `"testimony"`) absorbs these changes in the query plan layer.

### Why not GraphQL

GraphQL requires callers to know the schema — specifying exact fields defeats the abstraction goal. The two-level result structure (stable envelope + type-specific details) gives agents the flexibility of GraphQL's field selection without requiring schema knowledge.

### Alternatives considered

1. **Keep 50 tools, add better descriptions.** Doesn't solve composition burden or schema coupling. Agents still orchestrate multiple calls and stitch results in-context.

2. **Single `civic.query` with natural language.** Requires an LLM in the query path, adding cost and non-determinism. Reserved as a possible future enhancement.

3. **CLI-style `run(command="civic search ...")`.** Works well for filesystem/shell operations where LLMs have training data, but CivicOS queries are domain-specific — no LLM has seen our CLI in training data. Typed parameters with explicit corpus selection are more reliable.

4. **Expose SQL directly.** Maximum power, zero insulation. Schema changes break every consumer. Also a security risk.

## Open Questions

Raised during review, deferred to implementation:

1. **~~Query operators for composition.~~** RESOLVED. Implemented as `mode` extensions on `SearchRequest`:
    - `mode: "diff"` + `snapshot_date`: returns items dated after the snapshot (EXCEPT). Solves monitoring: "what's new since I last checked?"
    - `mode: "intersect"` + `intersect_corpus`: returns primary results with date/title overlap in secondary corpora (INTERSECT). Solves cross-corpus joins: "decisions that have testimony."
    - `+` (UNION) remains implicit in multi-corpus search.

2. **~~Civic jargon explanation.~~** RESOLVED. `civic.context` now accepts `concept` as an alternative to `ref`. `civic.context(concept="conditional use permit")` searches the `municipal_code` corpus and returns matching sections with excerpts. Mutually exclusive with `ref` (model validation enforces).

3. **Cross-corpus ranking calibration.** Reciprocal rank fusion is a reasonable starting point, but vector similarity scores across different embedding spaces may need corpus-specific weighting. Consider allowing callers to pass corpus weights: `corpus: {"decisions": 2.0, "legislation": 1.0}` (object form as alternative to array form).

4. **`civic.explore` investment.** This verb is the linchpin of agent self-service — if it's weak, agents hallucinate parameter values. It must stay perfectly synchronized with actual data availability. Needs dedicated testing and potentially a cache layer.

5. **Admin tools.** `admin_data_status`, `admin_vector_coverage`, `admin_system_health`, `admin_cost_dashboard`, `manage_api_keys` are explicitly out of scope for the 5-verb surface. They remain as v1 tools with admin auth.

## Migration Path

1. **Phase 1**: Add `civic.search` and `civic.explore` as new v2 endpoints, backed by existing handlers. Ship alongside v1 tools.
2. **Phase 2**: Add `civic.upcoming` and `civic.context` (wrapping existing `assemble_context`).
3. **Phase 3**: Add `civic.act`, consolidating participation tools.
4. **Phase 4**: Deprecate v1 tools for external consumers. Keep internally for handler-level testing.

Each phase is independently shippable and testable. The existing 50-tool handler code remains unchanged throughout — the verbs orchestrate it.

## References

- [Vector Storage ADR](./vector_storage.md) — pgvector + ChromaDB dual-backend design
- [Entity ID Namespace ADR](./entity_id_namespace.md) — ID format conventions (relevant to `ref` design)
- [Data Source Federation ADR](./data_source_federation.md) — multi-jurisdiction query patterns
- `packages/civicos-services/src/civicos_services/context/` — existing `assemble_context` implementation
- `apps/civicos-mcp/tools/registry.py` — current 50-tool registry
- `docs/public/api.md` — current REST API surface
- `docs/public/building-agents.md` — agent integration patterns

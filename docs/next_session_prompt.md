# Recommended: Context Assembly API Design

**Priority:** P0
**Area:** edge_intelligence > context_assembly_api
**Date:** 2026-02-08

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Strategy session identified the need for a **surface-agnostic context assembly layer**. The insight: the intelligence is in assembling rich context about a civic item, not in any specific UI. Whether the consumer is Open WebUI, a browser extension, Claude.ai via MCP, or an embeddable widget, they all should get the same pre-assembled context bundle and pass it to an LLM however that surface does chat.

This also enables a **browser extension distribution strategy** — inject CivicOS context into any page showing civic content (agenda PDFs, local news articles). Parallel to Open WebUI, potentially equally significant.

Key constraint raised at end of session: **context may come from federated relays and MCPs**, not just the local jurisdiction. The API design must account for federated context assembly (querying peer MCPs, aggregating cross-jurisdiction results).

## Recommended Task

Design the context assembly API — the endpoint contract, bundle schema, and orchestration logic. This is a **design session** (architecture doc + API sketch), not heavy implementation.

### Design Questions to Answer

1. **Bundle schema**: What fields? Structured JSON, pre-rendered markdown, or both? How much context per item type (agenda item vs decision vs issue vs legislation)?
2. **Endpoint contract**: `GET /context/{item_type}/{item_id}` — what item types, what query params (jurisdiction, depth, include/exclude sections)?
3. **Orchestration**: Which existing CivicOS API methods get called per item type? (`what_happened`, `what_applies`, `what_was_said`, vector search)
4. **Federation**: How does context assembly work across federated MCPs/relays? Fan-out to peers for cross-jurisdiction context (e.g., state bill affecting multiple cities)?
5. **Suggested questions**: Auto-generated per item type to seed the conversation
6. **Surface consumption patterns**: How does each surface (Open WebUI, browser extension, MCP, widget) consume the bundle?

### Use Cases to Inform the Design

- **Open WebUI**: User clicks agenda item → chat opens with full context as system prompt
- **Browser extension**: User visits city council agenda PDF → extension sidebar shows CivicOS context
- **MCP**: Claude.ai user asks about an item → MCP tool returns context bundle
- **Expandable decisions** (P1): Click decision row → fetch context bundle → render inline detail
- **User-created initiatives/voices**: Same bundle shape for platform-sourced and user-created items
- **State/federal items**: Context bundle works for municipal, state, and federal items (not just city)

## Key Files

- `pilot.json` — `edge_intelligence.context_assembly_api` item definition
- `packages/civicos/src/civicos/civic.py` — CivicOS API methods (what_happened, what_applies, what_was_said, etc.)
- `apps/civicos-mcp/tools/handlers.py:425-451` — `city_pulse()` already assembles some per-item context
- `packages/civicos/src/civicos/storage/pgvector_backend.py` — vector search methods
- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` — master architecture
- `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md` — multi-surface distribution design
- `docs/critical/COORDINATION_PROTOCOL.md` — federation/relay protocol
- `apps/civicos-mcp/tools/handlers.py` — existing MCP tools (federation query routing pattern)

## Suggested Approach

1. Read existing API methods in `civic.py` to catalog what context is already queryable per item type
2. Read `city_pulse()` in handlers.py — it already does lightweight context assembly, good starting point
3. Read federation query routing in MCP tools — pattern for fan-out to peer MCPs
4. Draft the context bundle JSON schema (consider: item metadata, related items, legal context, testimony, suggested questions, provenance)
5. Draft the endpoint contract (routes, params, response shape)
6. Write the design doc (new file in `docs/critical/`)
7. Update pilot.json subtasks with implementation plan

## Success Criteria

- [ ] Context bundle JSON schema defined (covers agenda items, decisions, issues, legislation, initiatives)
- [ ] Endpoint contract specified (routes, params, federation behavior)
- [ ] Surface consumption patterns documented (how Open WebUI / browser extension / MCP each use it)
- [ ] Federation strategy for cross-jurisdiction context assembly
- [ ] Design doc written to `docs/critical/CONTEXT_ASSEMBLY_API.md`
- [ ] Implementation subtasks added to pilot.json item

## P1 Items (for awareness, not this session)

- `expandable_decisions` — will be first consumer of context assembly API
- `civic_dashboard_mvp` — dashboard completeness (mostly done, needs expandable_decisions + provenance_footer)
- `action_tools` — MCP read tools for action state
- User-created initiatives/voices — write-side features that produce items the context API will serve

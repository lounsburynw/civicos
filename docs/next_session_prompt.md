# Recommended: Context Assembly API — Finish Integration

**Priority:** P0
**Area:** edge_intelligence > context_assembly_api
**Date:** 2026-02-12
**Previous session:** Provenance footer (data source transparency panel)

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed **provenance_footer** — a collapsible data provenance panel in the CityPulse dashboard header showing jurisdiction, MCP endpoint, data range, corpus counts (9 types, 12,979 docs), and update timestamp. Backend endpoint added to both Modal deployment (`rest_api.py`) and dev server (`routers/core.py`).

The **context_assembly_api** is the existing P0. The backend is fully implemented (all 6 sections: history, regulatory, community, financial, testimony, participation). Two integration tasks remain to close it out, which also unblock the browser extension (P2).

## Recommended Task: Context Assembly Integration

Two remaining subtasks:
1. **Add `get_item_context` MCP tool** — expose the context assembly endpoint as an MCP tool so Claude.ai/ChatGPT can use it
2. **Open WebUI "Chat with this item" button** — integrate context API into the dashboard so users can click a decision/agenda item and start a conversation with full context pre-loaded

## Key Files

- `packages/civicos-services/src/civicos_services/context/assembler.py` — ContextAssembler class (complete)
- `packages/civicos-services/src/civicos_services/servers/routers/context.py` — GET /api/context/{item_type}/{item_id} endpoint (complete)
- `packages/civicos-services/tests/test_context_assembly.py` — test file
- `apps/civicos-mcp/tools/handlers.py` — MCP tool handlers (add get_item_context here)
- `apps/civicos-mcp/rest_api.py` — REST API (may need context endpoint mirrored for Modal)
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — dashboard component
- `~/projects/civicos-openwebui/src/lib/components/civic/DecisionDetail.svelte` — decision expansion (good place for "Chat" button)
- `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` — browser extension architecture (unblocked by this work)

## Suggested Approach

1. Read the existing assembler.py and context router to understand the API shape
2. Add `get_item_context` as an MCP tool in handlers.py — takes item_type + item_id, returns context bundle
3. Wire the MCP tool as a REST endpoint in rest_api.py for Modal deployment
4. In the Open WebUI frontend, add a "Chat with this" button on decision/agenda items
5. On click, call the context API, then inject the context bundle as a system prompt for a new conversation

## Tests to Run
```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Context assembly tests
pytest packages/civicos-services/tests/test_context_assembly.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] `get_item_context` MCP tool works (returns context bundle for any civic item)
- [ ] REST endpoint mirrors the tool for Modal deployment
- [ ] "Chat with this item" button visible on decisions or agenda items in CityPulse
- [ ] Clicking launches a conversation with pre-loaded civic context
- [ ] `context_assembly_api` marked ready in pilot.json

## Also Notable
- **Browser extension** (P2) is unblocked once context assembly is done — see `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md`
- **Relay deployment still pending** — action attribution + voice/revoke endpoints committed but not deployed to Modal
- **SQL migration pending** — `scripts/sql/add_action_events.sql` needs to run on relay DB
- **Pilot at 94%** (452/478 items ready) — 26 remaining, mostly P3

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && VITE_CIVICOS_API_URL=http://localhost:8001 npm run dev` (localhost:5173)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Note: Frontend defaults to production API URL. Use VITE_CIVICOS_API_URL for local dev.

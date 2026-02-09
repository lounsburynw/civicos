# Recommended: Context Assembly API — Surface Integration

**Priority:** P0
**Area:** edge_intelligence > context_assembly_api
**Date:** 2026-02-08

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 1 of the Context Assembly API is **complete and live**. `GET /api/context/{item_type}/{item_id}` returns a rich context bundle with 6 sections (history, regulatory, community, financial, testimony, participation) assembled in parallel. Smoke tested with real San Rafael data — all item types and error cases verified.

This session also added a public `CivicOS.storage` property, replacing all `_storage` private access across civicos-services (architecture critic fix).

## Recommended Task

**Phase 2: Connect the context API to consumer surfaces.** Two options (pick one or both):

1. **MCP tool** — Add `get_item_context` tool so Claude.ai/ChatGPT users can get full context for any civic item in one call (replaces 3-5 separate tool calls)
2. **Open WebUI integration** — Add "Chat with this item" button to the civic dashboard that calls the context API and injects the bundle into a new chat as system prompt context

The MCP tool is simpler (~30 lines in handlers.py). The Open WebUI integration is higher-impact but touches the separate openwebui repo.

## Key Files

- `packages/civicos-services/src/civicos_services/context/assembler.py` — Core orchestrator (635 lines)
- `packages/civicos-services/src/civicos_services/context/models.py` — Pydantic models (235 lines)
- `packages/civicos-services/src/civicos_services/servers/routers/context.py` — FastAPI endpoint
- `docs/critical/CONTEXT_ASSEMBLY_API.md` — Full design doc (sections 5-6 cover surface consumption patterns)
- `apps/civicos-mcp/tools/handlers.py` — Existing MCP tools (add `get_item_context` here)
- `apps/civicos-openwebui-fork/` — Open WebUI frontend (symlink → ~/projects/civicos-openwebui)

## Suggested Approach (MCP tool)

1. Read `apps/civicos-mcp/tools/handlers.py` — understand existing tool patterns
2. Add `get_item_context(item_type, item_id, jurisdiction)` tool that calls the context API
3. Return the bundle as structured tool result (consider token limits — use `depth=standard`)
4. Test via Claude.ai or `mcp dev`

## Suggested Approach (Open WebUI)

1. Read the civic dashboard in `apps/civicos-openwebui-fork/src/lib/components/civic/`
2. Add a "Chat with this item" button to agenda item cards
3. On click: fetch `/api/context/agenda_item/{id}?jurisdiction=city-san-rafael`
4. Open a new chat with the context bundle injected as system prompt
5. Test via `cd ~/projects/civicos-openwebui && npm run dev`

## Known Issues

- **Regulatory section timeout**: `what_applies()` can exceed 10s timeout on large municipal code corpus (16K+ sections). V1 behavior — section returns `timeout` status, bundle is marked `degraded: true`. Consider bumping timeout to 15s or adding index optimization.
- **Community section sparse**: `whos_with_me()` returns empty `recent_voices` and `active_initiatives`. V1 stub — full implementation needs relay voice count integration.

## Tests to Run

```bash
# Smoke test the context endpoint (start server first)
./scripts/dev.sh api  # or use Python dotenv approach from this session
curl -s -H "Authorization: Bearer dev_key_local" \
  "http://localhost:8001/api/context/agenda_item/{item_id}?jurisdiction=city-san-rafael" | python3 -m json.tool

# Core smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] At least one consumer surface can use the context API (MCP tool or Open WebUI button)
- [ ] End-to-end test: user action → context bundle fetched → LLM conversation with context

## P1 Items (for awareness)

- `expandable_decisions` — first dashboard consumer of context API (click decision → expand with context)
- `civic_dashboard_mvp` — needs expandable_decisions + provenance_footer
- `action_tools` — MCP read tools for voice/action state

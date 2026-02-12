# Recommended: Context Assembly API — Finish the Surface-Agnostic Foundation

**Priority:** P0
**Area:** edge_intelligence > context_assembly_api
**Date:** 2026-02-12
**Previous session:** Architecture — browser extension design + micropayments

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session designed the **browser extension architecture** — the extension becomes CivicOS's primary distribution surface, acting as the Personal MCP directly in the browser. Full design is in `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` (new). The extension depends on `context_assembly_api` to assemble rich civic context bundles that get injected into AI surfaces (Claude.ai, ChatGPT, etc.). Context assembly Phase 1 is already complete — the remaining work is integration: add an MCP tool and wire it into Open WebUI.

Also added: **micropayments architecture** (L402 + NWC + Cashu) as a section in the extension doc, and two new P2 items in `pilot.json` (`browser_extension`, `micropayments`).

### P0 change from previous session
Previous session set `action_attribution` as P0. This session demoted it to P1 and kept `context_assembly_api` as P0 because it's nearly complete and directly enables the extension strategy. Action attribution is still important (P1) — see previous `next_session_prompt.md` in git history for full context on that item.

## Recommended Task: Finish Context Assembly API

### What Remains (2 subtasks)

1. **Add `get_item_context` MCP tool** — expose the context assembly endpoint as a Jurisdiction MCP tool so Claude.ai/ChatGPT users can query rich civic context directly
2. **Open WebUI "Chat with this item" integration** — wire context bundles into the Open WebUI fork's CityPulse component

### What's Already Done
- `GET /api/context/{item_type}/{item_id}` endpoint is live
- All 6 context sections implemented: history, regulatory, community, financial, testimony, participation
- Parallel assembly with Semaphore(3), per-section 10s timeout, error isolation
- Smoke tested with real San Rafael data

## Key Files

- `packages/civicos-services/src/civicos_services/context/assembler.py` — ContextAssembler (implemented)
- `packages/civicos-services/tests/test_context_assembly.py` — existing tests
- `apps/civicos-mcp/tools/registry.py` — add `get_item_context` tool definition here
- `apps/civicos-mcp/tools/handlers.py` — add handler that calls the context API
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — "Chat with this item" UI
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client for context endpoint

### New docs from this session
- `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` — full extension design (identity, MCP connections, context injection, payments, implementation phases)
- `pilot.json` — new items: `edge_intelligence/browser_extension` (P2), `edge_intelligence/micropayments` (P2); updated: `action_attribution` P0→P1, `action_templates` P0→P1

## Suggested Approach

1. Read `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md` to understand the strategic context
2. Read the context assembly endpoint implementation (`assembler.py`)
3. Add `get_item_context` to MCP tool registry + handler — it should call the existing `/api/context/{item_type}/{item_id}` endpoint
4. Test the MCP tool locally via Claude Desktop or stdio
5. Wire "Chat with this item" button in CityPulse — on click, fetch context bundle, inject as system prompt into Open WebUI chat

## Tests to Run
```bash
# Context assembly tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos-services/tests/test_context_assembly.py -q --override-ini="addopts="

# MCP tool tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/ -q --override-ini="addopts="

# Smoke tests
/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria
- [ ] `get_item_context` MCP tool returns rich context bundle for any item type
- [ ] Tool works in Claude Desktop (stdio) and HTTP mode
- [ ] Open WebUI CityPulse has "Chat with this item" on agenda items/decisions
- [ ] Clicking "Chat with this item" opens a chat pre-loaded with context
- [ ] Existing tests still pass

## Also Notable (P1)
- **Action attribution** (`relay/action_primitives/action_attribution`) — close the engagement feedback loop. See git history of this file for full context.
- **Action templates** (`relay/frontend_integration/action_templates`) — Phase 2 commitment tracking, marked ready.
- **Relay deployment** — action system changes committed locally but not deployed to Modal.

## Dev Environment
- Frontend: `cd ~/projects/civicos-openwebui && npm run dev` (localhost:5173, hot reload)
- Backend: `./scripts/dev.sh api` (localhost:8001)
- Use venv Python directly: `/Users/nicolaslounsbury/projects/civicos/civicos-env/bin/python3`

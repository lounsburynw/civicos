# Recommended: Refactor Chat Endpoint to FastMCP Code Mode

**Priority:** P0 is `turnkey_city_deployment` (deferred). Recommend this instead — eliminates a class of API errors and scales the tool architecture.
**Area:** deployment_artifacts > api_server
**Date:** 2026-03-05

> This is recommended context from Session 23. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 23 built Civic Journal Phase 2 (AI-suggested updates) and fixed two bugs found during testing:

1. **Identity locked on rapid searches** — service worker's `SIGN_MESSAGE` didn't restore session state before checking `isUnlocked()`. Fixed with `ensureRestored()`.
2. **Multi-tool_use 400 error** — `/api/ai/chat` only handled one `tool_use` block but Claude sometimes returns multiple. The Anthropic API requires every `tool_use` ID to have a matching `tool_result`. Fixed by executing all tool blocks.

Bug #2's fix works but is fragile — it's manual tool orchestration that grows more complex as tools increase. The user pointed to [FastMCP 3.1 Code Mode](https://www.jlowin.dev/blog/fastmcp-3-1-code-mode) as a structural solution: instead of Claude returning N tool_use blocks, it writes a Python script composing multiple `call_tool()` calls in a sandbox.

## What Session 23 Built
- Journal suggestions module (`journal-suggestions.ts`): tracks interactions, generates AI suggestions every 5 chats
- Suggestion banner UI in SidePanel with accept/dismiss per suggestion
- Options page live-reloads journal via `chrome.storage.onChanged`
- Fixed identity restore bug in service worker
- Fixed multi-tool_use handling in ai_proxy.py

## Recommended Task

Refactor the `/api/ai/chat` endpoint to use FastMCP Code Mode instead of manual tool orchestration.

**Why:**
- Eliminates the multi-tool_use matching problem structurally
- Reduces context window usage (discovery tools vs full schema dump)
- Scales to more tools without N-way orchestration complexity
- FastMCP bridge already exists (`apps/civicos-mcp/fastmcp_bridge.py`)

## Key Files
- `packages/civicos-services/src/civicos_services/servers/routers/ai_proxy.py:295-401` — Current chat endpoint (manual 2-call orchestration)
- `apps/civicos-mcp/fastmcp_bridge.py` — Existing FastMCP bridge wrapping all 39 ToolRegistry tools
- `apps/civicos-mcp/tools/registry.py` — ToolRegistry with chat tools (6 tools used by ai_proxy)
- `packages/civicos-services/src/civicos_services/servers/routers/ai_proxy.py:240-280` — `_ChatToolRegistry` with tool definitions

## Current Architecture (ai_proxy.py)
```
User question -> Claude picks tool(s) -> we execute -> Claude summarizes
  - 2 API calls minimum
  - Must match every tool_use ID with tool_result
  - Breaks when Claude returns multiple tool_use blocks (fixed but fragile)
```

## Target Architecture (Code Mode)
```
User question -> Claude writes Python script -> sandbox executes all calls -> Claude summarizes
  - Claude gets: search(), get_schema(), execute_code() (3 lightweight tools)
  - Composes multiple data queries in a single script
  - No tool_use/tool_result matching needed
```

## Suggested Approach
1. Read FastMCP Code Mode docs: `from fastmcp.experimental.transforms.code_mode import CodeMode`
2. Modify `fastmcp_bridge.py` to accept `transforms=[CodeMode()]`
3. Create a new chat endpoint (or refactor existing) that uses the FastMCP server directly instead of raw Anthropic API calls
4. Keep the existing endpoint as fallback during transition
5. Test with the same queries that triggered the multi-tool_use bug

## Reference
- Blog post: https://www.jlowin.dev/blog/fastmcp-3-1-code-mode
- FastMCP docs for `CodeMode` transform
- Existing bridge: `apps/civicos-mcp/fastmcp_bridge.py` (wraps 39 tools from ToolRegistry)

## Success Criteria
- [ ] Chat endpoint uses FastMCP Code Mode for tool orchestration
- [ ] Multi-tool queries work without manual tool_use/tool_result matching
- [ ] No regression on single-tool queries
- [ ] Existing chat UX unchanged (same response format to extension)

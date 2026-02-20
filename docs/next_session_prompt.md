# Recommended: engagement_ladder_ux — Local Tool Routing via Ollama

**Priority:** P0
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 15 shipped three things:
1. **Suggested query pills** — 4 preset queries below the empty chat input for discoverability
2. **Navigation actions** — tool results show "View in [Section]" buttons that expand + scroll to the relevant panel section (Meetings, Outcomes, Budget, Issue Map, Legislation tab)
3. **Ollama provider** — device-tier AI provider connecting to local Ollama instance (localhost:11434). Fully private drafting, no queries leave the machine.

We also traced the full AI architecture and identified a **privacy gap**: the AI chat bar is the only feature still locked to server-side inference. Draft/Enrich/Summary can all run locally via Ollama, but chat sends user queries to Modal → Anthropic because it needs server-side tool execution.

## Recommended Task

**Move the chat tool loop to the client** so it can run on local models via Ollama.

Current flow (server-side, privacy-leaking):
```
User question → POST /api/ai/chat → Claude picks tool → server executes tool → Claude summarizes → text response
```

Target flow (client-side, fully private):
```
User question → Ollama (local, picks tool from 6 tool schemas)
  → Extension calls CivicOS API directly for tool data (no npub, anonymous)
    → Ollama (local, synthesizes result) → display in chat bar
```

The CivicOS server only sees anonymous data requests — equivalent to visiting the city website. No one can reconstruct what questions the user asked.

## Architecture Notes

- The 6 chat tools: `search_meeting_history`, `get_upcoming_meetings`, `search_budget`, `get_public_testimony`, `search_legislation`, `find_similar_issues`
- Tool schemas are defined in `apps/civicos-mcp/modal_mcp.py` via `configure_chat_tools()` and `_build_chat_tools()`
- Ollama supports tool calling via `/api/chat` with `tools` parameter (same schema as OpenAI function calling)
- The existing `OllamaProvider.complete()` uses `/api/generate` — chat with tools needs `/api/chat`
- The 8B models (llama3.1:8b, qwen2.5:7b) handle structured tool selection well for civic queries
- Tool execution currently happens via `_chat_registry.call_tool()` on the server — need equivalent client-side API calls

## Design Decision: Dual Path

Keep both paths available:
- **Server path** (CivicOS Proxy) — works out of the box, no setup required. Good for users who don't run Ollama.
- **Local path** (Ollama) — fully private. Requires Ollama installed + model downloaded.

The `AIManager` already handles provider selection. The `chat()` method on `OllamaProvider` would implement local tool routing, while `CivicosProxyProvider.chat()` continues to use the server.

## Longer-term: Personal MCP + Local Memory

After local chat is working, proactive relevance (#2 from the engagement ladder) can be built with:
- A **Personal MCP** server running locally alongside Ollama
- Local memory files (`~/.civicos/preferences.md`, `voice-history.md`, `watchlist.md`)
- The local LLM reads both MCPs — public data from Jurisdiction MCP, personal context from local files
- Interest profiles never exist anywhere but the user's filesystem

This is the Two-MCP architecture from `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md`.

## Key Files

- `packages/civicos-client/src/ai/providers/ollama.ts` — Ollama provider (add `chat()` method)
- `packages/civicos-client/src/ai/types.ts` — `AIProvider` interface (has optional `chat?()`)
- `packages/civicos-client/src/ai/manager.ts:118` — `chat()` routing (finds first provider with `chat`)
- `packages/civicos-services/src/civicos_services/servers/routers/ai_proxy.py:213-225` — `_build_chat_tools()` tool schema definitions
- `apps/civicos-mcp/modal_mcp.py:388` — `configure_chat_tools()` wiring
- `packages/civicos-components/src/components/CivicChatBar.svelte` — Chat bar UI
- `apps/civicos-extension/src/lib/ai/providers/civicos-proxy.ts:130` — Server-side `chat()` for reference
- `docs/critical/EDGE_INTELLIGENCE_ARCHITECTURE.md` — Full vision doc

## Suggested Approach

1. **Extract tool schemas** — Get the 6 tool definitions into a shared format usable by both server and client
2. **Add `chat()` to OllamaProvider** — Use Ollama's `/api/chat` with `tools` parameter for tool selection
3. **Implement client-side tool execution** — Extension calls CivicOS API endpoints directly for tool data (existing `ApiClient` methods, no auth needed for public data)
4. **Second Ollama call for synthesis** — Feed tool result back to Ollama for summarization
5. **Wire into AIManager** — `chat()` routing already prefers providers that implement it; order Ollama before CivicOS Proxy when both are ready

## Tests

```bash
# Client type check
cd packages/civicos-client && npx tsc --noEmit

# Extension build
cd apps/civicos-extension && npm run build

# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] OllamaProvider implements `chat()` with local tool routing
- [ ] Tool schemas shared between server and client (no duplication)
- [ ] When Ollama is running, chat queries never hit Modal/Anthropic
- [ ] When Ollama is not running, falls back to CivicOS Proxy (existing behavior)
- [ ] Extension builds, no regressions

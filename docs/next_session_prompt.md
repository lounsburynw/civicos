# Recommended: Deploy & E2E Test FastMCP Code Mode Chat

**Priority:** P0 is `turnkey_city_deployment` (deferred). Recommend deployment testing of the Code Mode refactor.
**Area:** deployment_artifacts > api_server
**Date:** 2026-03-05

## Context

Session 24 completed the FastMCP Code Mode refactor of `/api/ai/chat`:

- Upgraded FastMCP 2.14.5 → 3.1.0 with code-mode extra
- Replaced manual 2-call tool orchestration with CodeMode meta-tools (search, get_schema, execute)
- Chat endpoint now uses agentic loop (max 5 turns) instead of fixed 2-call pattern
- Multi-tool composition in CodeMode sandbox eliminates the multi-tool_use bug from Session 23

## What's Done
- ai_proxy.py fully refactored and working locally
- 42 smoke tests pass
- Integration test confirms CodeMode meta-tools work with ToolRegistry
- Version bumps in modal_mcp.py, requirements-mcp.txt, pyproject.toml

## What Needs Testing
1. **Deploy to Modal** — `modal deploy apps/civicos-mcp/modal_mcp.py` and verify /health
2. **E2E chat test** — Use the browser extension to ask real questions and verify:
   - Single-tool queries work (e.g., "What happened with housing?")
   - Multi-tool queries work (e.g., "What's the budget for police and when's the next council meeting?")
   - No-tool queries work (general knowledge questions)
   - Response format unchanged (same JSON shape to extension)
3. **Latency check** — CodeMode adds discovery overhead (search + get_schema before execute). Typical flow is 3-4 API calls vs old 2. Check if response time is acceptable.

## Key Files
- `packages/civicos-services/src/civicos_services/servers/routers/ai_proxy.py` — Refactored endpoint
- `apps/civicos-mcp/fastmcp_bridge.py` — Existing bridge (unchanged, still used for MCP /mcp endpoint)
- `apps/civicos-mcp/modal_mcp.py:91` — FastMCP version constraint

## Potential Issues
- **Monty sandbox limitations**: The CodeMode sandbox (pydantic-monty) has restricted Python support. No f-strings with nested braces, limited stdlib. Claude needs to generate compatible code.
- **Latency**: The agentic loop may make 3-5 API calls per question. If too slow, consider pre-loading tool schemas in the system prompt to skip search + get_schema steps.
- **Cost**: More API calls per chat = higher cost. Monitor the CHAT_COST_PER_REQUEST vs actual usage.

## Fallback Plan
If CodeMode adds too much latency or the sandbox is too restrictive, the old pattern can be restored from git (commit 1183708). The key architectural win (agentic loop with proper multi-tool_use handling) can be kept even without CodeMode.

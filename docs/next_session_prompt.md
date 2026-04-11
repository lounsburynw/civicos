# Recommended: Scope policy table (`scope_policy_table`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session shipped MCP OAuth (stateless HMAC tokens, 401-on-unauth discovery) and Claude.ai can now connect via `https://san-rafael.civicosproject.org/mcp` in 2 clicks. Immediately after, a real user query surfaced the next problem: the connector is San Rafael–scoped, so asking "what about other Marin cities?" returned nothing useful even though the CivicOS DB already has data for them.

A design discussion produced a committed ADR (**`docs/public/decisions/tool_scope_and_federation.md`**) with a single load-bearing claim: **scope lives on tools, not deployments**. Reads expand vertically (city→state→federal) and horizontally (siblings/regions) with labeled results; writes stay strictly anchored to the server's primary jurisdiction. Federation is a data-plane concern handled separately.

This P0 is the first of four sequenced items (scope_policy_table → scope_policy_passthrough → region_config_concept → regional_server_deployment). Step 1 is small, contained, and unblocks everything downstream.

## Recommended Task

Build `apps/civicos-mcp/tools/scope.py` as the authoritative per-tool scope policy dict. Thread it into `_bind_handlers` in `modal_mcp.py` with an assertion that refuses to bind any tool without a scope entry. Not yet wiring the policies into actual v2 API calls — that's the next P0 (`scope_policy_passthrough`).

## Key Files

- **`docs/public/decisions/tool_scope_and_federation.md`** — *authoritative reference*. Contains the full scope policy table for every currently-bound tool (read-side, write-side, admin). Every row in `scope.py` must match this table exactly. If you want to change a policy, update the ADR and code together.
- `apps/civicos-mcp/tools/registry.py` — existing tool registry (`ToolRegistry`, `TOOL_DEFINITIONS`). `scope.py` lives next to this.
- `apps/civicos-mcp/modal_mcp.py:241-336` — `_bind_handlers` method. Add the assertion here that every bound tool has a scope entry.
- `apps/civicos-mcp/modal_mcp.py:337-374` — `_wrap_handler`. Consider adding a `_mcp_request_scope` contextvar similar to `_mcp_request_tier` so tool handlers can read the resolved scope at call time.
- `apps/civicos-mcp/tests/test_mcp_tools.py` — follow this pattern for `test_scope_policy.py`.

## Suggested Approach

1. **Create `apps/civicos-mcp/tools/scope.py`** with:
   - A `ScopePolicy` dataclass: `default_scope`, `expandable_scope`, `max_scope`, `kind` ("read" | "write" | "admin"), plus an optional `notes` field.
   - A `Scope` enum or literal type: `PRIMARY`, `PRIMARY_PLUS_PARENTS`, `PRIMARY_PLUS_SIBLINGS`, `PRIMARY_PLUS_REGION`, `FEDERAL`, `ALL_PARENTS`, `STATE`.
   - A `SCOPE_POLICIES: dict[str, ScopePolicy]` matching the ADR's table row-for-row. Every currently-bound tool name gets an entry.
   - A `get_scope_policy(tool_name: str) -> ScopePolicy` helper that raises `KeyError` with a clear message if the tool isn't in the table.

2. **Add a binding-time assertion** in `modal_mcp.py::_bind_handlers`: before binding each handler, call `get_scope_policy(name)` — if it raises, log an error and skip (or raise on unknown tools, configurable). This ensures new tools can't ship without a scope entry.

3. **Write `apps/civicos-mcp/tests/test_scope_policy.py`** that:
   - Validates every name in `handler_map` (from `modal_mcp.py`) has a `SCOPE_POLICIES` entry.
   - Asserts write-side tools have `default_scope == PRIMARY` and `kind == "write"`.
   - Asserts federal-only tools (`search_executive_orders`, etc.) have `default_scope == FEDERAL`.
   - Loads every entry and checks invariants (max_scope is at least as broad as default_scope).
   - Uses the ADR table as the source of truth — if the ADR changes, the test guides the code update.

4. **Add a `_mcp_request_scope` contextvar** in `modal_mcp.py` (parallel to `_mcp_request_tier`) that `_wrap_handler` sets based on the resolved scope. This is passive in this P0 — the context is populated but nothing reads it yet. Step 2 (`scope_policy_passthrough`) will make it load-bearing.

5. **Do NOT change tool handler behavior in this session.** No v2 API changes, no result labeling, no actual cross-jurisdiction queries. That's all step 2. This P0 is *just* the policy table and the plumbing to make it consulted.

## Tests to Run

```bash
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_scope_policy.py -v --override-ini="addopts="
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_oauth.py --override-ini="addopts="
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_mcp_tools.py --override-ini="addopts="
```

## Success Criteria

- [ ] `apps/civicos-mcp/tools/scope.py` exists with `SCOPE_POLICIES` dict matching the ADR table
- [ ] Every tool bound in `_bind_handlers` has an entry (assertion enforced at bind time)
- [ ] `test_scope_policy.py` validates coverage and invariants
- [ ] Read/write/admin classification is correct for all ~45 tools
- [ ] Existing OAuth + MCP tool tests still pass (no regressions)
- [ ] Adding a new tool without a scope entry fails loudly (assertion)
- [ ] ADR and code are in sync (if you change policy, change both)
- [ ] `scope_policy_passthrough` promoted to new P0 when this lands

## Non-goals for this session

- Actually passing `include_parents` / `include_siblings` to v2 API calls (that's step 2)
- Defining regions in `registry.json` (that's step 3)
- Deploying regional MCP servers (that's step 4)
- Changing tool result formatting (deferred)
- Implementing the contextvar consumer — just set it, step 2 reads it

## Open PRs

None from parallel sessions.

## Recent state

Last three commits on `main`:
- `1c986f04` Add scope work sequence (P0→P3) to launch.json, demote rate limiting
- `e495ec61` Add ADR: Tool scope and the read/write federation boundary
- `74db43f4` Return 401 on unauthenticated /mcp/ to enable Claude.ai OAuth discovery

Production MCP at `https://san-rafael.civicosproject.org/mcp` is stable and Claude.ai-connected — scope work won't touch it until step 2.

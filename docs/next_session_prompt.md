# Recommended: Cross-Jurisdiction Civic API Methods (`cross_jurisdiction_civic_api_methods`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-12

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed `add_real_source_item_id` (commit `05f760c8`). The launch checklist now has only 5 items remaining (all P2-P3 except this P0). This item unblocks cross-jurisdiction financial queries by adding a `jurisdiction_id` parameter to two CivicOS methods that currently only return data for their construction-time jurisdiction.

## Recommended Task

Refactor `CivicOS.funding_flow()` and `CivicOS.intergovernmental_revenue()` to accept an optional `jurisdiction_id` parameter, then wire both MCP handlers through `walk_scope` so they can fan out across the resolved scope (parent jurisdictions like county/state).

## Key Files

- `packages/civicos/src/civicos/civicos.py:1153-1180` — `funding_flow()` method. Add `jurisdiction_id: Optional[str] = None` kwarg, thread to storage calls.
- `packages/civicos/src/civicos/civicos.py:1509-1535` — `intergovernmental_revenue()` method. Same refactor.
- `apps/civicos-mcp/tools/handlers.py:2553-2578` — `get_funding_flow()` handler. Has TODO marker at line 2575. Replace direct `civic.funding_flow()` call with `walk_scope` pattern.
- `apps/civicos-mcp/tools/handlers.py:2645-2670` — `get_intergovernmental_revenue()` handler. Has TODO marker at line 2667. Same walk_scope wiring.
- `apps/civicos-mcp/tools/handlers.py:190-209` — `get_upcoming_meetings()` — **reference pattern** for how walk_scope is already wired. Copy this pattern.
- `apps/civicos-mcp/tools/scope_walk.py` — `walk_scope()` and `resolve_requested_scope()` functions.
- `apps/civicos-mcp/tests/test_scope_policy_passthrough.py` — Existing scope policy tests (1008 lines). Add tests for the two new handlers.
- `docs/public/decisions/tool_scope_and_federation.md` — ADR documenting scope policies. Update to reflect these handlers are now wired.

## Suggested Approach

1. **Add jurisdiction_id kwarg to CivicOS methods** — In `civicos.py`, add `jurisdiction_id: Optional[str] = None` to both `funding_flow()` and `intergovernmental_revenue()`. When provided, use it instead of `self.jurisdiction_id` for storage queries. Default `None` = use self (backwards compatible).

2. **Wire handlers through walk_scope** — In `handlers.py`, follow the `get_upcoming_meetings` pattern (lines 190-209):
   ```python
   def _storage_call(jid: str) -> list:
       return civic.funding_flow(jurisdiction_id=jid, program=program, ...)
   
   results = walk_scope(policy, jurisdiction, _storage_call)
   ```

3. **Remove TODO markers** — Delete the `TODO(cross_jurisdiction_civic_api_methods)` comments at lines 2575 and 2667.

4. **Update scope policy docstrings** — Remove "aspirational" language from handler docstrings (lines 2562-2568 and 2654-2661).

5. **Add tests** — Add test cases to `test_scope_policy_passthrough.py` verifying that both handlers respect scope policy and fan out correctly.

6. **Update ADR** — In `tool_scope_and_federation.md`, mark these two handlers as wired (no longer primary-only).

## Tests to Run

```bash
# Scope policy tests (direct target)
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_scope_policy_passthrough.py -v --override-ini="addopts="

# Smoke tests
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `CivicOS.funding_flow()` accepts `jurisdiction_id` kwarg
- [ ] `CivicOS.intergovernmental_revenue()` accepts `jurisdiction_id` kwarg
- [ ] `get_funding_flow` handler wired through `walk_scope`
- [ ] `get_intergovernmental_revenue` handler wired through `walk_scope`
- [ ] TODO markers removed from handlers.py
- [ ] Handler docstrings updated (no longer "aspirational")
- [ ] Tests verify scope fan-out for both handlers
- [ ] ADR updated to reflect wired status
- [ ] A new P0 assigned before session end

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items — 6 pre-existing failures total, stable across sessions.

## Open PRs

None.

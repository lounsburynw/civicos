# Recommended: Region config concept (`region_config_concept`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session shipped `scope_policy_passthrough` (step 2 of 4 in the scope work sequence). Commits:
- `51cda249` + `b74f9db8` — scope_policy_table (step 1, earlier session)
- **(this session)** — scope_policy_passthrough: built `tools/scope_walk.py`, wired 5 handlers, 20 new tests, all 222 relevant tests green.

**What step 2 actually shipped:**
- `apps/civicos-mcp/tools/scope_walk.py` — `resolve_scope_to_jurisdictions(scope, primary)` maps `Scope` enum → list of jurisdiction IDs via `registry.json` `parent_jurisdictions`. `walk_scope(policy, primary, storage_call)` fans a closure out across resolved jurisdictions and stamps each returned row with a `jurisdiction` label.
- `_mcp_request_scope` contextvar **moved** from `modal_mcp.py` into `tools/scope.py` — the producer (modal_mcp's `_wrap_handler`) and the new consumers (`tools/handlers.py`) share one binding without importing each other.
- 5 handlers wired: `search_legislation`, `get_upcoming_meetings`, `find_similar_issues`, `search_regulatory_stack`, `get_started`. Each reads the contextvar via `_mcp_request_scope.get()` and either calls `walk_scope` (real fan-out) or `resolve_scope_to_jurisdictions` (shallow labeling).
- `search_legislation` ships with an in-file `_LEGISLATION_STATE_CODE` map: `{country-united-states → US, state-california → CA}`. City/county jurisdictions return `None` and are skipped during the fan-out.
- `tools/scope_walk.py::resolve_scope_to_jurisdictions` **raises `NotImplementedError`** for `REGION` and `PRIMARY_PLUS_REGION`. That's your entry point for step 3.

**Headline proof test** (passing):
```python
def test_vertical_expansion_labels_state_and_federal(...):
    _mcp_request_scope.set(SCOPE_POLICIES["search_legislation"])
    output = handlers.search_legislation(civic, "city-san-rafael", ...)
    assert "SB-100 (CA) — state-california" in output
    assert "H.R.1 (US) — country-united-states" in output
```

## ⚠️ Architectural finding carried forward

The prior-prior handoff assumed MCP handlers called `civicos_services.query` (v2). They do **not** — handlers make 25 direct `civic.storage.*` calls. Step 2 chose Option C (hybrid): keep handlers on direct storage calls, wire scope via a thin helper (`scope_walk`). This decision stays in force for steps 3+. Don't assume v2 integration until a separate refactor item lands.

## Recommended Task

`region_config_concept` introduces the `regions` top-level key in `config/registry.json` and teaches `resolve_scope_to_jurisdictions` what `REGION` / `PRIMARY_PLUS_REGION` mean. This is the natural next step because:

1. `scope_walk` already raises `NotImplementedError` for those two scopes — a test exists that guards the raise. Flipping them on is a concrete, bounded change.
2. The sibling-walking path in `scope_walk` currently includes school districts sharing `county-marin` (19 siblings total for `city-san-rafael`). A region concept lets us tighten this to "cities in Marin" (11 members) without breaking the school-district sibling behavior elsewhere.
3. Two handlers have `PRIMARY_PLUS_REGION` as their `expandable_scope` (`get_upcoming_meetings`, `find_similar_issues`). Currently they can't expand to region — users who ask "what about other Marin cities?" hit `NotImplementedError`. Fixing this unlocks a real Claude.ai use case.

### Suggested plan

1. **Design the region schema** in `config/registry.json`:
   ```json
   "regions": {
     "marin": {
       "display_name": "Marin County",
       "members": ["county-marin", "city-san-rafael", "city-mill-valley", "city-san-anselmo", ...]
     },
     "bay-area": {
       "display_name": "SF Bay Area",
       "members": ["region-marin", "county-san-francisco", "county-alameda", ...]
     }
   }
   ```
   Nested regions (region listing other regions as members) should resolve recursively. Decide up front whether to prevent cycles or just cap recursion depth.

2. **Add region loading to the registry API.** Options:
   - (a) Extend `civicos.registry.get_registry()` callers to read the new top-level key. Cheapest.
   - (b) Add `get_region(name)` / `resolve_region_members(name)` to `civicos_config.JurisdictionRegistry`. Cleaner long-term but crosses a package boundary.
   I'd start with (a) and promote to (b) when a second caller appears.

3. **Teach `scope_walk`** about regions. Replace the two `NotImplementedError` branches with real resolution:
   ```python
   if scope == Scope.PRIMARY_PLUS_REGION:
       region_name = _region_for(primary_jurisdiction)  # contextual lookup
       return _dedupe([primary_jurisdiction, *_resolve_region_members(region_name)])
   if scope == Scope.REGION:
       region_name = _region_for(primary_jurisdiction)
       return _resolve_region_members(region_name)
   ```
   The question of **how a server knows its own region** is open. Two choices:
   - `CIVICOS_REGION` env var set per deployment (new).
   - Derive from the primary jurisdiction's county parent (e.g. `county-marin` → region `marin` if such a region exists).
   Either works for San Rafael. Pick the one that doesn't require a Modal secret redeploy.

4. **Wire the two `expandable_scope: PRIMARY_PLUS_REGION` handlers** (`get_upcoming_meetings`, `find_similar_issues`) to accept a `scope` argument from `args` and widen past their default when the caller asks for it. This is where the scope-widening UX becomes real for AI callers.

5. **Test:**
   - Unit: `test_resolve_region_members_expands_marin` — walking `Scope.REGION` on `city-san-rafael` returns the 11-ish Marin members.
   - Unit: `test_nested_region_bay_area_includes_marin_cities` — resolving `bay-area` recursively expands `region-marin`.
   - Integration: call `get_upcoming_meetings` with `{"scope": "primary_plus_region"}` on san-rafael and assert the result set contains sections for at least 3 Marin cities.
   - Guardrail: `test_region_cycle_detection` — region A lists region B which lists region A, must raise or cap.

## Key Files

- `apps/civicos-mcp/tools/scope_walk.py:105-112` — the two `NotImplementedError` branches to replace. Start here.
- `apps/civicos-mcp/tools/scope.py:49-53` — Scope.REGION and Scope.PRIMARY_PLUS_REGION docstrings. Update to reference the registry's `regions` key.
- `apps/civicos-mcp/tools/scope.py:113-120` — `get_upcoming_meetings` policy: `expandable_scope=PRIMARY_PLUS_REGION`. This is the handler whose expansion currently 500s.
- `apps/civicos-mcp/tools/scope.py:310-316` — `find_similar_issues` policy: same story.
- `apps/civicos-mcp/tools/handlers.py:169-230` — `get_upcoming_meetings` handler. Already reads the contextvar. Add `args.get("scope")` override handling.
- `apps/civicos-mcp/tools/handlers.py:232-330` — `find_similar_issues`. Same pattern.
- `config/registry.json` — where the region schema lands. Start with just `marin` to keep the PR small.
- `packages/civicos/src/civicos/registry.py:96` — `get_registry()` is the public loader. Add region helpers here or in `civicos-config`.
- `packages/civicos-services/src/civicos_services/query/jurisdictions.py` — existing sibling resolver. Useful reference for how a nested lookup handles fan-out caps.

## Tests to Run

```bash
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_scope_policy_passthrough.py -v --override-ini="addopts="
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_scope_policy.py --override-ini="addopts="
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_mcp_tools.py --override-ini="addopts="
# New file:
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_region_config.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] `config/registry.json` has a `regions` key with at least one concrete region (Marin) defined.
- [ ] `scope_walk.resolve_scope_to_jurisdictions` no longer raises for `REGION` / `PRIMARY_PLUS_REGION`.
- [ ] The two existing `test_region_raises_not_implemented` and `test_primary_plus_region_raises_not_implemented` tests in `test_scope_policy_passthrough.py` get **updated** (not deleted — the invariant is now "resolves correctly", not "raises").
- [ ] New integration test proves a user on city-san-rafael can ask for upcoming meetings across Marin and see labeled sections for ≥3 cities.
- [ ] `get_upcoming_meetings` and `find_similar_issues` accept `{"scope": "primary_plus_region"}` in args and widen.
- [ ] All 222+ existing tests still pass.
- [ ] Region cycle detection test in place.

## Non-goals

- Regional server deployment (step 4: `regional_server_deployment`)
- Refactoring handlers to v2 query functions
- Widening the remaining 52 handlers through scope_walk (see `widen_remaining_handlers_through_scope_walk` — now P2)
- Fixing pre-existing `python-multipart` test failures

## Open PRs

None.

## Pre-existing test failures (NOT regressions)

6 tests in `apps/civicos-mcp/tests/test_coordination_tools.py` and `test_initiative_tools.py` fail on main without any of this session's changes:
- `TestBroadcastVoiceHandler::test_tool_definition_exists` (required-fields schema drift)
- `TestBroadcastVoiceHandler::test_invalid_stance_rejected`
- `TestBroadcastVoiceHandler::test_handler_returns_error_without_relay`
- `TestToolRegistry::test_registry_has_38_tools`
- `TestToolRegistry::test_tool_registry_class_works`
- `TestListInitiativesHandler::test_connection_error_handled`

Confirmed pre-existing via stash-and-rerun. Separate cleanup item.

## Follow-up items added this session

- **`widen_remaining_handlers_through_scope_walk`** (P2, distribution) — walk the 52 remaining handlers, wire the non-PRIMARY defaults through `scope_walk`. Most are PRIMARY-only and need no changes; ~5-8 need wiring.

## Recent state

Last commits (this session's will be on top after `/commit`):
- `b74f9db8` Tighten test_handler_map_parses sanity check
- `51cda249` Add scope policy table and binding-time enforcement
- `1068424d` Fix depth pipeline subshell bug + first mutation/audit results
- `0eec6729` Prepare next session handoff: scope_policy_table (P0)
- `1c986f04` Add scope work sequence (P0→P3) to launch.json, demote rate limiting

Production MCP at `https://san-rafael.civicosproject.org/mcp` stable. `_mcp_request_scope` contextvar is now **load-bearing** on 5 handlers — the remaining 52 stay PRIMARY-only until `widen_remaining_handlers_through_scope_walk` ships.

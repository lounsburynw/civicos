# Recommended: Regional Server Deployment (`regional_server_deployment`)

**Priority:** P0
**Area:** distribution
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session shipped `widen_remaining_handlers_through_scope_walk` (step 4 of 5 in the scope work sequence) in commit `007e3a6e`. All non-PRIMARY, non-federal MCP handlers are now wired through `walk_scope` with jurisdiction labels. The region config (`config/registry.json` regions key) and per-handler scope policies are fully operational. This is the deployment-side capstone: stand up a regional MCP server so users install **one connector** for Marin-wide coverage instead of 11 per-city connectors.

**Scope work sequence state:**
- Step 1 `scope_policy_table` (done)
- Step 2 `scope_policy_passthrough` (done)
- Step 3 `region_config_concept` (done)
- Step 4 `widen_remaining_handlers_through_scope_walk` (done)
- **Step 5 `regional_server_deployment`** (this P0)

## Recommended Task

Deploy `marin.civicosproject.org/mcp` as a Modal app that serves the Marin region. It's the same codebase with different env vars. The key architectural decision is how to identify the regional server's "primary jurisdiction" — see the two options below.

## Key Decision: Synthetic Region ID vs. Reuse Existing City

**Option A (recommended): Add a `region-marin` entry to `config/registry.json`** with its own `modal_app_name`, `domain`, and `parent_jurisdictions`. The scope walker already resolves region membership via `find_region_for_jurisdiction()` — if `region-marin` is added as a member of the "marin" region, all tools will auto-widen. Requires a small change to `modal_mcp.py` to handle region-level primaries.

**Option B: Deploy with `CIVICOS_JURISDICTION=city-san-rafael` and `CIVICOS_REGION=marin`** as a parallel app name. Simpler deployment but muddies the question of "whose server is this?" — San Rafael's operator shouldn't own the regional connector.

Option A is cleaner for federation: a regional server is a distinct operator, not a city server that happens to be wider.

## Key Files

- `apps/civicos-mcp/modal_mcp.py:39` — `CIVICOS_JURISDICTION` env var read; line 80 derives `APP_NAME` from registry
- `apps/civicos-mcp/modal_mcp.py:44-72` — `get_secrets()` loads secret groups by jurisdiction tier
- `apps/civicos-mcp/modal_mcp.py:74-78` — `get_min_containers()` controls cold-start behavior
- `config/registry.json:320-337` — `regions.marin` with 11 member cities
- `config/registry.json:7-16` — `city-san-rafael` entry (template for new region entry)
- `packages/civicos/src/civicos/registry.py:217-248` — `find_region_for_jurisdiction()` and `resolve_region_members()`
- `apps/civicos-mcp/tools/scope_walk.py:66-103` — `_resolve_region_for_primary()` region lookup
- `docs/internal/deployment.md` — Modal deploy procedures, secrets, Cloudflare routing

## Suggested Approach

1. **Add `region-marin` to `config/registry.json`**: jurisdiction entry with `domain: marin.civicosproject.org`, `modal_app_name: civicos-marin`, `parent_jurisdictions: ["county-marin", "state-california", "country-united-states"]`. Also add `region-marin` to the `regions.marin.members` list so `find_region_for_jurisdiction` returns "marin" for it.

2. **Update `modal_mcp.py`** to handle region-level primaries: `get_secrets()` needs a region tier that maps to shared `civicos-env` secrets. `get_min_containers()` should return 1 for the regional server (it's the high-traffic entry point). Write-side tools should either refuse (return "use your city's connector to take this action") or route to the primary city — decide which.

3. **Update `get_modal_app_name()` in `registry.py`** to return `civicos-marin` for `region-marin` (reads the `modal_app_name` field from the registry entry, which it probably already does).

4. **DNS**: Add Cloudflare CNAME `marin.civicosproject.org` pointing to the Modal endpoint `civicos--civicos-marin-mcpserver-mcp-endpoint.modal.run`. This is the simplest routing — no Worker needed.

5. **Deploy**: `CIVICOS_JURISDICTION=region-marin modal deploy apps/civicos-mcp/modal_mcp.py`

6. **Test**: Install the connector at `marin.civicosproject.org/mcp` in Claude Desktop. Run `get_upcoming_meetings` — it should return meetings from all 11 Marin cities. Run `search_legislation` — should return CA + US bills labeled by jurisdiction. Run `compose_public_comment` — should either refuse (regional server) or route to the correct city's portal.

## Tests to Run

```bash
# Scope-related tests (must stay green)
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_scope_policy.py apps/civicos-mcp/tests/test_scope_policy_passthrough.py apps/civicos-mcp/tests/test_region_config.py -v --override-ini="addopts="

# MCP tools (confirm no regressions)
civicos-env/bin/python3 -m pytest apps/civicos-mcp/tests/test_mcp_tools.py --override-ini="addopts="
```

## Success Criteria

- [ ] `region-marin` entry exists in `config/registry.json` with `modal_app_name`, `domain`, and region membership.
- [ ] `modal_mcp.py` handles region-level primaries in `get_secrets()` and `get_min_containers()`.
- [ ] `CIVICOS_JURISDICTION=region-marin modal deploy apps/civicos-mcp/modal_mcp.py` succeeds.
- [ ] Cloudflare CNAME routes `marin.civicosproject.org` to the Modal endpoint.
- [ ] `get_upcoming_meetings` on the regional connector returns meetings from multiple Marin cities.
- [ ] Write-side tools have a clear policy on the regional server (refuse or route).
- [ ] All existing tests still passing (256+ scope tests).
- [ ] A new P0 assigned before session end.

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items. Don't let them derail the deployment work.

## Open PRs

None.

## Not in scope

- `cross_jurisdiction_civic_api_methods` (P3) — the core API refactor for `funding_flow` / `intergovernmental_revenue` jurisdiction kwargs.
- Bay Area or other multi-county regions — Marin is the proof of concept.
- Billing/metering for the regional server — that's a separate launch item.

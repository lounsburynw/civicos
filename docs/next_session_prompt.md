# Recommended: State/Federal UX Refinement + Initiatives

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session fixed the extension state/federal tabs — they now load legislation data, show jurisdiction-aware labels ("Key Legislation", "Bill Status"), and have green health dots. The `city_pulse` handler is level-aware (meetings for city, legislation for state/federal) and deployed to all 3 Modal servers. Now the user wants to iterate on the UX quality and expand functionality.

## Recommended Tasks (User-Directed)

Three related improvements, in priority order:

### 1. Simulated Feedback on State/Federal Tab UX
Evaluate the California and Federal tab content with critical eyes. The data is real (4.2K CA bills, 14.8K US bills, 9.6K with leverage points), but the presentation could be improved:
- "Key Legislation" shows top 10 bills with leverage points — is this the right selection?
- "Bill Status" shows 10 recent bills — the `outcome` mapping (passed/failed/on_agenda) may be too coarse
- "Committee Hearings" section is always empty — should it be hidden or populated?
- Date display shows "Recent" for bills without `last_action_date` — could show bill intro date instead

### 2. Enable State/Federal-Level Initiatives
Currently initiatives (start_something, list_initiatives) are city-level only. Extend to state/federal so users can organize around legislation:
- Add initiative tools to `CROSS_LEVEL_TOOLS` or state/federal tool sets
- Ensure relay coordination works across jurisdiction levels
- Consider: what does a "state-level initiative" look like vs city-level?

### 3. Attestation Origin Display
Design how attestation is displayed in the extension to distinguish its origin. Currently attestation is city-level (kind-30850 Nostr events). Questions to answer:
- How should attested vs non-attested voices be visually distinguished?
- Should attestation show the issuing jurisdiction?
- How does attestation work for state/federal level actions?

## Key Files

- `apps/civicos-mcp/tools/handlers.py:343` — `_legislation_pulse()` helper + `city_pulse` level dispatch
- `apps/civicos-mcp/handlers/loader.py:48` — `CROSS_LEVEL_TOOLS` (where to add initiative tools)
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — renders parent tab data with `level` prop
- `packages/civicos-client/src/api.ts:72` — `getCityPulseFromServer()` with retry
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:166` — `loadParentPulse()` and tab rendering
- `packages/civicos-relay/src/civicos_relay/voice/crypto.py` — Nostr signature/attestation
- `docs/critical/COORDINATION_PROTOCOL.md` — initiative and voice architecture

## Architecture Notes

- Cloudflare routes `*.civicosproject.org/mcp/*` to Modal (strips `/mcp` prefix). Other paths are NOT routed.
- The extension constructs URLs as `${mcp_endpoint}/api/tools/city-pulse` where `mcp_endpoint` includes `/mcp`.
- California/Federal servers have `MIN_CONTAINERS=0` (cold starts). Client has retry with 15s/30s timeout.
- `city_pulse` is now in `CROSS_LEVEL_TOOLS` — registered at all levels, handler dispatches by jurisdiction prefix.

## Commits This Session

- `f56677e` fix: Enable extension state/federal tabs with legislation pulse fallback
- `109ae82` fix: Handle Invalid Date in bill status and increase health check timeout
- `88a47fe` refactor: Move legislation pulse into handler layer (architecture critic)

## Deployment State

All 3 Modal servers redeployed with latest code:
- `civicos-san-rafael` (city) — warm (MIN_CONTAINERS=1)
- `civicos-california` (state) — cold start
- `civicos-federal` (federal) — cold start

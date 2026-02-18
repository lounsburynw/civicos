# Recommended: Redesign Connected Services Header + Redeploy Registry

**Priority:** P0 (`extension_connected_services_redesign`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

## Context

Last session added a Connected Services header dropdown to the extension side panel (commit `eeeabdc`). It shows jurisdiction chain with health dots, relay status, and latency. However:

1. **The UX should look like Supabase's breadcrumb header** — see screenshot reference. Supabase uses a horizontal breadcrumb with entity icons, badges (PRO, PRODUCTION), and chevron separators:
   ```
   👤 lounsburynw [PRO] > ⚡ civicos-mcp_san-rafael > 🌿 main [PRODUCTION]
   ```
   Our equivalent should be something like:
   ```
   🏠 San Rafael [primary] > 🏛 California [state] > 🇺🇸 Federal
   ```
   With health status indicators integrated into the breadcrumb, not a separate dropdown panel. Each segment should be clickable (to switch context/view that jurisdiction's data).

2. **Registry worker needs redeployment** — the code includes `relay_endpoint` and `relay_ws_endpoint` per server (falling back to global relay config), but the deployed Cloudflare Worker is stale. Until redeployed, no relay info shows in the extension.

## Task 1: Redesign Header as Supabase-style Breadcrumb

Replace the current header layout:
```
City Pulse  San Rafael + California, Federal    [ℹ] [●] [↻] [⚙]
```

With a Supabase-inspired breadcrumb:
```
San Rafael ● > California ○ > Federal ○        [ℹ] [↻] [⚙]
```

Where:
- Each jurisdiction segment is clickable (scrolls to/focuses that jurisdiction's data)
- Health dots are inline with each segment (green/gray/red)
- Primary jurisdiction shows `[primary]` badge or similar
- Relay status could be a small icon after the primary segment
- Clicking a segment could expand to show details (latency, version, tools)

### Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — main file (~5550 lines)
  - Lines 1946-1980: Current header with button row
  - Lines 2042-2108: Current services panel (dropdown below header)
  - Lines 97-105: `ServerHealthStatus` interface + state
  - Lines 593-647: `checkServerHealth()`, `checkRelayHealth()`, `checkAllHealth()`, `toggleServices()`, `overallHealthStatus()`
  - Lines 3870-3960: Connected Services CSS (`.services-panel`, `.service-row`, `.health-dot`, etc.)
- `apps/civicos-extension/src/lib/registry.ts` — `getRegistryServers()`, `getParentServers()`, `RegistryServer` type

### Design Notes
- The breadcrumb replaces both the current jurisdiction text AND the services dropdown
- Health information is surfaced inline, not hidden behind a click
- Keep the provenance (ℹ), refresh, and settings buttons
- Consider mobile/narrow width — breadcrumb could truncate or scroll

## Task 2: Redeploy Registry Worker

The registry worker code already includes relay fields but the deployed version is stale.

```bash
cd apps/civicos-registry
npx wrangler deploy
```

Verify after deploy:
```bash
curl -s https://registry.civicosproject.org/api/v1/servers | python3 -m json.tool | grep relay
```

Should show `relay_endpoint` and `relay_ws_endpoint` for each server.

### Registry Files
- `apps/civicos-registry/src/registry.ts:59-60` — relay_endpoint fallback logic
- `apps/civicos-registry/src/api.ts:23-24` — relay fields in API response
- `config/registry.json:35-40` — global relay config

## Tests
```bash
# Extension builds clean
cd apps/civicos-extension && npm run build

# Registry type-checks
cd apps/civicos-registry && npx tsc --noEmit
```

## Success Criteria
- [ ] Header shows Supabase-style breadcrumb with jurisdiction chain
- [ ] Health dots visible inline per jurisdiction segment
- [ ] Relay status visible (after registry redeploy)
- [ ] Registry worker redeployed with relay fields
- [ ] Extension builds without errors

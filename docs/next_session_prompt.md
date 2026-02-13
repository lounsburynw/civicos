# Handoff: Debug Create Initiative + Phase 3 Polish

**Priority:** P0 (extension_phase3_ai_viz — still needs debugging)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> Session 585 built Phase 3 features but Create Initiative button is non-clickable. Debug and fix before moving to Phase 4.

## Bug: Create Initiative Button Disabled

**Symptom:** User clicks "+" on Community Initiatives, fills out the form, but the "Create Initiative" button is not clickable.

**Root cause (likely):** The button has `disabled={!identity?.isUnlocked || ...}`. The user may not have an unlocked identity. But even if they DO have one, there may be a Nostr signing issue preventing submission.

**Debug steps:**
1. Check if identity is set up: Open Options page, verify identity exists
2. Check if identity is unlocked: Side panel should show unlock state
3. If identity IS unlocked, check the `handleCreateInitiative()` function — it signs a Nostr event via service worker then POSTs to the relay
4. Check relay CORS — was fixed to `allow_origins=["*"]` this session
5. Check relay endpoint: `curl -X POST https://api.civicosproject.org/coordination/initiative` (or whatever the relay URL is)
6. The relay may not be deployed with the new initiative routes from Phase 2b

**Key code locations:**
- Button: `SidePanel.svelte` ~line 1304 — `disabled={!identity?.isUnlocked || creatingInitiative || !newInitiative.topic.trim() || !newInitiative.title.trim() || !newInitiative.description.trim()}`
- Handler: `SidePanel.svelte` ~line 694 — `handleCreateInitiative()`
- API: `api.ts` — `createInitiative()` function
- Relay route: `packages/civicos-relay/src/civicos_relay/server/app.py` — `POST /coordination/initiative`

**Possible fixes:**
- If identity issue: Make the form work without signing (anonymous initiatives)
- If relay not deployed: Run `modal deploy` for the relay
- If CORS issue: Already fixed to `*` but verify it's deployed
- If the disabled logic is too strict: Relax the conditions

## Also Verify (from this session)

1. **Issue Map** — Fixed rendering with `$effect` + `requestAnimationFrame`. Verify tiles load and markers appear when section is expanded.
2. **Budget Chart** — Same fix. Verify doughnut chart renders with department breakdown.
3. **Ask AI / Summarize buttons** — Should work (clipboard + open Claude.ai). Test on a decision with testimony.

## What Was Built This Session (585)

### Commits (4):
```
2aeb0f1 fix: Initiative creation visibility, map/chart rendering issues
ed29b2b feat: Browser extension Phase 3 — AI context injection + visualizations
0f784e2 feat: Browser extension Phase 2b — initiatives, civic actions, commitments + CORS fix
```

### Phase 3 Features:
- "Ask AI about this" on agenda items + decision cards (clipboard → Claude.ai)
- "Summarize" button on Public Testimony sections
- Leaflet issue map (dark CARTO tiles, color-coded markers, lazy-load)
- Chart.js budget doughnut chart (department breakdown, lazy-load)
- Initiative "+" button now visible without identity (shows hint)

### Libraries Added:
- leaflet + @types/leaflet
- chart.js

### Rendering Fix Applied:
- Replaced `setTimeout(50)` with Svelte 5 `$effect` watching `bind:this` refs
- Added `requestAnimationFrame` for DOM readiness
- Added `invalidateSize()` for Leaflet re-expand

## Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` (~2400 lines)
- `apps/civicos-extension/src/lib/api.ts` — all API methods
- `apps/civicos-extension/src/lib/types.ts` — data models
- `packages/civicos-relay/src/civicos_relay/server/app.py` — relay with initiative routes

## Relay URL Configuration
The extension gets relay URL from `chrome.storage.local` key `civicos_relay_url`. Check `api.ts` `getRelayUrl()` function. Default may point to a URL that doesn't have the new routes deployed.

## pilot.json Status
- `extension_phase3_ai_viz`: marked `ready` but needs debugging
- `extension_phase4_micropayments`: P0 (set for after Phase 3 is solid)
- Consider reverting phase3 to `not_ready` if bugs are significant

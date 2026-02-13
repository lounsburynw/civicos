# Handoff: Browser Extension Phase 2b — Debug & Complete

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> Session 584 implemented Phase 2b (initiatives + commitments) but the user reports they don't see changes in the extension. Debug and complete.

## What Was Built (This Session)

### Relay Routes (NEW — `packages/civicos-relay/src/civicos_relay/server/app.py`)
- `POST /coordination/initiative` — create initiative
- `GET /coordination/initiatives/{jurisdiction}` — list initiatives
- `GET /coordination/initiative/{id}` — get detail
- `POST /coordination/civic-action` — create civic action (Kind 30810)
- `GET /coordination/civic-actions/{initiative_id}` — list actions
- `GET /coordination/civic-action/{id}/progress` — progress counts
- `POST /coordination/civic-action/{id}/commit` — Kind 30811
- `POST /coordination/civic-action/{id}/complete` — Kind 30812
- `POST /coordination/civic-action/{id}/withdraw` — withdraw
- Wired `CivicActionService` + `initiative_storage` in `lifespan()`
- Added request models: `CreateInitiativeRequest`, `CreateCivicActionRequest`, `CivicCommitRequest`, `CivicCompleteRequest`

### Extension Changes
1. **`apps/civicos-extension/src/lib/types.ts`** — Added `Initiative`, `CivicAction`, `CivicActionProgress` interfaces
2. **`apps/civicos-extension/src/lib/api.ts`** — Added 8 relay API methods: `getInitiatives`, `getCivicActions`, `getCivicActionProgress`, `commitToCivicAction`, `completeCivicAction`, `withdrawCivicAction`, `createInitiative`, `createCivicAction`
3. **`apps/civicos-extension/src/side-panel/SidePanel.svelte`** (~2100 lines now):
   - Meetings label "Upcoming Meetings" → "Meetings", calendar buttons disabled for past
   - Community Initiatives section with expandable cards, voice counts, coordination links
   - "+" button to create initiatives (form: topic, title, description, coordination URL)
   - Nested civic actions with progress bars, deadline badges (normal/urgent/overdue)
   - "+ Add Action" form inside expanded initiatives (type dropdown, description, target, deadline)
   - Commit/Complete/Withdraw buttons with Kind 30811/30812 Nostr signing
   - My Commitments section using stored metadata (renders without expanding parent initiative)
   - `committedActionMeta` Map persisted to `chrome.storage.local`

### What Builds Successfully
- Extension: `cd apps/civicos-extension && npm run build` — 789ms, clean
- Relay: `from civicos_relay.server.app import create_app` — imports clean

## Problem: User Can't See Changes

Likely causes to investigate:
1. **Extension not reloaded in Chrome** — user needs to go to `chrome://extensions`, click reload on CivicOS extension, then reopen the side panel
2. **Relay not redeployed** — the new routes exist in code but the production relay at `api.civicosproject.org` hasn't been redeployed. The extension calls that URL. Without redeploying, `getInitiatives()` returns `[]` and the section shows "No active initiatives"
3. **CORS issue** — `app.py` line ~228 has `allow_origins` limited to `localhost:5173` and `localhost:8080`. Chrome extension origins (`chrome-extension://...`) are not listed. Need to add `"*"` or the extension's origin
4. **Modal deployment needed** — relay deploys via Modal, not local. Code changes aren't live until `modal deploy` runs

## Debugging Steps

```bash
# 1. Rebuild extension
cd apps/civicos-extension && npm run build

# 2. Check CORS in relay
grep -n "allow_origins" packages/civicos-relay/src/civicos_relay/server/app.py

# 3. Fix CORS if needed (add chrome-extension origins)
# allow_origins=["*"] for dev, or add chrome-extension://<id>

# 4. Test relay locally
cd packages/civicos-relay && python3 -m civicos_relay.server.app
# Then curl http://localhost:8000/coordination/initiatives/city-san-rafael

# 5. Deploy relay to Modal
modal deploy packages/civicos-relay/src/civicos_relay/modal_app.py

# 6. Reload extension in chrome://extensions
# 7. Open side panel, check console for errors (right-click side panel → Inspect)
```

## CORS Fix (Almost Certainly Needed)

In `packages/civicos-relay/src/civicos_relay/server/app.py`, around line 228:
```python
# Current (too restrictive):
allow_origins=["http://localhost:5173", "http://localhost:8080"],

# Fix:
allow_origins=["*"],  # Extensions use chrome-extension:// origins
```

## Key Files
- `packages/civicos-relay/src/civicos_relay/server/app.py` — relay routes (all new routes here)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — main UI
- `apps/civicos-extension/src/lib/api.ts` — API client
- `apps/civicos-extension/src/lib/types.ts` — TypeScript interfaces
- `apps/civicos-extension/src/lib/providers/types.ts` — Nostr event helpers (unchanged)

## pilot.json Status
- `extension_phase2b_commitments`: marked `ready` (may need to revert to `not_ready` if debugging reveals issues)
- `extension_phase3_ai_viz`: set as P0

## Success Criteria
- [ ] User can see Community Initiatives section in side panel
- [ ] User can create an initiative via the "+" button
- [ ] User can add civic actions to an initiative
- [ ] Commit/Complete/Withdraw buttons work with relay
- [ ] My Commitments section shows after committing
- [ ] Relay deployed to Modal with CORS fix

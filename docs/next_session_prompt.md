# Recommended: Browser Extension Phase 2b — Commitments + Initiative Tracking

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context
Session 583 completed Phase 2 (voice signing): the extension now has Support/Oppose/Watch buttons on agenda items and decisions, with Kind 30800 Nostr signing via the service worker, relay submission with optimistic updates + rollback, and stance persistence via `chrome.storage.local`.

| Phase | Item | Priority | Status |
|---|---|---|---|
| Phase 1 | `extension_phase1_city_pulse` | P1 | **ready** |
| Phase 1b | `extension_phase1b_read_enhancements` | P1 | **ready** |
| Phase 2 | `extension_phase2_voice_signing` | P1 | **ready** |
| **Phase 2b** | **`extension_phase2b_commitments`** | **P0** | **not_ready** (NEXT) |
| Phase 3 | `extension_phase3_ai_viz` | P2 | not_ready |

## Quick Fix First: Meetings Section UI Polish
User feedback from Session 583 — address before starting Phase 2b:
1. **Rename "Upcoming Meetings"** to "Meetings" or "Recent & Upcoming" — currently shows past meetings under an "Upcoming" label
2. **Disable calendar buttons for past meetings** — `isPastMeeting()` already exists, just gate the calendar button
3. These are ~10-line changes in `SidePanel.svelte`

## Recommended Task: Phase 2b
Add user-spawned initiatives with push/pull coordination. Show community initiatives with nested civic actions, progress bars, and commit/complete/withdraw buttons via the relay.

### Features
- My Commitments section with deadline tracking
- Community initiatives listing with voice counts
- Civic actions per initiative with progress bars
- Commit/complete/withdraw action buttons (Kind 30810/30811/30812)
- Deadline countdown (urgent if <=3d, overdue coloring)
- Coordination channel links (Signal/Matrix/Telegram)

## Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — main UI (~1290 lines), add initiatives section
- `apps/civicos-extension/src/lib/api.ts` — add initiative/action API methods
- `apps/civicos-extension/src/lib/providers/types.ts` — already has `CivicEventKinds` (30810/30811/30812), `createActionEventContent()`, `createActionCommitmentContent()`, `createActionCompletionContent()`, and all related tag helpers

### Reference implementation (Open WebUI)
- Check `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` for initiative rendering patterns
- Check `~/projects/civicos-openwebui/src/lib/apis/civic.ts` for initiative/action API calls

### Relay API Endpoints
Base URL: `https://api.civicosproject.org`
- Check relay routes for initiative CRUD and action commit/complete endpoints
- Voice endpoints (already integrated): `POST /coordination/voice`, `POST /coordination/voice/revoke`

## User Priority Notes
The user also wants the **interactive issues map** (Phase 3, `extension_phase3_ai_viz`) to replace the current plain issues section. This requires a map library (Leaflet or similar). Keep this in mind when structuring Phase 2b — the issues section will be replaced in Phase 3.

## Build & Test
```bash
cd apps/civicos-extension && npm run build
# Reload in chrome://extensions
# Open side panel, verify initiatives section appears
# Test commit/complete/withdraw flows
```

## Success Criteria
- [ ] Meetings section label fixed (not "Upcoming" when showing past meetings)
- [ ] Calendar buttons disabled for past meetings
- [ ] Community initiatives section with voice counts
- [ ] Civic actions per initiative with progress indicators
- [ ] Commit/complete/withdraw buttons with relay submission
- [ ] My Commitments personal tracker with deadline display
- [ ] pilot.json item `extension_phase2b_commitments` marked ready

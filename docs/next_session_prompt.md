# Recommended: Browser Extension Phase 1b — Read-Only Enhancements

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context
Session 581 completed Phase 1 of the browser extension: the side panel now fetches live data from the CivicOS REST API and displays upcoming meetings, agenda items, recent decisions, and community issues (commit `b24d56d`). The user tested it in Chrome and confirmed it works — described as "a rudimentary version of the city pulse dashboard." They want to reach parity with the Open WebUI CityPulse component.

A full gap analysis was done comparing the extension vs Open WebUI CityPulse. The work is broken into multiple sessions:

| Phase | Item | Priority | Status |
|---|---|---|---|
| Phase 1 | `extension_phase1_city_pulse` | P0 | **ready** |
| **Phase 1b** | **`extension_phase1b_read_enhancements`** | **P0** | **not_ready** (NEXT) |
| Phase 2 | `extension_phase2_voice_signing` | P1 | not_ready |
| Phase 2b | `extension_phase2b_commitments` | P1 | not_ready |
| Phase 3 | `extension_phase3_ai_viz` | P2 | not_ready |

## Recommended Task
Phase 1b: enrich the existing City Pulse sections with read-only enhancements. These all use existing REST API endpoints — no relay integration or signing needed.

### Features to add
1. **Voice counts display** (read-only) — show support/oppose/watching tallies on agenda items and decisions. Fetch via batch endpoint.
2. **Expandable decision detail** — click a decision card to expand with full context, testimony excerpts, related decisions. Uses `POST /decision-detail` API.
3. **Calendar buttons** — "Add to Google Calendar" URL and `.ics` file download per meeting. Port logic from Open WebUI CityPulse.
4. **Data provenance panel** — info button in header revealing data sources, corpus counts, vector coverage, freshness. Uses `GET /data-provenance` API.
5. **Past meeting badge** — visual indicator (clock icon, muted styling) for meetings that have already occurred. Simple date comparison.

## Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — main UI to enhance (673 lines)
- `apps/civicos-extension/src/lib/api.ts` — add new API methods (getCityPulse only right now)
- `apps/civicos-extension/src/lib/types.ts` — add types for decision detail, provenance, voice counts
- `apps/civicos-mcp/rest_api.py` — REST API reference for endpoint shapes
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — reference implementation (2000+ lines)

## REST API Endpoints to Use
All endpoints are at `https://san-rafael.civicosproject.org/api/tools/`:
- `POST /decision-detail` — `{title: string}` → full decision context with testimony
- `GET /data-provenance` — corpus counts, vector coverage, freshness
- `POST /get-item-context` — `{item_type, item_id, depth}` → rich context bundle

For voice counts, check the relay coordination API:
- Relay URL is in `.env` as `CIVICOS_RELAY_URL` or use `civicos.registry.get_relay_url()`
- `GET /coordination/voices/{entity_id}` — voice counts for an entity
- Batch approach: fetch counts for all visible entity IDs on load

## Suggested Approach
1. Add new API methods to `src/lib/api.ts`: `getDecisionDetail()`, `getDataProvenance()`, `getVoiceCounts()`
2. Add corresponding TypeScript interfaces to `src/lib/types.ts`
3. Enhance `SidePanel.svelte`:
   - Decision cards: add click-to-expand with slide transition, show detail inside
   - Meeting cards: add calendar dropdown (Google Cal URL + .ics blob download)
   - Header: add info button that toggles provenance panel
   - Meeting cards: compare `meeting_datetime` to `new Date()` for past badge
   - Agenda/decision cards: show voice count badges if available
4. Keep the same dark theme and collapsible section patterns

## Reference: Open WebUI Calendar Logic
```typescript
// Google Calendar URL
const gcalUrl = `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${startISO}/${endISO}&location=${encodeURIComponent(location)}`;

// .ics file
const icsContent = `BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:${startISO}\nDTEND:${endISO}\nSUMMARY:${title}\nLOCATION:${location}\nEND:VEVENT\nEND:VCALENDAR`;
const blob = new Blob([icsContent], { type: 'text/calendar' });
```

## Build & Test
```bash
cd apps/civicos-extension && npm run build
# Reload extension in chrome://extensions (click refresh icon)
# Open side panel — click a decision to expand, click calendar on a meeting
```

## Success Criteria
- [ ] Decision cards expand on click showing detail + testimony
- [ ] Meeting cards have "Add to Calendar" dropdown (Google Cal + .ics)
- [ ] Info button in header shows data provenance panel
- [ ] Past meetings visually distinguished from upcoming
- [ ] Voice count badges shown if data available
- [ ] pilot.json item `extension_phase1b_read_enhancements` marked ready

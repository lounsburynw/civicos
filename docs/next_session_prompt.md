# Recommended: Browser Extension Phase 1 — City Pulse Feed

**Priority:** P0
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-12

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context
Session 580 completed the browser extension Phase 0: identity scaffold with Chrome storage persistence and working unlock flow (commit `9628362`). The side panel currently shows a placeholder "City Pulse — coming in Phase 1". The user wants to build out the extension with live civic data.

## Recommended Task
Implement the City Pulse feed in the extension's side panel. Connect to the CivicOS REST API to show upcoming meetings, recent decisions, and community issues — the same data the Open WebUI CityPulse dashboard displays.

## Key Files
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — current placeholder, needs City Pulse sections
- `apps/civicos-extension/src/side-panel/main.ts` — side panel entry point
- `apps/civicos-extension/src/background/service-worker.ts` — message handler (may need new message types for API calls)
- `apps/civicos-mcp/rest_api.py` — REST API with all available endpoints
- `docs/critical/BROWSER_EXTENSION_ARCHITECTURE.md:72-125` — City Pulse UX spec with wireframe

## Existing REST API Endpoints (on Modal at civicos MCP endpoint)
The extension can call these directly:
- `POST /city-pulse` — main dashboard data
- `POST /get-upcoming-meetings` — upcoming meetings
- `POST /search-meeting-history` — past meeting search
- `POST /find-similar-issues` — SeeClickFix issues
- `GET /data-provenance` — data source info
- `POST /get-item-context` — context assembly for specific items
- `GET /budget-summary` — budget overview

## Suggested Approach
1. Read `BROWSER_EXTENSION_ARCHITECTURE.md:72-125` for the City Pulse wireframe and section spec
2. Read the Open WebUI CityPulse component for reference patterns: `~/projects/civicos-openwebui/src/lib/components/civic/`
3. Add an API client module (`src/lib/api.ts`) that calls the REST API endpoints
4. Route API calls through the service worker (extension pages can't make cross-origin requests directly; the SW can via `fetch`)
5. Build City Pulse sections in `SidePanel.svelte`: identity chip (done), upcoming meetings, recent decisions, community issues
6. Start with Layer 1 (deterministic) — just data display, no AI integration yet

## Architecture Note
Per the architecture doc, the side panel fetches civic data from the Jurisdiction MCP via HTTP. API calls should go through the service worker (add `FETCH_CITY_PULSE`, `FETCH_MEETINGS` etc. message types) since the SW has network access and can cache responses. The extension needs to know the MCP endpoint URL — store in `chrome.storage.local` alongside identity data.

## Build & Test
```bash
cd apps/civicos-extension && npm run build
# Reload extension in chrome://extensions
# Open side panel — should show live civic data instead of placeholder
```

## Success Criteria
- [ ] Side panel shows upcoming meetings from the CivicOS API
- [ ] Side panel shows recent decisions
- [ ] Side panel shows community issues
- [ ] Data refreshes on panel open
- [ ] pilot.json item `extension_phase1_city_pulse` marked ready

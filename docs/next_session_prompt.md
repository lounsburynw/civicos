# Recommended: Dashboard MVP — Next P1 Feature

**Priority:** P0 (civic_dashboard_mvp umbrella) with P1 sub-items ready to implement
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-07

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 541 completed `add_to_cal` (calendar links for upcoming meetings). The dashboard MVP now has: IssueMap with filtering, voice toggle, comment threads, and calendar links. Backend deployed to Modal with `location` + `meeting_datetime` in city-pulse response.

Remaining P1 items from the dashboard batch:

## Recommended: `comment_synthesis` (highest pilot value)

For agenda items with comments, show an AI-synthesized summary: total count, sentiment breakdown (support/oppose/neutral), key themes, notable quotes. This is the "why CivicOS matters" feature for council member demos.

**Implementation plan:**
- **Backend**: New `/comment-synthesis` endpoint in `rest_api.py` or `tools/handlers.py`
  - Fetch comments for an entity from relay (`getComments`)
  - Call LLM (OpenAI via existing config) for synthesis
  - Cache result (simple in-memory or database-backed)
- **Relay**: Comment data already accessible via `packages/civicos-relay/src/civicos_relay/coordination/` endpoints
- **Frontend**: Expandable synthesis panel per agenda item in CityPulse.svelte, below the comment count button
- **Key challenge**: LLM latency — consider async loading with a spinner, or pre-compute on comment submission

**Key files:**
- `apps/civicos-mcp/tools/handlers.py` — add synthesis handler
- `apps/civicos-mcp/rest_api.py` — add REST endpoint
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — synthesis UI
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — API client
- `packages/civicos-relay/src/civicos_relay/coordination/comment_storage.py` — comment data access

## Other P1/P2 Items (if comment_synthesis is too complex for one session)

### `budget_treemap_viz` (P1, data ready, visually compelling)
58 budget_items ($180M) already in PostgreSQL. Horizontal bar chart in CityPulse sidebar.

- **Backend**: New `/budget-summary` endpoint grouping budget_items by category
- **Data**: `packages/civicos/src/civicos/storage/postgres_backend.py` — budget methods
- **Frontend**: New `BudgetChart.svelte` component

### `agenda_actionability` (P1, important for credibility)
Classify agenda items as actionable vs informational. Hides voice/comment UI on informational items (e.g. "Open Time for Public Expression"). Uses LLM structured output.

- **Schema**: Add `actionability` field to agenda items
- **Ingestion**: Post-processing step after `store_meetings()`
- **Frontend**: Conditional rendering of voice/comment controls in CityPulse

### `expandable_decisions` (P2)
Expand decision rows to show vote breakdown, related testimony, linked docs.

### `provenance_footer` (P2)
Data provenance info panel showing MCP endpoint, relay ID, data freshness.

## Completed This Session
- [x] `add_to_cal` — Calendar icon + dropdown (Google Calendar + .ics download) on each upcoming meeting
- [x] Backend deployed to Modal with location + meeting_datetime fields
- [x] pilot.json updated, all changes committed

## Dev Workflow Reminder

**Use Vite dev server for frontend iteration (NOT Docker rebuilds):**
```bash
cd ~/projects/civicos-openwebui && npm run dev   # localhost:5173, hot reload
```

## Key Files
- `pilot.json` — all items under `frontend_refinement.city_status_dashboard.*`
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — main dashboard
- `apps/civicos-mcp/tools/handlers.py` — backend tool handlers (city-pulse, etc.)
- `apps/civicos-mcp/rest_api.py` — REST endpoint definitions

## Success Criteria
- [ ] At least one P1 item implemented and deployed
- [ ] Tested via Vite dev server
- [ ] P0 updated in pilot.json for next session

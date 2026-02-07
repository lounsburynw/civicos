# Recommended: Dashboard MVP — P1 Feature Batch

**Priority:** P0 (civic_dashboard_mvp umbrella) with P1 sub-items ready to implement
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-07

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The dashboard MVP core is functional: IssueMap with recency filtering (30d/90d/All), status filtering (Open/Closed), trend TLDR, full-screen expand modal, type legend, comment threads, and voice toggle. We broke out 6 new P1/P2 items from user feedback. The highest-impact next work is the P1 batch.

## Uncommitted Work

- **civicos-openwebui**: IssueMap Closed filter change is committed+pushed (`85118a6`), but the Docker container at `:8080` is 2 commits behind. Rebuild when ready for production testing.
- **civicos**: `pilot.json` updates (6 new items) and CLAUDE.md/launch docs are **uncommitted**. Commit these first.

## Recommended: Pick from P1 Batch (in suggested order)

### 1. `add_to_cal` — Meeting calendar links (quickest win, ~30min)
Generate .ics and Google Calendar links for meetings in Upcoming section. Data is ready (`meeting_datetime`, title in meetings table). Self-contained, no backend changes needed beyond possibly adding location to the API response.

- **Frontend**: `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — add calendar icon per meeting row
- **API**: `apps/civicos-mcp/rest_api.py:170-200` — city-pulse endpoint (check if location is returned)

### 2. `comment_synthesis` — AI-summarized public sentiment (highest pilot value)
For agenda items with comments, show synthesized summary: count, sentiment breakdown, key themes. This is the "why CivicOS matters" feature for council member demos.

- **Backend**: New `/comment-synthesis` endpoint in `rest_api.py`
- **Relay**: Comment data via `packages/civicos-relay/src/civicos_relay/coordination/` endpoints
- **Frontend**: Expandable synthesis panel in CityPulse
- **Needs**: LLM call (OpenAI via existing config) + response caching

### 3. `budget_treemap_viz` — Budget visualization (data ready, visually compelling)
58 budget_items ($180M) already in PostgreSQL. Horizontal bar chart in CityPulse sidebar.

- **Backend**: New `/budget-summary` endpoint grouping budget_items by category
- **Data**: `packages/civicos/src/civicos/storage/postgres_backend.py` — budget methods around line 3900+
- **Frontend**: New `BudgetChart.svelte` component

### 4. `agenda_actionability` — LLM classification (important for credibility)
Classify agenda items as actionable vs informational at ingestion time. Hides voice/comment UI on informational items (e.g. "Open Time for Public Expression"). No heuristics — uses LLM structured output.

- **Schema**: Add `actionability` field to agenda items
- **Ingestion**: Post-processing step after `store_meetings()`
- **Frontend**: Conditional rendering of voice/comment controls in CityPulse

## Dev Workflow Reminder

**Use Vite dev server for frontend iteration (NOT Docker rebuilds):**
```bash
cd ~/projects/civicos-openwebui && npm run dev   # localhost:5173, hot reload
```
Only rebuild Docker for final production testing. See CLAUDE.md "Open WebUI Development" section.

## Key Files
- `pilot.json` — all new items under `frontend_refinement.city_status_dashboard.*`
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — main dashboard
- `~/projects/civicos-openwebui/src/lib/components/civic/IssueMap.svelte` — enhanced map
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts:726` — IssuePoint type with created_at
- `apps/civicos-mcp/rest_api.py:236` — issue-geography endpoint (deployed to Modal)
- `packages/civicos/src/civicos/storage/postgres_backend.py:3782` — get_issues with created_after

## Success Criteria
- [ ] pilot.json and doc changes committed
- [ ] At least one P1 item implemented and deployed
- [ ] Tested via Vite dev server (not Docker rebuild loop)
- [ ] P0 updated in pilot.json for next session

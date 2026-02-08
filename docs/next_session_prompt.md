# Recommended: Agenda Item Actionability Classification

**Priority:** P0
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-07

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed `budget_treemap_viz` (BudgetChart.svelte + /budget-summary endpoint deployed to Modal) and wired up the comment synthesis frontend (getCommentSynthesis was defined but never called, now integrated with sentiment bar). The dashboard MVP now has: IssueMap with filtering, voice toggle, comment threads, calendar links, comment synthesis sentiment bar, and budget allocation chart.

The last P1 sub-item under the dashboard MVP is `agenda_actionability`. Items like "Open Time for Public Expression" currently show voice/comment UI, which is confusing — there's no decision point. Classification at ingestion time was chosen over edge intelligence because actionability is an objective property of the item, not a user preference.

## Recommended Task

Classify agenda items as `actionable` / `informational` / `mixed` at ingestion time using LLM structured output. Store the field permanently. Frontend hides voice/comment UI on informational items.

## Architecture Decision: Ingestion Time

Classify at **ingestion time** (not request time or edge). Rationale:
- Actionability is a data property, not a user judgment
- Classify once, store forever — no LLM latency at render time
- Consistent across all users
- Personal relevance is a separate edge intelligence concern

## Implementation Plan

1. **Schema**: Add `actionability` column to meetings/agenda items in PostgreSQL
   - Enum: `actionable`, `informational`, `mixed`
   - Nullable (for backward compat with existing data)

2. **LLM Classification**: Post-processing step after `store_meetings()`
   - Structured output: `{actionability: str, confidence: float, reasoning: str}`
   - Prompt: classify based on title + summary/description
   - Use OpenAI (existing config in .env)

3. **Retroactive Backfill**: Run classification on existing 98 meetings' agenda items

4. **City-pulse handler**: Include `actionability` field in `upcoming_items` response

5. **Frontend**: In CityPulse.svelte, conditionally render voice/comment/draft controls
   - `actionable`/`mixed`: show all controls (current behavior)
   - `informational`: hide controls, show subtle "Informational" badge

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py:5758` — `store_meetings()` method
- `apps/civicos-mcp/tools/handlers.py:342` — `city_pulse()` handler builds `upcoming_items`
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte:500-600` — agenda item rendering with voice/comment controls
- `~/projects/civicos-openwebui/src/lib/apis/civic.ts` — `AgendaItem` type (add `actionability` field)
- `pilot.json:2648` — `agenda_actionability` item definition

## Dev Workflow

```bash
cd ~/projects/civicos-openwebui && npm run dev   # Frontend: localhost:5173
modal deploy apps/civicos-mcp/modal_mcp.py       # Deploy MCP server (from project root)
```

## Success Criteria

- [ ] Agenda items classified with actionability field at ingestion time
- [ ] Existing items retroactively classified
- [ ] Frontend hides voice/comment on informational items
- [ ] "Informational" badge visible on non-actionable items
- [ ] Deployed to Modal

## Completed This Session

- [x] `budget_treemap_viz` — BudgetChart.svelte (CSS horizontal bars), /budget-summary endpoint with auto fiscal year detection, deployed to Modal
- [x] Comment synthesis frontend wired up — getCommentSynthesis() called on thread open, sentiment bar shows comment-based data, refreshes after posting
- [x] Commits: civicos `8e08ce6`, `36d4bca`; openwebui `6c2ad0d`

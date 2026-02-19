# Recommended: Engagement Ladder UX — Deploy + Participation Layer

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Two sessions built the state/federal tab UX: the first enabled tabs with legislation data (f56677e), and this session rewrote `_legislation_pulse()` with proper Legiscan status mapping, topic overview grids, leverage point descriptions, and better bill activity ordering. The **Awareness and Relevance** layers of the engagement ladder are now solid. The code is committed but **not yet deployed to Modal**.

## Recommended Tasks (in priority order)

### 1. Deploy to Modal and Verify in Extension
The committed changes need deployment to the California and Federal Modal servers. Verify the new topic grid and bill activity renders correctly in the extension.

```bash
# Deploy state + federal servers
modal deploy apps/civicos-mcp/modal_app.py --name civicos-california
modal deploy apps/civicos-mcp/modal_app.py --name civicos-federal
```

Then load the extension and check:
- California tab: Topic grid (Budget, Environment, Housing, etc.) with stage counts
- Federal tab: Stage overview (Introduced, Engrossed, Passed, Vetoed) — no topics yet
- Key Legislation: Shows bill name + topic badge + leverage action description
- Bill Activity: Proper status labels (Passed, Failed, Vetoed, Introduced, etc.)

### 2. Enable State/Federal-Level Initiatives (Participation layer)
Currently `start_something` and `list_initiatives` are city-level only. Extend to state/federal so users can organize around legislation:
- Add initiative tools to `CROSS_LEVEL_TOOLS` in `apps/civicos-mcp/handlers/loader.py:49`
- Ensure relay coordination works across jurisdiction levels
- Consider: what does a "state-level initiative" look like vs city-level?

### 3. Enrich Federal Bill Topics
Federal bills all show as "Other" (no topics). Consider running AI batch enrichment:
- The leverage point enrichment pipeline from the earlier session could be adapted
- Would make the Federal tab topic grid actually useful

## Key Files

- `apps/civicos-mcp/tools/handlers.py:343` — `LEGISCAN_STATUS` mapping, `_resolve_bill_status()`, `_bill_date()`, `_legislation_pulse()` (rewritten this session)
- `apps/civicos-mcp/handlers/loader.py:49` — `CROSS_LEVEL_TOOLS` frozenset (add initiative tools here)
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — Topic grid (isLegislative branch), leverage descriptions, updated labels
- `packages/civicos-components/src/utils/civic-helpers.ts:30` — `outcomeIcon()`/`outcomeClass()` extended for legislative statuses
- `packages/civicos-client/src/api.ts:72` — `getCityPulseFromServer()` with retry
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:166` — `loadParentPulse()` and tab rendering

## What Changed This Session

**Backend (`_legislation_pulse` rewrite):**
- Legiscan status codes mapped to labels: 1=Introduced, 2=Engrossed, 3=Enrolled, 4=Passed, 5=Vetoed, 6=Failed
- Section 1: "Active Topics" — topic grid with bill stage counts (CA) or stage overview (US fallback)
- Section 2: "Key Legislation" — bills with leverage points, topic badges, action descriptions
- Section 3: "Bill Activity" — resolved bills first (7) + active with leverage (3), proper status labels
- Community pulse: topic breakdown instead of generic "Actionable: X"

**Frontend:**
- 2-column topic grid for legislative levels (replaces empty CivicMeetingCard section)
- Leverage point descriptions shown on Key Legislation cards
- Outcome helpers handle all legislative statuses

## Architecture Notes

- Cloudflare routes `*.civicosproject.org/mcp/*` to Modal (strips `/mcp` prefix)
- California/Federal servers have `MIN_CONTAINERS=0` (cold starts). Client has retry with 15s/30s timeout.
- `city_pulse` is in `CROSS_LEVEL_TOOLS` — registered at all levels, handler dispatches by jurisdiction prefix.

## Commits This Session

- `54dcf8a` feat: Improve state/federal tab UX with topic overview and proper bill status

## Deployment State

Modal servers need redeployment with latest code:
- `civicos-san-rafael` (city) — warm (MIN_CONTAINERS=1), already has latest
- `civicos-california` (state) — cold start, **needs deploy**
- `civicos-federal` (federal) — cold start, **needs deploy**

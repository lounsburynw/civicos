# Recommended: engagement_ladder_ux — Phase 4 (State/Federal Polish + Topic Tagging)

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 3 (UX polish) is complete across 12 commits. The city tab now has: attention bar with official + initiative items, Official/Public section hierarchy, draft-to-route workflow (AI draft → official mailto or community comment), cached AI summaries, collapsible Issue Map and Budget sections, and all "attested" text replaced with checkmark icons. Several Svelte 5 reactivity bugs were fixed (TDZ errors, state mutation, tick timing).

The ultimate goal is organizing read-MCP and public-relay items like a library — tagged by topic, actionable items at top — to enable a chat router that triggers tool calls. Phase 4 brings state/federal tabs to the same polish standard, and lays the topic tagging foundation.

## What Was Done (Session 8 — Phase 3)

- Attention bar: city-only + initiatives with voices/recent, scrollable, "Upcoming actionable items" title
- Official/Public group headers for information hierarchy
- Issue Map and Budget restored as collapsible sections under Official
- Draft-to-route workflow: "Draft with AI" on cards → editable draft → route to official (mailto) or community comment
- AI summary toggle: cached responses collapse/expand, regenerate option
- Initiatives surfaced in attention bar (voices > 0 or created within 7 days) with scroll-to-card
- All "attested" text → green checkmark icons (AgendaItemCard, DecisionCard, CommentThread, InitiativeCard)
- My Commitments section removed
- Monochrome palette applied to initiatives
- Past meetings filtered out (today or future only)
- Fixed: Svelte 5 `$state` Record mutation (spread reassign), `tick()` for lazy component load timing, TDZ error in CivicIssueMap (ISSUE_COLORS declared after `$state` that referenced it)

## Phase 4 Tasks

### 4a: State/federal tab polish (CivicReadOnlyPulse)
Apply the same UX patterns from the city tab to `CivicReadOnlyPulse.svelte`:
- Attention bar with comment periods, hearings, governor's desk items
- Official/Public section grouping
- Monochrome palette consistency (some blue accents may remain)
- Collapsible sections with chevrons
- Current code: `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte`

### 4b: Topic tagging foundation
This bridges the gap from time-sorted feed to topic-organized library:
- Agenda items and decisions don't currently have topic tags (initiatives do)
- Need topic classification on all entity types — either from MCP data or derived client-side
- This enables "browse by topic" and powers the future chat router ("show me housing items")
- Consider: lightweight client-side topic extraction from titles, or add topic field to pulse API

### 4c: Svelte 5 reactivity audit
Several Svelte 5 bugs were hit this session. Key patterns to watch:
- `$state` with `Record<string, boolean>` — must spread-reassign, not mutate properties
- `const` declarations must come before `$state()` that references them (TDZ)
- Lazy components in `{#if}` blocks need `await tick()` before `bind:this` ref is available
- `$effect` calling functions that modify tracked `$state` → use `untrack()` or avoid

## Key Files

- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — Main panel layout, attention bar (~line 786), sections, toggle logic
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — State/federal tab renderer (Phase 4a target)
- `packages/civicos-components/src/components/CivicAgendaView.svelte` — Agenda cards with draft workflow
- `packages/civicos-components/src/components/CivicInitiativeView.svelte` — Initiative section with `expandAndScrollTo()` export
- `packages/civicos-components/src/components/CivicIssueMap.svelte` — Leaflet map (ISSUE_COLORS must be before $state)
- `packages/civicos-components/src/components/CivicBudgetBreakdown.svelte` — Chart.js budget viz
- `packages/civicos-components/src/utils/civic-helpers.ts` — Shared utilities (urgency, calendar, focal meetings)

## Build & Test

```bash
cd apps/civicos-extension && npm run build   # Verify compilation
cd apps/civicos-extension && npm run dev     # Live reload for iteration
```

## Success Criteria

- [ ] State/federal tabs have attention bar for actionable items
- [ ] State/federal tabs use Official/Public section grouping
- [ ] Monochrome palette consistent across all tabs
- [ ] Topic tagging prototype on at least one entity type
- [ ] No Svelte 5 TDZ or reactivity errors
- [ ] Extension builds and works with live data

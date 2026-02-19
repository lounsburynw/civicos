# Recommended: Civic Web Components — Phase 9+ (Remaining Extractions)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phases 1-8 extracted **11 components** (4,653 lines) into `@civicos/components`, reducing SidePanel from 5,540 to **2,217 lines (-60%)**. The major content sections (agenda, decisions, initiatives, issue map, budget) are all extracted. What remains in SidePanel is smaller UI pieces and the orchestration shell.

### Current component inventory (4,653 lines, 11 components):
- `CivicVoiceButtons` (96) — Phase 1, leaf
- `CivicSynthesisBar` (58) — Phase 1, leaf
- `CivicAgendaItemCard` (159) — Phase 2, leaf
- `CivicDecisionCard` (629) — Phase 2, leaf
- `CivicInitiativeCard` (542) — Phase 3, leaf
- `CivicCommentThread` (489) — Phase 4, leaf
- `CivicAgendaView` (593) — Phase 5, smart view
- `CivicDecisionView` (287) — Phase 6, smart view
- `CivicInitiativeView` (1,224) — Phase 7, smart view
- `CivicIssueMap` (371) — Phase 8, visualization
- `CivicBudgetBreakdown` (205) — Phase 8, visualization

### SidePanel: 2,217 lines

## Recommended Task — Phase 9

The next session should decide between two directions:

### Option A: Continue extracting remaining SidePanel sections
Remaining inline sections (ordered by size/impact):
1. **Parent Jurisdiction Tab** (~130 lines, template lines ~1025-1160) — duplicates meetings/agenda/outcomes rendering from primary tab. Could extract a `CivicParentJurisdictionPanel` or create shared `CivicMeetingCard` to deduplicate.
2. **Data Provenance Panel** (~50 lines, template lines ~660-710) — read-only data display, self-contained
3. **Identity Chip** (~35 lines, template lines ~740-775) — Nostr npub display, unlock flow
4. **Connector Setup Banner** (~30 lines, template lines ~715-740) — MCP onboarding, stateless

### Option B: Pivot to second-surface proof or other P0 work
The 60% reduction may be sufficient for the `civic_web_components` item. Consider whether further extraction has diminishing returns vs. moving to other pilot items. Run `/start` to check priorities.

## Key Files

- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — 2,217 lines remaining
- `packages/civicos-components/src/index.ts` — component registry (11 components)
- `packages/civicos-components/src/components/` — all extracted components
- `packages/civicos-components/package.json` — deps include leaflet, chart.js as peer/dev

## Design Patterns (established in Phases 1-8)

1. **Leaf components** use `<svelte:options customElement="civic-*" />` for web component registration
2. **Smart view components** are regular Svelte components (no customElement) — they own internal state and compose leaf components
3. **Visualization components** expose `export async function load()` for lazy loading via `bind:this` refs
4. **Local type declarations** mirror `@civicos/client` types (avoids coupling)
5. **Props pattern:** `api`, `session`, `renderMarkdown` passed as dependency injection

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works
```

## Success Criteria

- [ ] Decide direction (continue extraction vs. pivot)
- [ ] If continuing: extract 1-2 remaining sections, both packages build clean
- [ ] If pivoting: mark civic_web_components status, set new P0

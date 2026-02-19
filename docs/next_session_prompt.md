# Recommended: Civic Web Components — Phase 6 (Decision View)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 5 introduced the first **smart view component** — `CivicAgendaView` (593 lines) — which owns comment thread, AI draft, and AI response state internally while receiving shared data as props. SidePanel dropped from 4,933 → 4,508 lines (-425). Phase 6 follows the same pattern for the **Decisions section**.

### Current component inventory (2,566 lines total, 7 components):
- `<civic-voice-buttons>` (96 lines) — Phase 1
- `<civic-synthesis-bar>` (58 lines) — Phase 1
- `<civic-agenda-item-card>` (159 lines) — Phase 2
- `<civic-decision-card>` (629 lines) — Phase 2
- `<civic-initiative-card>` (542 lines) — Phase 3
- `<civic-comment-thread>` (489 lines) — Phase 4
- **`CivicAgendaView`** (593 lines) — Phase 5 (smart view, no customElement)

### SidePanel: 4,508 lines

## Recommended Task — Phase 6

Extract the **Decisions section** from SidePanel into a `CivicDecisionView` smart component, following the same pattern as CivicAgendaView.

### What moves INTO the component:

**State (lines 49-53):**
- `expandedDecisions`, `decisionDetails`, `decisionLoading` — decision expansion & detail loading
- `expandedTestimony`, `expandedCouncil` — sub-section toggles

**Handler functions:**
- `toggleDecisionDetail()` (lines 396-420) — fetches decision details on expand
- `composeDecisionContext()` (lines 830-862) — AI context for decisions
- `composeTestimonySummary()` (lines 864-883) — AI context for testimony
- `composeSentimentBlock()` (lines 816-828) — shared, already duplicated in CivicAgendaView

**Template (lines 1817-1867, ~51 lines):**
- The `<!-- Recent Decisions -->` section with `{#each pulseData.recent_outcomes}`
- CivicDecisionCard usage with all its props

**CSS:** `.decision-card`, `.expanded-card` styles (check around line 3700+)

### What stays in SidePanel (passed as props):
- `voiceCounts`, `userStances`, `votingInProgress` (shared)
- `aiResponses`, `aiResponseLoading` (shared — or component can own its own)
- `identity`, `aiAvailable`, `activeProviderName` (shared)
- `session`, `api`, `renderMarkdown` (dependencies)
- Callbacks: `onvoice`, `onopenexternalai`, `ontoast`

### Architecture (same as Phase 5):
```
SidePanel → CivicDecisionView (owns detail/AI state, calls session)
  └→ CivicDecisionCard (leaf — already extracted in Phase 2)
```

## Key Files

- `apps/civicos-extension/src/side-panel/SidePanel.svelte:1817-1867` — decisions template section
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:396-420` — toggleDecisionDetail handler
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:830-883` — decision context composition
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:49-53` — decision state declarations
- `packages/civicos-components/src/components/CivicAgendaView.svelte` — reference pattern for smart component
- `packages/civicos-components/src/components/CivicDecisionCard.svelte` — leaf component to compose
- `packages/civicos-components/src/index.ts` — register new component

## Design Decisions (already resolved by Phase 5)

1. **Session/API access:** Pass as props (dependency injection)
2. **Where it lives:** `packages/civicos-components/` alongside other components
3. **AI responses:** Component owns its own `aiResponses`/`aiResponseLoading` maps (separate from parent's)
4. **No customElement:** Smart views are regular Svelte components (complex props)

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works
```

## Success Criteria

- [ ] `CivicDecisionView` renders the full decisions section
- [ ] Decision detail expansion works (toggle, lazy load)
- [ ] Testimony/council sub-section toggles work
- [ ] AI action buttons work (ask decision, ask testimony, external AI)
- [ ] Voice buttons work (delegated to parent via onvoice)
- [ ] SidePanel reduced by ~100+ lines (smaller extraction than Phase 5)
- [ ] Both packages build clean

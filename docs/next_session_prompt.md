# Recommended: Civic Web Components — Phase 3 (Initiative Card)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 2 is complete (commit `e909f8b`). The `@civicos/components` package now has 4 components:
- `<civic-voice-buttons>` — Support/Oppose/Watch (Phase 1)
- `<civic-synthesis-bar>` — stacked bar chart (Phase 1)
- `<civic-agenda-item-card>` — agenda item with tags, voice counts, voice buttons (Phase 2)
- `<civic-decision-card>` — expandable decision with testimony, council, related, voice, AI callbacks (Phase 2)

SidePanel is at **5349 lines** (down from ~5540). Both card components are integrated and both packages build clean. Standalone bundle is 120KB.

Key pattern: Components render card *content* (no `.card` wrapper) so the parent can embed them alongside siblings. All state management via callback props. AI response HTML passed pre-rendered.

## Recommended Task — Phase 3

Extract the initiative card from SidePanel into `<CivicInitiativeCard>`. The initiative section (lines 2273-2570, ~300 lines) includes:

### `<civic-initiative-card>` (recommended scope)
- Collapsed: topic pill, title, description, voice count, coordination icon, expand chevron, stats
- Expanded: coordination link, action list with commit/complete/withdraw buttons, progress bars
- Composes `<CivicVoiceButtons>` if voice support is added
- Source: SidePanel.svelte lines 2370-2564 (the `{#each initiatives as initiative}` block)

### What to EXCLUDE (keep in parent):
- Create initiative form (lines 2298-2358) — complex form with topic chips, validation, identity unlock
- Create action form (lines 2480-2555) — complex form with AI drafting, multiple field types
- Forms stay in parent due to heavy two-way binding and identity management

### Props
```typescript
{
  initiative: Initiative;
  expanded?: boolean;
  actions?: CivicAction[];
  actionsLoading?: boolean;
  actionProgress?: Map<string, CivicActionProgress>;
  committedActions?: Set<string>;
  completedActions?: Set<string>;
  actionInProgress?: Set<string>;
  isUnlocked?: boolean;
  showCreateAction?: boolean;
  onexpand?: () => void;
  oncommit?: (action: CivicAction) => void;
  oncomplete?: (action: CivicAction) => void;
  onwithdraw?: (action: CivicAction) => void;
  onshowcreateaction?: () => void;
  oncopytemplate?: (text: string) => void;
}
```

## Key Files

- `packages/civicos-components/src/components/CivicAgendaItemCard.svelte` — Phase 2 pattern to follow
- `packages/civicos-components/src/components/CivicDecisionCard.svelte` — Phase 2 pattern (complex)
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2370-2564` — initiative card to extract
- `packages/civicos-client/src/types.ts` — `Initiative`, `CivicAction`, `CivicActionProgress` types
- `packages/civicos-components/src/index.ts` — register new component
- `packages/civicos-components/vite.config.ts` — build config (customElement: true)

## Technical Notes

- Components render content without `.card` wrapper — parent provides `<div class="ini-card">`
- Use callback props for all events (same pattern as Phase 1/2)
- `actionTypeLabel()`, `deadlineClass()`, `deadlineLabel()` helper functions in SidePanel (~lines 1330-1370) — duplicate as pure functions in component
- Action template display has a "Copy" button — use `oncopytemplate` callback
- Initiative stats (`committed`, `completed` counts) can be computed internally from props

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works
```

## Success Criteria

- [ ] `<civic-initiative-card>` renders initiative with topic, title, description, voice count
- [ ] Expanded state shows actions with commit/complete/withdraw buttons and progress bars
- [ ] Component composes action list internally
- [ ] Extension SidePanel uses the initiative card component
- [ ] Create initiative/action forms remain in parent (NOT extracted)
- [ ] Both packages build clean
- [ ] Standalone demo updated with initiative card example

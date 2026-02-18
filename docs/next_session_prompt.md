# Recommended: Civic Web Components — Phase 2 (Card Components)

**Priority:** P0 (`civic_web_components`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 1 is complete (commit `9b888f4`). The `@civicos/components` package exists with:
- `<civic-voice-buttons>` — Support/Oppose/Watch with active state, callback props
- `<civic-synthesis-bar>` — stacked bar chart for comment distribution
- Dual consumption: Svelte components (extension) + Custom Elements (standalone bundle, 76KB)
- Extension SidePanel has 1 voice buttons + 1 synthesis bar replaced

Key design decision: **Callback props** (`onvoice`) instead of `$host()` dispatch. This works in both Svelte-to-Svelte and custom element modes. The `<svelte:options customElement="...">` directive is present but only activates in the standalone bundle build (which uses `customElement: true` in vite config). In the extension build, components compile as regular Svelte components (with expected warnings).

## Recommended Task — Phase 2

Build the medium-complexity card components that compose Phase 1 components:

### `<civic-agenda-item-card>`
- Agenda item card with title, description, eligibility tags, voice counts
- Composes `<CivicVoiceButtons>` and `<CivicSynthesisBar>` internally
- Props: `item` (PulseAgendaItem), `voiceCounts`, `userStance`, `commentCount`, `isUnlocked`, `aiAvailable`
- Events: `onvoice`, `ondraft`, `oncommenttoggle`, `onaskai`
- Source: SidePanel.svelte ~lines 2030-2200 (agenda item rendering block)

### `<civic-decision-card>`
- Expandable decision with outcome, vote tally, voice buttons
- Composes `<CivicVoiceButtons>` internally
- Props: `decision`, `expanded`, `voiceCount`, `userStance`, `detail`
- Events: `ontoggleexpand`, `onvoice`, `onaskai`, `onloaddetails`
- Source: SidePanel.svelte ~lines 2380-2520 (decision rendering block)

## Key Files

- `packages/civicos-components/` — the components package (Phase 1 done)
- `packages/civicos-components/src/components/CivicVoiceButtons.svelte` — voice buttons component
- `packages/civicos-components/src/components/CivicSynthesisBar.svelte` — synthesis bar component
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — monolith to decompose (~5,540 lines after Phase 1)
- `packages/civicos-client/src/types.ts` — `PulseAgendaItem`, `PulseOutcome`, `VoiceCounts`, etc.

## Technical Notes

- Import types from `@civicos/client` for prop typing
- Components should accept callback props for all events (same pattern as Phase 1)
- Card components compose Phase 1 components internally (not via custom element tags)
- Keep styles self-contained within each component's `<style>` block
- The extension imports components via `@civicos/components/src/components/...`
- No need for `$host()` — callback props handle all event communication

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile
cd apps/civicos-extension && npm run build         # Extension still works
```

## Success Criteria

- [ ] `<civic-agenda-item-card>` renders agenda items with voice buttons + synthesis bar
- [ ] `<civic-decision-card>` renders expandable decisions with voice buttons
- [ ] Both card components compose Phase 1 components internally
- [ ] Extension SidePanel uses at least one card component
- [ ] Both packages build clean
- [ ] Standalone demo updated with card examples

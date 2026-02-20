# Recommended: engagement_ladder_ux — Phase 3 (UX Polish & Information Architecture)

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 2 (Interactive Overlay) is complete: scroll-to-card, highlighted card state, cross-level attention bar, section pips. Phase 3 addresses user feedback on information architecture and visual polish. The attention bar now merges city/state/federal items but needs refinement — it shows "39 items need attention" with only 5 visible, lacks category tags, and needs scrollability. Several other UX issues were identified.

## What Was Done (Phase 2 — complete, uncommitted)

- Card IDs: `id="card-{item.id}"` on each agenda card (`CivicAgendaView.svelte:414`)
- Highlighted card: `.highlighted` CSS with white inset glow, 2s auto-clear
- Scroll-to-card: `scrollToCard()` in SidePanel.svelte expands section + smooth scroll + highlight
- Cross-level attention bar: merges city items + state hearings + federal comment periods + governor's desk, sorted by urgency
- Section pips: 6px white dots on Agenda Items header when actionable items exist
- Extension builds cleanly

## Phase 3 Tasks (from user feedback, in suggested priority order)

### 3a: Attention bar overhaul
The attention bar shows "39 items need attention" but only 5 are visible. Needs:
- **Rename title** to "Upcoming actionable items" (not "X items need attention")
- **Make scrollable** or paginated — show all items, not just `.slice(0, 5)`
- **Add category tags** — visual distinction for city vs state vs federal items (small pill/label)
- **Consider partitioning** — should this be per-tab (city/state/federal) or unified? User unsure; make a recommendation
- **Visual distinction** — the bar should look distinct from the rest of the feed (currently same card style)
- Current code: `SidePanel.svelte:783-821` (attention bar template), `:1326-1380` (CSS)

### 3b: Section headers — Official vs Public
Add two major section headers to organize content:
- **"Official"** (or "Government") — contains Meetings, Agenda Items, Recent Decisions
- **"Public"** — contains Community Initiatives
- This creates clearer information hierarchy

### 3c: Summary button rename + caching
The `<diamond> Claude ↗` button on agenda cards should:
- Rename to just **"Summary"** (remove Claude branding and external link icon)
- Cache the AI response so re-clicking collapses/expands (not re-fetches)
- Add a "Regenerate" option when cached summary is shown
- Current code: `CivicAgendaView.svelte:479-481` (Claude button), `:468-482` (AI action row)

### 3d: Remove "My Commitments" section
Remove for now — confusing and not useful yet. The CivicInitiativeView component currently includes commitments.
- Current code: `SidePanel.svelte:925-940` (CivicInitiativeView rendering)

### 3e: Initiative section visual parity
Initiatives should have same font size as official items and take up less wasted real estate. Remove "attested" badge/indicator — going forward, all push capabilities should be attested by default.
- See `CivicInitiativeView.svelte` for current styling

### 3f: Count badge visual refinement
Section item counts (e.g., "Agenda Items 12") are nice but could be slightly more visually distinct. Subtle improvement, not drastic.
- Current CSS: `SidePanel.svelte` `.count-badge` styles

### 3g: Section pip explanation (UX clarity)
The white dot next to "Agenda Items" (section pip) needs to either be self-explanatory or have a tooltip. User asked "what does the white dot represent?" — it indicates actionable items exist in that section.

### 3h: Identity unlock UX (longer-term)
The constant "unlock identity" requirement is foreign to users accustomed to centralized auth. Needs a longer-term solution (auto-unlock with session, biometric, etc.). Not Phase 3 scope but should be tracked.

## Key Files

- `apps/civicos-extension/src/side-panel/SidePanel.svelte:783-821` — Attention bar template
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:163-178` — scrollToCard function
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:925-940` — CivicInitiativeView (My Commitments)
- `packages/civicos-components/src/components/CivicAgendaView.svelte:468-482` — AI action row (Claude button)
- `packages/civicos-components/src/components/CivicInitiativeView.svelte` — Initiative section
- `apps/civicos-extension/tests/visual/mockup-overlay-highlight.html` — Design reference

## Build & Test

```bash
cd apps/civicos-extension && npm run build   # Verify compilation
cd apps/civicos-extension && npm run dev     # Live reload for iteration
```

## Success Criteria

- [ ] Attention bar renamed to "Upcoming actionable items" and is scrollable
- [ ] Items in attention bar have category tags (city/state/federal)
- [ ] Official vs Public section headers organize the feed
- [ ] Summary button (not "Claude") with cached/collapsible responses
- [ ] My Commitments section removed
- [ ] Initiatives match official item font size, no attested badge
- [ ] Extension builds and works with live data

# Community Initiatives UX Overhaul

**Priority:** P0 (`extension_phase2b_commitments`)
**Area:** edge_intelligence > browser_extension
**Date:** 2026-02-16

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Decision detail is now solid (AI summaries, speaker attribution, video links, upcoming/past distinction). The last major section to polish is **Community Initiatives** — the UI and content need to be tight and provide real utility. The user specifically called out: "the Start Initiative button looks like shit" and suggested using the Open WebUI CityPulse dashboard as a reference since its initiative UX looks good.

## Recommended Task

**Overhaul the Community Initiatives section in the browser extension side panel. Use the Open WebUI CityPulse initiative rendering as the design reference.**

### What Exists Now (Extension)

The initiatives section has functional but rough UI:
- Section with expand/collapse, initiative count badge
- "Start Initiative" button (small, ugly pill — user feedback)
- Create form: topic chips, title, description, coordination URL, identity unlock
- Initiative cards with title, topic tag, voice buttons, coordination link
- Expandable actions per initiative with commit/complete/withdraw
- Action progress bars
- "My Commitments" section (localStorage-backed)

### What the Open WebUI Version Does Better

The Open WebUI `CityPulse.svelte` has a cleaner initiative pattern:
- `+ New` button integrated into the section header (not a separate bar)
- `CreateInitiativeModal.svelte` — separate modal component (not inline form)
- Inline voice counts with thumbs up/down SVG icons next to title
- Coordination link icon visible in collapsed state
- Expandable detail with action cards, progress, commit buttons

## Key Files

**Extension (modify these):**
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:2441` — Community Initiatives section HTML
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:4609` — Initiative CSS block
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:1171` — `loadInitiatives()`, `toggleInitiativeDetail()`
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:85` — Initiative state variables
- `apps/civicos-extension/src/lib/types.ts:47` — `PulseOutcome`, `Initiative`, `CivicAction` types
- `apps/civicos-extension/src/lib/api.ts` — `getInitiatives`, `createInitiative`, `getCivicActions`

**Open WebUI (reference only — do not modify):**
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte:1425` — Initiative section rendering
- `~/projects/civicos-openwebui/src/lib/components/civic/CreateInitiativeModal.svelte` — Modal pattern

**Backend (if needed):**
- `apps/civicos-mcp/tools/handlers.py` — `list_initiatives`, `create_initiative` handlers

## Suggested Approach

1. **Read the Open WebUI CityPulse initiative section** (`CityPulse.svelte:1425-1700`) and `CreateInitiativeModal.svelte` to catalog the design patterns
2. **Redesign the "Start Initiative" button** — integrate into section header as `+ New` or similar. The current `ini-start-btn` is a tiny outlined pill that doesn't look like a real CTA
3. **Improve initiative cards** — add inline voice counts (support/oppose), coordination link icon, topic tag styling, better expand/collapse
4. **Polish the create form** — consider whether to keep inline or extract to a modal. Either way, improve visual hierarchy and spacing
5. **Review action cards** — progress bars, commit/complete/withdraw buttons, deadline indicators
6. **Verify end-to-end**: create initiative, add actions, commit, complete. Build: `cd apps/civicos-extension && npm run build && npx tsc --noEmit`

## Success Criteria

- [ ] "Start Initiative" button is visually integrated and looks intentional
- [ ] Initiative cards show voice counts, topic, coordination link inline
- [ ] Create form has good visual hierarchy (whether inline or modal)
- [ ] Action progress and commitment flow works end-to-end
- [ ] Extension builds clean (vite + tsc)
- [ ] User would rate the initiatives section as "tight and providing utility"

## Session Commits (2026-02-16)

This session made 4 commits to decision detail:
- `bae6811` — Speaker attribution (3-tier name resolution via roster)
- `25d39c4` — AI summaries, outcome descriptions, video URLs, better excerpts
- `6a7e3ce` — Strip markdown headers from summaries, deduplicate citations
- `cb80fff` — Distinguish upcoming agenda items from past decisions (blue badge, future-tense summaries)

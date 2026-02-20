# Recommended: Engagement Ladder UX — Radical Simplification

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

8 sessions have built the engagement ladder for the browser extension. Cross-level consistency is structurally complete (city/state/federal all have "Take Action" focal points, urgency badges, section hints, collapsed outcomes). But **the user tested the extension and gave critical feedback:**

1. **Meetings aren't actionable — agenda items are.** The city "Take Action" section surfaces upcoming meetings, but meetings are informational, not actionable. What's actionable: individual agenda items you can comment on, initiatives you can join, comment periods you can respond to. Rethink what qualifies as a "focal point."

2. **Information overload.** Despite progressive disclosure (collapsed outcomes, section hints), the dashboard is still overwhelming. The user said *"even my brain immediately shuts off from overload."* The next session needs a more radical approach to simplification — not just hiding sections, but fundamentally reducing default visual density.

## What's Built (Working)

- `CivicCityFocal.svelte` — Reusable "Take Action" component for city meetings (needs redesign)
- `CivicReadOnlyPulse.svelte` — State/federal rendering with focal points (working well for those levels)
- `CivicAgendaItemCard.svelte` — Now has `daysUntil` prop + urgency badge
- `civic-helpers.ts` — Shared utilities: `computeCityFocalMeetings()`, `urgencyClass()`, `meetingDaysUntil()`
- Visual testing harness: `npm run harness` at `localhost:5199` (city/state/federal)
- Playwright screenshots: `npx playwright screenshot --viewport-size="380,900" "http://localhost:5199/?level=city" screenshot.png`

## Two Problems to Solve

### Problem 1: What is "actionable"?

Current focal points by level:
- **City**: Upcoming meetings (wrong — meetings are informational, agenda items are actionable)
- **State**: Hearings + Governor's desk (good — these have clear actions: testify, call governor)
- **Federal**: Comment periods (great — "Submit Official Comment" is a clear CTA)

**Redesign idea**: City focal points should surface **agenda items with upcoming deadlines** where the user can comment or voice support/oppose. The meeting is context, not the action. Consider:
- Show agenda items that are `comment_eligible` or `stance_eligible` with their meeting's urgency
- Group by meeting if needed, but the card is the agenda item, not the meeting
- Initiatives with active participation could also be focal points

More broadly: define a **universal "actionability" signal** — an item is focal if the user can DO something (comment, vote, attend, sign) and there's a DEADLINE.

### Problem 2: Visual density

The extension shows too much at once. Potential radical simplifications:

- **"One thing" mode**: Show only the single most urgent actionable item as a hero card. Everything else behind a "See more" expansion.
- **Summary strip**: Replace the current multi-section layout with a single summary line per section ("2 meetings this week · 3 items to review · 1 decision made") that expands on tap.
- **Progressive revelation by engagement level**: New users see only focal points + a teaser count. Returning users see expanded sections. Power users see everything.
- **Remove visual chrome**: Less borders, less badges, less uppercase headers. Let whitespace and hierarchy do the work instead of colors and boxes.
- **Card consolidation**: Instead of separate Meetings → Agenda Items → Decisions sections, show a single **timeline** view: "This week in San Rafael" with items sorted by urgency.

**Design principle from the handoff**: *"Every element should either inform (what's happening), orient (why it matters to me), or activate (what I can do right now). If it does none of these, question whether it belongs on the default view."*

## Key Files

- `packages/civicos-components/src/components/CivicCityFocal.svelte` — City focal component (needs redesign for agenda items)
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte:1025-1110` — City focal rendering in harness
- `packages/civicos-components/src/components/CivicAgendaItemCard.svelte` — Agenda item card (has urgency badge)
- `packages/civicos-components/src/components/CivicAgendaView.svelte:400-425` — Where items render
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:738-860` — City tab rendering (wires components)
- `packages/civicos-components/src/utils/civic-helpers.ts` — Shared urgency utilities
- `apps/civicos-extension/tests/visual/mock-data.ts` — Mock data (adjust for new design)
- `apps/civicos-extension/tests/visual/HarnessApp.svelte` — Visual harness

## Suggested Approach

1. **Start with screenshots** — `npm run harness` + Playwright screenshots of current state
2. **Sketch the "one thing" layout** — What does the extension look like if it shows ONE hero actionable item + counts for everything else?
3. **Redefine city focal points** — Surface `comment_eligible` agenda items instead of meetings. The meeting is metadata on the agenda item card, not a standalone section.
4. **Implement minimal viable simplification** — Pick ONE density reduction approach and ship it
5. **Get user feedback** — The user is engaged and testing actively. Ship early, iterate.

## Success Criteria

- [ ] City "Take Action" surfaces actionable agenda items, not meetings
- [ ] Default view is noticeably simpler (user doesn't feel overloaded)
- [ ] All 3 tabs still feel like the same product at different scales
- [ ] `/visual-review` shows cleaner, calmer aesthetic
- [ ] Extension builds and works with live data

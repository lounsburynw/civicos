# Recommended: Browser Extension UX Audit — Cross-Level Consistency & Information Density

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The browser extension now has a **visual testing harness** with Playwright screenshots at all 3 jurisdiction levels (city, state, federal). This session should use `/visual-review` to take screenshots, simulate user reactions, audit cross-level consistency, and reduce information density without losing richness. The overarching goal: **CivicOS as the antidote to doomscrolling** — seamlessly guiding people from awareness to action.

Previous sessions (1-5) built the engagement ladder: focal points, comment threads, AI integration, voice buttons, and the visual harness. This session focuses on **polish and coherence**.

## Three Focus Areas

### 1. Simulated User Opinions

Use `/visual-review` to take fresh screenshots, then simulate 3-4 user personas reviewing them:

- **Busy parent** (2 minutes max, wants "what do I need to know?")
- **Engaged retiree** (reads everything, wants depth)
- **First-time user** (opened extension for the first time, no civic background)
- **Policy wonk** (wants data density, official links, bill numbers)

For each persona, read the screenshots and write a brief reaction: what works, what confuses, what they'd click first, what they'd skip.

### 2. Cross-Level Consistency

Current inconsistencies to address:

| Feature | City | State/Federal | Fix |
|---------|------|---------------|-----|
| "Take Action" focal group | Missing | Yellow-trimmed section at top | Add city focal points for items with upcoming deadlines |
| Urgency badges | None | Days-remaining countdown | Add urgency to city items near meeting dates |
| Section hints | None | "Your comment directly shapes..." | Add city hints |
| Outcome icons | Pass/fail icons on decisions | None on bill activity | Add to legislative outcomes |
| Calendar buttons | On meeting cards | Missing on hearing cards | Already in hearings — verify consistent |

### 3. Reducing Clutter (Without Losing Richness)

The extension packs a lot of info. Potential approaches:

- **Progressive disclosure**: Cards show headline + 1 key action; tap to expand for full detail
- **Visual hierarchy**: Primary actions large/colored; metadata smaller/subdued
- **Collapse-by-default**: Less-urgent sections collapsed, showing only header + count badge
- **Action-first ordering**: Items you can act on NOW sorted to top of each section
- **Summary strips**: Replace verbose card metadata with compact icon+label strips

Key question: which sections feel most cluttered? The state tab with legislation + focal points + topic grid + bill activity is the densest.

## Key Files

- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — State/federal pulse (focal points, legislation, outcomes) — 1634 lines
- `apps/civicos-extension/src/side-panel/SidePanel.svelte:601-951` — City pulse rendering, panel chrome, breadcrumb nav
- `packages/civicos-components/src/components/CivicMeetingCard.svelte` — City meeting cards
- `packages/civicos-components/src/components/CivicAgendaView.svelte` — City agenda items (has AI integration pattern)
- `packages/civicos-components/src/components/CivicDecisionView.svelte` — City decisions/outcomes
- `apps/civicos-extension/tests/visual/mock-data.ts` — Mock data for visual harness
- `apps/civicos-extension/tests/visual/HarnessApp.svelte` — Harness wrapper
- `apps/civicos-extension/playwright.config.ts` — Playwright config (380x900 viewport)

## Visual Testing Harness (New This Session)

```bash
cd apps/civicos-extension

# Manual inspection (opens in browser)
npm run harness
# → http://localhost:5199/?level=city
# → http://localhost:5199/?level=state
# → http://localhost:5199/?level=federal

# Generate baseline screenshots
npm run test:visual:update

# Compare against baselines
npm run test:visual
```

The `/visual-review` skill automates: take screenshots → Claude reads PNGs → UX review + baseline comparison.

## Suggested Session Plan

1. **Run `/visual-review`** — Get fresh screenshots and initial UX assessment
2. **Simulate user personas** — Read screenshots through 4 different lens, write reactions
3. **Prioritize fixes** — Based on persona feedback, pick the 3-5 highest-impact changes
4. **Implement consistency fixes** — Cross-level alignment (focal points, hints, badges)
5. **Implement density reduction** — Progressive disclosure or visual hierarchy (pick 1-2 approaches)
6. **Run `/visual-review` again** — Before/after comparison to verify improvements
7. **Update baselines** — `npm run test:visual:update` if changes are intentional

## Design Principle

> Every element should either **inform** (what's happening), **orient** (why it matters to me), or **activate** (what I can do right now). If it does none of these, question whether it belongs on the default view.

## Success Criteria

- [ ] Simulated user personas documented with specific, actionable feedback
- [ ] At least 2 cross-level consistency improvements implemented
- [ ] At least 1 information density reduction implemented
- [ ] All 3 tabs feel like the same product at different scales
- [ ] `/visual-review` shows no regressions — extension feels cleaner, not busier
- [ ] Before/after screenshots reviewed and baselines updated

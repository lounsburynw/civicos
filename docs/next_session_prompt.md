# Recommended: Browser Extension UX Alignment & Clarity

**Priority:** P0 (engagement_ladder_ux — refinement)
**Area:** frontend_refinement > browser_extension
**Date:** 2026-02-19

> This is a UX-focused session. The browser extension has grown feature-rich across city, state, and federal tabs — but inconsistencies between levels and information density need attention. The goal: make every level feel like the same product while keeping information rich but not cluttered.

## Guiding Principle

CivicOS exists as the **antidote to doomscrolling** — seamlessly fostering constructive action. Every design decision should ask: *does this help a resident move from awareness to action without feeling overwhelmed?*

## Three Focus Areas

### 1. Cross-Level Consistency ("Follow Suit")

City, state, and federal tabs should feel like the same product at different scales. Current inconsistencies:

| Feature | City | State/Federal | Action Needed |
|---------|------|---------------|---------------|
| **"Take Action" focal group** | Missing | Amber-trimmed section at top | Add city focal points (public hearing deadlines, comment periods on zoning/planning items) |
| **Calendar links** | Google Cal + .ics on meetings | Missing on hearings | Add calendar buttons to state/federal hearing cards |
| **Meeting cards** | Full cards (CivicMeetingCard) | 2-column topic grid | Harmonize — either elevate state topics to cards or create a shared "event card" |
| **Section hints** | None | "Your comment directly shapes..." | Add city hints ("Public comment is open — attend or email the clerk") |
| **Urgency badges** | None | Days-remaining countdown | Add urgency to city items approaching meeting dates |
| **Outcome icons** | Passed/Failed/Upcoming icons | None on bill activity | Add outcome icons to legislative bill status |
| **Official comment path** | "Submit Official Comment" (mailto clerk) | "Submit Official Comment" (regulations.gov) | Consistent now! Consider adding "Contact Representative" for state bills |

**Key files:**
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — State/federal pulse (focal points, legislation, outcomes)
- `packages/civicos-components/src/components/CivicAgendaView.svelte` — City agenda items
- `packages/civicos-components/src/components/CivicMeetingCard.svelte` — City meeting cards
- `packages/civicos-components/src/components/CivicDecisionView.svelte` — City decisions/outcomes

### 2. Information Density vs. Clarity ("Have Our Cake and Eat It Too")

The extension packs a lot of information, which is starting to feel cluttered. We need to maintain richness while creating visual breathing room and clear action hierarchy.

**Potential approaches (explore and recommend):**
- **Progressive disclosure**: Cards show headline + 1 key action by default; expand for full detail
- **Visual hierarchy**: Primary actions (Submit Comment, Vote) prominent; secondary info (topics, dates, metadata) more subdued
- **Grouping**: Cluster related cards under clear section headers with counts, collapsible by default for less-urgent sections
- **Whitespace**: Increase card padding/margins slightly — dense ≠ cluttered if spacing is right
- **Action-first ordering**: Within each section, sort by "actionability" (items you can act on NOW at top)
- **Summary strips**: Replace verbose card metadata with compact icon+label strips (date icon, location icon, committee icon)

**Key question**: Which sections feel most cluttered? Audit each tab with fresh eyes and propose specific changes.

**Reference files for current card density:**
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — Focal point cards (comment periods, hearings, governor's desk all show: title, meta row, topics, abstract, action links, voice buttons, comment thread)
- `packages/civicos-components/src/components/CivicAgendaView.svelte` — Agenda items (title, type badge, description, AI buttons, voice, comments, clerk email)

### 3. AI Integration for State/Federal Sections

City tab has mature AI integration (Ask AI, Draft with AI, Enrich with context, Summarize threads). State/federal tabs need equivalent treatment.

**What exists now:**
- Drag-to-AI context composers for all focal point types (comment periods, hearings, governor's desk)
- Comment thread "Summarize" on focal point cards
- Voice buttons on all focal point and legislation cards

**What's missing:**
- No "Ask AI" button on individual state/federal cards (city agenda items have this)
- No "Draft with AI" for composing official comments on federal rules
- No "What does this bill mean for me?" AI prompt on hearing/governor's desk cards
- No plain-language bill summary generation

**Suggested AI integration points:**
1. **"Explain This" button** on legislation cards — generates plain-language summary of bill impact
2. **"Draft Comment" button** on federal comment period cards — AI drafts a public comment based on user's stance
3. **"Prepare for Hearing" button** on hearing cards — generates talking points, key questions, background
4. **"What Does This Mean?" tooltip** on governor's desk — explains bill impact in plain language
5. **Consistent "Ask AI" placement** across all card types at all levels

**Key files:**
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — AI provider integration, askQuestion handler
- `packages/civicos-components/src/components/CivicAgendaView.svelte:350-389` — City AI integration pattern to mirror

## Architecture Notes

- All components are Svelte 5 with `$state()` reactivity
- AI integration goes through `session.askQuestion()` → configured AI provider (Claude, OpenAI, etc.)
- Voice/comments go through relay at `{domain}/relay/coordination/*`
- State/federal data comes from `_legislation_pulse()` handler in `apps/civicos-mcp/tools/handlers.py`
- City data comes from `city_pulse` tool handler

## Suggested Session Plan

1. **Audit** (15 min): Open extension, screenshot each tab, annotate inconsistencies
2. **Harmonize** (30 min): Add missing features to bring levels into alignment (calendar on hearings, focal points for city, section hints)
3. **Declutter** (30 min): Pick 2-3 highest-impact density improvements, implement
4. **AI** (30 min): Add AI buttons to state/federal cards, mirroring city pattern
5. **Polish** (15 min): Test all three tabs end-to-end, verify consistency

## Success Criteria

- [ ] All three tabs feel like the same product at different scales
- [ ] "Take Action" focal points visible at city level (if applicable city data exists)
- [ ] Calendar buttons on state/federal hearings
- [ ] At least 1 density improvement implemented (progressive disclosure or visual hierarchy)
- [ ] "Ask AI" or equivalent on state/federal legislation cards
- [ ] No visual clutter regression — extension feels cleaner, not busier

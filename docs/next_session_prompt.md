# Recommended: Settings UX Redesign — iOS-Style Flat Grouped List

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-03-05

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 19 redesigned the Settings page (Options.svelte) through several iterations with user feedback. Current state: merged AI settings into Advanced, added field descriptions, softened aesthetic. But the user says it's "not quite there yet" — the card-based layout still feels disjointed. We collaboratively designed an iOS-style flat grouped list approach that the user approved. This needs to be implemented.

## The Design

Drop card containers entirely. Use a flat scrollable page with group headers (like iOS Settings):

```
Settings

YOUR CITY
  [San Rafael (city)        v]    <- auto-saves on change
  Also includes Marin County, California, Federal
  ✓ Verified resident

YOUR PROFILE                      <- only if hub connected
  [Name                      ]    <- "Shown when you comment"
  [Neighborhood              ]    <- "We'll prioritize issues near you"
  [housing] [transportation] [+]  <- pill-based interests
  [Save]

──────────────────────────────
AI & Privacy                 >    <- expandable row
Account & Security           >    <- expandable row (identity, recovery, delete)
```

**Key principles:**
1. Top section = immediate, useful, zero-friction (city + profile)
2. Bottom rows = "I know what I'm doing" power-user territory
3. No card borders competing for attention — just subtle group headers
4. Every field has a brief description of what it does for the app experience
5. Target audience is tech-illiterate; power users are edge cases

## What Session 19 Already Shipped
- Pill-based interest editing (type + Enter, × to remove, backspace to delete last)
- Merged AI settings into Advanced collapsible section
- Auto-save jurisdiction on change (no Save Jurisdiction button)
- Field descriptions ("Determines what meetings, decisions, and issues you see")
- Softer aesthetic (rgba borders, transitions, smaller typography)
- Removed confusing "npx civicos-personal-mcp" hint (profile just hides when hub unavailable)

## Key File
- `apps/civicos-extension/src/options/Options.svelte` — the entire settings page
  - Template starts at ~line 542, styles at ~line 924
  - All logic (AI provider, Ollama, identity, attestation) is already working — this is purely a template/CSS restructure

## Suggested Approach
1. Read current Options.svelte to understand all existing state/logic
2. Replace card-based template with flat grouped sections
3. Top groups (YOUR CITY, YOUR PROFILE) render directly — no container cards
4. Bottom: "AI & Privacy" and "Account & Security" as clickable rows that expand inline
5. Remove `.card` backgrounds, use spacing and dividers instead
6. Keep all existing save/test/load functions untouched — template-only change

## Style Reference
- Group headers: small, muted, uppercase (like iOS section headers)
- Fields: full-width, minimal borders, generous padding
- Expandable rows: single line with chevron, expand content below
- Divider between essentials and advanced: subtle horizontal rule
- Dark theme but softer — rgba transparency, no hard #hex borders

## Tests
```bash
cd apps/civicos-extension && npm run build       # Must build cleanly
cd apps/civicos-extension && npx tsc --noEmit    # Pre-existing passkey errors OK
```

## Success Criteria
- [ ] Settings page fits on ~1 screen before scrolling (city + profile visible, rest collapsed)
- [ ] No card containers — flat layout with group headers
- [ ] Every editable field has a 1-line description of what it does
- [ ] AI settings and account/identity behind expandable rows
- [ ] User can pick city and edit interests without scrolling
- [ ] Build passes

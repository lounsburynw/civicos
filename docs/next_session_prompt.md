# Recommended: Turnkey City Deployment

**Priority:** P0 (`turnkey_city_deployment`)
**Area:** city_onboarding > scaling
**Date:** 2026-02-18

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The `civic_web_components` item is now **ready** — 15 components + shared utils in `@civicos/components` (5,370 lines). SidePanel reduced from 5,540 to 1,231 lines (78% reduction). The component library is production-ready and enables building new surfaces by composing `<civic-*>` elements.

The next P0 is `turnkey_city_deployment` — making the unified config system actually reduce new city deployment effort. Currently config handles ~20% of the work; extractors, HUD mapping, and elections are ~80%.

## Key Files

- `pilot.json` — turnkey_city_deployment item (line ~1556)
- `config/registry.json` — unified jurisdiction config
- `packages/civicos-extraction/` — platform-specific extractors
- `docs/critical/CITY_ONBOARDING_GUIDE.md` — current onboarding docs

## What Changed This Session (Web Components Phase 9)

- Extracted 4 new components: CivicMeetingCard, CivicProvenancePanel, CivicIdentityChip, CivicReadOnlyPulse
- Created shared utils module: `@civicos/components/src/utils/civic-helpers.ts`
- CivicDecisionCard now imports from shared utils (deduplication)
- Removed ~1,000 lines of dead/moved CSS from SidePanel
- Cleaned up all unused imports

## Tests

```bash
cd packages/civicos-components && npm run build   # Components compile (15 components)
cd apps/civicos-extension && npm run build         # Extension still works
```

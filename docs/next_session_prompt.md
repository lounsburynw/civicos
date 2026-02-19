# Recommended: Turnkey City Deployment

**Priority:** P0 (turnkey_city_deployment)
**Area:** city_onboarding > scaling
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The engagement ladder UX is complete (sessions 1-4). Pilot progress is at 94% (462/488 items ready, 23 remaining). The next priority is making city deployment turnkey — currently config is ~20% of work while extractors, HUD mapping, and elections are ~80%.

### Recent Commits
- `458e4db` feat: Complete engagement ladder UX with comment threads, data enrichment, and bug fix
- `058f00a` chore: Mark engagement_ladder_ux ready, promote turnkey_city_deployment to P0

## Item Details

Make unified config system actually reduce new city deployment effort. Currently config is ~20% of work; extractors, HUD mapping, and elections are ~80%.

### Current State (from Session 545 audit)
**Generalizable** (70-75%):
- Core API & Storage (5/5)
- Pipeline stages (5/5)
- Legistar/CivicClerk clients (5/5)
- Federal data sources (4/5)
- Municipal code (4.5/5)
- ProudCity (4/5)

**Manual work required per city**:
- Election data — completely jurisdiction-specific (1/5)
- HUD grantee mapping — requires research per city
- School board meetings — platform varies
- Transcription roster data — per jurisdiction

### Improvements Needed
1. Auto-discover HUD grantee from FAC/HUD API
2. Onboarding wizard (detect platform → generate config → validate)
3. Config validation schema with helpful errors
4. Generic election scraper framework (template-based)

### Effort Estimates
- Berkeley MVP (meetings + federal + municipal code): 3-5 days
- Berkeley full parity (includes elections): 2-3 weeks

## Key Files
- `docs/critical/CITY_DEPLOYMENT_AUDIT.md` — Detailed audit reference
- `docs/critical/CITY_ONBOARDING_GUIDE.md` — Current onboarding docs
- Configuration files for San Rafael (reference implementation)

## Suggested Approach
1. Read the deployment audit doc for full context
2. Assess what can be automated vs what requires per-city customization
3. Focus on the onboarding wizard or config validation — highest ROI for reducing deployment friction
4. Consider: is this the right priority, or should we tackle one of the 22 remaining P3 items instead?

## Remaining Pilot Items
- 23 items not_ready (1 P0, 22 P3)
- All P3 items are lower priority and can be deferred

# Recommended: Onboarding E2E Validation + /onboard Skill

**Priority:** P0 is `turnkey_city_deployment`
**Area:** city_onboarding > scaling
**Date:** 2026-03-06

> This is recommended context from Session 28. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 28 built the `civicos-onboard` CLI (detect platform → generate YAML config → validate) and marked turnkey_city_deployment as ready. But we only tested config generation — never proved the full pipeline produces a working city. The item has been reverted to not_ready until E2E validation passes.

## Recommended Task

### Step 1: E2E Proof — Berkeley Dry-Run (~30 min)

1. Run `civicos-onboard "Berkeley" --url https://berkeleyca.gov --state CA --county Alameda --dry-run`
2. Compare generated config against existing `data/jurisdictions/city-berkeley.yaml` — gaps reveal what the wizard misses
3. Run `civicos-deploy city-berkeley --dry-run` to verify the deploy pipeline accepts the config
4. Document what works vs what still needs manual intervention

### Step 2: Create `/onboard` Skill

Wrap the multi-step onboarding in a Claude Code skill that:
- Asks clarifying questions (city name, URL, state, county)
- Runs platform detection interactively
- Generates config and explains TODOs
- Runs validation and guides user through fixes
- Tests connectivity to detected platform

Create as `.claude/commands/onboard.md`.

### Step 3: Mark Ready (if E2E passes)

Update `pilot.json` turnkey_city_deployment status to "ready" once the pipeline is proven.

## Key Files
- `packages/civicos/src/civicos/cli.py:1503-1700` — onboard_main() and _generate_config_yaml()
- `packages/civicos/src/civicos/cli.py:348-372` — generalized ingest_live() (config-driven, was hardcoded)
- `data/jurisdictions/city-berkeley.yaml` — existing Berkeley config (reference for comparison)
- `packages/civicos-extraction/src/civicos_extraction/platform_detection.py` — platform detection
- `docs/user_guides/CITY_ONBOARDING_GUIDE.md` — onboarding docs (has Quick Start section)

## Success Criteria
- [ ] Berkeley dry-run produces valid config matching existing template
- [ ] `civicos-deploy city-berkeley --dry-run` succeeds
- [ ] `/onboard` skill created and tested
- [ ] pilot.json `turnkey_city_deployment` marked ready with E2E proof

## Also Pending (P3)
- `feedback_channel` — Add feedback mechanism for pilot users (simple, ~30 min)

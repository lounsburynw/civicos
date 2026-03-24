# Recommended: Issue Provider Detection

**Priority:** P0 (issue_provider_detection)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We just completed `issue_provider_dispatch` (done). `fetch_issues()` now reads `issue_source` from `ExtractionConfig` and dispatches to the correct 311 client. `SUPPORTED_ISSUE_SOURCES` registry exists. SeeClickFix is default.

**Issue provider detection is next** because onboarding a new city currently requires manually knowing which 311 provider they use. Auto-detection probes known APIs by city/county name and writes the result to the extraction config. This completes the turnkey onboarding story for issues.

## What Was Done This Session

1. `ExtractionConfig.issue_source` — new optional field (default None → "seeclickfix")
2. `SUPPORTED_ISSUE_SOURCES` registry in `clients/__init__.py`
3. `fetch_issues()` — config-driven dispatch with parameterized checkpoint keys
4. `onboard.py` — issue stages gated by `SUPPORTED_ISSUE_SOURCES`
5. `san-rafael.json` — explicit `"issue_source": "seeclickfix"`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/onboard.py` | Where detection logic should live (discovery phase) |
| `packages/civicos-extraction/src/civicos_extraction/clients/seeclickfix.py` | Existing SeeClickFix client — probe `get_issues()` with small page |
| `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:118` | `SUPPORTED_ISSUE_SOURCES` registry |
| `packages/civicos-extraction/src/civicos_extraction/clients/base.py:194` | `ExtractionConfig.issue_source` field |
| `data/extraction/san-rafael.json` | Example config with `issue_source` set |

## Suggested Approach

1. **Read `onboard.py` discovery phase** — understand how it currently detects meeting sources
2. **Add `detect_issue_source()` function** — probe known 311 APIs by city name:
   - SeeClickFix: `GET /api/v2/issues?place_url={city_name}&per_page=1` — if returns issues, SeeClickFix is active
   - Future: FixItMarin, QAlert probes
3. **Wire into onboard discovery** — call during the discovery phase, write `issue_source` to extraction config JSON
4. **Make re-runnable** — detection can update an existing config's `issue_source` if provider changes
5. **Test with San Rafael** (SeeClickFix) and a city without SeeClickFix presence

## Important Context

- See memory `memory/project_311_providers.md` — Marin County switching to FixItMarin
- SeeClickFix API is public, no auth needed — safe to probe
- Detection should be best-effort: if no provider found, leave `issue_source` as None (will default to seeclickfix in fetch, but won't crash)

## Success Criteria

- [ ] `detect_issue_source()` probes SeeClickFix API by city name
- [ ] Integrated into `onboard.py` discovery phase
- [ ] Writes detected `issue_source` to extraction config JSON
- [ ] Re-runnable (can update existing config)
- [ ] Graceful fallback when no provider detected
- [ ] Smoke tests pass

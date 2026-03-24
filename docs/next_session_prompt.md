# Recommended: Issue Provider Dispatch

**Priority:** P0 (issue_provider_dispatch)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We just completed `html_agenda_extraction` (done). The chunk extraction pipeline now handles HTML agendas as a first-class path — pre-extracts HTML chunks from already-downloaded content and uses them as fallback when PDF strategies fail.

**Issue provider dispatch is next** because `fetch_issues()` is hardcoded to SeeClickFix. Marin County is switching to FixItMarin (Mar 2026), and other cities use QAlert, PublicStuff, etc. The pattern should match `fetch_meetings()` which already has source-type dispatch via `SUPPORTED_MEETING_SOURCES`.

## What Was Done This Session

1. `extract_chunks_from_html_agenda()` — added `html_content` param to skip redundant re-download
2. `extract_chunks_from_meeting()` — pre-extract HTML chunks upfront in degenerate case
3. Fixed dead-end bug at second `is_valid_pdf` check — falls back to HTML instead of error
4. 5 new tests, all 15 HTML chunk + 20 smoke tests pass

## Key Files

| File | Line | Purpose |
|------|------|---------|
| `scripts/modal_ingest.py:3204` | `fetch_issues()` | Hardcoded to SeeClickFix — this is what needs refactoring |
| `scripts/modal_ingest.py:3232` | `from ...seeclickfix_client import SeeClickFixClient` | Hardcoded import |
| `scripts/modal_ingest.py:2822` | `fetch_meetings()` | Model dispatch pattern to follow |
| `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:115` | `SUPPORTED_MEETING_SOURCES` | Registry pattern to replicate for issues |
| `packages/civicos-extraction/src/civicos_extraction/clients/seeclickfix.py` | SeeClickFix client | Existing provider |
| `data/extraction/` | Per-city extraction configs | Where `issue_source` field should live |

## Suggested Approach

1. **Read `fetch_issues()` at `modal_ingest.py:3204`** — understand the SeeClickFix-specific logic
2. **Read `fetch_meetings()` at `modal_ingest.py:2822`** — see how it dispatches on `source_type` using `elif` branches and `SUPPORTED_MEETING_SOURCES`
3. **Add `SUPPORTED_ISSUE_SOURCES` registry** in `clients/__init__.py` (next to `SUPPORTED_MEETING_SOURCES` at line 115)
4. **Refactor `fetch_issues()`** to read `issue_source` from extraction config and dispatch to the appropriate client
5. **Keep SeeClickFix as default** — backward-compatible for cities without explicit `issue_source`
6. **Test with San Rafael** — ensure existing SeeClickFix issues still work

## Important Context

- See memory file `memory/project_311_providers.md` — cities change 311 providers. Don't hardcode SeeClickFix.
- `scripts/modal_ingest.py:3278` already normalizes `issue["provider"]` — the field exists, just needs dispatch
- `scripts/modal_ingest.py:3308-3316` — checkpoint keys are hardcoded to "seeclickfix", need parameterizing

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `SUPPORTED_ISSUE_SOURCES` registry created in `clients/__init__.py`
- [ ] `fetch_issues()` dispatches on `issue_source` from extraction config
- [ ] SeeClickFix remains default (backward-compatible)
- [ ] Checkpoint keys parameterized (not hardcoded "seeclickfix")
- [ ] San Rafael issue count unchanged after refactor
- [ ] Smoke tests pass

## Turnkey Onboarding Roadmap (remaining)

After issue_provider_dispatch:
- P2: `onboard_quality_gates`, `issue_provider_detection`, `onboard_end_to_end_test`
- P3: `onboard_transcript_auto`, `onboard_deploy_integration`, `onboard_batch_mode`

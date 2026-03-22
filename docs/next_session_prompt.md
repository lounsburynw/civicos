# Recommended: Generalize RefreshRunner

**Priority:** P0 (configurable_refresh_policies)
**Area:** operator_readiness
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Roadmap decision (2026-03-22): Reordered priorities to focus on data pipeline scalability before token issuance. RefreshRunner currently only handles municipal code. All other corpora (meetings, issues, legislation, transcripts) have bespoke ingestion logic in `modal_ingest.py`. The YAML `refresh:` blocks in jurisdiction configs define policies that nothing reads except for municipal_code.

The goal: make RefreshRunner the single refresh path for all corpus types, so adding a new jurisdiction means writing a YAML config — not custom ingestion code.

## What Exists Today

- `RefreshRunner` class with `refresh_municipal_code()` — works, tested, 41 tests
- `RefreshableCorpus` protocol — `check_for_update()`, `get_fingerprint()`, `stream_sections()`
- `RefreshPolicy` + `load_refresh_policies()` — reads YAML, parses interval/strategy
- Content hash diffing with safety valves (>50% modified or >20% removed = abort)
- `MunicipalCodeCorpus` implements `RefreshableCorpus` (Municode fingerprint gate)
- YAML `refresh:` blocks in `data/jurisdictions/*.yaml` (san-rafael has meetings: 1d, issues: 1d, legislation: 7d, municipal_code: 90d)

## What Needs to Be Done (Phase 1)

Extend `RefreshableCorpus` to non-legal corpora and add a generic `refresh_corpus()` method:

1. **Meetings** — ProudCity/Granicus clients need `check_for_update()` (compare latest meeting date vs stored) and `get_fingerprint()` (latest meeting datetime as string)
2. **Issues** — SeeClickFix client needs `check_for_update()` (compare latest issue date vs stored) and `get_fingerprint()` (latest issue created_at)
3. **Legislation** — LegiScan/CA Legislature clients need the same pattern (latest bill update date)
4. **Generic dispatch** — Add `RefreshRunner.refresh_corpus(jurisdiction_id, corpus_type)` that looks up the right provider by corpus type, calls check_for_update, fetches if changed, diffs, upserts
5. **Tests** — Extend `test_refresh.py` with tests for each new corpus type

## Key Files

- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py:66` — `RefreshableCorpus` protocol
- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py:242` — `RefreshRunner` class
- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py:283` — `refresh_municipal_code()` (pattern to follow)
- `packages/civicos/src/civicos/_internal/legal/corpus/municipal.py:561` — `MunicipalCodeCorpus.check_for_update()` (reference implementation)
- `scripts/modal_ingest.py:4202` — `scheduled_low_velocity_refresh()` (bespoke logic to replace)
- `scripts/modal_ingest.py:4513` — `scheduled_high_velocity_refresh()` (bespoke logic to replace)
- `data/jurisdictions/city-san-rafael.yaml:155` — refresh policy block (already has meetings/issues/legislation)
- `packages/civicos/tests/test_refresh.py` — existing 41 tests

## Suggested Approach

1. Start by reading `refresh.py` in full — understand the RefreshRunner pattern
2. Read the bespoke ingestion logic for meetings in `modal_ingest.py` — find `fetch_meetings`
3. Implement `RefreshableCorpus` on the meeting extraction client (ProudCity first)
4. Add `RefreshRunner.refresh_meetings()` following the `refresh_municipal_code()` pattern
5. Test with san-rafael meetings
6. Repeat for issues, then legislation
7. Add generic `refresh_corpus()` dispatch method

## Tests to Run

```bash
# Existing refresh tests
pytest packages/civicos/tests/test_refresh.py -q --override-ini="addopts="

# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `RefreshableCorpus` implemented on ProudCity meeting client
- [ ] `RefreshableCorpus` implemented on SeeClickFix issue client
- [ ] `RefreshableCorpus` implemented on legislation clients (LegiScan or CA Legislature)
- [ ] `RefreshRunner.refresh_corpus()` generic dispatch method works
- [ ] Existing 41 refresh tests still pass
- [ ] New tests for meeting/issue/legislation refresh

## Roadmap Context

This is Phase 1 of the agreed scalability roadmap:
- **Phase 1 (P0):** Generalize RefreshRunner <-- YOU ARE HERE
- **Phase 2 (P1):** Wire cron orchestrators to use RefreshRunner (`cron_refresh_wiring`)
- **Phase 3 (P2):** Onboarding YAML generation
- **Phase 4 (P2):** Token issuance track
- **Phase 5 (P3):** Turnkey state onboarding (post-launch)

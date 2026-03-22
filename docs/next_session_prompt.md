# Recommended: Wire Cron Orchestrators to RefreshRunner

**Priority:** P0 (cron_refresh_wiring)
**Area:** operator_readiness
**Date:** 2026-03-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Phase 1 of the scalability roadmap is complete: `CorpusProvider` protocol + 3 providers + `RefreshRunner.refresh_corpus()`. This session (Phase 2) wires the cron orchestrators in `modal_ingest.py` to use the new infrastructure instead of bespoke per-corpus ingestion logic.

The goal: `scheduled_high_velocity_refresh()` and `scheduled_low_velocity_refresh()` in `modal_ingest.py` should instantiate providers and call `runner.refresh_corpus(provider)` instead of calling `fetch_meetings()`, `fetch_issues()`, `sync_legislation()` directly.

## What Exists Now (Phase 1 Output)

- `CorpusProvider` protocol with `fetch_and_store(storage) -> int` — provider owns data + storage dispatch
- `MeetingCorpusProvider` — wraps ProudCity/Granicus, calls `storage.store_meetings()`
- `IssueCorpusProvider` — wraps SeeClickFix, paginates + normalizes, calls `storage.store_issues()`
- `LegislationCorpusProvider` — wraps LegiScan master list, batch stores via `storage.store_legislation()`
- `RefreshRunner.refresh_corpus(provider)` — scheduling, change detection, metadata, re-embedding
- `source_name` threaded through metadata lookups for correct interval checks
- `index_from_storage` (not `index_corpus`) — fixed to match VectorBackend protocol
- 79 tests passing, validated against real Postgres + APIs

## What Needs to Be Done (Phase 2)

1. **`scheduled_high_velocity_refresh()`** (~line 4513): Currently calls `fetch_meetings()` and `fetch_issues()` per jurisdiction. Replace with:
   - Create `MeetingCorpusProvider` + `IssueCorpusProvider` per jurisdiction
   - Call `runner.refresh_corpus(provider)` for each
   - Preserve the reactive downstream logic (extract_chunks, extract_agenda_items only if meetings changed)

2. **`scheduled_low_velocity_refresh()`** (~line 4202): Currently calls `sync_legislation()`. Replace with:
   - Create `LegislationCorpusProvider` per state
   - Call `runner.refresh_corpus(provider)`
   - Preserve text population step (`fetch_legislation`) and other low-velocity stages

3. **Preserve the reactive pipeline**: The bespoke `fetch_meetings()` returns `has_new_material`, `new_meeting_ids`, etc. via `MeetingStoreResult`. The provider's `fetch_and_store()` returns just `int`. The downstream stages (chunks, agenda items, transcripts) need change signals. Options:
   - Have the cron check `MeetingStoreResult` details via a separate call after refresh
   - Or keep reactive stages as-is, only replacing the fetch+store portion

## Key Files

- `scripts/modal_ingest.py:4513` — `scheduled_high_velocity_refresh()` (daily cron)
- `scripts/modal_ingest.py:4202` — `scheduled_low_velocity_refresh()` (weekly cron)
- `scripts/modal_ingest.py:2799` — `fetch_meetings()` (bespoke, to be replaced)
- `scripts/modal_ingest.py:3147` — `fetch_issues()` (bespoke, to be replaced)
- `scripts/modal_ingest.py:593` — `sync_legislation()` (bespoke, to be replaced)
- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py:564` — `refresh_corpus()` method
- `packages/civicos/src/civicos/_internal/legal/corpus/providers.py` — 3 provider implementations
- `.github/workflows/cron-high-velocity-refresh.yml` — GH Actions trigger
- `.github/workflows/cron-low-velocity-refresh.yml` — GH Actions trigger

## Suggested Approach

1. Read `scheduled_high_velocity_refresh()` in full — understand the reactive pipeline
2. Refactor meetings portion: instantiate `MeetingCorpusProvider`, call `runner.refresh_corpus()`
3. Handle the reactive downstream (chunks/agenda_items need `has_new_material` signal)
4. Refactor issues portion similarly
5. Test the high-velocity flow with `modal run scripts/modal_ingest.py::scheduled_high_velocity_refresh --dry-run` or similar
6. Refactor `scheduled_low_velocity_refresh()` for legislation
7. Do NOT delete the old `fetch_meetings()`, `fetch_issues()`, `sync_legislation()` functions yet — they're still used by `modal run` CLI entrypoints

## Tests to Run

```bash
# Refresh tests (must stay green)
pytest packages/civicos/tests/test_refresh.py -q --override-ini="addopts="

# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `scheduled_high_velocity_refresh()` uses `RefreshRunner.refresh_corpus()` for meetings + issues
- [ ] `scheduled_low_velocity_refresh()` uses `RefreshRunner.refresh_corpus()` for legislation
- [ ] Reactive downstream stages (chunks, agenda_items) still triggered correctly
- [ ] YAML interval policies respected (meetings: 1d, issues: 1d, legislation: 7d)
- [ ] All 79 refresh tests pass
- [ ] No regression in scheduled cron behavior

## Roadmap Context

- **Phase 1 (DONE):** Generalize RefreshRunner — CorpusProvider protocol + 3 providers
- **Phase 2 (P0):** Wire cron orchestrators <-- YOU ARE HERE
- **Phase 3 (P1):** Deploy remaining servers + fix Cloudflare proxies
- **Phase 4 (P2):** Onboarding YAML generation
- **Phase 5 (P2):** Token issuance track
- **Phase 6 (P3):** Turnkey state onboarding

# Recommended: Fix Decisions Adapter NoneType Crash (`decisions_adapter_crashes_on_empty_vectors`)

**Priority:** P0
**Area:** federation_testbed > decisions_adapter_crashes_on_empty_vectors
**Date:** 2026-04-07

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

`fix_tiburon_empty` (the previous P0) is **done** as of 2026-04-07 evening (commit `fb989a99`). Re-ran `/onboard city-tiburon`, persisted 9 meetings / 8 decisions / 933 chunks / 846 muni sections / 13 agenda items / 2 issues, committed the previously-untracked configs. `validate_mass_ingest.py` now reports **15 PASS / 0 FAIL** (was 14P/1F).

While running that validation pass, the `Corpus decisions error: 'NoneType' object has no attribute 'get_city_state'` error fired **twice** — once during `city-tiburon` and once during `city-sausalito`. This is the silent failure already filed as `decisions_adapter_crashes_on_empty_vectors` (was P2). It's still active even after tiburon got 8 decisions, so the trigger is NOT "no decisions at all" — it's some other empty-vector path. Picked as the next P0 because it's small, contained, and eliminates a real silent failure that's been observed in production-shaped runs three times in the past 24 hours.

## The smoking gun

`packages/civicos-services/src/civicos_services/query/adapters.py:57` — `DecisionsAdapter.search()` calls `civicos.history.search_decisions(state_manager=None, ...)`. When the explicit `vector_backend` returns no results and the per-corpus auto-detect ALSO returns empty for decisions, `search_decisions` falls through to `packages/civicos/src/civicos/history.py:1207`:

```python
city_state = state_manager.get_city_state(jurisdiction)
```

`state_manager` is `None`. AttributeError. The verbs layer at `packages/civicos-services/src/civicos_services/query/verbs.py` catches it per-corpus and emits `Corpus decisions error: ...` at WARN, but does NOT propagate to the response — the user just sees fewer results with no indication anything failed.

## Recommended Task

Make `search_decisions` defensive so the `state_manager=None` path returns `[]` instead of crashing. Add a regression test. Also raise the per-corpus exception log level in `verbs.py` from WARN to ERROR for `AttributeError` (not for expected timeout/connection errors) so silent NoneType derefs are visible in production logs.

## Key Files

- `packages/civicos-services/src/civicos_services/query/adapters.py:57` — `DecisionsAdapter.search()` is the caller passing `state_manager=None`
- `packages/civicos/src/civicos/history.py:1207` — the `state_manager.get_city_state(jurisdiction)` deref that crashes
- `packages/civicos-services/src/civicos_services/query/verbs.py` — per-corpus exception handler that swallows the error at WARN
- `scripts/validate_mass_ingest.py` — **the regression repro**: every run of this script will currently hit the bug for 1+ jurisdictions. Use it to verify the fix.
- `launch.json` lines 1258-1270 — `decisions_adapter_crashes_on_empty_vectors` full notes
- Memory: `feedback_data_status_gaps.md` — DataStatus underreports patterns
- Memory: `project_mass_ingest_april_2026.md` — context for which jurisdictions trigger this

## Suggested Approach

1. **Reproduce first**: `python3 scripts/validate_mass_ingest.py` and grep for `Corpus decisions error` in stderr. Confirm it still fires (it did this morning, twice).
2. **Read `history.py:1207` in context** (a few hundred lines around it) to understand what `state_manager.get_city_state(jurisdiction)` was supposed to return and what the legacy keyword fallback does. The fix should be the smaller of:
   - **Option A** (preferred per the launch.json notes): defensive guard at the entry point — if `state_manager is None` and the explicit vector path returned nothing, return `[]` immediately without falling through to the legacy keyword fallback.
   - **Option B**: make `DecisionsAdapter` pass a real `state_manager` (requires more plumbing).
3. **Write a unit test** at `packages/civicos/tests/test_history_search_decisions.py` (create if missing) that exercises `search_decisions(state_manager=None, jurisdiction='city-tiburon', query='housing', vector_backend=<empty backend>)` and asserts it returns `[]` without raising.
4. **Bump verbs.py log level**: in the per-corpus exception swallowing logic, log at ERROR (with stack trace) when the exception type is `AttributeError` or `TypeError`; keep WARN for expected `TimeoutError`/`ConnectionError`.
5. **Re-run validation**: `python3 scripts/validate_mass_ingest.py` should produce zero `Corpus decisions error` lines on stderr.

## Tests to Run

```bash
# Smoke
source civicos-env/bin/activate && pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Targeted: the new regression test (after creating it)
pytest packages/civicos/tests/test_history_search_decisions.py -q --override-ini="addopts="

# End-to-end repro / verification
python3 scripts/validate_mass_ingest.py 2>&1 | grep -i "corpus decisions error" || echo "FIXED"
```

## Success Criteria

- [ ] `validate_mass_ingest.py` produces zero `Corpus decisions error` lines on a full pass
- [ ] New regression test in `packages/civicos/tests/` covers the `state_manager=None` + empty-vector path
- [ ] `verbs.py` per-corpus exception logging escalates `AttributeError`/`TypeError` to ERROR with stack trace
- [ ] `decisions_adapter_crashes_on_empty_vectors` marked done in launch.json
- [ ] New P0 promoted before next `/nextsesh`. Reasonable candidates:
  - `complete_alameda_ingest_or_scope` (P1, federation_testbed) — the only other concrete launch blocker among the mass-ingest 15
  - `upcoming_verb_ignores_jurisdiction` (P2, federation_testbed) — small fix, real cross-jurisdiction routing bug
  - File a new item for **modal Phase 2.5 sample timeout** (see Followups below)

## Caveats

- **Don't fix the wrong layer.** The temptation is to fix `DecisionsAdapter` to pass a real `state_manager`. That's bigger and risks breaking other adapter paths. The smaller fix is at `history.search_decisions` — make it tolerate `state_manager=None` gracefully, which matches existing patterns elsewhere in `history.py`.
- **The verbs.py log level bump is one line.** Don't refactor the whole exception handling while you're in there.
- **Don't expand scope.** Other silent-failure patterns exist (the upcoming verb's missing jurisdiction filter, the Postgres NUL-byte chunk drop) but they're filed separately. Fix this one.

## Followups Surfaced This Session (NOT this P0)

These are real bugs but should NOT be conflated with this P0:

1. **Modal Phase 2.5 sample function-call expiry** — the tiburon ingest crashed at the very end of the sample run with `GRPCError: FAILED_PRECONDITION: Function call has expired`. The pipeline persisted most data before the crash but Phase 3 (full 365-day backfill) never dispatched. Worth filing as a new item: multi-stage Modal pipelines that take ~10+ minutes wall-time hit Modal's function call expiration. Likely fix: spawn each stage as a separate Modal call rather than chaining inside one function.
2. **Postgres NUL-byte chunk drop** — during tiburon chunk extraction, 270 chunks from one meeting hit `cloud storage failed: A string literal cannot contain NUL (0x00) characters` and were "kept local file only" — silent partial data loss. Worth filing.
3. **Of 9 tiburon meetings**, 4 had agenda URLs that redirect to a Google Docs viewer the chunk extractor cannot follow (cancelled/older meetings). Known Granicus pattern, not actionable.

## Working Tree Notes

- This session committed `fb989a99` ("Session: Close fix_tiburon_empty (P0) — tiburon non-empty, 15P/0F") with only `data/jurisdictions/city-tiburon.yaml`, `data/extraction/city-tiburon.json`, `launch.json`, and `claude-progress.txt`.
- All other modified/untracked files in the working tree (sandbox sqlites, civicos-env binaries, ambient data file edits) are pre-existing and unrelated to this session. The previous handoff (now overwritten) noted the same.
- `/tmp/mass_ingest_validation.json` is the latest validation report (15P/0F).
- `/tmp/tiburon_onboard.log` is the modal ingest run log from this session — useful if you want to see exactly where the GRPC expiry hit.

## Open PRs

None as of session end.

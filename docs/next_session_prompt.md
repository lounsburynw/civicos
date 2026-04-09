# Recommended: Fix upcoming verb cross-jurisdiction routing (`upcoming_verb_ignores_jurisdiction`)

**Priority:** P0
**Area:** federation_testbed > upcoming_verb_ignores_jurisdiction
**Date:** 2026-04-09

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

`decisions_adapter_crashes_on_empty_vectors` (the previous P0) is **done** as of 2026-04-09 (commit `8f01b1fb`). Added a defensive guard in `search_decisions()` and missing error logging in the cross-jurisdiction run_corpus handler. `validate_mass_ingest.py` now produces zero corpus errors across all 15 jurisdictions.

This P0 is a **silent data correctness bug**: `execute_upcoming()` returns the wrong jurisdiction's events during cross-jurisdiction fan-out. When a single CivicOS instance is reused, all jurisdictions get San Rafael's meetings. Discovered during mass-ingest validation on 2026-04-07 — tiburon, county-marin, county-alameda, and city-belvedere all returned the same "Bicycle & Pedestrian Advisory Committee" result.

## The bug

`packages/civicos-services/src/civicos_services/query/verbs.py:641` — `execute_upcoming()` calls `civic.whats_next(days=request.days)` three times (lines 641, 663, 682) for meetings, hearings, and comment_periods event types. `whats_next()` at `packages/civicos/src/civicos/civicos.py:682` queries `self._data_source.get_meetings(jurisdiction_id=self.jurisdiction, ...)` — using the CivicOS instance's jurisdiction, NOT the `jid` from the request.

The `jid` variable (line 632: `jid = request.jurisdiction or jurisdiction`) is correctly computed but only used for building `ref` strings in the response. The actual data query ignores it.

## Key Files

- `packages/civicos-services/src/civicos_services/query/verbs.py:624-745` — `execute_upcoming()` function, three calls to `civic.whats_next()` at lines 641, 663, 682
- `packages/civicos/src/civicos/civicos.py:650-718` — `whats_next()` method, uses `self.jurisdiction` at line 682
- `packages/civicos-services/src/civicos_services/query/verbs.py:530-600` — `_execute_single_jurisdiction_search()` is the search equivalent — worth checking how it handles jurisdiction correctly for comparison
- `scripts/validate_mass_ingest.py` — validation script (currently confirms search works but doesn't validate upcoming)
- `launch.json` lines 1247-1257 — item full notes

## Suggested Approach

**Preferred: Option A — call storage directly in `execute_upcoming`, bypass `whats_next()`.**

The CLAUDE.md adapter-refactor guidance says "v2 adapters should call storage/vector backends directly instead of CivicOS methods." `execute_upcoming()` already receives `civic` but should query `civic.storage.get_meetings(jurisdiction_id=jid, since=..., until=...)` directly. This avoids modifying the CivicOS class API and follows the refactor direction.

1. **Read `execute_upcoming` carefully** — understand the three event types (meetings, hearings, comment_periods) and how each uses `civic.whats_next()` results
2. **Replace the three `civic.whats_next(days=request.days)` calls** with direct storage calls: `civic.storage.get_meetings(jurisdiction_id=jid, since=start_of_today, until=cutoff)`. Mirror the date window logic from `whats_next()` (lines 670-677 of civicos.py). Share the result across all three event types to avoid triple-querying.
3. **Convert raw meeting dicts to Meeting objects** — copy the conversion logic from `whats_next()` (lines 696-718) or extract it into a helper. The current code expects `Meeting` objects with `.agenda_items`, `.id`, `.title`, `.date`, `.body`, `.location`.
4. **Write a regression test** — construct one CivicOS instance for jurisdiction A, call `execute_upcoming(request, civic, jid_b)`, and verify results reflect jid_b's meetings, not jid_a's. Use real Postgres data if available.
5. **Re-run validation** — extend `validate_mass_ingest.py` to test the upcoming verb per-jurisdiction (optional, but valuable).

**Alternative: Option B — add `jurisdiction` kwarg to `whats_next()`.**

Simpler change but goes against the adapter-refactor direction. Only if Option A proves too complex.

## Tests to Run

```bash
# Smoke
source civicos-env/bin/activate && pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Targeted: new regression test (after creating it)
pytest packages/civicos/tests/test_upcoming_jurisdiction.py -q --override-ini="addopts="

# Previous P0 regression (should still pass)
pytest packages/civicos/tests/test_search_decisions_none_state_manager.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `execute_upcoming(request, civic_san_rafael, "city-tiburon")` returns tiburon meetings, not san-rafael meetings
- [ ] All three event types (meetings, hearings, comment_periods) use `jid` not `civic.jurisdiction`
- [ ] Regression test covers the cross-jurisdiction case
- [ ] `upcoming_verb_ignores_jurisdiction` marked done in launch.json
- [ ] New P0 promoted. Candidates:
  - `complete_alameda_ingest_or_scope` (P1, federation_testbed) — alameda has decisions but no transcripts/chunks
  - `index_county_marin_decision_vectors` (P1-ish, federation_testbed) — 105 decisions but 0 decision vectors

## Caveats

- **Don't modify `CivicOS.whats_next()` unless Option A is infeasible.** The adapter-refactor direction is to bypass CivicOS methods from v2 adapters.
- **The `comment_periods` branch also queries `civic.storage.get_open_comment_periods()` (line 699-702).** That's federal data, not jurisdiction-specific — leave it as-is.
- **Three calls to `civic.whats_next()` can be consolidated into one storage query** — meetings/hearings/comment_periods all filter the same meeting list differently. Query once, filter three ways.

## Working Tree Notes

- This session committed `8f01b1fb` with history.py fix, verbs.py logging fix, new regression test, launch.json, and progress.
- Untracked sandbox .sqlite files, civicos-env binaries, and data extraction files are pre-existing and unrelated.

## Open PRs

None as of session end.

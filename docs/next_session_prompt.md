# Recommended: Add Real Source Item ID (`add_real_source_item_id`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-11

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed `free_tier_rate_limiting` (commit `63bda209`). OAuth sessions now have per-session rate limiting (50/day + 10/min burst). The launch checklist is nearly complete — only 6 items remain (all P2-P3 except this P0). This item strengthens decision ID stability by threading real platform source IDs through the extraction pipeline, replacing the current "synthetic-D" approach that derives IDs from LLM-extracted fields.

## Recommended Task

Add `source_item_id: Optional[str]` to `HighStakesDecision` dataclass and thread real platform-internal IDs (Granicus event item ID, Legistar MatterId, BoardDocs item ID) through to `compute_stable_decision_id()`. When present, the hash function should include `source_item_id` in the key, providing ground-truth dedup instead of relying on synthetic fields (item_type, outcome, budget_amount).

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/processing/retrospective_analyzer.py:37-77` — `HighStakesDecision` dataclass. Add `source_item_id: Optional[str] = None` field here.
- `packages/civicos/src/civicos/storage/integrity.py:129-159` — `compute_stable_decision_id()`. Add `source_item_id` parameter; include in hash when present.
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` — Granicus client. Events have internal IDs; thread through to decisions.
- `packages/civicos-extraction/src/civicos_extraction/clients/legistar.py:399-408` — Legistar client already uses `EventId` for meeting IDs. Items have `MatterId` available from the API.
- `packages/civicos-extraction/src/civicos_extraction/cli/decisions.py` — CLI entry point that calls retrospective_analyzer; passes results to storage.
- `packages/civicos/src/civicos/storage/postgres_backend.py` — `store_decisions()` calls `compute_stable_decision_id()`.
- `packages/civicos/tests/test_integrity.py` — Existing tests for `compute_stable_decision_id()`.
- `packages/civicos/tests/test_integration_decision_dedup.py` — Integration tests for dedup behavior.

## Suggested Approach

1. **Add field to dataclass** — `source_item_id: Optional[str] = None` on `HighStakesDecision`. Both copies (civicos-extraction and civicos-services) must be updated.

2. **Update hash function** — In `compute_stable_decision_id()`, add `source_item_id: Optional[str] = None` parameter. When non-None, include it in the hash key. This means decisions with a source ID get a stronger key, while existing decisions without one continue using synthetic-D.

3. **Thread through Granicus client** — Granicus events API returns items with internal IDs. Parse these and populate `source_item_id` when available.

4. **Thread through Legistar client** — Legistar items have `MatterId`. The client already parses `EventId` for meetings (line 399). Do the same for agenda items.

5. **Thread through storage** — `store_decisions()` in postgres_backend.py calls `compute_stable_decision_id()`. Pass `source_item_id` through.

6. **Test** — Update `test_integrity.py` with cases for: source_item_id present (stronger key), source_item_id absent (backwards compatible), same decision with/without source_item_id (should produce different IDs — this is expected, not a bug).

## Tests to Run

```bash
# Integrity tests (direct target)
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_integrity.py -v --override-ini="addopts="

# Decision dedup integration
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_integration_decision_dedup.py -v --override-ini="addopts="

# Smoke tests
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `HighStakesDecision` has `source_item_id: Optional[str] = None` field
- [ ] `compute_stable_decision_id()` accepts and uses `source_item_id` when present
- [ ] Granicus client populates `source_item_id` from platform event item IDs
- [ ] Legistar client populates `source_item_id` from `MatterId`
- [ ] Backwards compatible: existing decisions without source_item_id still produce same IDs
- [ ] Tests cover both with/without source_item_id paths
- [ ] A new P0 assigned before session end

## Pre-existing test failures (NOT regressions)

- `test_coordination_tools.py`: 5 failures (broadcast_voice schema drift, registry count drift)
- `test_initiative_tools.py::test_connection_error_handled`: relay is reachable, premise broken

These are separate cleanup items — 6 pre-existing failures total, stable across sessions.

## Open PRs

None.

## Not in scope

- BoardDocs client (no existing client in codebase — only add if Granicus/Legistar are straightforward)
- Migrating existing decisions to use source_item_id (that's a separate data migration)
- CivicClerk client (lower priority platform)

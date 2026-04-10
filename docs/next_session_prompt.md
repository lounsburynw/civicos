# Recommended: Add real source item ID (`add_real_source_item_id`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-10

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

This session fixed the SF county parent hierarchy issue. The next P0 is threading real source-platform item IDs through the extraction pipeline for more robust decision dedup.

## Problem

Decision IDs currently use a synthetic-D approach: `compute_stable_decision_id()` hashes fields like `item_ref`, `title`, `item_type`, `outcome`, `budget_amount`. This works in practice but is theoretically fragile — if two genuinely-distinct decisions in one meeting share all those fields, they'd collide. A real platform-native ID (Granicus clip ID, Legistar matter ID, BoardDocs item ID) would be ground-truth.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/processing/retrospective_analyzer.py` — `HighStakesDecision` dataclass, `compute_stable_decision_id()`
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` — Granicus extraction client
- `packages/civicos-extraction/src/civicos_extraction/clients/legistar.py` — Legistar extraction client
- `packages/civicos/src/civicos/storage/integrity.py` — Storage-level dedup

## Suggested Approach

1. **Add `source_item_id: Optional[str]` to `HighStakesDecision`** dataclass
2. **Update Granicus client** to populate source_item_id from clip/event ID
3. **Update Legistar client** to populate source_item_id from matter ID
4. **Update `compute_stable_decision_id()`** to include source_item_id in hash when present
5. **Test** with existing data — ensure no regressions in dedup behavior

## Design Notes

- The source_item_id should be Optional — LLM-extracted decisions from PDF text won't have one
- When present, it provides stronger uniqueness than synthetic fields
- Backwards compatible: existing decisions without source_item_id keep their current hash

## Success Criteria

- [ ] `source_item_id` field added to `HighStakesDecision`
- [ ] Granicus client populates it
- [ ] Legistar client populates it
- [ ] Hash function uses it when present
- [ ] Existing decision IDs unchanged when source_item_id is None
- [ ] New P0 promoted

## Open PRs

None.

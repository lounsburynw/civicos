# Recommended: automated_decision_extraction

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-05

> This is recommended context from Session 471. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 471 fixed the blocking issue: `store_meetings()` now uses proper upsert pattern, and `get_meetings()` returns all 46 meetings. Decision extraction can now query historical meetings.

## The Task

Add decision extraction to the automated Modal pipeline. Currently:
- `batch_extract_decisions.py` is a **manual** script
- 44 decisions exist (Oct-Dec 2025) from manual runs
- Need to automate this in the weekly Modal schedule

## Current State

```
Decisions extracted:     44 (from manual runs)
Minutes PDFs available:  ~20+ meetings have minutes
Decision extraction:     NOT automated
```

## Key Files

- `scripts/batch_extract_decisions.py` - Manual extraction script
- `scripts/modal_ingest.py` - Automated pipeline (needs decision extraction added)
- `packages/civic-extraction/src/civic_extraction/cli/decisions.py` - CLI for extraction

## Implementation Approach

1. **Understand existing extraction**
   - Read `batch_extract_decisions.py` to understand the flow
   - Check how minutes PDFs are downloaded and processed

2. **Add to Modal pipeline**
   - Add decision extraction to `scheduled_weekly_refresh` (not daily - minutes lag)
   - Pattern: `get_meetings()` → filter those with minutes_url → extract decisions → `store_decisions()`

3. **Testing**
   - Run locally first: `modal run scripts/modal_ingest.py --decisions`
   - Verify new decisions are stored

## Notes

- Minutes PDFs lag meetings by days/weeks, so this should be weekly not daily
- The extraction uses regex + optional LLM QA for quality
- `store_decisions()` already has proper upsert pattern (fixed in Session 390)

## Success Criteria

- [ ] Decision extraction added to Modal `scheduled_weekly_refresh`
- [ ] Can run `modal run scripts/modal_ingest.py --decisions` successfully
- [ ] pilot.json updated: `automated_decision_extraction` → ready

## Scope Boundaries

**This session:** Add decision extraction to Modal pipeline only.

**Not in scope:**
- `automated_chunk_extraction` - already coded, just blocked (can test now)
- LLM QA improvements
- New decision types

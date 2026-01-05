# Recommended: automated_decision_extraction

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-04

> This is recommended context from Session 470. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 470 completed automated chunk extraction. The pipeline now runs:
1. `fetch_meetings()` - Scrape meetings from ProudCity
2. `fetch_issues()` - Fetch issues from SeeClickFix
3. `extract_chunks()` - **NEW** Download PDFs, extract text chunks (incremental)
4. `index_vectors()` - Index meetings, issues, chunks to pgvector

Decision extraction is still manual (`batch_extract_decisions.py`). This session should add it to the Modal pipeline.

## Recommended Task

Add decision extraction to `scheduled_low_velocity_refresh` in `scripts/modal_ingest.py`.

**Why weekly (not daily)?** Minutes PDFs lag meetings by weeks. Daily extraction would find nothing new most days.

### Key Files

- `scripts/modal_ingest.py:788-854` - `scheduled_low_velocity_refresh()` function
- `scripts/batch_extract_decisions.py` - Current manual extraction script
- `packages/civic-extraction/src/civic_extraction/cli/decisions.py` - Decision extraction CLI (if exists)
- `packages/civic/src/civic/storage/postgres_backend.py` - `store_decisions()` method

## Suggested Approach

1. **Review existing decision extraction:**
   ```bash
   grep -rn "extract.*decision\|store_decisions" packages/ scripts/
   ```

2. **Understand the extraction flow:**
   - Decisions are extracted from meeting **minutes** PDFs (not agendas)
   - Minutes are published weeks after meetings
   - Extraction uses regex patterns + optional LLM QA

3. **Create new Modal function `extract_decisions()`:**
   - Similar pattern to `extract_chunks()`
   - Read meetings from Postgres that have minutes_url
   - Check which meetings haven't had decisions extracted
   - Parse minutes PDFs, extract decisions
   - Store via `store_decisions()`

4. **Add to `scheduled_low_velocity_refresh()`:**
   - Runs weekly (Sunday 3 AM UTC)
   - Good fit since minutes don't change frequently

## Implementation Notes

- Decision extraction may not have a CLI wrapper like chunks
- May need to import functions directly from extraction package
- Consider: 44 decisions exist (Oct-Dec 2025), ~2 months of coverage

## Tests to Run

```bash
# Check existing decisions
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v -k "decision"

# Full test suite before commit
pytest packages/civic/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] New `extract_decisions()` function in modal_ingest.py
- [ ] Function added to `scheduled_low_velocity_refresh()`
- [ ] Incremental extraction (skip meetings with existing decisions)
- [ ] Error handling (failures don't crash pipeline)
- [ ] pilot.json updated: `automated_decision_extraction` -> ready

## Scope Boundaries

**This session:** Implement decision extraction automation only.

**Future items (don't tackle yet):**
- `vector_sql_sync_verification` - Issues mismatch investigation
- `temporal_versioning_review` - Meeting versioning design

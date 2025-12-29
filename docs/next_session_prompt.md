# Recommended: etl_cost_provenance

**Priority:** P0
**Area:** monitoring_observability > cost_tracking
**Date:** 2025-12-29

> This is recommended context from Session 396. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Before running the $46 transcription job (18 remaining videos × $2.40), we need centralized cost tracking. Currently costs are logged per-run in checkpoint files but not aggregated or queryable.

This unblocks `transcripts_e2e_cloud` (P1) which is ready to run once we can track the spend.

## Recommended Task

Implement minimal ETL cost provenance:
1. Add `etl_costs` table to Postgres
2. Update `transcribe.py` to insert cost records after each run
3. Verify with a test transcription

## Schema

```sql
CREATE TABLE etl_costs (
    id SERIAL PRIMARY KEY,
    pipeline VARCHAR(50) NOT NULL,        -- 'transcribe', 'research', etc.
    jurisdiction_id VARCHAR(100) NOT NULL,
    run_date TIMESTAMP DEFAULT NOW(),
    items_processed INTEGER,
    cost_usd DECIMAL(10,4),
    duration_seconds INTEGER,
    notes TEXT
);
```

## Key Files

- `packages/civic-extraction/src/civic_extraction/cli/transcribe.py:68` - TranscribeCheckpoint has `total_cost_usd`
- `packages/civic/src/civic/storage/postgres_backend.py` - Add `store_etl_cost()` method
- `packages/civic-extraction/src/civic_extraction/research/base.py:132` - Research also tracks `total_cost`

## Suggested Approach

1. **Add table to Postgres schema** (via migration or direct SQL)
2. **Add `store_etl_cost()` to PostgresBackend**
3. **Update transcribe.py** to call `store_etl_cost()` after successful runs
4. **Test with limit 1** to verify cost is recorded
5. **Run full transcription** (~$46, now tracked)

## Success Criteria

- [ ] `etl_costs` table exists in Postgres
- [ ] Test transcription (limit 1) creates cost record
- [ ] Query shows cost: `SELECT * FROM etl_costs`
- [ ] Mark `etl_cost_provenance` as ready
- [ ] Then run `transcripts_e2e_cloud` (now P1)

## Notes

- Keep it minimal - dashboard and alerts (P2) can come later
- Also update `research.py` if time permits (Perplexity costs)
- The $46 transcription spend will be the first tracked cost

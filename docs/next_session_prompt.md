# Recommended: etl_cost_tracking_all_pipelines

**Priority:** P0
**Area:** monitoring_observability > cost_tracking
**Date:** 2025-12-29

> This is recommended context from Session 397. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 397 implemented cost tracking for `transcribe.py`. Before running more E2E ingestion (especially the $46 transcription job), we need cost tracking on ALL cost-generating pipelines.

## Task

Add `store_etl_cost()` calls to remaining cost-generating pipelines:

| Pipeline | File | Cost Source | Status |
|----------|------|-------------|--------|
| transcribe | `cli/transcribe.py:758-779` | AssemblyAI | ✅ Done |
| research | `research/base.py` | Perplexity API (`total_cost`) | ❌ TODO |
| decisions | `cli/decisions.py` | LLM API costs | ❌ TODO |
| vectors | `cli/vectors.py` | Embedding API (if paid) | ❌ TODO |

## Pattern to Follow

From `transcribe.py:758-779`:

```python
# At end of run, after successful processing:
if items_processed > 0 and cloud_mode:
    try:
        from civic.storage import get_storage_backend
        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            cost_id = backend.store_etl_cost(
                pipeline="pipeline_name",  # e.g., "research", "decisions"
                jurisdiction_id=jurisdiction_id,
                items_processed=items_processed,
                cost_usd=total_cost,
                duration_seconds=duration_seconds,  # Optional
                notes=f"Description of what was processed",
            )
            logger.info(f"ETL cost recorded (id={cost_id}): ${total_cost:.2f}")
    except Exception as e:
        logger.warning(f"Failed to record ETL cost: {e}")
```

## Key Files to Modify

1. **research/base.py** - Look for `total_cost` tracking, add `store_etl_cost()` after research completes
2. **cli/decisions.py** - Check if LLM costs are tracked, add if applicable
3. **cli/vectors.py** - Check if using paid embedding API, add if applicable

## Success Criteria

- [ ] `research.py` records Perplexity costs to etl_costs table
- [ ] `decisions.py` records LLM costs (if applicable)
- [ ] `vectors.py` records embedding costs (if using paid API)
- [ ] Mark `etl_cost_tracking_all_pipelines` as ready
- [ ] Then proceed with `transcripts_e2e_cloud` (P1)

## Verification

```python
from civic.storage import get_storage_backend
backend = get_storage_backend()

# After running a research job:
backend.get_etl_costs(pipeline="research")
# Should show cost records

# Summary across all pipelines:
backend.get_etl_cost_summary()
```

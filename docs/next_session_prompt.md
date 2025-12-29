# Recommended: transcripts_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 397. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

ETL cost tracking is now in place (Session 397). Ready to run the $46 transcription job.

Current state:
- 19 audio files in R2 blob storage
- 1/19 transcripts complete in Postgres
- 18 remaining × $2.40 avg = ~$43 estimated cost

## Recommended Task

Run the full transcription job:

```bash
civic-extract transcribe --jurisdiction city-san-rafael --cloud
```

This will:
1. Read audio files from R2
2. Transcribe via AssemblyAI with speaker diarization
3. Store transcripts in Postgres
4. **Automatically record costs in etl_costs table**

## Verification

After completion:
```python
from civic.storage import get_storage_backend
backend = get_storage_backend()

# Check transcript count
backend.get_transcript_count("city-san-rafael")  # Should be 19

# Check recorded costs
backend.get_etl_cost_summary(pipeline="transcribe")
# {'total_cost_usd': ~46.0, 'total_items': 18, 'run_count': N}
```

## Success Criteria

- [ ] All 19 transcripts in Postgres
- [ ] Costs recorded in etl_costs table
- [ ] Mark `transcripts_e2e_cloud` as ready in pilot.json

---

## Future Work: Extend Cost Tracking to Other Pipelines

Session 397 added cost tracking infrastructure. Pattern to follow for other pipelines:

### Integration Pattern (from transcribe.py:758-779)

```python
# At end of run, after successful processing:
if items_processed > 0 and cloud_mode:
    try:
        from civic.storage import get_storage_backend
        backend = get_storage_backend()
        if backend.backend_type == "postgres":
            cost_id = backend.store_etl_cost(
                pipeline="your_pipeline_name",  # e.g., "research", "embed"
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

### Pipelines Needing Integration

| Pipeline | File | Cost Source |
|----------|------|-------------|
| research | `research/base.py:132` | Perplexity API (`total_cost`) |
| embed | Future | Embedding API costs |

### Query Methods Available

```python
backend.store_etl_cost(...)      # Record a cost
backend.get_etl_costs(...)       # List recent costs
backend.get_etl_cost_summary(...) # Aggregate totals
```

# Recommended: cost_dashboard

**Priority:** P0
**Area:** monitoring_observability > cost_tracking
**Date:** 2025-12-31

> This is recommended context from Session 423. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 423 completed `automated_incremental_pipeline` - added scheduled Modal functions for automated data refresh with incremental detection for high-velocity corpora (meetings, issues). The `etl_costs` table already tracks cost data for all pipelines; now we need a dashboard to visualize it.

## Why This Matters

Foundation-funded project requires strict cost control (<$7/month operational). The `etl_costs` table logs every pipeline run with cost data, but there's no way to visualize cumulative costs by pipeline, time period, or jurisdiction. This is critical for:
- Monitoring burn rate before pilot
- Identifying cost spikes early
- Budget planning for multi-city scaling

## Recommended Task

Build an admin dashboard endpoint or CLI command that aggregates ETL costs from the `etl_costs` table and displays daily/weekly/monthly breakdown by pipeline type.

## Key Files

| File | Line | Purpose |
|------|------|---------|
| `packages/civic/src/civic/storage/postgres_backend.py` | 2713 | `store_etl_cost()` - how costs are stored |
| `packages/civic/src/civic/storage/postgres_backend.py` | 2766 | `get_etl_costs()` - query cost records |
| `packages/civic/src/civic/storage/postgres_backend.py` | 2822 | `get_etl_cost_summary()` - aggregation helper |
| `packages/civic-services/src/civic_services/api/` | - | API server (if adding endpoint) |

## Existing Schema

```sql
CREATE TABLE etl_costs (
    id SERIAL PRIMARY KEY,
    pipeline TEXT NOT NULL,           -- 'transcribe', 'decisions', 'vectors', etc.
    jurisdiction_id TEXT NOT NULL,
    run_date TIMESTAMPTZ NOT NULL,
    items_processed INTEGER,
    cost_usd DECIMAL(10, 6),
    duration_seconds INTEGER,
    notes TEXT
);
```

## Suggested Approach

1. **Query existing data** to understand current cost patterns:
   ```python
   backend.get_etl_cost_summary(days=30)  # Already implemented
   ```

2. **Create dashboard endpoint or CLI**:
   - Option A: Add `/admin/costs` endpoint to API server
   - Option B: Add `civic-extract costs` CLI command
   - Option C: Simple Python script in `scripts/cost_dashboard.py`

3. **Display aggregations**:
   - Total cost by pipeline (last 7/30/90 days)
   - Daily cost trend chart data
   - Cost per jurisdiction breakdown

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Test existing cost methods work
python3 -c "
from civic.storage import get_storage_backend
backend = get_storage_backend()
summary = backend.get_etl_cost_summary(days=30)
print(summary)
"
```

## Success Criteria

- [ ] Dashboard displays total ETL costs for last 7/30/90 days
- [ ] Costs broken down by pipeline type (transcribe, decisions, vectors, etc.)
- [ ] Shows cost trend (daily or weekly aggregation)
- [ ] Works with existing `etl_costs` data

## Session 423 Stats

- Completed: `automated_incremental_pipeline`
- Added: `refresh_metadata` table for incremental fetch tracking
- Added: `scheduled_low_velocity_refresh` (weekly) and `scheduled_high_velocity_refresh` (daily)
- Added: `--meetings`, `--issues`, `--incremental` flags to modal_ingest.py
- Deploy command: `modal deploy scripts/modal_ingest.py`
- Pilot: 222/244 items (91%)

# Recommended: ca_state_controller_ingestion

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-03

> This is recommended context from Session 451. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 451 documented the distinction between FAC and USAspending data and discovered that the **CA State Controller** (bythenumbers.sco.ca.gov) provides structured, queryable intergovernmental revenue data that fills our state funding gap.

**Why this matters:**
- FAC only has federal expenditures (audited, but 18-24 month lag)
- USAspending only has direct federal awards (misses pass-through)
- CA State Controller has federal + state + county revenue, with FY2024 already available

## Recommended Task

Build a `CAStateControllerClient` to ingest intergovernmental revenue data from the CA State Controller's Socrata API.

**API Endpoint:** `https://bythenumbers.sco.ca.gov/resource/rrtv-rsj9.csv`

**San Rafael data verified in Session 451:**

| Year | Federal | State | County | Total |
|------|---------|-------|--------|-------|
| 2024 | $171K | $3.5M | $909K | $4.5M |
| 2023 | $817K | $3.1M | $1.4M | $5.3M |
| 2022 | $16.2M | $2.8M | $1.3M | $20.3M |

## Key Files

- `docs/critical/FEDERAL_FUNDING_DATA_SOURCES.md` - Documentation of all funding data sources
- `packages/civic-extraction/src/civic_extraction/clients/fac.py` - FAC client (pattern to follow)
- `packages/civic/src/civic/storage/postgres_backend.py` - Storage backend (may need new table)
- `pilot.json:1453` - Task definition with resources

## Suggested Approach

1. Create `packages/civic-extraction/src/civic_extraction/clients/ca_state_controller.py`
2. Follow the FAC client pattern: `health()`, `validate()`, `get_revenues()` methods
3. Query Socrata API with parameters: `entity_name`, `fiscal_year`, `$select`, `$where`
4. Normalize data to a consistent schema (similar to FAC normalization)
5. Add storage method to PostgresBackend (or reuse existing if appropriate)
6. Add Civic API method: `c.intergovernmental_revenue(audit_year=2024)`

## Example API Query

```python
import requests

url = "https://bythenumbers.sco.ca.gov/resource/rrtv-rsj9.csv"
params = {
    "$limit": 500,
    "entity_name": "San Rafael",
    "fiscal_year": "2024"
}
response = requests.get(url, params=params)
# Returns CSV with columns: entity_name, fiscal_year, category, subcategory_1, value, etc.
```

## Tests to Run

```bash
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] CAStateControllerClient with `health()`, `validate()`, `get_revenues()` methods
- [ ] Data ingested for San Rafael (FY2003-2024, 20+ years)
- [ ] Civic API method to query intergovernmental revenue
- [ ] `ca_state_controller_ingestion` marked ready in pilot.json

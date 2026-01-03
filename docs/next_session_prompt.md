# Recommended: Budget Query API

**Priority:** P0
**Area:** data_readiness > budget
**Date:** 2026-01-02

> This is recommended context from Session 436. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 436 completed `san_rafael_fy2526_budget` - extracted 58 budget line items ($180M) from official city PDFs and stored in Supabase. The budget pipeline now has real data:
- 12 General Fund departments ($104.5M): Police $30.9M, Fire $26M, Public Works $16.1M...
- 46 Other Fund items ($75.6M): Special Revenue, Enterprise, Capital, Internal Service

Next up: **Civic.budget()** method to query this data.

## Recommended Task

Add `Civic.budget()` method for structured budget queries.

## Key Design Decision: Extensibility for Intergovernmental Funding

Session 436 added `intergovernmental_funding` to the roadmap (7 items) for tracking federal→state→city funding flows. **Design the API signature to accommodate future parameters without breaking changes:**

```python
# Phase 1 (this session) - municipal queries
def budget(
    self,
    department: str = None,
    fund: str = None,
    program: str = None,
    min_amount: int = None,
    max_amount: int = None,
    fiscal_year: str = None,
) -> list[BudgetItem]

# Phase 2 (future) - add these parameters later
    funding_source: str = None,      # "federal", "state", "local"
    cfda_number: str = None,         # Federal program identifier (e.g., "14.218")
    include_upstream: bool = False,  # Include federal/state source data
```

The `budget_items.metadata` JSONB column can store `funding_source_id` when linking is implemented.

## Key Files

- `packages/civic/src/civic/civic.py` - Add budget() method
- `packages/civic/src/civic/storage/postgres_backend.py:4437` - get_budget_items() already implemented
- `packages/civic/src/civic/storage/postgres_backend.py:4520` - get_budget_summary() already implemented
- `scripts/extract_san_rafael_budget.py` - Reference for data structure
- `data/budgets/san_rafael/FY25-26-extracted.json` - 58 items to query

## Suggested Approach

1. **Define BudgetItem dataclass** in `packages/civic/src/civic/models.py` or similar
2. **Add budget() method to Civic class** that wraps StorageBackend calls
3. **Handle jurisdiction resolution** (budget queries should use current jurisdiction)
4. **Add convenience formatting** (amounts in dollars, department summaries)

## Example Usage

```python
c = Civic("san-rafael")

c.budget(department="Police")           # → [BudgetItem($30.9M)]
c.budget(fund="General Fund")           # → [12 BudgetItems totaling $104.5M]
c.budget(min_amount=10_000_000)         # → [3 items over $10M]
c.budget()                              # → All 58 items
```

## Tests to Run

```bash
# Smoke tests (includes Civic API)
pytest packages/civic/tests/test_civic.py -q

# If adding new test file
pytest packages/civic/tests/test_budget_queries.py -v
```

## Success Criteria

- [ ] Civic.budget() method implemented with filtering parameters
- [ ] Returns structured BudgetItem objects (not raw dicts)
- [ ] Works with existing PostgresBackend methods
- [ ] API signature designed for future extensibility (intergovernmental params)
- [ ] Smoke tests pass
- [ ] Basic integration test with real San Rafael data

## Related Roadmap Items

**Budget pipeline (3 of 5 complete):**
1. ~~budget_schema~~ ✅ Session 434
2. ~~budget_etl_template~~ ✅ Session 435
3. ~~san_rafael_fy2526_budget~~ ✅ Session 436
4. **budget_query_api** ← THIS SESSION
5. decision_financial_extraction (P2)

**Intergovernmental funding (new, all P2):**
- federal_awards_schema → usaspending_ingestion → state_passthrough_schema → ca_grants_ingestion → budget_funding_source_linking → funding_reconciliation → funding_flow_api

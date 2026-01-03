# Recommended: Federal Awards Schema

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 438. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 438 completed `decision_financial_extraction` - the final item in the budget pipeline:

1. ~~budget_schema~~ ✅ Session 434
2. ~~budget_etl_template~~ ✅ Session 435
3. ~~san_rafael_fy2526_budget~~ ✅ Session 436
4. ~~budget_query_api~~ ✅ Session 437
5. ~~decision_financial_extraction~~ ✅ Session 438

Now beginning **intergovernmental funding tracking** - a new 7-item sequence to trace federal→state→city funding flows.

## Recommended Task

Create StorageBackend schema and methods for federal award/grant data.

**Artifact:** StorageBackend methods for federal award/grant data

## Schema Design

The schema needs these fields (from pilot.json):
- `award_id` - Unique federal award identifier
- `cfda_number` - Catalog of Federal Domestic Assistance number
- `recipient_uei` - Unique Entity Identifier (replaced DUNS)
- `recipient_name` - Organization name
- `amount_cents` - Award amount in cents (integer precision)
- `period_start` - Award period start date
- `period_end` - Award period end date
- `program_name` - Federal program name
- `awarding_agency` - Federal agency awarding the grant
- `funding_agency` - Federal agency providing the funding

## Key Files

- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol (add new methods)
- `packages/civic/src/civic/storage/postgres_backend.py:291` - Table creation (add federal_awards table)
- `packages/civic/src/civic/storage/sqlite_backend.py` - Add stub implementations

## Suggested Approach

1. **Add protocol methods** to `backend.py`:
   - `store_federal_awards(jurisdiction_id, awards, as_of) -> int`
   - `get_federal_awards(jurisdiction_id, cfda_number, period_start, period_end, as_of, limit) -> List[Dict]`
   - `get_federal_awards_count(jurisdiction_id) -> int`

2. **Create table schema** in `postgres_backend.py`:
   - Use cents (BIGINT) for amounts, not decimals
   - Add temporal versioning (valid_from, valid_to) like other tables
   - Add indexes on (jurisdiction_id, cfda_number), (recipient_uei)

3. **Add SQLite stubs** for local dev

4. **Write tests** for the new storage methods

## Patterns to Follow

Reference the budget_items implementation from Session 434:
- `postgres_backend.py:413-480` - budget_items table and indexes
- `postgres_backend.py:1808-1930` - store_budget_items/get_budget_items methods

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `federal_awards` table created with temporal versioning
- [ ] StorageBackend protocol extended with award methods
- [ ] PostgresBackend implements store/get for federal awards
- [ ] SQLiteBackend has stubs
- [ ] Storage protocol tests pass

## Related Work

After `federal_awards_schema`, the sequence continues:
- **usaspending_ingestion** (P2) - Ingest from USAspending.gov API
- **state_passthrough_schema** (P2) - Schema for state-administered federal funds
- **ca_grants_ingestion** (P2) - Ingest CA state grants
- **budget_funding_source_linking** (P2) - Link budget items to funding sources
- **funding_reconciliation** (P2) - Reconcile amounts
- **funding_flow_api** (P2) - Civic.funding_flow() method

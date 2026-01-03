# Recommended: USAspending Ingestion

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 439. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 439 completed `federal_awards_schema` - the storage layer for federal awards. The table and StorageBackend methods are ready. Now we need to ingest actual data from USAspending.gov API.

**Intergovernmental Funding Sequence:**
1. ~~federal_awards_schema~~ - Session 439
2. **usaspending_ingestion** - P0 (YOU ARE HERE)
3. state_passthrough_schema - P2
4. ca_grants_ingestion - P2
5. budget_funding_source_linking - P2
6. funding_reconciliation - P2
7. funding_flow_api - P2

## Recommended Task

Ingest federal awards from USAspending.gov API for San Rafael.

**Artifact:** Ingest federal awards from USAspending.gov API

**Note from pilot.json:** Free API, no key required. Filter by recipient (San Rafael UEI), place of performance (94901-94915), or CFDA. Returns contracts, grants, loans, direct payments.

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py:4661-4860` - store_federal_awards/get_federal_awards methods
- `packages/civic/src/civic/storage/backend.py:1184-1251` - Protocol definition
- `packages/civic-extraction/` - Where ETL extractors live (pattern reference)

## USAspending.gov API

**Base URL:** https://api.usaspending.gov/api/v2/

**Key endpoints:**
- `/search/spending_by_award/` - Search awards by various criteria
- `/recipient/duns/` - Look up by DUNS/UEI
- `/awards/last_updated/` - Get latest data timestamp

**Filtering options:**
- `recipient_search_text` - Organization name (e.g., "San Rafael")
- `place_of_performance_locations` - Zip codes (94901-94915)
- `def_codes` - CFDA numbers

## Suggested Approach

1. **Create extractor** in `packages/civic-extraction/`:
   - `usaspending_extractor.py` or similar
   - Use requests to query USAspending.gov API
   - Map API response to our award schema

2. **Map API fields to schema:**
   - `generated_unique_award_id` -> `award_id`
   - `cfda_number` -> `cfda_number` (CFDA deprecated, now Assistance Listing)
   - `recipient_uei` -> `recipient_uei`
   - `recipient_name` -> `recipient_name`
   - `total_obligation` (in dollars) -> `amount_cents` (convert to cents)
   - `period_of_performance_start_date` -> `period_start`
   - `period_of_performance_current_end_date` -> `period_end`
   - `awarding_agency_name` -> `awarding_agency`
   - `funding_agency_name` -> `funding_agency`

3. **Store via StorageBackend:**
   - Use `store_federal_awards(jurisdiction_id, awards, as_of)`
   - The method handles upsert with temporal versioning

4. **Add test** to verify ingestion works

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] USAspending.gov API client/extractor created
- [ ] Can query awards for San Rafael (by UEI, zip, or name)
- [ ] Maps API response to federal_awards schema
- [ ] Stores awards via store_federal_awards method
- [ ] Test verifies at least 1 award ingested

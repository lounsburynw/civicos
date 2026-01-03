# Recommended: fac_ingestion_client

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 448. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 448 investigated why `funding_flow()` was showing "Unknown" for budget descriptions. We discovered:

1. **Jurisdiction ID mismatch** (FIXED): Storage layer now normalizes jurisdiction IDs (e.g., "san-rafael" → "city-san-rafael")

2. **Keyword matching is unreliable**: The FundingMatcher was linking budget items to federal awards based on keyword overlap (e.g., "fire prevention" → CFDA 97.044). This produced spurious links - the $3.9M "Measure C Wildfire Prevention" budget item (a local ballot measure) was incorrectly linked to a $190K federal firefighters grant.

3. **No explicit linkage data**: Budget PDFs don't contain CFDA numbers or grant IDs. Amount-based matching produces too many false positives.

## The Solution: Federal Audit Clearinghouse

Cities receiving >$750K in federal funds must file **Single Audits** with the [Federal Audit Clearinghouse](https://app.fac.gov/dissemination/search/). These contain the **Schedule of Expenditures of Federal Awards (SEFA)** - an audited table with:

- CFDA number
- Federal grantor agency
- Pass-through grantor (state agency, if applicable)
- Program name
- Expenditures

This is the actual accounting - not keyword guessing.

## Recommended Task

Build a `FederalAuditClearinghouseClient` to ingest SEFA data from San Rafael's Single Audit.

### Approach

1. **Search FAC for San Rafael** - Use https://app.fac.gov/dissemination/search/
2. **Download Single Audit PDF** - Or use FAC API if available
3. **Parse SEFA table** - Extract CFDA, agency, pass-through, amounts
4. **Store as `federal_audit_expenditures`** - New table with explicit CFDA→expenditure links
5. **Update `funding_flow()`** - Query audit data instead of keyword matcher

### Resources

- [FAC Search](https://app.fac.gov/dissemination/search/) - Official repository
- [San Rafael Financial Reports](https://www.cityofsanrafael.org/financial-reports/) - Single Audits 2012-2023
- [FAC Search Resources](https://www.fac.gov/search-resources/) - API documentation

## Current Database State

```
city-san-rafael:
  - Budget items: 58 (FY25-26)
  - Federal awards: 65 (from USAspending.gov)
  - State grants: 141 (from CA Grants Portal - no federal CFDA linkage)
  - Funding links: 0 (removed spurious keyword matches)
```

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py` - Now normalizes jurisdiction IDs
- `packages/civic/src/civic/_internal/funding/matcher.py` - Keyword matcher (to be replaced/supplemented)
- `pilot.json` - `fac_ingestion_client` item added

## Success Criteria

- [ ] FAC client can search for and download San Rafael Single Audit
- [ ] SEFA table parsed with CFDA numbers and expenditures
- [ ] Data stored in PostgreSQL with explicit linkages
- [ ] `funding_flow()` returns audited data (not keyword guesses)

## Code Changes This Session

1. Added `normalize_jurisdiction()` to storage backend methods:
   - `store_budget_items`, `get_budget_items`
   - `store_federal_awards`, `get_federal_awards`
   - `store_state_passthrough_funds`, `get_state_passthrough_funds`
   - `store_budget_funding_links`, `get_budget_funding_links`

2. Migrated data from `san-rafael` to `city-san-rafael`

3. Capped `variance_percentage` in FundingMatcher to fit database NUMERIC(5,2)

4. Removed spurious funding links based on keyword matching

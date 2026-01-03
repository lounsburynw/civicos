# Recommended: funding_flow_e2e

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 449. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 449 completed the FAC ingestion client. We now have audited federal expenditure data from the Federal Audit Clearinghouse (52 records, 2016-2023). The question is: how should `funding_flow()` use this authoritative data?

**The problem:** Session 448 found that keyword-based matching of budget items to federal awards produces spurious links. Budget PDFs don't contain CFDA numbers, so there's no reliable way to automatically link them.

**What we have now:**
- `federal_expenditures()` - Returns audited SEFA data (authoritative)
- `funding_flow()` - Returns budget→federal links (unreliable keyword matching)

## Recommended Task

Decide the approach for `funding_flow()` and implement it:

### Option A: Document the separation
- `federal_expenditures()` = "What federal grants did we spend?" (authoritative)
- `funding_flow()` = "Which budget items are grant-funded?" (best-effort, low confidence)
- Update docstrings and possibly add warnings about match quality

### Option B: Enhance funding_flow() with audit data
- For each budget item with a federal link, enrich with FAC expenditure amounts
- Show discrepancy between USAspending award amounts and audited expenditures
- Mark source as "audited" vs "estimated"

### Option C: Remove keyword matcher entirely
- Delete the unreliable keyword matching logic
- Only show links that are manually confirmed or have explicit CFDA in source data

## Key Files

- `packages/civic/src/civic/civic.py:1135` - `funding_flow()` method
- `packages/civic/src/civic/civic.py:1340` - `federal_expenditures()` method (NEW)
- `packages/civic/src/civic/_internal/funding/matcher.py` - Keyword matcher (unreliable)
- `packages/civic/src/civic/storage/postgres_backend.py:5064` - `store_federal_audit_expenditures()`

## Current State

```python
# Authoritative FAC data available:
c = Civic("san-rafael")
exp = c.federal_expenditures(audit_year=2023)
# Returns 7 programs: Medicaid $658K, Highway $637K, FEMA $562K, etc.

summary = c.federal_expenditures_summary(audit_year=2023)
# Returns: {total_dollars: 2022048, programs: [...]}

# Unreliable funding_flow data:
flows = c.funding_flow()
# Returns 0 flows (we deleted spurious keyword matches in Session 448)
```

## Suggested Approach

1. Read existing `funding_flow()` implementation (~100 lines)
2. Decide on approach (A, B, or C above)
3. Implement changes
4. Update tests if needed
5. Mark `funding_flow_e2e` as ready in pilot.json

## Tests to Run

```bash
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Clear documentation of what `funding_flow()` vs `federal_expenditures()` provide
- [ ] No spurious keyword matches in output
- [ ] Users can answer "what federal money did we spend?" using the API
- [ ] `funding_flow_e2e` marked ready in pilot.json

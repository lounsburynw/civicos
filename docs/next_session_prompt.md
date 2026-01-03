# Recommended: funding_reconciliation

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 444. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 444 completed `budget_funding_source_linking` - the infrastructure to link city budget items to federal/state funding sources. The table, StorageBackend methods, and FundingMatcher are ready. Now we need to reconcile amounts.

**Intergovernmental Funding Sequence:**
1. ~~federal_awards_schema~~ - Session 439
2. ~~usaspending_ingestion~~ - Session 440
3. ~~state_passthrough_schema~~ - Session 442
4. ~~ca_grants_ingestion~~ - Session 443
5. ~~budget_funding_source_linking~~ - Session 444
6. **funding_reconciliation** - P0 (YOU ARE HERE)
7. funding_flow_api - P2

## Recommended Task

Reconcile federal award amounts with city budget receipts.

**Artifact:** Reconcile federal award amounts with city budget receipts

**Note from pilot.json:** Validate: SUM(city budget grants) ≈ SUM(federal/state awards to city). Flag discrepancies >5%. Account for multi-year awards, indirect costs, pass-through timing.

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py:5210-5465` - budget_funding_source_links methods
- `packages/civic/src/civic/_internal/funding/matcher.py` - FundingMatcher with Match.to_link()
- `packages/civic/src/civic/storage/backend.py:1337-1448` - Protocol definition

## Already Available

1. **Budget Items** - San Rafael FY25-26 budget extracted (103 items)
2. **Federal Awards** - USAspending.gov client and data
3. **State Grants** - California Grants Portal client
4. **Linking Table** - budget_funding_source_links with match_confidence, variance_cents, reconciliation_status

## Suggested Approach

1. **Implement reconciliation logic:**
   - Load budget items with matching federal/state funding links
   - Compare budget_cents vs (federal_cents or local_cents)
   - Calculate variance_cents and variance_percentage
   - Update reconciliation_status: "match" (<1%), "variance" (<10%), "unverified"

2. **Add reconciliation report:**
   - Total linked vs unlinked budget items
   - Total amounts matched vs variance
   - Flag items with variance >5% for review

3. **Handle edge cases:**
   - Multi-year awards spanning fiscal years
   - Indirect cost allocations
   - Pass-through timing differences

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Reconciliation logic implemented
- [ ] Variance calculation accurate (budget vs award amounts)
- [ ] reconciliation_status updated: match/variance/unverified
- [ ] Report shows linked items with variance breakdown
- [ ] Discrepancies >5% flagged for review

# Recommended: funding_flow_e2e

**Priority:** P0
**Area:** data_readiness > intergovernmental_funding
**Date:** 2026-01-02

> This is recommended context from Session 447. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 447 successfully ingested funding data to PostgreSQL:
- **65 federal awards** ($25.3M) from USAspending.gov
- **141 state grants** ($15B statewide) from CA Grants Portal
- **58 budget items** from San Rafael FY25-26 budget
- **2 funding links** created (fire prevention → CFDA 97.044)

**Problem:** Data was ingested with mismatched jurisdiction IDs:
- Budget items stored as `city-san-rafael` (from extraction script)
- Federal awards stored as `san-rafael`
- State passthroughs stored as `san-rafael`
- Funding links use `san-rafael`

Result: `funding_flow()` returns 2 flows but shows "Unknown" for budget descriptions because budget item lookup fails.

## Recommended Task

Normalize jurisdiction IDs to `san-rafael` and regenerate funding links so funding_flow() works end-to-end with real data.

## Key Files

- `scripts/extract_san_rafael_budget.py:245` - Uses `jurisdiction_id="city-san-rafael"` (needs to be `san-rafael`)
- `packages/civic/src/civic/civic.py:1100-1244` - funding_flow() method
- `packages/civic/src/civic/_internal/funding/matcher.py` - FundingMatcher for creating links

## Current PostgreSQL State

```
san-rafael:
  - Budget items: 0
  - Federal awards: 65
  - State passthroughs: 141
  - Funding links: 2

city-san-rafael:
  - Budget items: 116 (58 items × 2 from duplicate runs)
```

## Suggested Approach

1. **Option A: Re-run budget extraction with correct jurisdiction**
   ```bash
   # Modify scripts/extract_san_rafael_budget.py line 245
   # Change: jurisdiction_id="city-san-rafael"
   # To: jurisdiction_id="san-rafael"
   # Then re-run the script
   ```

2. **Option B: Copy budget items to san-rafael via SQL**
   ```python
   # Get items from city-san-rafael, store to san-rafael
   items = pg.get_budget_items("city-san-rafael", fiscal_year="2025-2026")
   pg.store_budget_items("san-rafael", items)
   ```

3. **Regenerate funding links** after budget items are in san-rafael:
   ```python
   matcher = FundingMatcher(federal_awards, passthroughs)
   links = matcher.generate_links(budget_items, "san-rafael", min_confidence=0.5)
   pg.store_budget_funding_links("san-rafael", links)
   ```

4. **Verify funding_flow() returns complete data**:
   ```python
   c = Civic("san-rafael")
   flows = c.funding_flow()
   # Should show budget descriptions, not "Unknown"
   ```

## Tests to Run

```bash
pytest packages/civic/tests/test_funding_flow.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] Budget items exist under `san-rafael` (not `city-san-rafael`)
- [ ] `funding_flow()` returns flows with actual budget descriptions (not "Unknown")
- [ ] Federal award details populated in flows (agency, program name, dollars)
- [ ] All 21 funding_flow tests still pass

## Database Connection

```bash
DATABASE_URL="postgresql://postgres.lhtuixsynupnkejpahxk:GeAvR38a5vj6iZkZ@aws-0-us-west-2.pooler.supabase.com:6543/postgres"
```

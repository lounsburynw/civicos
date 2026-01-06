# Recommended: cfr_ingestion

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-06

> This is recommended context from Session 484. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 484 completed `extraction_versioning`. Priorities were reordered: data completeness before distribution. The new order is:
1. **P0-P1:** Data gaps (CFR, case law, codified law, elections, financial configs)
2. **P2:** Monitoring/admin tools
3. **P3:** Social features
4. **P4:** Distribution channels (GPT, MCP, web frontend)

## Recommended Task

Implement CFR (Code of Federal Regulations) ingestion pipeline to add federal regulatory context to the what_applies() method.

## Key Files

- `scripts/modal_legislation.py` - Pattern for federal data ingestion
- `scripts/modal_executive_orders.py` - Similar federal ingestion job
- `packages/civic/src/civic/storage/postgres_backend.py` - Storage methods
- `packages/civic-extraction/src/civic_extraction/clients/` - Extractor patterns

## Suggested Approach

1. **Research CFR API access:**
   - eCFR API: https://www.ecfr.gov/api/
   - GovInfo bulk data: https://www.govinfo.gov/bulkdata/CFR

2. **Create CFR extractor client:**
   ```python
   # packages/civic-extraction/src/civic_extraction/clients/ecfr.py
   class ECFRClient:
       def get_titles(self, title_numbers: List[int]) -> List[CFRSection]:
           # Title 24 (HUD), Title 40 (EPA), etc.
   ```

3. **Create Modal job:**
   ```python
   # scripts/modal_cfr.py
   @app.function()
   def fetch_cfr(titles: List[int]) -> int:
       # Fetch relevant CFR titles, store to Supabase
   ```

4. **Add storage method:**
   ```python
   # PostgresBackend.store_cfr_sections()
   ```

5. **Wire into what_applies():**
   Include CFR sections in regulatory stack results

## Data Scope (Start Small)

Focus on titles relevant to local government:
- Title 24: Housing and Urban Development
- Title 40: Protection of Environment (EPA)
- Title 49: Transportation

## Tests to Run

```bash
pytest packages/civic/tests/test_civic.py -v -k "what_applies"
```

## Success Criteria

- [ ] ECFRClient can fetch CFR sections by title
- [ ] Modal job stores CFR sections to Supabase
- [ ] what_applies() includes relevant CFR sections
- [ ] pilot.json updated: cfr_ingestion -> ready

## Related P1 Items (Next)

After cfr_ingestion:
- `case_law_ingestion` - Court decisions affecting local policy
- `codified_law_vectors` - Vector embeddings for code search
- `election_*` items - Election data integration

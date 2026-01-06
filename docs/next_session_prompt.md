# Recommended: case_law_ingestion

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-06

> This is recommended context from Session 485. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 485 completed `cfr_ingestion`. The CFR parser and Modal ingestion script are ready. Data completeness continues: next is federal case law to provide judicial interpretation context for `what_applies()`.

Priority order (from Session 484):
1. **P0-P1:** Data gaps (CFR ✓, case law, codified law vectors, elections)
2. **P2:** Monitoring/admin tools
3. **P3:** Social features
4. **P4:** Distribution channels (GPT, MCP, web frontend)

## Recommended Task

Implement case law ingestion from CourtListener API to add federal court decisions to the regulatory stack in `what_applies()`.

## Key Files

- `packages/civic-extraction/src/civic_extraction/cfr.py` - Pattern for legal code parser
- `scripts/modal_cfr.py:100-300` - Pattern for Modal ingestion script
- `packages/civic/src/civic/storage/postgres_backend.py:4072` - `store_codified_law()` pattern
- `packages/civic/src/civic/context.py:185-215` - CFR integration pattern

## Suggested Approach

1. **Research CourtListener API:**
   - API docs: https://www.courtlistener.com/api/
   - Free tier: 5000 queries/day
   - Focus on federal circuit courts (9th Circuit for San Rafael)

2. **Create case law parser:**
   ```python
   # packages/civic-extraction/src/civic_extraction/case_law.py
   @dataclass
   class CaseLawDecision:
       case_name: str
       citation: str  # e.g., "123 F.3d 456"
       court: str
       date_filed: str
       opinion_text: str
       topics: List[str]
   ```

3. **Create Modal ingestion job:**
   ```python
   # scripts/modal_case_law.py
   @app.function()
   def ingest_case_law(courts: List[str], topics: List[str]) -> dict:
       # Fetch from CourtListener, store to PostgreSQL
   ```

4. **Add storage (options):**
   - Extend `codified_law` table with `regulation_type='case_law'`
   - Or create dedicated `case_law` table if schema differs significantly

5. **Integrate into what_applies():**
   - Add case law search after CFR search
   - Return decisions with `type='case_law'`

## Data Scope (Start Small)

Focus on cases relevant to San Rafael pilot:
- 9th Circuit Court of Appeals
- California district courts
- Topics: housing, zoning, environmental, civil rights

## Tests to Run

```bash
pytest packages/civic/tests/test_civic.py -v -k "what_applies"
pytest packages/civic-extraction/tests/test_case_law.py -v  # after creating
```

## Success Criteria

- [ ] CourtListener client can fetch cases by court/topic
- [ ] Modal job stores case decisions to PostgreSQL
- [ ] what_applies() includes relevant case law in federal layer
- [ ] pilot.json updated: case_law_ingestion -> ready

## Related P1 Items (Next)

After case_law_ingestion:
- `codified_law_vectors` - Vector embeddings for code search
- `election_*` items - Election data integration

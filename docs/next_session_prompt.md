# Recommended: Decision Financial Extraction

**Priority:** P0
**Area:** data_readiness > budget
**Date:** 2026-01-02

> This is recommended context from Session 437. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 437 completed `budget_query_api` - added `Civic.budget()` and `Civic.budget_summary()` methods. The budget pipeline is now 4/5 complete:

1. ~~budget_schema~~ ✅ Session 434
2. ~~budget_etl_template~~ ✅ Session 435
3. ~~san_rafael_fy2526_budget~~ ✅ Session 436
4. ~~budget_query_api~~ ✅ Session 437
5. **decision_financial_extraction** ← THIS SESSION

## Recommended Task

Extract financial impact from staff reports/decisions to populate `financial_impact_cents` field.

**Artifact:** Enhanced staff report extraction populates `financial_impact_cents`

## Design Considerations

Staff reports often contain fiscal impact sections with dollar amounts. These should be:
1. Extracted during PDF processing
2. Stored in the decision/agenda item metadata
3. Linked to relevant budget items (if applicable)

Example fiscal impact text:
```
FISCAL IMPACT:
This project will cost $150,000 from the General Fund Capital Projects budget.
```

## Key Files

- `packages/civic-extraction/src/civic_extraction/prompts/` - Extraction prompts
- `packages/civic-extraction/src/civic_extraction/structured/` - Structured extraction
- `packages/civic/src/civic/storage/postgres_backend.py` - Storage for decisions

## Suggested Approach

1. **Review existing extraction** - Check how staff reports are currently parsed
2. **Add fiscal impact extraction** - Look for patterns like "FISCAL IMPACT:", dollar amounts
3. **Store in metadata** - Add `financial_impact_cents` to decision/agenda item storage
4. **Test with real data** - Verify extraction works on San Rafael staff reports

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q

# Extraction tests (if they exist)
pytest packages/civic-extraction/tests/ -q
```

## Success Criteria

- [ ] Staff report extraction identifies fiscal impact sections
- [ ] Dollar amounts parsed and stored as cents
- [ ] Financial impact available via Civic API
- [ ] Smoke tests pass

## Related Work

After this item, the budget pipeline is complete. Next priority areas:
- **intergovernmental_funding** (7 items, all P2) - Track federal→state→city funding
- **embedding_infrastructure** (5 items, P3) - Improve RAG quality

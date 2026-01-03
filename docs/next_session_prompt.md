# Recommended: budget_extractor_protocol

**Priority:** P0
**Area:** data_architecture > financial_data_infrastructure
**Date:** 2026-01-03

> This is recommended context from Session 453. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 453 completed `financial_client_protocol_compliance` (verified already done) and `extraction_config_financial_section` (added FinancialConfig to ExtractionConfig). The financial infrastructure is maturing - we have FinancialConfig for config-driven client creation, but budget extraction still uses a separate `BudgetLineItem` in `prompts/`. Moving it to `clients/base.py` aligns with the established pattern.

## Recommended Task

Move `BudgetLineItem` dataclass from `prompts/budget_extraction.py` to `clients/base.py` and create a `BudgetExtractor` protocol following the existing `Extractor` protocol pattern.

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/base.py:321-356` - `Extractor` protocol (pattern to follow)
- `packages/civic-extraction/src/civic_extraction/prompts/budget_extraction.py:30-71` - Current `BudgetLineItem` location
- `packages/civic-extraction/src/civic_extraction/prompts/__init__.py` - Re-exports BudgetLineItem
- `packages/civic-extraction/tests/test_budget_extraction.py` - Existing budget tests
- `scripts/extract_san_rafael_budget.py` - Uses BudgetLineItem

## Suggested Approach

1. Read existing `Extractor` protocol in `base.py` to understand pattern
2. Move `BudgetLineItem` dataclass to `base.py` (after FinancialConfig, before ExtractionConfig)
3. Create `BudgetExtractor` protocol with methods:
   - `extract_budget(fiscal_year: str) -> List[BudgetLineItem]`
   - `normalize_line_item(raw: Dict) -> BudgetLineItem`
4. Update imports in `prompts/budget_extraction.py` to import from `base`
5. Update `prompts/__init__.py` re-export
6. Verify existing tests still pass

## Tests to Run

```bash
pytest packages/civic-extraction/tests/test_budget_extraction.py -v
pytest packages/civic-extraction/tests/test_clients.py -v
```

## Success Criteria

- [ ] `BudgetLineItem` moved to `clients/base.py`
- [ ] `BudgetExtractor` protocol defined in `clients/base.py`
- [ ] Backward-compatible imports preserved in `prompts/`
- [ ] All existing budget extraction tests pass
- [ ] All client tests pass (85 tests)

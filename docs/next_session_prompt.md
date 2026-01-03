# Recommended: shared_config_package

**Priority:** P0
**Area:** data_architecture > embedding_infrastructure
**Date:** 2026-01-03

> This is recommended context from Session 455. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 455 completed `budget_acfr_reconciliation_automation` (JSON output + manifest integration) and simplified `FinancialConfig` to minimal fields (state, county, fiscal_year_start_month). The session then reprioritized pilot.json to focus on **hardening first, then build out**. This item is the foundation for cleaning up cross-package imports.

## Problem

`civic-services` imports from `civic` (cross-layer violation):
- `civic_services/processing/civic_schema_adapter.py:19` → `from civic.jurisdiction import JurisdictionRegistry`
- `civic_services/monitoring/automated_civic_refresh.py:22` → `from civic.jurisdiction import CITY_CONFIGS`

This creates a dependency where the services layer depends on the core API layer.

## Recommended Task

Create a shared config package (`packages/civic-config/`) to hold `JurisdictionRegistry`, `JurisdictionConfig`, and related types. Both `civic` and `civic-services` can then import from this shared package.

## Key Files

- `packages/civic/src/civic/jurisdiction.py:1-50` - Current location of `JurisdictionRegistry`, `JurisdictionConfig`
- `packages/civic-services/src/civic_services/processing/civic_schema_adapter.py:19` - Imports `JurisdictionRegistry`
- `packages/civic-services/src/civic_services/monitoring/automated_civic_refresh.py:22` - Imports `CITY_CONFIGS`
- `packages/civic-services/src/civic_services/chat/civic_chat_router.py:144` - Imports `CITY_CONFIGS`

## Suggested Approach

1. Create `packages/civic-config/` with standard package structure
2. Move `JurisdictionRegistry`, `JurisdictionConfig`, `GranicusConfig`, `CITY_CONFIGS` to `civic-config`
3. Update `civic/jurisdiction.py` to re-export from `civic-config` (backward compatibility)
4. Update `civic-services` imports to use `civic-config` directly
5. Add `civic-config` as dependency to both `civic` and `civic-services` pyproject.toml

## Alternative Approach

If a new package feels heavyweight, consider:
- Move config to `civic-extraction` (already shared)
- Or accept the cross-layer import as pragmatic (it's just config, not logic)

## Tests to Run

```bash
pytest packages/civic/tests/test_civic.py -v -q --override-ini="addopts="
pytest packages/civic-services/tests/ -v -q --override-ini="addopts=" 2>/dev/null || echo "Check civic-services tests"
```

## Success Criteria

- [ ] No direct imports from `civic.jurisdiction` in `civic-services`
- [ ] `JurisdictionRegistry` accessible from shared location
- [ ] Backward-compatible re-exports in `civic/jurisdiction.py`
- [ ] All existing tests pass

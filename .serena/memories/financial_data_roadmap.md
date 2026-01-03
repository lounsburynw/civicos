# Financial Data Roadmap

**Date**: 2026-01-03
**Context**: Session exploring budget/ACFR/intergovernmental data integration

## Current State Summary

| Level | Budget | ACFR | Intergovernmental | Federal |
|-------|--------|------|-------------------|---------|
| San Rafael | ✅ FY25-26 | ✅ FY24-25 | ✅ SCO FY24 | ✅ FAC/USAspending |
| Marin County | ❌ | ❌ | ✅ Available | ✅ Available |
| CA State | N/A | N/A | ✅ SCO API | N/A |
| Federal | N/A | N/A | N/A | ✅ APIs working |

## Proposed Tasks (Priority Order)

### P1: Integrate Financial Clients with DataSource Protocol
**Why**: Enables unified health monitoring, consistent error handling
**Files**: `clients/ca_state_controller.py`, `clients/fac.py`, `clients/usaspending.py`
**Effort**: ~2 hours
**Sub-tasks**:
1. Add `health()` method to CAStateControllerClient
2. Add `validate()` method to CAStateControllerClient
3. Repeat for FACClient, USAspendingClient

### P1: Add Financial Section to ExtractionConfig
**Why**: Enables per-city financial data configuration
**Files**: `clients/base.py`, `data/extraction/san-rafael.json`
**Effort**: ~1 hour
**Sub-tasks**:
1. Extend ExtractionConfig dataclass with optional `financial` field
2. Update san-rafael.json with financial hints
3. Add fiscal_year_start, sco_city_name, budget_url_pattern

### P2: Create BudgetExtractor Protocol
**Why**: Standardizes budget extraction like MeetingExtractor
**Files**: `clients/base.py`
**Effort**: ~2 hours
**Sub-tasks**:
1. Define BudgetLineItem dataclass in base.py (move from prompts/)
2. Define BudgetExtractor protocol
3. Create PDFBudgetExtractor implementing protocol

### P2: Automate Budget-to-ACFR Reconciliation
**Why**: Enables "follow the money" from budget to actual
**Files**: New `scripts/reconcile_funding_sources.py` (exists, needs integration)
**Effort**: ~3 hours
**Sub-tasks**:
1. Load budget from ExtractionConfig
2. Load ACFR from standard location
3. Output reconciliation report
4. Integrate with IngestionManifest

### P3: Add Marin County Configuration
**Why**: Enables county-level financial context
**Files**: `data/extraction/marin-county.json`
**Effort**: ~1 hour
**Sub-tasks**:
1. Create extraction config
2. Query SCO for county intergovernmental
3. Identify budget/ACFR PDF locations

### P3: Multi-Year Budget Trend
**Why**: Enables "what changed" analysis
**Effort**: ~2 hours
**Sub-tasks**:
1. Extract FY24-25 budget PDF
2. Store with consistent naming
3. Create trend comparison utility

## Not Prioritized (Future)

- State budget context (affects local funding formulas)
- Proposition tracking (funding source changes)
- CFDA enrichment (federal program descriptions)
- Grant-to-program mapping (requires manual curation)

## Integration Points

All tasks should:
1. Use existing `ExtractionConfig` system
2. Implement `DataSource` protocol where applicable
3. Create `IngestionManifest` entries for provenance
4. Output canonical schemas defined in `base.py`

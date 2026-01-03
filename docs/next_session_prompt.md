# Recommended: financial_client_protocol_compliance

**Priority:** P0
**Area:** data_architecture > financial_data_infrastructure
**Date:** 2026-01-03

> This is recommended context from Session 452. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 452 explored financial data integration (budget, ACFR, intergovernmental revenue). Found existing ETL infrastructure is mature—`DataSource` protocol, `ExtractionConfig`, `IngestionManifest` already exist. Financial clients (SCO, FAC, USAspending) work but don't implement the standard `DataSource` protocol, preventing unified monitoring.

## Recommended Task

Add `health()` and `validate()` methods to financial clients to match existing `DataSource` protocol in `clients/base.py`.

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/base.py:152-198` - `DataSource` protocol definition
- `packages/civic-extraction/src/civic_extraction/clients/ca_state_controller.py` - SCO client (new, needs protocol)
- `packages/civic-extraction/src/civic_extraction/clients/fac.py` - FAC client (needs protocol)
- `packages/civic-extraction/src/civic_extraction/clients/usaspending.py` - USAspending client (needs protocol)
- `docs/critical/FINANCIAL_DATA_INTEGRATION.md` - Strategy doc created this session

## Suggested Approach

1. Read `DataSource` protocol in `base.py` (health(), validate(), source_id, source_type)
2. Add protocol implementation to `CAStateControllerClient` first (reference)
3. Add to `FACClient` and `USAspendingClient`
4. Create test file `tests/test_financial_clients.py`

## Tests to Run

```bash
pytest packages/civic-extraction/tests/test_clients.py -v
```

## Success Criteria

- [ ] `CAStateControllerClient` implements `DataSource` protocol
- [ ] `FACClient` implements `DataSource` protocol
- [ ] `USAspendingClient` implements `DataSource` protocol
- [ ] `health()` returns `HealthStatus` with API connectivity check
- [ ] `validate()` returns `ValidationResult` with config validation

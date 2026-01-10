# URGENT: Fix CI Failures

**Priority:** P0
**Date:** 2026-01-10

## Context

Session 497 completed `data_freshness_alerting` but uncovered CI failures that were masked by dependency issues. After fixing civic-config and psycopg2-binary dependencies, actual test failures are now visible.

## Current CI Status

Smoke tests pass, but Full Suite has failures:

### Failing Tests

1. **Jurisdiction validation is too strict** - Tests expect unknown jurisdictions to be handled gracefully, not raise errors:
   - `test_e2e_verification.py::test_unknown_jurisdiction` - expects `Civic("fake-city")` to NOT raise
   - `test_e2e_verification.py::test_civic_api_logging_no_secrets` - uses `test-jurisdiction`
   - `test_integration_rag_san_rafael.py::test_get_public_testimony_unknown_jurisdiction` - expects empty list, not error

2. **Missing dependencies in Full Suite**:
   - `psycopg2-binary` and `boto3` needed (partially fixed, need to verify)

3. **Storage protocol tests** - Various failures in `test_storage_protocols.py`

## Root Cause

`civic.py:508` calls `normalize_jurisdiction()` which defaults to `strict=True`:
```python
self.jurisdiction = normalize_jurisdiction(self.jurisdiction)
```

The tests expect **non-strict** behavior where unknown jurisdictions return empty results instead of raising `JurisdictionError`.

## Fix Options

1. **Change Civic to use strict=False** - Allow unknown jurisdictions, return empty results
2. **Update tests** - Make them expect errors for unknown jurisdictions
3. **Add strict parameter to Civic** - Let caller decide

Option 1 aligns with test expectations in comments:
> "Civic can be instantiated with unknown jurisdiction"
> "Query methods return empty/placeholder results, not errors"

## Key Files

- `packages/civic/src/civic/civic.py:508` - normalize_jurisdiction call
- `packages/civic/src/civic/_internal/jurisdiction.py:107` - strict parameter
- `packages/civic/tests/test_e2e_verification.py:2222` - test_unknown_jurisdiction
- `.github/workflows/tests.yml:75` - Full Suite dependencies (added psycopg2-binary, boto3)

## Suggested Fix

```python
# In civic.py line 508, change:
self.jurisdiction = normalize_jurisdiction(self.jurisdiction)
# To:
self.jurisdiction = normalize_jurisdiction(self.jurisdiction, strict=False)
```

## Commits Made This Session

1. `f6ce8ee` - Add data freshness alerting GitHub Action
2. `e645313` - Fix CI: Add civic-config dependency to all workflows
3. `dca5989` - Fix CI: Add civic-config to pgvector integration job
4. `a8afea4` - Fix CI: Add psycopg2-binary and fix MCP jurisdiction

## Uncommitted Changes

- `.github/workflows/tests.yml` - Added `psycopg2-binary boto3` to Full Suite (staged, not pushed)

## Next Steps

1. Push the staged tests.yml change
2. Fix jurisdiction strict=False in civic.py
3. Run CI and verify all tests pass
4. Then proceed to `automated_transcript_ingestion` (original P0)

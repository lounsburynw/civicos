# Recommended: Jurisdiction Registry Consolidation

**Priority:** P0 (IMMEDIATE)
**Area:** data_architecture > configuration_management
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 343 completed `operations_backend_protocol` - adding operation tracking to the StorageBackend protocol (148/173 items ready, 85.5%). The next priority item is consolidating jurisdiction configuration which is currently scattered across multiple files with duplicate hardcoded mappings.

**The problem:** `CITY_CONFIGS` exists in one file, but timezone mappings and other jurisdiction metadata are duplicated in multiple places, violating DRY and making it error-prone to add new cities.

## Recommended Task

Create a centralized `JurisdictionRegistry` class that consolidates all jurisdiction configuration:

1. Promote `CITY_CONFIGS` to a `JurisdictionRegistry` class in core location
2. Add missing fields (county, state, civic_center_address)
3. Refactor files with duplicate hardcoded mappings to import from registry

## Key Files

**Authoritative Source (to promote):**
- `packages/civic-services/src/civic_services/monitoring/automated_civic_refresh.py:23-100` - `CITY_CONFIGS` dict with jurisdiction_id, agent_type, meeting_urls, timezone, etc.

**Files with Duplicate Mappings (to refactor):**
- `packages/civic-services/src/civic_services/processing/civic_schema_adapter.py:20-42` - `JURISDICTION_TIMEZONES` module-level constant (duplicate)
- `packages/civic-services/src/civic_services/processing/civic_schema_adapter.py:255-279` - `JURISDICTION_TIMEZONES` inside `_apply_jurisdiction_timezone()` (duplicate)
- `packages/civic-services/src/civic_services/processing/civic_schema_adapter.py:604-613` - `TIMEZONE_DISPLAY` mapping
- `packages/civic-services/src/civic_services/processing/civic_schema_adapter.py:946-960` - Yet another `JURISDICTION_TIMEZONES` copy

**API integration:**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py:1628-1687` - Imports CITY_CONFIGS, uses it for jurisdiction metadata

## Suggested Approach

1. **Create JurisdictionRegistry class** in `packages/civic/src/civic/jurisdiction.py`:
   ```python
   @dataclass
   class JurisdictionConfig:
       jurisdiction_id: str
       agent_type: str
       meeting_urls: List[str]
       timezone: str
       website: Optional[str] = None
       county: Optional[str] = None
       state: str = "CA"
       # ... other fields

   class JurisdictionRegistry:
       @classmethod
       def get(cls, city_key: str) -> JurisdictionConfig: ...
       @classmethod
       def get_by_id(cls, jurisdiction_id: str) -> JurisdictionConfig: ...
       @classmethod
       def get_timezone(cls, jurisdiction_id: str) -> str: ...
   ```

2. **Migrate CITY_CONFIGS data** from automated_civic_refresh.py to the registry

3. **Refactor civic_schema_adapter.py** to use registry instead of hardcoded mappings

4. **Refactor automated_civic_refresh.py** to import from registry

5. **Add tests** for registry lookups

## Tests to Run

```bash
# Smoke tests (core API)
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# If you add tests for JurisdictionRegistry
pytest packages/civic/tests/test_jurisdiction.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] JurisdictionRegistry class in packages/civic/src/civic/
- [ ] All jurisdiction data consolidated in one location
- [ ] No duplicate JURISDICTION_TIMEZONES mappings in civic_schema_adapter.py
- [ ] automated_civic_refresh.py imports from registry
- [ ] Existing tests still pass
- [ ] pilot.json `jurisdiction_registry_consolidation` marked as ready

## Pilot Progress

- 148/173 items ready (85.5%)
- 25 items remaining
- P0: jurisdiction_registry_consolidation (this item)

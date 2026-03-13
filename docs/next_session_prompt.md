# Recommended: Add eScribe Platform Client

**Priority:** P0 (`escribe_client`)
**Area:** federation_testbed
**Date:** 2026-03-13

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session made onboarding fully turnkey and generalizable across US cities, counties, states, Canadian provinces, and UK councils (96 tests, 5 jurisdiction types validated E2E). Stress testing found **one platform coverage gap: Portland, OR uses eScribe**, which we don't have a client for. All other major US cities land on Granicus, Legistar, CivicClerk, or ProudCity.

The existing abstraction (`BaseExtractor` + factory + discovery) is already designed for this — adding a new platform is a well-defined task with no new abstractions needed.

## Recommended Task

Implement an eScribe client following the existing patterns. Four pieces:

### 1. Client: `clients/escribe.py` (~200 lines)
- Subclass `BaseExtractor` (defined at `clients/base.py:413`)
- Implement `get_events()`, `normalize_event()`, `platform_name`, `health()`, `validate()`
- Research eScribe's meeting API endpoints (Portland's instance)
- Reference existing clients for patterns:
  - `clients/granicus.py:49` — `GranicusClient(BaseExtractor)` (most complete example)
  - `clients/legistar.py:24` — `LegistarClient(BaseExtractor)` (simpler API client)

### 2. Factory: `clients/factory.py:36`
- Add `elif source_type == "escribe":` case (2 lines, follows existing pattern)

### 3. Discovery: `platform_detection.py`
- Add `discover_escribe_instance(city_name, state)` function
- Register in `discover_platform()` orchestrator alongside Legistar/CivicClerk/Granicus/ProudCity

### 4. Onboard integration: `onboard.py`
- Add eScribe case to the pre-discovered platform handling (~820-870)
- Add `_discover_escribe()` helper (follows `_discover_granicus()` pattern at line 295)

## Key Files

- `clients/base.py:413` — `BaseExtractor` ABC (the contract to implement)
- `clients/base.py:245` — `DataSource` protocol (health/validate)
- `clients/base.py:294` — `Meeting` dataclass (normalization target)
- `clients/factory.py` — source factory (add escribe case)
- `clients/granicus.py:49` — best reference client implementation
- `platform_detection.py` — discovery functions (add escribe discovery)
- `onboard.py:820-870` — platform-specific onboard paths (add escribe case)

All paths relative to `packages/civicos-extraction/src/civicos_extraction/`.

## Suggested Approach

1. **Research eScribe API** — find Portland's eScribe instance URL, understand their meeting/event endpoints
2. **Write `clients/escribe.py`** — implement `BaseExtractor` with `get_events()` and `normalize_event()`
3. **Add to factory** — 2-line addition to `factory.py`
4. **Add discovery** — `discover_escribe_instance()` in `platform_detection.py`
5. **Add onboard path** — `_discover_escribe()` in `onboard.py`
6. **Test** — verify `discover_platform("Portland", state="OR")` now finds eScribe
7. **E2E** — `onboard_jurisdiction(city_name="Portland", state="OR", level="city", generate_yaml=True)`

## Tests to Run

```bash
# Platform detection + onboarding tests (96 currently passing)
pytest packages/civicos-extraction/tests/test_platform_detection.py -q --override-ini="addopts="

# Regression: existing jurisdictions
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
for j in ['city-san-rafael', 'city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(j)
    print(f'{j}: {len(c.storage.get_meetings(j))} meetings')"
```

## Success Criteria

- [ ] `discover_platform("Portland", state="OR")` returns `{"platform": "escribe", ...}`
- [ ] `EScribeClient` implements `BaseExtractor` with `get_events()`, `normalize_event()`, `health()`, `validate()`
- [ ] `factory.py` dispatches `source_type="escribe"` correctly
- [ ] Portland onboards end-to-end: `onboard_jurisdiction(city_name="Portland", state="OR")`
- [ ] All 96 existing tests still pass
- [ ] All 3 existing jurisdictions still work

## Known Issues

- **Legistar API intermittent 500s** — Berkeley/SF return 500. Oakland/Dublin work. Legistar's issue.
- **CivicClerk meeting titles generic** — El Cerrito returns "Meeting" for all entries

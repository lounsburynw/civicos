# Next Session: ETL Modularization for City Onboarding

## Context

Session 310 completed:
- Created `scripts/dev.sh` for launching dev servers
- Fixed 90+ bare imports across civic_services
- Added `/launch` command
- Reprioritized `pilot.json`: ETL modularization before dashboard redesign

## Why ETL First?

The admin dashboard is confusing because it reflects tangled internals. The fix isn't better UI—it's cleaner abstractions.

**Current state:**
- Dashboard shows "6/15 coverage" (meeting types) vs "0 ingested" (actual meetings)—confusing
- Bare imports everywhere (just fixed 90+)
- No standard interface for data sources

**Target state:**
- Each data source implements `DataSource` interface with `health()` method
- Pipeline has clear stages: discover → ingest → index
- Dashboard simply displays `source.health()` output

## Priority 1 Items (from pilot.json)

```
city_onboarding/configuration/extraction_config_schema
  → Define DataSource interface with health() method

city_onboarding/configuration/san_rafael_extraction_config
  → Implement ProudCitySource(DataSource) with config-driven setup

city_onboarding/orchestration/generalized_pipeline_runner
  → Pipeline class with stages, each with status callbacks

city_onboarding/orchestration/full_city_bootstrap
  → Single command: civic bootstrap san-rafael

city_onboarding/validation/preflight_checks
  → source.validate() for fail-fast config validation
```

## Suggested Interface Design

```python
class DataSource(Protocol):
    """Interface for all civic data sources."""

    def health(self) -> SourceHealth:
        """Return current source status."""
        ...

    def validate(self) -> ValidationResult:
        """Check config and connectivity before running."""
        ...

    def discover(self) -> list[DiscoveredItem]:
        """Find available items from source."""
        ...

    def ingest(self, items: list[DiscoveredItem]) -> IngestResult:
        """Fetch and store items in database."""
        ...

@dataclass
class SourceHealth:
    available: int           # Items available at source
    last_checked: datetime   # When we last queried source
    errors: list[str]        # Any current errors

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]        # e.g., "API key missing", "Endpoint unreachable"
```

## Files to Explore

**Existing extraction code:**
- `packages/civic-extraction/src/civic_extraction/clients/proudcity.py` - ProudCity scraper
- `packages/civic-extraction/src/civic_extraction/clients/seeclickfix.py` - SeeClickFix API
- `packages/civic-extraction/src/civic_extraction/clients/base.py` - Existing base class

**Pipeline orchestration:**
- `scripts/batch_process_san_rafael_meetings.py` - Current batch processing
- `packages/civic-services/src/civic_services/monitoring/automated_civic_refresh.py` - CITY_CONFIGS

**Admin status (dashboard data source):**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py` - `serve_admin_status()` ~line 7325

## Implementation Order

1. **Define interfaces** in `packages/civic-extraction/src/civic_extraction/interfaces/`
2. **Refactor ProudCityClient** to implement DataSource
3. **Create Pipeline class** that orchestrates sources
4. **Update admin_status endpoint** to consume `source.health()`
5. **Dashboard becomes trivial** - just display the clean data

## Launch the App

```bash
./scripts/dev.sh
```

## Success Criteria

A new person can run:
```bash
civic bootstrap my-city --platform proudcity --url https://my-city.proudcity.com
```

And see clear output:
```
✓ Config validated
✓ Discovered 47 meetings
✓ Ingested 47 meetings (23 new, 24 updated)
✓ Indexed 47 for search
```

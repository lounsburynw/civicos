# Extractor Protocol Documentation

This document describes the protocols and interfaces for building platform extractors in the Civic data pipeline.

## Overview

The extraction layer (`civic-extraction` package) provides a standardized way to fetch civic data from various platforms (Legistar, CivicClerk, ProudCity, etc.) and normalize it into a common format for storage and indexing.

## Core Protocols

### DataSource Protocol

All platform clients must implement the `DataSource` protocol for unified health monitoring.

```python
from civic_extraction.clients.base import DataSource, HealthStatus, ValidationResult

class MyPlatformSource:
    """Implements DataSource protocol."""

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction, e.g. 'legistar-berkeley'."""
        return f"myplatform-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source: 'legistar', 'civicclerk', 'proudcity', etc."""
        return "myplatform"

    def health(self) -> HealthStatus:
        """Check source availability and return standardized status."""
        # Implementation required
        ...

    def validate(self) -> ValidationResult:
        """Validate configuration and API access before running pipeline."""
        # Implementation required
        ...
```

### Extractor Protocol

Platform clients that extract meetings must implement the `Extractor` protocol.

```python
from civic_extraction.clients.base import Extractor, Meeting

class MyPlatformClient:
    """Implements Extractor protocol."""

    def get_events(self, days_ahead: int = 90, days_past: int = 0) -> List[Dict[str, Any]]:
        """Extract events/meetings from the platform in native format."""
        ...

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize a platform-native event to the Meeting format."""
        ...
```

## Data Types

### HealthStatus

Standardized health check response for monitoring dashboards.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | `str` | Unique identifier, e.g., "legistar-berkeley" |
| `source_type` | `str` | Platform type: "legistar", "civicclerk", "proudcity" |
| `jurisdiction_id` | `str` | Jurisdiction identifier, e.g., "city-berkeley" |
| `is_available` | `bool` | Can connect and fetch data |
| `available_count` | `int` | Number of items available in last check |
| `last_checked` | `datetime` | When health() was called |
| `check_duration_ms` | `float` | How long the health check took |
| `errors` | `List[str]` | Recent error messages |
| `last_successful` | `datetime` | Last successful fetch (optional) |
| `coverage_percent` | `float` | Extraction coverage (optional) |
| `metadata` | `Dict` | Platform-specific stats (optional) |

### ValidationResult

Result of preflight validation before running the pipeline.

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | `bool` | All checks passed, safe to proceed |
| `config_valid` | `bool` | Config structure is correct |
| `api_reachable` | `bool` | API endpoint is accessible |
| `errors` | `List[str]` | Critical errors (fail fast) |
| `warnings` | `List[str]` | Non-blocking issues |
| `check_duration_ms` | `float` | Validation duration |
| `metadata` | `Dict` | Additional context |

### Meeting

Normalized meeting data structure compatible with the storage layer.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `str` | Yes | Unique meeting identifier |
| `title` | `str` | Yes | Meeting title/name |
| `meeting_datetime` | `datetime` | Yes | When the meeting occurs |
| `jurisdiction_id` | `str` | Yes | Jurisdiction identifier |
| `meeting_type` | `str` | No | Type (Regular Meeting, Special Meeting, etc.) |
| `status` | `str` | No | Status (Scheduled, Cancelled, etc.) |
| `location` | `str` | No | Physical location |
| `virtual_url` | `str` | No | Virtual meeting URL (Zoom, etc.) |
| `agenda_url` | `str` | No | URL to agenda document |
| `minutes_url` | `str` | No | URL to minutes document |
| `video_url` | `str` | No | URL to video recording |
| `source_platform` | `str` | No | Platform name (default: "unknown") |
| `source_url` | `str` | No | Original URL on source platform |
| `raw_data` | `Dict` | No | Original platform data (for debugging) |

### ExtractionConfig

Configuration for a data extraction source, loaded from JSON files.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | `str` | Unique identifier, e.g., "proudcity-san-rafael" |
| `source_type` | `str` | Platform type |
| `jurisdiction_id` | `str` | Jurisdiction identifier |
| `base_url` | `str` | Platform base URL |
| `auto_discover` | `bool` | Whether to auto-discover meeting archives |
| `archives` | `Dict[str, str]` | meeting_type -> archive path mapping |
| `metadata` | `Dict` | Additional configuration |

## BaseExtractor Abstract Class

For common functionality, extend the `BaseExtractor` abstract class:

```python
from civic_extraction.clients.base import BaseExtractor, Meeting

class MyPlatformClient(BaseExtractor):
    """Platform-specific extractor implementation."""

    def __init__(self, jurisdiction_id: str, api_key: str = None):
        super().__init__(jurisdiction_id)
        self.api_key = api_key

    def get_events(self, days_ahead: int = 90, days_past: int = 0) -> List[Dict]:
        """Fetch meetings from the platform API."""
        # Your platform-specific implementation
        ...

    def normalize_event(self, event: Dict) -> Meeting:
        """Convert platform data to normalized Meeting."""
        return Meeting(
            id=f"{self.jurisdiction_id}-{event['id']}",
            title=event['name'],
            meeting_datetime=parse_datetime(event['date']),
            jurisdiction_id=self.jurisdiction_id,
            source_platform="myplatform",
            source_url=event.get('url'),
        )
```

## Existing Implementations

| Platform | Client Class | File |
|----------|--------------|------|
| Legistar | `LegistarClient` | `clients/legistar.py` |
| CivicClerk | `CivicClerkClient` | `clients/civicclerk.py` |
| ProudCity | `ProudCityClient`, `ProudCitySource` | `clients/proudcity.py` |

## Pipeline Integration

Extractors integrate with the 4-stage pipeline:

```
discover → ingest → store → index
```

1. **Discover**: `DataSource.health()` checks availability
2. **Ingest**: `Extractor.get_events()` + `normalize_event()` fetches and normalizes data
3. **Store**: Validated meetings are persisted to `StorageBackend`
4. **Index**: Stored meetings are indexed in ChromaDB for search

### Usage with Pipeline

```python
from civic_extraction.pipeline import Pipeline
from civic_extraction.clients.proudcity import ProudCitySource
from civic.storage.sqlite_backend import SQLiteBackend

# Create source and storage
source = ProudCitySource.from_jurisdiction("city-san-rafael")
storage = SQLiteBackend()

# Create and run pipeline
pipeline = Pipeline(
    source=source,
    jurisdiction_id="city-san-rafael",
    storage_target=storage,
    validate_on_ingest=True,  # Enable schema validation
)

result = pipeline.run(
    days_past=30,
    days_ahead=90,
)

print(f"Stored {result.stages['store'].items_processed} meetings")
```

## Schema Validation

Meetings are validated against JSON schema before storage. See `meeting_schema.py` for the schema definition and `MeetingValidator` class.

## Adding a New Platform

1. Create `clients/myplatform.py`
2. Implement `DataSource` protocol for health monitoring
3. Implement `Extractor` protocol for data extraction
4. Create config file in `data/extraction/`
5. Add tests in `tests/test_myplatform.py`
6. Register in `clients/__init__.py`

## Configuration Files

Extraction configs are stored in `data/extraction/{jurisdiction}.json`:

```json
{
  "source_id": "proudcity-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "https://www.cityofsanrafael.org",
  "auto_discover": true,
  "archives": {
    "city_council": "/city-council-meetings/",
    "planning_commission": "/planning-commission/"
  },
  "metadata": {
    "timezone": "America/Los_Angeles"
  }
}
```

## Related Documentation

- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - System architecture
- `docs/TESTING_STRATEGY.md` - Testing approach
- `packages/civic-extraction/src/civic_extraction/meeting_schema.py` - Schema validation

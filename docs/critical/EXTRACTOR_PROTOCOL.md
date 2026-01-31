# Extractor Protocol Documentation

This document describes the protocols and interfaces for building platform extractors in the Civic data pipeline.

## Overview

The extraction layer (`civicos-extraction` package) provides a standardized way to fetch civic data from various platforms (Legistar, CivicClerk, ProudCity, etc.) and normalize it into a common format for storage and indexing.

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

## StorageBackend Usage

Ingestion scripts must use the `StorageBackend` protocol for all data persistence. This ensures portability across SQLite (local dev) and PostgreSQL (production).

### Protocol Methods

The `StorageBackend` protocol (`packages/civic/src/civic/storage/backend.py`) provides methods for each data type:

| Data Type | Store Method | Get Method | Count Method |
|-----------|--------------|------------|--------------|
| Meetings | `store_meetings()` | `get_meetings()` | via `get_stats()` |
| Decisions | `store_decisions()` | `get_decisions()` | `get_decision_count()` |
| Chunks | `store_chunks()` | `get_chunks()` | `get_chunk_count()` |
| Issues | `store_issues()` | `get_issues()` | `get_issue_count()` |
| Transcripts | `store_transcripts()` | `get_transcripts()` | `get_transcript_count()` |
| Videos | `store_videos()` | `get_videos()` | `get_video_count()` |
| Municipal Code | `store_municipal_code()` | `get_municipal_code()` | `get_municipal_code_count()` |
| Legislation | `store_legislation()` | `get_legislation()` | `get_legislation_count()` |
| Budget Items | `store_budget_items()` | `get_budget_items()` | `get_budget_items_count()` |
| Agenda Items | `store_agenda_items()` | `get_agenda_items()` | `get_agenda_item_count()` |

### Updating Meeting Metadata

When ingestion pipelines upload resources to blob storage (R2), they need to update URL fields on existing meetings. Use `update_meeting()` for this:

```python
# After uploading PDF to R2, update the meeting's agenda_url
backend.update_meeting(
    jurisdiction_id="school-san-rafael",
    meeting_id="srcs-meeting-12345",
    updates={"agenda_url": "https://blob.civic.dev/school-san-rafael/agendas/12345.pdf"}
)
```

**Allowed fields:** `agenda_url`, `minutes_url`, `video_url`, `source_url`, `virtual_url`, `location`, `status`

This method:
- Only updates the current (non-expired) version
- Does not create a new temporal version (metadata update, not content change)
- Raises `ValueError` for disallowed fields

### Protocol Compliance Rules

Scripts in `scripts/` must follow these rules for StorageBackend usage:

**ALLOWED:**
- Import from any package (`civic`, `civicos-extraction`, `civicos-services`)
- Use public protocol methods (`store_meetings`, `update_meeting`, etc.)
- Combine multiple pipeline stages in a single script

**NOT ALLOWED:**
- Accessing private/internal methods (prefixed with `_`)
- Bypassing protocol interfaces (e.g., `backend._get_connection()`)
- Duplicating protocol logic instead of using protocol methods
- Direct SQL updates that bypass the protocol

```python
# GOOD: Uses StorageBackend protocol
backend.update_meeting(jurisdiction_id, meeting_id, {"agenda_url": url})

# BAD: Bypasses protocol, ties to specific backend
conn = backend._get_connection()
cursor.execute("UPDATE meetings SET agenda_url = ...")
```

### Blob Storage Pattern

For pipelines that upload files to R2 blob storage:

1. **Download** the resource (PDF, audio, etc.)
2. **Upload** to R2 with appropriate key structure
3. **Update** the meeting record via `update_meeting()`

```python
# Example: SRCS agenda PDF upload pattern
pdf_content = fetch_agenda_pdf(meeting)
r2_key = f"{jurisdiction_id}/agendas/{meeting_id}.pdf"
upload_to_r2(r2_key, pdf_content)

backend.update_meeting(
    jurisdiction_id=jurisdiction_id,
    meeting_id=meeting_id,
    updates={"agenda_url": f"{R2_PUBLIC_URL}/{r2_key}"}
)
```

This pattern:
- Keeps PDFs accessible to Modal workers for LLM extraction
- Updates meeting records portably across backends
- Enables graceful degradation if R2 is unavailable

### Operation Tracking

Long-running ingestion operations should use the operation tracking methods for admin dashboard visibility:

```python
import uuid

# Start operation
op_id = str(uuid.uuid4())
backend.create_operation(op_id, jurisdiction_id, "ingest_meetings")
backend.update_operation_status(op_id, "running", current_step="Fetching page 1")

# Track progress
backend.update_operation_status(
    op_id, "running",
    current_step=f"Processing meeting {i}",
    progress_percent=i / total * 100,
    items_processed=i,
    items_total=total
)

# Complete
backend.complete_operation(op_id, {"meetings_stored": count})
```

## Related Documentation

- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - System architecture
- `docs/TESTING_STRATEGY.md` - Testing approach
- `packages/civicos-extraction/src/civic_extraction/meeting_schema.py` - Schema validation
- `.critics/pipeline.critic.md` - Pipeline protocol compliance checks
- `.critics/architecture.critic.md` - Architecture layer validation

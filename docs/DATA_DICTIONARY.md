# Civic Data Dictionary

This document provides field-level documentation for the core data types used in the Civic platform.

## Overview

The Civic platform processes three main types of civic data:

| Data Type | Source | Description |
|-----------|--------|-------------|
| **Meeting** | Legistar, CivicClerk, ProudCity | City council and commission meetings |
| **Decision** | Meeting minutes, staff reports | Outcomes of council votes |
| **Issue** | SeeClickFix, native | Civic complaints and 311 reports |

## Meeting

Normalized meeting data from various municipal platforms.

**Source File:** `packages/civic-extraction/src/civic_extraction/clients/base.py`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | Yes | Unique meeting identifier. Format: `{jurisdiction}-{platform}-{native_id}` |
| `title` | `string` | Yes | Meeting title/name (e.g., "City Council Meeting") |
| `meeting_datetime` | `datetime` | Yes | When the meeting occurs (ISO 8601 format) |
| `jurisdiction_id` | `string` | Yes | Jurisdiction identifier (e.g., "city-san-rafael") |
| `meeting_type` | `string` | No | Type classification: "city_council", "planning_commission", "special_meeting", etc. |
| `status` | `string` | No | Current status: "scheduled", "cancelled", "completed", "postponed" |
| `location` | `string` | No | Physical meeting location address |
| `virtual_url` | `string` | No | Virtual meeting URL (Zoom, Teams, etc.) |
| `agenda_url` | `string` | No | URL to agenda document (PDF or HTML) |
| `minutes_url` | `string` | No | URL to approved minutes document |
| `video_url` | `string` | No | URL to meeting video recording |
| `source_platform` | `string` | No | Origin platform: "legistar", "civicclerk", "proudcity", "unknown" |
| `source_url` | `string` | No | Original URL on the source platform |
| `raw_data` | `object` | No | Original platform data (for debugging, not stored) |

### Validation Rules

- `id`: Non-empty string, minimum length 1
- `title`: Non-empty string, minimum length 1
- `meeting_datetime`: Valid ISO 8601 datetime string
- `jurisdiction_id`: Non-empty string, minimum length 1
- URL fields: Valid URI format when present

### JSON Schema

See `packages/civic-extraction/src/civic_extraction/meeting_schema.py` for the full JSON Schema definition.

---

## Decision

Council decision extracted from meeting minutes and related documents.

**Source File:** `packages/civic/src/civic/_internal/meetings/decision.py`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision_id` | `string` | Yes | Unique identifier. Format: `{YYYYMMDD}-item-{agenda_ref}` |
| `meeting_date` | `string` | Yes | ISO date (YYYY-MM-DD) of the meeting |
| `agenda_item` | `string` | Yes | Agenda item reference (e.g., "6.a", "5.b.1") |
| `title` | `string` | Yes | Decision title (from agenda or minutes) |
| `summary` | `string` | Yes | 1-2 sentence summary of what was decided |
| `outcome` | `string` | Yes | Result: "approved", "denied", "continued", "withdrawn", "received", "adopted", "other" |
| `vote` | `object` | Yes | Vote details (see Vote structure below) |
| `staff_recommendation` | `object` | No | Staff recommendation details |
| `public_input` | `object` | No | Public comment summary |
| `legal_instruments` | `array` | No | Related resolutions/ordinances |
| `topics` | `array` | No | Topic classifications: "housing", "transportation", "environment", etc. |
| `source_documents` | `array` | No | Paths to source documents (PDFs, JSONs) |
| `extraction_method` | `string` | No | How extracted: "llm", "simple", "manual" |

### Vote Structure

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ayes` | `array[string]` | Yes | Council members voting yes |
| `noes` | `array[string]` | Yes | Council members voting no |
| `absent` | `array[string]` | Yes | Absent council members |
| `motion_by` | `string` | No | Who made the motion |
| `second_by` | `string` | No | Who seconded the motion |
| `passed` | `boolean` | No | Whether the motion passed |
| `unanimous` | `boolean` | No | Whether vote was unanimous |
| `vote_count` | `string` | No | Human-readable count (e.g., "4-1") |

### Validation Rules

- `decision_id`: Non-empty string, minimum length 1
- `meeting_date`: Valid ISO date format (YYYY-MM-DD)
- `agenda_item`: Non-empty string
- `outcome`: Must be one of the allowed values

### JSON Schema

See `packages/civic/src/civic/_internal/meetings/decision_schema.py` for the full JSON Schema definition.

---

## Issue

Civic issue or complaint, typically from 311 systems like SeeClickFix.

**Source File:** `packages/civic/src/civic/_internal/state/models.py`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | Yes | Unique issue identifier |
| `jurisdiction_id` | `string` | Yes | Parent jurisdiction |
| `source` | `string` | Yes | Data source: "seeclickfix", "native" |
| `title` | `string` | Yes | Issue summary/title |
| `source_id` | `string` | No | ID from the source system |
| `description` | `string` | No | Detailed description of the issue |
| `issue_type` | `string` | No | Category: "pothole", "graffiti", "streetlight", "trash", etc. |
| `address` | `string` | No | Location address |
| `latitude` | `float` | No | GPS latitude coordinate |
| `longitude` | `float` | No | GPS longitude coordinate |
| `status` | `string` | No | Current status: "open", "acknowledged", "closed" (default: "open") |
| `closed_reason` | `string` | No | Why the issue was closed |
| `created_at` | `datetime` | No | When the issue was reported |
| `updated_at` | `datetime` | No | Last update timestamp |
| `matched_meetings` | `array[string]` | No | IDs of related meetings |
| `matched_agenda_items` | `array[string]` | No | IDs of related agenda items |
| `match_score` | `float` | No | Relevance score for matched items |
| `match_reason` | `string` | No | Why items were matched |
| `follower_count` | `integer` | No | Number of followers/upvotes |
| `coordination_thread_id` | `string` | No | ID of coordination thread |
| `valid_from` | `datetime` | No | Temporal versioning start |
| `valid_to` | `datetime` | No | Temporal versioning end |

### Issue Types

Common issue categories from SeeClickFix:

| Type | Description |
|------|-------------|
| `pothole` | Road surface damage |
| `graffiti` | Vandalism/tagging |
| `streetlight` | Street lighting issues |
| `trash` | Illegal dumping, missed pickup |
| `sidewalk` | Sidewalk damage or obstruction |
| `tree` | Tree hazards or removal requests |
| `parking` | Parking violations or issues |
| `sign` | Sign damage or missing signs |
| `water` | Water leaks or drainage issues |
| `other` | Uncategorized issues |

### Status Values

| Status | Description |
|--------|-------------|
| `open` | Newly reported, awaiting action |
| `acknowledged` | City has reviewed the issue |
| `in_progress` | Work is underway |
| `closed` | Issue resolved |

---

## Supporting Types

### HealthStatus

Health check response for data sources (see EXTRACTOR_PROTOCOL.md).

### ValidationResult

Preflight validation result (see EXTRACTOR_PROTOCOL.md).

### StorageStats

Storage backend statistics (see storage layer documentation).

---

## Data Flow

```
Source Platform → Extractor → Meeting/Issue → Validator → StorageBackend → VectorIndex
```

1. **Extraction**: Platform clients fetch raw data
2. **Normalization**: Raw data converted to Meeting/Issue dataclasses
3. **Validation**: Schema validation before storage
4. **Storage**: SQLite/PostgreSQL persistence with temporal versioning
5. **Indexing**: ChromaDB vector embeddings for semantic search

---

## Temporal Versioning

Both Meeting and Issue support temporal versioning via `valid_from` and `valid_to` fields:

- `valid_from`: When this version became active
- `valid_to`: When this version was superseded (NULL = current)

This enables point-in-time queries and audit trails.

---

## Related Documentation

- `docs/EXTRACTOR_PROTOCOL.md` - Protocol documentation
- `packages/civic-extraction/src/civic_extraction/meeting_schema.py` - Meeting JSON Schema
- `packages/civic/src/civic/_internal/meetings/decision_schema.py` - Decision JSON Schema
- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - System architecture

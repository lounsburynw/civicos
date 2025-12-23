# Civic Data Dictionary

This document provides field-level documentation for the core data types used in the Civic platform.

## Overview

The Civic platform processes civic data organized into these main types:

| Data Type | Source | Description |
|-----------|--------|-------------|
| **CityState** | Internal | Jurisdiction state snapshot |
| **Meeting** | Legistar, CivicClerk, ProudCity | City council and commission meetings |
| **AgendaItem** | Legistar, CivicClerk | Items on meeting agendas |
| **Decision** | Meeting minutes, staff reports | Outcomes of council votes |
| **Issue** | SeeClickFix, native | Civic complaints and 311 reports |

**Source Files:**
- `packages/civic/src/civic/_internal/state/models.py` - Core models (CityState, Meeting, AgendaItem, Issue)
- `packages/civic/src/civic/_internal/meetings/decision.py` - Decision models (Decision, VoteTally, LegalInstrument, etc.)

---

## CityState

Represents the overall state of a jurisdiction.

**Source File:** `packages/civic/src/civic/_internal/state/models.py:14`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `jurisdiction_id` | `string` | Yes | Unique identifier (e.g., "city-san-rafael") |
| `jurisdiction_name` | `string` | Yes | Display name (e.g., "City of San Rafael") |
| `as_of` | `datetime` | Yes | Timestamp of this state snapshot |
| `active_residents` | `integer` | No | Number of active users (default: 0) |
| `pending_comments` | `integer` | No | Draft comments awaiting submission (default: 0) |
| `coordination_threads` | `integer` | No | Active coordination discussions (default: 0) |
| `completeness_score` | `float` | No | Data quality score 0.0-1.0 (default: 0.0) |
| `data_sources` | `array[string]` | No | Platforms providing data |
| `extraction_version` | `string` | No | Version of extraction pipeline |
| `created_at` | `datetime` | No | When jurisdiction was created |
| `updated_at` | `datetime` | No | Last update timestamp |

---

## Meeting

Normalized meeting data from various municipal platforms.

**Source File:** `packages/civic/src/civic/_internal/state/models.py:42`

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

## AgendaItem

Represents an item on a meeting agenda.

**Source File:** `packages/civic/src/civic/_internal/state/models.py:80`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | Yes | Unique item identifier |
| `meeting_id` | `string` | Yes | Parent meeting ID (foreign key) |
| `title` | `string` | Yes | Item title |
| `item_number` | `string` | No | Agenda item number (e.g., "5.1", "6.a") |
| `description` | `string` | No | Full item description |
| `project_type` | `string` | No | Category: housing, transportation, environment, etc. (AI-enriched) |
| `actionability` | `string` | No | Level of public participation possible (AI-enriched) |
| `impact_level` | `string` | No | Significance assessment (AI-enriched) |
| `financial_impact_cents` | `integer` | No | Dollar impact in cents |
| `summary` | `string` | No | AI-generated summary |
| `why_it_matters` | `string` | No | Plain-language explanation of significance (AI-enriched) |
| `participation_guide` | `string` | No | How residents can participate (AI-enriched) |
| `comment_count` | `integer` | No | Number of public comments received (default: 0) |
| `following_count` | `integer` | No | Number of users following this item (default: 0) |
| `relevant_bills` | `array[string]` | No | Related state/federal legislation IDs (AI-enriched) |
| `federal_programs` | `array[string]` | No | Related federal program IDs (AI-enriched) |
| `matched_complaints` | `array[string]` | No | Related SeeClickFix issue IDs (AI-matched) |
| `extracted_at` | `datetime` | No | When item was extracted |
| `enriched_at` | `datetime` | No | When AI enrichment was applied |
| `valid_from` | `datetime` | No | Temporal validity start (SCD Type 2) |
| `valid_to` | `datetime` | No | Temporal validity end (SCD Type 2) |
| `full_data` | `object` | No | Raw data from source for debugging |
| `video_start_ms` | `integer` | No | Video timestamp when discussion starts (milliseconds) |
| `video_end_ms` | `integer` | No | Video timestamp when discussion ends (milliseconds) |

### Usage Examples

```python
from civic import Civic

c = Civic("san-rafael")

# Prepare for a specific agenda item
prep = c.prepare(meeting_id="2025-01-15-council", item_number="6.a")
print(prep.summary)
print(prep.participation_guide)
```

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

### Vote Structure (VoteTally)

**Source File:** `packages/civic/src/civic/_internal/meetings/decision.py:25`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ayes` | `array[string]` | Yes | Council members voting yes |
| `noes` | `array[string]` | Yes | Council members voting no |
| `absent` | `array[string]` | Yes | Absent council members |
| `motion_by` | `string` | No | Who made the motion |
| `second_by` | `string` | No | Who seconded the motion |

**Computed Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `passed` | `boolean` | True if ayes > noes |
| `unanimous` | `boolean` | True if no noes and at least one aye |
| `vote_count` | `string` | Human-readable count (e.g., "4-1") |

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

## StaffRecommendation

Staff recommendation that informed a decision.

**Source File:** `packages/civic/src/civic/_internal/meetings/decision.py:103`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `department` | `string` | Yes | Originating department |
| `authors` | `array[string]` | Yes | Staff members who prepared report |
| `recommendation_text` | `string` | Yes | The recommendation text |
| `financial_impact` | `string` | No | Budget impact description |
| `property_details` | `object` | No | For real estate transactions: address, APNs |

---

## PublicInput

Summary of public input on a decision.

**Source File:** `packages/civic/src/civic/_internal/meetings/decision.py:85`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `speaker_count` | `integer` | Yes | Number of public speakers |
| `speaker_names` | `array[string]` | Yes | Names of speakers |
| `has_video_transcript` | `boolean` | No | Whether video transcript is available (default: false) |

---

## LegalInstrument

Resolution or ordinance that implements a decision.

**Source File:** `packages/civic/src/civic/_internal/meetings/decision.py:63`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instrument_type` | `string` | Yes | Type: "resolution", "ordinance", "urgency_ordinance" |
| `number` | `string` | No | Instrument number (e.g., "15478") |
| `title` | `string` | Yes | Full title |
| `purpose` | `string` | Yes | Purpose statement |
| `legal_authority` | `array[string]` | Yes | Legal basis (e.g., "Government Code Section 8698") |
| `effective_date` | `string` | No | When the instrument takes effect |

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

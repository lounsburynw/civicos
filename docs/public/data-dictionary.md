# Data Dictionary

Canonical data schemas for CivicOS. All types are defined in `packages/civicos/src/civicos/types.py` (Python) and `packages/civicos-client/src/types.ts` (TypeScript).

## City-Level Corpora

### Meetings

Source: ProudCity (San Rafael city website)

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique meeting ID |
| `title` | str | Meeting name (e.g., "City Council Regular Meeting") |
| `meeting_datetime` | datetime | Meeting date and time |
| `body` | str | Governing body (e.g., "City Council") |
| `location` | str | Physical location |
| `virtual_url` | str | Virtual meeting link |
| `agenda_url` | str | Link to agenda PDF |
| `minutes_url` | str | Link to minutes PDF |
| `video_url` | str | Link to video recording |
| `status` | str | Meeting status |
| `agenda_items` | list | Associated agenda items |

**Schema note:** The date column is `meeting_datetime`, not `meeting_date`.

### Agenda Items

| Field | Type | Description |
|-------|------|-------------|
| `title` | str | Item title |
| `project_type` | str | Category |
| `actionability` | str | Whether public can act |
| `impact_level` | str | Impact assessment |
| `financial_impact_cents` | int | Dollar impact (stored in cents) |
| `participation_guide` | str | How to participate |

### Decisions

Source: Minutes extraction (LLM-assisted)

| Field | Type | Description |
|-------|------|-------------|
| `decision_id` | str | Unique decision ID |
| `meeting_date` | str | Date of the meeting |
| `meeting_id` | str | Link to parent meeting |
| `agenda_item` | str | Agenda item reference |
| `title` | str | Decision title |
| `summary` | str | Decision summary |
| `outcome` | str | One of: approved, denied, continued, withdrawn, received, adopted, other |
| `vote` | object | `{ ayes, noes, absent, motion_by, second_by, passed, unanimous, vote_count }` |
| `staff_recommendation` | str | Staff recommendation |
| `public_input` | str | Public input summary |
| `topics` | list | Topic tags |
| `financial_impact_cents` | int | Dollar impact (stored in cents) |

### Transcripts

Source: YouTube + AssemblyAI

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Excerpt ID |
| `text` | str | Transcript text |
| `speaker` | str | Speaker name |
| `speaker_role` | str | Role (council member, staff, public) |
| `video_id` | str | YouTube video ID |
| `start_timestamp` | float | Start time in seconds |
| `end_timestamp` | float | End time in seconds |
| `is_public_comment` | bool | Whether this is public testimony |

### Chunks (Agenda Packets)

Source: City agenda PDFs, parsed into sections

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Chunk ID |
| `meeting_id` | str | Link to parent meeting |
| `content` | str | Text content |
| `metadata` | dict | Source page, section info |

**Schema note:** Link column is `meeting_id`, not `content_id`.

### Community Issues

Source: SeeClickFix (311)

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | str | SeeClickFix issue ID |
| `issue_type` | str | Category (e.g., "Pothole", "Graffiti") |
| `address` | str | Location address |
| `latitude` | float | GPS latitude |
| `longitude` | float | GPS longitude |
| `status` | str | Resolution status |
| `matched_meetings` | list | Linked meeting IDs |

### Budget Items

Source: FY25-26 budget PDF extraction

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Budget item ID |
| `fund` | str | Fund name |
| `department` | str | Department |
| `program` | str | Program name |
| `line_item` | str | Line item description |
| `budgeted_dollars` | float | Budgeted amount |
| `revised_dollars` | float | Revised amount |
| `actual_dollars` | float | Actual spending |
| `fiscal_year` | str | Fiscal year |
| `source_url` | str | Source document URL |
| `source_page` | int | Page in source PDF |

### Municipal Code

Source: Municode

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Section ID |
| `jurisdiction_id` | str | Jurisdiction |
| `section_number` | str | Section number (e.g., "14.01.020") |
| `section_title` | str | Section heading |
| `full_text` | str | Complete section text |
| `chapter` | str | Chapter number |
| `chapter_title` | str | Chapter heading |
| `title_number` | str | Title number |
| `ordinance_history` | str | Amendment history |

## State/Federal Corpora

### Legislation

Source: LegiScan (CA + federal bills)

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Internal ID |
| `bill_id` | str | LegiScan bill ID |
| `state` | str | State code (e.g., "CA") |
| `bill_number` | str | Bill number (e.g., "SB 123") |
| `bill_name` | str | Short title |
| `status` | str | Legislative status |
| `summary` | str | Bill summary |
| `leverage_point` | str | How citizens can engage |
| `keywords` | list | Topic keywords |
| `local_implementation_required` | bool | Whether cities must act |

### Executive Orders

Source: Federal Register

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Internal ID |
| `document_number` | str | FR document number |
| `title` | str | Executive order title |
| `president` | str | Issuing president |
| `eo_number` | str | EO number |
| `abstract` | str | Summary |
| `signing_date` | str | Date signed |
| `status` | str | Current status |
| `revoked_by_eo` | str | If revoked, by which EO |

### Federal Expenditures

Source: Federal Audit Clearinghouse (FAC)

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | str | FAC report ID |
| `cfda_number` | str | CFDA program number |
| `audit_year` | int | Audit year |
| `amount_expended_dollars` | float | Amount expended |
| `federal_program_name` | str | Program name |
| `is_major` | bool | Major program flag |
| `is_passthrough` | bool | Pass-through flag |

## Vector Embeddings

All corpora are semantically indexed using OpenAI embeddings stored in pgvector. Corpus types are defined in `packages/civicos/src/civicos/storage/corpus_types.py`.

| Corpus Type | Embedding Count | Enables |
|-------------|-----------------|---------|
| `transcripts` | ~4,296 | `what_was_said()`, `get_public_testimony()` |
| `chunks` | ~5,084 | PDF/agenda packet search |
| `municipal_code` | ~5,857 | Legal code search |
| `issues` | ~1,459 | `whos_with_me()` semantic matching |
| `decisions` | ~44 | `what_happened()` semantic search |
| `meetings` | ~46 | Meeting search |

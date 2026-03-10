# Storage Schema Reference

Internal database schemas. These are **not** the API return types — see [docs/public/data-dictionary.md](../public/data-dictionary.md) for what consumers see.

## Schema Notes

- Date column for meetings is `meeting_datetime`, not `meeting_date`
- Chunk link column is `meeting_id`, not `content_id`
- Vector embeddings table is `vector_embeddings` (pgvector), not `embeddings`
- Financial amounts are stored in cents internally, converted to dollars at the API layer

## Tables

### meetings

Source: ProudCity extraction

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | Primary key |
| `jurisdiction_id` | str | |
| `title` | str | |
| `meeting_datetime` | datetime | **Not** `meeting_date` |
| `body` | str | Governing body |
| `location` | str | |
| `virtual_url` | str | |
| `agenda_url` | str | |
| `minutes_url` | str | |
| `video_url` | str | |
| `status` | str | |
| `agenda_items` | jsonb | |

### decisions

Source: LLM-assisted minutes extraction

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | Primary key (e.g., `decision:city-san-rafael:2026-02-17:5-b`) |
| `jurisdiction_id` | str | |
| `meeting_date` | str | Date string |
| `meeting_id` | str | FK to meetings |
| `agenda_item` | str | Agenda item number (e.g., "5.b") |
| `agenda_item_id` | str | FK to agenda items |
| `title` | str | |
| `summary` | str | |
| `outcome` | str | approved, denied, continued, withdrawn, received, adopted, other |
| `item_type` | str | presentation, consent, action, etc. |
| `vote_json` | jsonb | `{ ayes, noes, absent, motion_by, second_by, passed, unanimous, vote_count }` |
| `staff_recommendation_json` | jsonb | |
| `public_input_json` | jsonb | |
| `legal_instruments_json` | jsonb | |
| `topics` | jsonb | Topic tags array |
| `financial_impact_cents` | int | Dollar impact in cents |
| `source_documents` | jsonb | `[{ url, type }]` |
| `extraction_method` | str | e.g., `retrospective_analyzer_gemini` |
| `extracted_at` | datetime | |
| `extraction_version` | str | |
| `content_hash` | str | SHA-256 for dedup |
| `valid_from` | datetime | Temporal versioning |
| `valid_to` | datetime | null = current |
| `deleted_at` | datetime | Soft delete |

### transcripts

Source: YouTube + AssemblyAI

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | |
| `jurisdiction_id` | str | |
| `meeting_id` | str | FK to meetings |
| `text` | str | Transcript text |
| `speaker` | str | |
| `speaker_role` | str | council, staff, public |
| `video_id` | str | YouTube video ID |
| `start_timestamp` | str | HH:MM:SS |
| `end_timestamp` | str | HH:MM:SS |
| `start_ms` | int | Milliseconds |
| `end_ms` | int | Milliseconds |
| `is_public_comment` | bool | |

### chunks

Source: City agenda PDFs, parsed into sections

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | |
| `jurisdiction_id` | str | |
| `meeting_id` | str | **Not** `content_id` |
| `content` | str | Text content |
| `metadata` | jsonb | Source page, section info |

### issues

Source: SeeClickFix (311)

| Column | Type | Notes |
|--------|------|-------|
| `source_id` | str | SeeClickFix issue ID |
| `jurisdiction_id` | str | |
| `issue_type` | str | Category |
| `address` | str | |
| `latitude` | float | |
| `longitude` | float | |
| `status` | str | |
| `matched_meetings` | jsonb | Linked meeting IDs |

### budget_items

Source: FY25-26 budget PDF extraction

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | |
| `jurisdiction_id` | str | |
| `fund` | str | |
| `department` | str | |
| `program` | str | |
| `line_item` | str | |
| `budgeted_dollars` | float | |
| `revised_dollars` | float | |
| `actual_dollars` | float | |
| `fiscal_year` | str | |
| `source_url` | str | |
| `source_page` | int | |
| `notes` | str | |

### municipal_code

Source: Municode

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | |
| `jurisdiction_id` | str | |
| `section_number` | str | e.g., "14.01.020" |
| `section_title` | str | |
| `full_text` | str | |
| `chapter` | str | |
| `chapter_title` | str | |
| `title_number` | str | |
| `title_name` | str | |
| `node_id` | str | Municode node ID |
| `ordinance_history` | str | |
| `source` | str | "municode", "qcode" |
| `extraction_version` | str | |

### legislation

Source: LegiScan (CA + federal)

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | |
| `bill_id` | str | e.g., `ca-sb123` |
| `state` | str | "CA", "US" |
| `bill_number` | str | |
| `bill_name` | str | |
| `status` | str | LegiScan status code |
| `status_label` | str | Human-readable |
| `summary` | str | |
| `full_text` | str | |
| `leverage_point` | str | |
| `keywords` | jsonb | |
| `topic` | str | LLM-classified |
| `enacted_date` | str | |
| `official_url` | str | |
| `local_implementation_required` | bool | |
| `local_deadline` | str | |
| `jurisdiction_id` | str | |
| `legiscan_id` | int | |
| `metadata` | jsonb | |

### executive_orders

Source: Federal Register

| Column | Type | Notes |
|--------|------|-------|
| `id` | int | |
| `document_number` | str | FR document number |
| `title` | str | |
| `president` | str | |
| `eo_number` | int | |
| `president_id` | str | |
| `abstract` | str | |
| `full_text` | str | |
| `signing_date` | str | |
| `publication_date` | str | |
| `html_url` | str | |
| `pdf_url` | str | |
| `status` | str | active, revoked |
| `revoked_by_eo` | int | |
| `metadata` | jsonb | |

### federal_expenditures

Source: Federal Audit Clearinghouse (FAC)

| Column | Type | Notes |
|--------|------|-------|
| `report_id` | str | FAC report ID |
| `cfda_number` | str | |
| `audit_year` | int | |
| `amount_expended_dollars` | float | |
| `federal_program_total_dollars` | float | |
| `cluster_total_dollars` | float | |
| `federal_program_name` | str | |
| `cluster_name` | str | |
| `federal_agency_prefix` | str | |
| `is_major` | bool | |
| `is_passthrough` | bool | |
| `source_url` | str | |

### intergovernmental_revenue

Source: CA State Controller

| Column | Type | Notes |
|--------|------|-------|
| `fiscal_year` | int | |
| `form_table` | str | SCO form code |
| `source` | str | federal, state, county, undetermined |
| `amount_dollars` | float | |
| `category` | str | |
| `subcategory` | str | |
| `line_description` | str | |
| `entity_name` | str | |
| `county` | str | |

### coordination_rate_limits

Source: Relay acceptance policy (auto-populated)

| Column | Type | Notes |
|--------|------|-------|
| `public_key_hash` | str | SHA-256 of pubkey, truncated to 16 hex chars |
| `event_type` | str | voice, comment, initiative, action_create, action_commit, action_complete |
| `day` | date | Current date (auto-set) |
| `count` | int | Number of writes today |

Primary key: `(public_key_hash, event_type, day)`. Rows older than 7 days are cleaned up on relay startup.

### coordination_write_metadata

Source: Relay acceptance policy (auto-populated)

| Column | Type | Notes |
|--------|------|-------|
| `public_key_hash` | str | SHA-256 of pubkey, truncated to 16 hex chars |
| `entity` | str | Entity written to |
| `acceptance_tier` | str | attested, paid, rate_limited, legacy |
| `accepted_at` | timestamptz | When the write was accepted |

Primary key: `(public_key_hash, entity)`. Migration: `scripts/sql/add_relay_acceptance_policy.sql`.

## Vector Embeddings

All corpora are semantically indexed using OpenAI embeddings stored in pgvector (`vector_embeddings` table).

| Corpus Type | Count | Enables |
|-------------|-------|---------|
| `transcripts` | ~4,296 | `what_was_said()`, `get_public_testimony()` |
| `chunks` | ~5,084 | PDF/agenda packet search |
| `municipal_code` | ~5,857 | Legal code search |
| `issues` | ~1,459 | Issue search |
| `decisions` | ~44 | `what_happened()` semantic search |
| `meetings` | ~46 | Meeting search |

Corpus types defined in `packages/civicos/src/civicos/storage/corpus_types.py`.

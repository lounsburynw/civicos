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

### coordination_feedback

Source: User feedback (kind 1804)

| Column | Type | Notes |
|--------|------|-------|
| `id` | str | Primary key |
| `feedback_type` | str | bug, feature, general |
| `content` | str | Free-text feedback body |
| `public_key` | str | Hex-encoded pubkey |
| `jurisdiction` | str | |
| `created_at` | timestamptz | |

Rate limited: 10/hour per pubkey. Stored on relay database (`RELAY_DATABASE_URL`).

### platform_api_keys

Source: API key management (tiered access)

| Column | Type | Notes |
|--------|------|-------|
| `key_id` | str | Format: `cvk_{8_hex_chars}` |
| `key_hash` | str | SHA-256 of raw key |
| `name` | str | Human-readable name |
| `email` | str | Contact email |
| `tier` | str | open, free, builder, organization, city, admin |
| `status` | str | active, suspended, revoked |
| `rate_limit_per_minute` | int | |
| `jurisdictions` | jsonb | Array of jurisdiction IDs |
| `stripe_customer_id` | str | Stripe integration |
| `stripe_subscription_id` | str | Stripe integration |
| `expires_at` | timestamptz | |
| `created_at` | timestamptz | |
| `last_used_at` | timestamptz | |

Stored on platform database (`PLATFORM_DATABASE_URL` or fallback to `DATABASE_URL`).

### platform_usage_logs

Source: API usage tracking

| Column | Type | Notes |
|--------|------|-------|
| `key_id` | str | FK to platform_api_keys |
| `endpoint` | str | |
| `method` | str | HTTP method |
| `status_code` | int | |
| `response_time_ms` | float | |
| `jurisdiction` | str | |
| `timestamp` | timestamptz | |

### operating_costs

Source: Cost tracking instrumentation

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial | Primary key |
| `service` | str | openai, modal, assemblyai, r2, supabase, google |
| `category` | str | llm, compute, transcription, storage, database, geocoding |
| `amount_dollars` | float | |
| `metadata` | jsonb | Service-specific (model, tokens, function_name, gpu_type, etc.) |
| `jurisdiction_id` | str | |
| `recorded_at` | timestamptz | |

## Vector Embeddings

All corpora are semantically indexed using OpenAI embeddings stored in pgvector (`vector_embeddings` table), **partitioned by `corpus_type`** using PostgreSQL LIST partitioning.

### Schema

```sql
CREATE TABLE vector_embeddings (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    corpus_type TEXT NOT NULL,          -- Partition key
    content TEXT NOT NULL,
    embedding vector(768),              -- pgvector column
    embedding_model TEXT DEFAULT 'unknown',
    meeting_id TEXT,
    meeting_title TEXT,
    meeting_datetime TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY LIST (corpus_type);
```

### Partitions

Each corpus type has its own partition (15 total) with an independent HNSW index. This avoids contention during bulk inserts — only the target partition's index is affected.

| Corpus Type | Count (as of March 2026) | Enables |
|-------------|-------|---------|
| `transcripts` | ~4,296 | `what_was_said()`, `get_public_testimony()` |
| `chunks` | ~5,084 | PDF/agenda packet search |
| `municipal_code` | ~5,857 | Legal code search |
| `issues` | ~1,459 | Issue search |
| `decisions` | ~44 | `what_happened()` semantic search |
| `meetings` | ~46 | Meeting search |

### HNSW Index Management

Per-partition HNSW indexes use `m=16, ef_construction=64`. For bulk inserts, use deferred indexing:

1. `drop_hnsw_index(corpus_type)` — Drop the partition's HNSW index
2. Execute bulk inserts (no per-row HNSW maintenance)
3. `rebuild_hnsw_index(corpus_type)` — Rebuild using session pooler (port 5432, required for SET commands)

Rebuild sets `statement_timeout=30min`, `maintenance_work_mem=256MB`. Parallel rebuilds across partitions are safe (each uses a separate connection).

### Connection Modes

- **Transaction pooler** (port 6543): Default for queries. Does not support SET statements.
- **Session pooler** (port 5432): Required for DDL and SET commands (index rebuild, maintenance_work_mem).

Corpus types defined in `packages/civicos/src/civicos/storage/corpus_types.py`.

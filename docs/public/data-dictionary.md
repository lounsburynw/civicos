# Data Dictionary

Types returned by the CivicOS API. All amounts are in **dollars**. All dates are ISO 8601 datetimes.

For storage-level schemas (database columns, internal fields), see [docs/internal/storage-schema.md](../internal/storage-schema.md).

## Meetings & Decisions

### Decision

Returned by `what_happened()`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique decision ID |
| `title` | str | Decision title |
| `date` | datetime | Date of the meeting |
| `outcome` | str | One of: `approved`, `denied`, `continued`, `withdrawn`, `received`, `adopted`, `other` |
| `body` | str | Governing body (e.g., "City Council") |
| `votes` | dict | Vote details (see below) |

**votes object:** `{ ayes, noes, absent, motion_by, second_by, passed, unanimous, vote_count }` — may be `null` for consent calendar items.

### DecisionWithContext

Returned by `what_happened_full_context()`. A decision enriched with linked transcript excerpts.

| Field | Type | Description |
|-------|------|-------------|
| `decision` | Decision | The decision (see above) |
| `transcript_links` | list | Linked transcript excerpts (see TranscriptExcerpt) |
| `link_confidence` | float | Overall confidence of decision-to-transcript linking |
| `link_type` | str | `"high_confidence"`, `"medium_confidence"`, `"low_confidence"`, `"none"` |

Properties: `has_transcript`, `public_comments`, `staff_discussion`, `council_discussion`

### Meeting

Returned by `whats_next()`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique meeting ID |
| `title` | str | Meeting name (e.g., "City Council Regular Meeting") |
| `date` | datetime | Meeting date and time |
| `body` | str | Governing body |
| `location` | str | Physical location |
| `agenda_items` | list | Agenda items (see below) |

**Agenda item fields:** `title`, `project_type` (category), `actionability`, `impact_level`, `financial_impact_cents` (int), `participation_guide`

### TranscriptExcerpt

Returned by `what_was_said()` and `get_public_testimony()`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Excerpt ID |
| `text` | str | Transcript text |
| `speaker` | str | Speaker name |
| `speaker_role` | str | `"council"`, `"staff"`, `"public"`, etc. |
| `video_id` | str | YouTube video ID |
| `start_timestamp` | str | Start time (HH:MM:SS) |
| `end_timestamp` | str | End time (HH:MM:SS) |
| `is_public_comment` | bool | Whether this is public testimony |
| `score` | float | Search relevance score |

Property: `video_url` — YouTube link with timestamp (e.g., `https://youtube.com/watch?v=...&t=123s`)

### RegulatoryStack

Returned by `what_applies()`.

| Field | Type | Description |
|-------|------|-------------|
| `topic` | str | Search topic |
| `jurisdiction` | str | Jurisdiction ID |
| `federal` | list | Federal legislation matches |
| `state` | list | State legislation matches |
| `local` | list | Municipal code section matches |

Each item in `federal`/`state` is a Legislation object. Each item in `local` is a MunicipalCodeSection.

## Legislation

### Legislation

Returned within `RegulatoryStack` and via `/api/legislation/` endpoints.

| Field | Type | Description |
|-------|------|-------------|
| `bill_id` | str | Unique bill identifier (e.g., `ca-sb123`) |
| `state` | str | State code (`"CA"`, `"US"`) |
| `bill_number` | str | Bill number (e.g., "SB 123") |
| `bill_name` | str | Full bill title |
| `status` | str | Legislative status code |
| `summary` | str | Bill summary |
| `leverage_point` | str | How citizens can engage |
| `keywords` | list | Topic keywords |
| `local_implementation_required` | bool | Whether cities must act |

Source: LegiScan (CA + federal bills)

### Executive Order

Returned via `/api/legislation/` endpoints.

| Field | Type | Description |
|-------|------|-------------|
| `document_number` | str | Federal Register document number |
| `title` | str | Executive order title |
| `president` | str | Issuing president |
| `eo_number` | int | EO number |
| `abstract` | str | Summary |
| `signing_date` | str | Date signed |
| `status` | str | `"active"`, `"revoked"` |
| `revoked_by_eo` | int | EO number that revoked this one |

Source: Federal Register

### Municipal Code Section

Returned within `RegulatoryStack.local`.

| Field | Type | Description |
|-------|------|-------------|
| `section_number` | str | Section number (e.g., "14.01.020") |
| `section_title` | str | Section heading |
| `full_text` | str | Complete section text |
| `chapter` | str | Chapter number |
| `chapter_title` | str | Chapter heading |

Source: Municode

## Budget & Finance

### BudgetItem

Returned by `budget()`.

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

### BudgetSummary

Returned by `budget_summary()`.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Department, fund, or program name |
| `budgeted_dollars` | float | Total budgeted |
| `item_count` | int | Number of line items |
| `revised_dollars` | float | Revised total |
| `actual_dollars` | float | Actual spending total |

### FederalExpenditure

Returned by `federal_expenditures()`. Audited federal spending from the Single Audit.

| Field | Type | Description |
|-------|------|-------------|
| `cfda_number` | str | CFDA program number (e.g., "93.778") |
| `federal_program_name` | str | Program name (e.g., "MEDICAL ASSISTANCE PROGRAM") |
| `amount_expended_dollars` | float | Amount expended |
| `audit_year` | int | Audit year |
| `cluster_name` | str | Cluster name (e.g., "MEDICAID CLUSTER") |
| `is_major` | bool | Major program flag |
| `is_passthrough` | bool | Pass-through flag |
| `source_url` | str | Link to FAC report |

Source: Federal Audit Clearinghouse (FAC)

### IntergovernmentalRevenueSummary

Returned by `intergovernmental_revenue()`. Revenue from federal, state, and county sources.

| Field | Type | Description |
|-------|------|-------------|
| `fiscal_year` | int | Fiscal year |
| `entity_name` | str | City name |
| `federal_total_dollars` | float | Total federal revenue |
| `state_total_dollars` | float | Total state revenue |
| `county_total_dollars` | float | Total county revenue |
| `total_dollars` | float | Grand total |
| `details` | list | Line-item breakdown (see below) |

**Detail fields:** `source` ("federal"/"state"/"county"), `amount_dollars` (float), `category`, `subcategory`, `line_description`

Source: CA State Controller

### FundingFlow

Returned by `funding_flow()`. Traces federal-to-state-to-city funding paths.

> **Note:** Linkage data not yet available for all jurisdictions.

| Field | Type | Description |
|-------|------|-------------|
| `budget_item_id` | str | City budget item ID |
| `budget_description` | str | Budget line description |
| `budget_dollars` | float | City-level amount |
| `department` | str | City department |
| `federal_cfda_number` | str | Federal CFDA number |
| `federal_program_name` | str | Federal program name |
| `federal_dollars` | float | Federal award amount |
| `match_confidence` | float | Linkage confidence (0.0–1.0) |

### FundingFlowImpact

Returned by `funding_flow_impact()`. Models hypothetical funding cuts.

> **Note:** Depends on funding flow linkage data (see above).

| Field | Type | Description |
|-------|------|-------------|
| `program_name` | str | Program being cut |
| `cut_percentage` | float | Cut percentage (e.g., 0.20) |
| `total_current_dollars` | float | Current funding level |
| `total_impact_dollars` | float | Dollar impact of cut |
| `affected_items` | list | Affected FundingFlow items |

## Voting Records

### VotingRecord

Returned by `get_voting_record()`.

| Field | Type | Description |
|-------|------|-------------|
| `official_name` | str | Display name |
| `topic` | str | Topic filter (if applied) |
| `total_votes` | int | Total votes cast |
| `yes_votes` | int | Yes/aye votes |
| `no_votes` | int | No/nay votes |
| `abstain_votes` | int | Abstentions/absences |
| `decisions` | list | Vote details: `decision_id`, `title`, `date`, `vote` |

Properties: `yes_percentage`, `no_percentage`, `abstain_percentage`

## Community Issues

### Issue (SeeClickFix / 311)

Returned via `/api/operational-issues/`.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | str | SeeClickFix issue ID |
| `issue_type` | str | Category (e.g., "Pothole", "Graffiti") |
| `address` | str | Location address |
| `latitude` | float | GPS latitude |
| `longitude` | float | GPS longitude |
| `status` | str | Resolution status |

Source: SeeClickFix (311)

## AI Actions

### ActionDraft

Returned by `draft_action()`.

| Field | Type | Description |
|-------|------|-------------|
| `draft` | str | Generated text (public comment, letter, etc.) |
| `description` | str | Action description |
| `citations` | list | Source citations |

## Data Coverage (San Rafael Pilot)

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | ProudCity |
| Decisions | ~44 | Minutes extraction |
| Transcripts | ~19 | YouTube + AssemblyAI |
| Agenda packets | ~5,084 chunks | City agenda PDFs |
| Municipal code | ~16,175 sections | Municode |
| Community issues | ~1,730 | SeeClickFix (311) |
| Budget items | ~58 | FY25-26 budget ($180M) |
| Legislation | ~17,719 | LegiScan (CA + federal) |
| Federal expenditures | 52 | FAC Single Audit |
| Intergovernmental revenue | 10 line items | CA State Controller |

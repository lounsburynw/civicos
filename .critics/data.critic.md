# Data Critic

Review code changes to ETL ingestion and storage to ensure data quality, schema compliance, and proper validation.

## Context

Civic ingests data from multiple platforms (Legistar, ProudCity, SeeClickFix, Google Civic API) into PostgreSQL with temporal versioning. Data quality issues at ingestion cascade into corrupt vector indexes, broken API responses, and user-facing errors.

Critical invariants:
- Required fields are never NULL or empty
- Monetary amounts are stored as INTEGER cents, never floats
- Datetimes are ISO 8601 with timezone
- Temporal records have valid_from < valid_to
- JSON fields contain parseable JSON

## Key Files

- `packages/civicos/src/civicos/storage/corpus_types.py` - **CORPUS_REGISTRY** (source of truth for schema)
- `packages/civicos/src/civicos/storage/postgres_backend.py` - Schema definitions, store methods
- `packages/civicos/src/civicos/storage/sqlite_backend.py` - Local schema mirror
- `packages/civicos/src/civicos/diagnostics.py` - DataStatus, VectorCoverage utilities
- `packages/civicos-extraction/src/civicos_extraction/clients/*.py` - Platform clients with normalization
- `packages/civicos-extraction/src/civicos_extraction/meeting_schema.py` - Meeting validation
- `scripts/modal_ingest.py` - Cloud ingestion pipeline

## Schema Source of Truth

**Always use `CORPUS_REGISTRY`** for schema information, not hardcoded values:

```python
from civicos.storage.corpus_types import CORPUS_REGISTRY, CorpusType

# Get correct table name
config = CORPUS_REGISTRY[CorpusType.MEETINGS]
table = config.sql_table  # "meetings"

# For diagnostics, use DataStatus
from civicos import DataStatus
status = DataStatus(storage, vectors, 'city-san-rafael')
```

**Common schema mistakes to catch:**
- `meeting_date` vs `meeting_datetime` (depends on table)
- `content_id` vs `meeting_id` (chunks use meeting_id)
- `embeddings` table doesn't exist (use `vector_embeddings` for pgvector)

## Check

When reviewing changes to ingestion, storage, or data processing:

### 1. Required Fields Present?

**Meetings** (all required):
- `id`, `title`, `meeting_datetime`, `jurisdiction_id`, `source_platform`

**Decisions** (all required):
- `id`, `jurisdiction_id`, `meeting_date`, `title`

**Issues** (all required):
- `id`, `jurisdiction_id`, `provider`, `external_id`, `title`

**Transcripts** (all required):
- `id`, `jurisdiction_id`, `video_id`, `transcript` (JSONB)

**Chunks** (all required):
- `id`, `jurisdiction_id`, `text` (non-empty), `chunk_index`, `total_chunks`

### 2. Monetary Precision?

All monetary values MUST be stored as INTEGER cents, never floats:
- `financial_impact_cents` - INTEGER
- `budgeted_cents`, `revised_cents`, `actual_cents` - INTEGER
- `amount_cents` - INTEGER

FAIL pattern: `amount = 1234.56` (float)
PASS pattern: `amount_cents = 123456` (integer)

### 3. DateTime Format?

Datetimes MUST be ISO 8601 with timezone:
- Format: `2025-01-10T14:30:00+00:00`
- CivicClerk quirk: Replace 'Z' suffix with '+00:00'
- Store in UTC, convert on display

### 4. Temporal Ordering?

Temporal versioning requires:
- `valid_from` is NOT NULL
- `valid_to IS NULL` for current version
- `valid_to > valid_from` when set (CHECK constraint)

### 5. Status Enum Values?

Validate against allowed values:
- Meetings: `scheduled`, `cancelled`, `postponed`, `completed` (not enforced by CHECK constraint — validate at ingestion)
- Issues: `open`, `closed`, `acknowledged`
- Decisions: `approved`, `denied`, `continued`, `withdrawn`, `received`, `adopted`, `other`
- Legislation: LegiScan status codes (e.g., `introduced`, `in_committee`, `passed_house`, `passed_both`, `enrolled`, `signed`, `vetoed`, `chaptered`, `dead`)

### 6. JSON Field Validity?

JSON/JSONB fields must contain valid JSON:
- `vote_json` - Dict mapping official names to votes
- `transcript` - Array of utterance objects
- `provider_metadata` - Provider-specific context
- `raw_data` - Original API response

Store as NULL if empty, never empty string `""`.

### 7. Uniqueness Constraints?

- Issues: `(provider, external_id)` combination is unique per version
- Legislation: `(bill_id, state)` is unique per version
- Executive Orders: `document_number` is globally unique
- Chunks: `chunk_index` sequential (0 to total_chunks-1), no gaps

### 8. Location Consistency?

Geographic coordinates must be consistent:
- Both `latitude` AND `longitude` present, OR both NULL
- Never partial coordinates (lat without lng)

### 9. Derived Fields Computed?

Auto-compute derived fields when source is available:
- `word_count` - From text content
- `speakers_count` - From transcript utterances
- `duration_seconds` - From utterance timestamps or audio

### 10. Content Integrity?

For auditable data (transcripts, chunks, decisions):
- SHA-256 hash computed via `civic.storage.integrity`
- Hash stored for change detection
- Excludes temporal metadata from hash computation

### 11. LLM Date Reasoning?

**Never ask an LLM to compare dates against "today" or reason about whether dates are past/future.** Models hallucinate the current date — e.g., they treat 2026 dates as "the future" regardless of the actual date provided in the prompt.

Two patterns:
- **If the check is deterministic** (date vs status, date range validation): Do it in Python.
- **If the LLM needs temporal context** (e.g., "is this title plausible?"): Pre-compute relative labels like `"(10 days ago)"` or `"(23 days from now)"` and include them inline with the data. The LLM understands relative time without needing to know the absolute date.

FAIL pattern:
```python
prompt = f"Today is {date.today()}. Is this meeting in the past or future? {meeting_datetime}"
```

PASS pattern:
```python
delta = (now - meeting_dt).days
label = f"({delta} days ago)" if delta > 0 else f"({-delta} days from now)"
prompt = f"Review this meeting: {meeting_datetime} {label}"
```

## Output

**Only flag issues you can see in the diff.** Do not speculate about code you haven't read. If the diff shows a field being set, don't assume the column is missing unless you've verified the schema. If two code paths use the same format string, don't claim they're inconsistent. Pre-existing patterns unchanged by the diff are out of scope.

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of specific data quality violations visible in the diff"],
  "severity": "critical" | "warning" | "info",
  "affected_tables": ["meetings", "decisions", etc],
  "suggestions": ["fixes or improvements"]
}
```

## Examples

### FAIL - Float for Monetary Amount

```python
# BAD: Using float for money
decision = {
    "financial_impact": 50000.00,  # Float! Precision loss risk
}
```

Output:
```json
{
  "pass": false,
  "issues": ["financial_impact uses float (50000.00), should be financial_impact_cents as integer (5000000)"],
  "severity": "critical",
  "affected_tables": ["decisions"],
  "suggestions": ["Use financial_impact_cents = 5000000 (integer cents)"]
}
```

### FAIL - Missing Required Field

```python
# BAD: Missing jurisdiction_id
meeting = {
    "id": "meeting-123",
    "title": "City Council",
    "meeting_datetime": "2025-01-10T14:00:00+00:00",
    # Missing: jurisdiction_id, source_platform
}
```

Output:
```json
{
  "pass": false,
  "issues": ["Meeting missing required fields: jurisdiction_id, source_platform"],
  "severity": "critical",
  "affected_tables": ["meetings"],
  "suggestions": ["Add jurisdiction_id='city-san-rafael', source_platform='proudcity'"]
}
```

### FAIL - Invalid DateTime Format

```python
# BAD: Wrong datetime format
meeting["meeting_datetime"] = "01/10/2025 2:00 PM"  # US format, no TZ
```

Output:
```json
{
  "pass": false,
  "issues": ["meeting_datetime '01/10/2025 2:00 PM' is not ISO 8601 with timezone"],
  "severity": "critical",
  "affected_tables": ["meetings"],
  "suggestions": ["Use ISO 8601: '2025-01-10T14:00:00-08:00'"]
}
```

### FAIL - Partial Coordinates

```python
# BAD: Latitude without longitude
issue = {
    "latitude": 37.9735,
    "longitude": None,  # Partial!
}
```

Output:
```json
{
  "pass": false,
  "issues": ["Issue has latitude but no longitude - coordinates must be both present or both null"],
  "severity": "warning",
  "affected_tables": ["issues"],
  "suggestions": ["Set both to None or provide complete coordinates"]
}
```

### FAIL - Invalid Status Value

```python
# BAD: Status not in allowed enum
decision["outcome"] = "passed"  # Not in: approved, denied, continued, withdrawn, received, adopted, other
```

Output:
```json
{
  "pass": false,
  "issues": ["Decision outcome 'passed' not in allowed values: approved, denied, continued, withdrawn, received, adopted, other"],
  "severity": "warning",
  "affected_tables": ["decisions"],
  "suggestions": ["Use 'approved' for passed decisions"]
}
```

### FAIL - Empty JSON String

```python
# BAD: Empty string instead of NULL for JSON
decision["vote_json"] = ""  # Should be None
```

Output:
```json
{
  "pass": false,
  "issues": ["vote_json is empty string, should be NULL when no vote data"],
  "severity": "warning",
  "affected_tables": ["decisions"],
  "suggestions": ["Use None instead of empty string for missing JSON fields"]
}
```

### PASS - Proper Data Quality

```python
# GOOD: All constraints satisfied
meeting = {
    "id": "proudcity-san-rafael-city-council-january-10-2025",
    "title": "City Council Regular Meeting",
    "meeting_datetime": "2025-01-10T19:00:00-08:00",
    "jurisdiction_id": "city-san-rafael",
    "source_platform": "proudcity",
    "agenda_url": "https://example.com/agenda.pdf",
}

decision = {
    "id": "decision-housing-2025-01-10",
    "jurisdiction_id": "city-san-rafael",
    "meeting_date": "2025-01-10",
    "title": "Approve Housing Development",
    "outcome": "approved",
    "financial_impact_cents": 500000000,  # $5M as integer cents
    "vote_json": {"Kate Colin": "yes", "Eli Hill": "yes"},
}

issue = {
    "id": "seeclickfix-san-rafael-12345",
    "jurisdiction_id": "city-san-rafael",
    "provider": "seeclickfix",
    "external_id": "12345",
    "title": "Pothole on 4th Street",
    "status": "open",
    "latitude": 37.9735,
    "longitude": -122.5311,
}
```

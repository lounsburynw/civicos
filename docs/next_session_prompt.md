# Recommended: legislation_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 401. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 401 added vector infrastructure for new corpus types (transcripts, municipal_code, issues) but pivoted to `legislation_e2e_cloud` before running indexing. CA state legislation needs to be in Postgres before vector indexing can include it.

**Good news:** Significant infrastructure already exists!

## What Already Exists

### 1. LegiScan API Client
`packages/civic-services/src/civic_services/clients/legiscan_client.py`
- Free tier: 30,000 queries/month
- Methods: `search_bills()`, `get_bill_details()`, `get_master_list()`, `get_recent_bills()`
- State codes: California = "CA"

### 2. Legislative CLI
`packages/civic-extraction/src/civic_extraction/cli/legislative.py`
```bash
civic-extract legislative --topic housing        # Single topic
civic-extract legislative --topic all            # All topics
civic-extract legislative --topic housing --dry-run
```
Topics: housing, transportation, environment, budget, education

### 3. Existing Data (JSON files)
`data/legislation/state/california/`
- housing.json (9 bills with rich metadata)
- transportation.json, environment.json, budget.json, education.json

Example bill structure from housing.json:
```json
{
  "ca-sb9": {
    "bill": "California Housing Opportunity and More Efficiency (HOME) Act",
    "status": "Active",
    "enacted": "2021-09-16",
    "leverage_point": "Residents can advocate for local compliance...",
    "official_url": "https://leginfo.legislature.ca.gov/...",
    "summary": "SB 9 allows homeowners to split single-family lots...",
    "keywords": ["housing", "zoning", "density", "lot split"],
    "_legiscan_id": 1234567
  }
}
```

### 4. LLM-Assisted Relevance Filtering
`packages/civic-services/src/civic_services/legislative/legislative_discovery.py`
- Filters bills for local actionability
- Generates "leverage_point" for citizen engagement

## What's Missing

1. **No `legislation` table in Postgres** - schema needs to be created
2. **No `--cloud` mode** in legislative CLI - writes to JSON files only
3. **No `store_legislation()` / `get_legislation()` methods** in PostgresBackend

## Task

Ingest California state legislation to Postgres `legislation` table.

## Suggested Approach

### Step 1: Add legislation table schema
Add to `packages/civic/src/civic/storage/postgres_backend.py`:

```sql
CREATE TABLE IF NOT EXISTS legislation (
    id SERIAL PRIMARY KEY,
    bill_id TEXT NOT NULL UNIQUE,        -- e.g., "ca-sb9"
    state TEXT NOT NULL,                 -- e.g., "CA"
    jurisdiction_id TEXT,                -- NULL for state-level
    bill_number TEXT,                    -- e.g., "SB 9"
    bill_name TEXT,                      -- Full name
    status TEXT,                         -- "Active", "Enacted", "Failed"
    enacted_date DATE,
    summary TEXT,
    leverage_point TEXT,                 -- For civic engagement
    official_url TEXT,
    keywords JSONB,
    topic TEXT,                          -- "housing", "transportation", etc.
    local_implementation_required BOOLEAN,
    local_deadline DATE,
    legiscan_id INTEGER,                 -- LegiScan API reference
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP
);
```

### Step 2: Add storage methods
Add to PostgresBackend:
- `store_legislation(state, bill_data)`
- `get_legislation(state, topic=None)`
- `get_legislation_count(state)`

### Step 3: Update CLI
Add `--cloud` flag to `civic-extract legislative`:
- When `--cloud`: store to Postgres instead of JSON
- Option A: Migrate existing JSON data
- Option B: Re-fetch from LegiScan (ensures fresh data)

### Step 4: Run ingestion
```bash
civic-extract legislative --topic all --cloud
```

## Key Files to Modify

| File | Changes |
|------|---------|
| `packages/civic/src/civic/storage/postgres_backend.py` | Add legislation table schema + store/get methods |
| `packages/civic-extraction/src/civic_extraction/cli/legislative.py` | Add `--cloud` flag |

## API Keys Required

```bash
# In .env
LEGISCAN_API_KEY=xxx    # Free: https://legiscan.com/ (30k queries/month)
OPENAI_API_KEY=xxx      # For LLM relevance filtering (optional)
```

## Tests to Run

```bash
# Check existing CLI works
civic-extract legislative --topic housing --dry-run

# After implementation
civic-extract legislative --topic housing --cloud --dry-run
civic-extract legislative --topic all --cloud
```

## Verification Query

```sql
SELECT COUNT(*) FROM legislation WHERE state = 'CA'
```

## Success Criteria

- [ ] `legislation` table exists in Postgres with temporal versioning
- [ ] `store_legislation()` / `get_legislation()` methods work
- [ ] `civic-extract legislative --topic all --cloud` ingests all topics
- [ ] Key CA housing bills (SB 9, SB 35, AB 2011, etc.) are in Postgres
- [ ] Mark `legislation_e2e_cloud` as ready in pilot.json

## Session 401 Uncommitted Changes

The following changes were made but NOT committed:

1. **pgvector_backend.py** - Added vector support for transcripts, municipal_code, issues corpus types
2. **vectors.py CLI** - Updated with new corpus types
3. **pilot.json** - Updated priorities:
   - `legislation_e2e_cloud` → P0
   - `vectors_e2e_cloud` → P1 (added "legislation" to target_count)
   - Added new `federal_legislation_e2e_cloud` → P2

Run `git diff` to see all changes. Consider committing infrastructure changes before starting legislation work.

## Future: Federal Legislation (P2)

A separate item `federal_legislation_e2e_cloud` was added at P2 for federal programs (CDBG, HUD, IIJA). LegiScan supports `state='US'` for Congress queries. Lower priority since CA state legislation is more directly actionable at city council meetings.

## Data Sources

- [LegiScan API](https://legiscan.com/legiscan) - 30k free queries/month
- [LegiScan CA Datasets](https://legiscan.com/CA/datasets) - Bulk downloads
- [CA Legislative Info](https://leginfo.legislature.ca.gov/) - Official bill text

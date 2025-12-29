# Recommended: federal_legislation_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 403. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 402 completed CA state legislation ingestion (2,839 bills via bulk LegiScan API). Now we need to ingest **federal legislation** affecting local governance using the same infrastructure.

## What Already Exists

### 1. LegiScan API Client
`packages/civic-services/src/civic_services/clients/legiscan_client.py`
- Free tier: 30,000 queries/month
- Methods: `get_master_list(state)` - **Use `state='US'` for Congress**
- Session 402 used bulk approach: 1 API call gets all bills for a session

### 2. Legislative CLI with Cloud Support
`packages/civic-extraction/src/civic_extraction/cli/legislative.py`
```bash
civic-extract legislative --bulk --cloud           # Bulk ingest all bills
civic-extract legislative --migrate-json --cloud   # Migrate curated JSON
```

### 3. Postgres Infrastructure (Ready)
- `legislation` table exists with temporal versioning
- `store_legislation()` / `get_legislation()` methods work
- pgvector indexing works for legislation corpus

### 4. CA Legislation Complete
```sql
SELECT COUNT(*) FROM legislation WHERE state = 'CA'
-- Returns: 2,839
```

## Task

Ingest federal legislation to Postgres `legislation` table using `state='US'`.

## Key Federal Programs for Local Governance

Target legislation affecting municipalities:
- **CDBG** - Community Development Block Grant
- **HUD programs** - Housing and Urban Development
- **IIJA** - Infrastructure Investment and Jobs Act
- **IRA** - Inflation Reduction Act (climate/energy provisions)
- **ARP** - American Rescue Plan (local fiscal recovery)

## Suggested Approach

### Option A: Bulk Ingestion (Recommended)
Modify CLI to support federal bills:
```bash
civic-extract legislative --bulk --cloud --state US
```

The existing `--bulk` mode calls `get_master_list(state)` which should work with `state='US'` for Congress.

### Option B: Targeted Ingestion
Search for specific federal programs:
```bash
civic-extract legislative --topic "CDBG" --cloud --state US
civic-extract legislative --topic "infrastructure" --cloud --state US
```

### Implementation Steps

1. **Update CLI** to accept `--state` parameter (default: CA)
2. **Test LegiScan API** with `state='US'` to verify it returns Congress bills
3. **Run bulk ingestion**: `civic-extract legislative --bulk --cloud --state US`
4. **Verify**: `SELECT COUNT(*) FROM legislation WHERE state = 'US'`

## Key Files

| File | Purpose |
|------|---------|
| `packages/civic-extraction/src/civic_extraction/cli/legislative.py` | Add `--state` parameter |
| `packages/civic-services/src/civic_services/clients/legiscan_client.py` | LegiScan API client |
| `packages/civic/src/civic/storage/postgres_backend.py` | Already has legislation storage |

## API Consideration

LegiScan free tier: 30,000 queries/month
- CA bulk ingestion used ~1 query (master list)
- US Congress bulk should also be ~1 query
- Budget is fine

## Verification

```sql
-- Check federal legislation count
SELECT COUNT(*) FROM legislation WHERE state = 'US'

-- Check key programs exist
SELECT bill_number, bill_name FROM legislation
WHERE state = 'US' AND (
  summary ILIKE '%CDBG%' OR
  summary ILIKE '%community development block%' OR
  summary ILIKE '%infrastructure%'
)
LIMIT 10
```

## Success Criteria

- [ ] CLI accepts `--state US` parameter
- [ ] Federal bills ingested to Postgres with `state='US'`
- [ ] Key programs (CDBG, HUD, IIJA) are findable
- [ ] Mark `federal_legislation_e2e_cloud` as ready in pilot.json

## After This: vectors_e2e_cloud (P1)

Once federal legislation is complete, the next priority is building vector indexes for remaining corpus types (chunks, decisions, issues, municipal_code, transcripts). Legislation vectors are already done.

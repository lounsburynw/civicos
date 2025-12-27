# Recommended: agenda_items_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-27

> This is recommended context from Session 387. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 387 completed `api_cloud_storage_backend` - the API server now correctly reads from cloud Postgres when `DATABASE_URL` is set. Data Browser shows 46 meetings and 1,330 issues from cloud.

**CRITICAL REQUIREMENT:** All data must be ingested E2E to cloud storage from scratch. NO MIGRATION from local. This validates the production pipeline actually works.

## Current Cloud Data Status

| Data Type | Cloud Count | Status | Action |
|-----------|-------------|--------|--------|
| Meetings | 46 | ready | Done |
| Issues | 1,330 | ready | Done |
| **Agenda Items** | **0** | **P0** | **NEXT** |
| Decisions | 0 | P1 | Pending |
| Chunks (PDFs) | 0 | P1 | Pending |
| Transcripts | 0 | P1 | Pending |
| Municipal Code | 0 | P1 | Pending |
| Legislation | 0 | P2 | Pending |
| Vector Indexes | 0 | P1 | After SQL data |

## Recommended Task

Run the agenda item extraction pipeline to populate cloud Postgres with agenda items E2E. The 46 meetings exist in cloud - now extract their agenda items.

## Key Files

1. **Extraction CLI:** `packages/civic-extraction/src/civic_extraction/` - look for agenda item extraction
2. **Storage Backend:** `packages/civic/src/civic/storage/postgres_backend.py` - has `store_meetings()` pattern to follow
3. **Pipeline:** `packages/civic-extraction/src/civic_extraction/pipeline.py` - 4-stage ETL

## Suggested Approach

### Step 1: Find agenda extraction code
```bash
grep -rn "agenda" packages/civic-extraction/src/
grep -rn "agenda_items" packages/civic/src/civic/storage/
```

### Step 2: Run extraction against cloud
```bash
# Ensure DATABASE_URL is set
source .env
civic-extract agenda --cloud --jurisdiction city-san-rafael
# OR
civic-extract pipeline --stage=extract --cloud
```

### Step 3: Verify in Data Browser
```bash
./scripts/dev.sh
# Check Data Browser - agenda_items should show count > 0
curl -H "Authorization: Bearer dev_key_local" "http://localhost:8001/api/admin/data/agenda_items?jurisdiction=san-rafael&per_page=1"
```

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v
```

## Success Criteria

- [ ] Agenda items extracted from meeting pages and stored in cloud Postgres
- [ ] Data Browser shows agenda_items count > 0 (proportional to 46 meetings)
- [ ] `pilot.json` item `agenda_items_e2e_cloud` marked as ready

## E2E Cloud Verification Checklist

From `pilot.json` section `e2e_cloud_data_verification`:

```
agenda_items_e2e_cloud     P0  <- THIS SESSION
decisions_e2e_cloud        P1
chunks_e2e_cloud           P1
transcripts_e2e_cloud      P1
municipal_code_e2e_cloud   P1
legislation_e2e_cloud      P2
vectors_e2e_cloud          P1  <- After all SQL data
```

## Notes

- DO NOT migrate local data - run fresh E2E extraction
- The pipeline must prove it works from scratch for production credibility
- After agenda items, continue down the E2E checklist (decisions, chunks, etc.)

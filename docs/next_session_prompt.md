# Recommended: decisions_e2e_cloud

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-27

> This is recommended context from Session 388. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 388 completed `agenda_items_e2e_cloud` - the agenda item extraction pipeline is now working E2E to cloud:
- Created `civic-extract agenda --cloud` CLI command
- Added `store_agenda_items()`, `get_agenda_items()`, `get_agenda_item_count()` to PostgresBackend
- Fixed broken import in agenda_integration.py
- Extracted 44 agenda items from 46 meetings (8 cancelled meetings detected)

**CRITICAL REQUIREMENT:** All data must be ingested E2E to cloud storage from scratch. NO MIGRATION from local. This validates the production pipeline actually works.

## Current Cloud Data Status

| Data Type | Cloud Count | Status | Action |
|-----------|-------------|--------|--------|
| Meetings | 46 | ready | Done |
| Issues | 1,330 | ready | Done |
| Agenda Items | 44 | ready | Done (Session 388) |
| **Decisions** | **0** | **P0** | **NEXT** |
| Chunks | 49 | P1 | Pending |
| Transcripts | 0 | P1 | Pending |
| Municipal Code | 0 | P1 | Pending |
| Legislation | 0 | P2 | Pending |
| Vector Indexes | 0 | P1 | After SQL data |

## Recommended Task

Run the decision extraction pipeline to populate cloud Postgres with decisions E2E. The decisions CLI already exists (`civic-extract decisions --cloud`) - just need to run it.

## Key Files

1. **Decision CLI:** `packages/civic-extraction/src/civic_extraction/cli/decisions.py` - Already has `--cloud` support
2. **Storage Backend:** `packages/civic/src/civic/storage/postgres_backend.py` - Has `store_decisions()` method
3. **Retrospective Analyzer:** `packages/civic-services/src/civic_services/processing/retrospective_analyzer.py` - LLM-based extraction

## Suggested Approach

### Step 1: Dry-run to see what would be processed
```bash
source civic-env/bin/activate
export DATABASE_URL="postgresql://..."  # from .env
civic-extract decisions --jurisdiction city-san-rafael --cloud --dry-run
```

### Step 2: Run extraction
```bash
civic-extract decisions --jurisdiction city-san-rafael --cloud
```

### Step 3: Verify in cloud
```bash
python3 -c "
import os
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM decisions WHERE jurisdiction_id = %s', ('city-san-rafael',))
print(f'Decision count: {cursor.fetchone()[0]}')
conn.close()
"
```

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q

# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v
```

## Success Criteria

- [ ] Decisions extracted from meeting agendas/minutes and stored in cloud Postgres
- [ ] Count > 0 (proportional to 46 meetings)
- [ ] `pilot.json` item `decisions_e2e_cloud` marked as ready

## Notes

- Decision extraction uses Gemini 2.5 Pro (expensive ~$0.50/meeting)
- Consider using `--limit 5` first to verify it works
- DO NOT migrate local data - run fresh E2E extraction
- After decisions, continue with chunks, transcripts, etc.

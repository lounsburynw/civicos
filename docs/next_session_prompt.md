# Recommended: decision_extraction_diagnosis

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-04

> This is recommended context from Session 468. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 468 diagnosed multiple data pipeline issues - **broader than just decisions**:

| Issue | Status | Details |
|-------|--------|---------|
| **Duplicate meetings** | 🔴 Bug | 17 meeting types duplicated 3-9x each |
| **Chunks stale** | 🟡 Stale | Stop at Dec 17, missing Dec 18+ |
| **Decisions stale** | 🟡 Stale | Stop at Dec 15, 3 weeks behind |
| **Minutes missing** | 🟡 Expected | Recent meetings don't have minutes yet |

**Root cause hypothesis:** The automated pipeline (`modal_ingest.py`) is:
1. Creating duplicate meetings on each run (not deduplicating by source URL or ID)
2. Not triggering chunk extraction for new meetings
3. Not triggering decision extraction at all

## Recommended Task

Diagnose the full pipeline completeness issue:

### 1. Meeting Deduplication Bug
```bash
# Check how meetings are being inserted
grep -n "store_meetings\|upsert\|ON CONFLICT" scripts/modal_ingest.py packages/civic/src/civic/storage/postgres_backend.py
```
- Are we using upsert or blind insert?
- What's the unique key (source_url? meeting_id + datetime?)

### 2. Chunk Extraction Gap
```bash
# What triggers chunk extraction?
grep -n "chunk\|extract\|pdf" scripts/modal_ingest.py

# Is there a separate chunk extraction script?
find scripts -name "*chunk*" -o -name "*pdf*" | head -10
```
- Chunks stop at Dec 17 but meetings exist through Jan 6
- Is chunk extraction part of the pipeline or manual?

### 3. Decision Extraction Gap
```bash
# Check if decisions are in modal_ingest.py
grep -n "decision" scripts/modal_ingest.py

# Find decision extraction code
ls packages/civic-extraction/src/civic_extraction/extractors/
```
- Decisions require meeting minutes (PDF) + LLM extraction
- This is likely a manual process not yet automated

## Key Files

- `scripts/modal_ingest.py` - Automated ingestion (check for dedup logic)
- `packages/civic/src/civic/storage/postgres_backend.py` - `store_meetings()` method
- `packages/civic-extraction/src/civic_extraction/extractors/` - Extraction logic
- `.github/workflows/vector-refresh.yml` - Weekly vector indexing
- `pilot.json:1784-1810` - Pipeline completeness tasks

## Diagnostic Queries

```bash
# Check duplicate meeting IDs
source civic-env/bin/activate
DATABASE_URL=$(grep "^DATABASE_URL=" .env | cut -d'=' -f2-) python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Check if meetings have unique source URLs
cur.execute('''
    SELECT source_url, COUNT(*) as cnt
    FROM meetings
    WHERE jurisdiction_id = %s
    GROUP BY source_url
    HAVING COUNT(*) > 1
    LIMIT 5
''', ('city-san-rafael',))
print('Duplicate source URLs:')
for row in cur.fetchall():
    print(f'  {row[1]}x: {row[0][:60]}...')
"
```

## Success Criteria

- [ ] Identified root cause of meeting duplicates
- [ ] Documented chunk extraction trigger (manual vs automated)
- [ ] Documented decision extraction process
- [ ] Created fix plan for deduplication (SQL cleanup + prevention)
- [ ] Updated pilot.json with findings

## Scope Boundaries

**This session:** Diagnose only. Document findings and create action items.

**Next sessions (P1):**
- `automated_decision_extraction` - Add to pipeline
- `vector_sql_sync_verification` - Fix mismatches
- Meeting dedup fix (may need new pilot.json item)

## Data Snapshot (Jan 4, 2026)

```
PostgreSQL (Supabase):
  Meetings: 97 (but ~46 unique, rest are duplicates)
  Decisions: 44 (through Dec 15)
  Chunks: 5,084 (through Dec 17)
  Issues: 1,630
  Transcripts: 19

Vectors (pgvector):
  Total: 31,951
  Issues mismatch: 1,430 vectors vs 1,630 SQL rows
  Meetings mismatch: 46 vectors vs 97 SQL rows
```

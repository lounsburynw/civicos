# Recommended: srcs_vector_indexing

**Priority:** P0
**Area:** data_readiness > school_district
**Date:** 2026-01-09

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 493 completed SRCS agenda item extraction:
- **598 agenda items** extracted from 33 school board meetings using Gemini LLM
- Added R2 URL support to `parse_agenda_content()` for blob storage PDFs
- Fixed token truncation issue (max_tokens 2000 -> 6000)
- Backfilled R2 agenda URLs for 43 meetings

**The agenda items are in PostgreSQL but NOT YET INDEXED in pgvector for semantic search.**

## Recommended Task

Index SRCS agenda items in pgvector to enable semantic search queries:
- `what_happened("school funding")` - Search historical decisions
- `whats_next()` - Find upcoming agenda items
- Enables school board data in the Civic API

## Key Files

- `scripts/modal_ingest.py:920-1002` - Vector indexing logic
- `packages/civic/src/civic/storage/pgvector_backend.py` - PgVectorBackend.index_from_storage()
- `data/checkpoints/agenda_school-san-rafael.json` - Extraction checkpoint (598 items)

## Current State Verification

```bash
# Check SRCS agenda items (should be 598)
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute('''
    SELECT COUNT(*) FROM agenda_items ai
    JOIN meetings m ON ai.meeting_id = m.id
    WHERE m.jurisdiction_id = 'school-san-rafael'
''')
print(f'SRCS agenda_items: {cur.fetchone()[0]}')
"

# Check current SRCS vector count (should be 0 for agenda_items corpus)
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os, psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
cur.execute('''
    SELECT COUNT(*) FROM vectors
    WHERE jurisdiction_id = 'school-san-rafael'
    AND corpus_type = 'agenda_items'
''')
print(f'SRCS agenda_items vectors: {cur.fetchone()[0]}')
"
```

## Suggested Approach

1. **Run vector indexing for school-san-rafael:**
   ```bash
   modal run scripts/modal_ingest.py --vectors --jurisdiction school-san-rafael
   ```

2. **Verify vectors indexed:**
   ```bash
   # Should show ~598 agenda_items vectors
   python3 -c "
   from dotenv import load_dotenv; load_dotenv()
   import os, psycopg2
   conn = psycopg2.connect(os.getenv('DATABASE_URL'))
   cur = conn.cursor()
   cur.execute('''
       SELECT corpus_type, COUNT(*) FROM vectors
       WHERE jurisdiction_id = 'school-san-rafael'
       GROUP BY corpus_type
   ''')
   for row in cur.fetchall():
       print(f'{row[0]}: {row[1]}')
   "
   ```

3. **Test semantic search:**
   ```python
   from civic import Civic
   c = Civic('school-san-rafael')
   results = c.what_happened("budget")  # Should return school budget items
   ```

## Success Criteria

- [ ] agenda_items vectors indexed in pgvector (~598 vectors)
- [ ] `Civic('school-san-rafael').what_happened("budget")` returns results
- [ ] Update pilot.json: `srcs_vector_indexing` status -> ready
- [ ] Set next P0 (suggest: `srcs_decision_extraction` or another data item)

## Alternative: CLI Command

If Modal is not set up, use the CLI directly:
```bash
civic-extract vectors --jurisdiction school-san-rafael --corpus agenda_items --cloud
```

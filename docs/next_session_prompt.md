# Recommended: decision_extraction_diagnosis

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-04

> This is recommended context from Session 468. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 468 completed `corpus_type_registry` and diagnosed a data staleness issue:
- **Meetings**: 97 in SQL (through Jan 6, 2026) - current
- **Decisions**: 44 in SQL (through Dec 15, 2025) - **3 weeks stale**
- The automated pipeline (`modal_ingest.py`) handles meetings/issues but NOT decision extraction

This is blocking because users querying "what happened" will get stale results.

## Recommended Task

Diagnose why decision extraction stopped at Dec 15:

1. **Understand current decision extraction process**
   - How are decisions currently extracted? (manual script? automated?)
   - What triggers decision extraction?
   - Is it dependent on meeting minutes PDFs?

2. **Identify the gap**
   - Are meeting minutes available for Dec 16 - Jan 6?
   - Is there an extraction script that needs to be run?
   - Is there a broken automation?

3. **Document the path forward**
   - Manual catch-up steps
   - What's needed to automate (P1 task: `automated_decision_extraction`)

## Key Files

- `scripts/modal_ingest.py` - Automated ingestion (meetings/issues, NOT decisions)
- `packages/civic-extraction/src/civic_extraction/extractors/` - Extraction logic
- `.github/workflows/vector-refresh.yml` - Weekly vector indexing
- `pilot.json:1784-1810` - Pipeline completeness tasks

## Diagnostic Commands

```bash
# Check what modal_ingest.py supports
grep -n "decision" scripts/modal_ingest.py

# Find decision extraction scripts
find scripts -name "*decision*" -o -name "*extract*" | head -20

# Check extraction package for decision extractor
ls -la packages/civic-extraction/src/civic_extraction/extractors/

# Query Supabase for decision dates
source civic-env/bin/activate
DATABASE_URL=$(grep "^DATABASE_URL=" .env | cut -d'=' -f2-) python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT meeting_date, COUNT(*) FROM decisions GROUP BY meeting_date ORDER BY meeting_date DESC LIMIT 10')
for row in cur.fetchall(): print(row)
"
```

## Success Criteria

- [ ] Documented how decisions are currently extracted
- [ ] Identified why extraction stopped at Dec 15
- [ ] Listed meetings between Dec 16 - Jan 6 that need decision extraction
- [ ] Created clear path forward (manual steps + automation requirements)
- [ ] Updated `decision_extraction_diagnosis` to ready in pilot.json

## Related Tasks (Do NOT work on these yet)

These depend on this diagnosis:
- `automated_decision_extraction` (P1) - Add to Modal pipeline
- `vector_sql_sync_verification` (P1) - Fix vector-SQL mismatches
- `data_freshness_alerting` (P2) - Add monitoring

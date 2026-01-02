# Recommended: Ingest Executive Orders

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-02

> This is recommended context from Session 431. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Sessions 429-431 completed the major codified law ingestion work:
- **Session 429-430:** U.S. Code (50,809 sections from 57 titles including appendices)
- **Session 431:** California Codes (161,219 sections from 29 codes)
- **Total:** 212,028 codified law sections now searchable in PostgreSQL

Executive Orders are the logical next step in building a complete regulatory stack.

## Recommended Task

Ingest Executive Orders from the Federal Register API to expand coverage of federal executive actions.

## Key Context

The Federal Register API provides structured access to Executive Orders:
- API: https://www.federalregister.gov/developers/documentation/api/v1
- Historical EOs: ~15,000+ orders from multiple administrations
- Current format: JSON with full text, signing dates, CFR citations

## Suggested Approach

1. **Explore the Federal Register API:**
   ```bash
   curl -s "https://www.federalregister.gov/api/v1/documents.json?conditions[presidential_document_type]=executive_order&per_page=3" | python3 -m json.tool | head -50
   ```

2. **Identify data fields to extract:**
   - Document number, title, signing date
   - Full text or abstract
   - CFR references
   - President name

3. **Determine storage approach:**
   - Option A: Extend `codified_law` table (jurisdiction_id = "federal-US-EO")
   - Option B: Create new `executive_orders` table with specific schema
   - Consider: EOs are executive actions, not codified statutes

4. **Create ingestion script:**
   - Pattern after `scripts/modal_cacode.py` or `scripts/modal_uscode.py`
   - Handle pagination (API returns max 1000 per request)
   - Deduplicate on document number

5. **Test and ingest:**
   ```bash
   modal run scripts/modal_executive_orders.py --dry-run
   modal run scripts/modal_executive_orders.py
   ```

## Database Status

```
Codified Law Sections:
  California: 161,219
  U.S. Code: 50,809
  Total: 212,028

Executive Orders: 0 (target: ~15k)
```

## Tests to Run

```bash
# Verify existing data still works
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic.storage.postgres_backend import PostgresBackend
import os
db = PostgresBackend(os.environ['DATABASE_URL'])
print(f'CA Codes: {db.get_codified_law_count(\"state-CA\"):,}')
print(f'US Code: {db.get_codified_law_count(\"federal-US\"):,}')
"
```

## Success Criteria

- [ ] Federal Register API structure understood
- [ ] Ingestion script created (`scripts/modal_executive_orders.py`)
- [ ] Executive Orders ingested to PostgreSQL
- [ ] Searchable via existing search methods

## Key Files from Previous Sessions

- `scripts/modal_uscode.py` - Pattern for Modal ingestion with R2
- `scripts/modal_cacode.py` - Pattern for parsing and bulk insert
- `packages/civic/src/civic/storage/postgres_backend.py:3452` - `store_codified_law()` method

## Alternative P1 Items (if EO API proves complex)

- `budget_schema` - Local budget data for San Rafael
- Vector indexing - Embed 212k sections to pgvector for semantic search

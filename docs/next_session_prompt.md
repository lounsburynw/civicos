# Recommended: Ingest U.S. Code Appendices

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-02

> This is recommended context from Session 429. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 429 completed ingestion of 53 main U.S. Code titles (50,783 sections) to PostgreSQL. The appendices (5a, 11a, 18a, 28a) failed because they have a different XML structure that causes `title_number` to be null.

**Completed this session:**
- Downloaded all 57 titles locally via parallel script (312MB)
- Uploaded to R2 for fast Modal access (172MB, ~2s download vs hours from gov servers)
- Ingested 50,783 sections from 53 main titles
- `what_applies()` now returns U.S. Code sections via full-text search

## Recommended Task

Fix the USCodeParser to handle appendix XML structure and ingest the 4 appendix titles.

## The Problem

Appendices fail with `NotNullViolation: null value in column "title_number"`:
```
Failing row contains (39567, None U.S.C. § 1, null, null, 1, Short title, ...)
identifier: /us/usc/t18a/pl/91/538/s1
```

The parser expects `<title identifier="/us/usc/t42">` but appendices structure is different.

## Key Files

- `scripts/modal_uscode.py:73-110` - Inline USCodeParser (extract title_number logic)
- `scripts/modal_uscode.py:56-66` - ALL_TITLES list (appendices currently excluded)
- `data/uscode/xml_usc05a.zip` - Sample appendix XML to investigate
- `data/uscode/xml_usc18a.zip` - Title 18 Appendix (where error occurred)

## Suggested Approach

1. **Investigate appendix XML structure:**
   ```bash
   cd data/uscode && unzip -p xml_usc18a.zip | head -100
   # Look for how title/section identifiers differ from main titles
   ```

2. **Check identifier patterns:**
   ```bash
   unzip -p xml_usc18a.zip | grep -o 'identifier="[^"]*"' | head -20
   # Expected: /us/usc/t18a/... patterns
   ```

3. **Fix parser title extraction:**
   - Main titles: `/us/usc/t42` → title_number = 42
   - Appendices: `/us/usc/t18a/...` → title_number should be 18 (or "18a")
   - May need to extract from identifier if `<title>` element missing

4. **Update schema if needed:**
   - `title_number` is INTEGER - appendices like "18a" won't fit
   - Options: change to TEXT, or store as 18 with appendix flag in metadata

5. **Test and ingest:**
   ```bash
   modal run scripts/modal_uscode.py --title 18a --dry-run
   modal run scripts/modal_uscode.py --all --start-from 05a
   ```

## Database Status

```
Total U.S. Code sections: 50,783
Release point: PL 119-59 (Jan 2026)
Missing: 5a, 11a, 18a, 28a (appendices)
```

## Tests to Run

```bash
# Verify main titles still work
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic.storage.postgres_backend import PostgresBackend
import os
db = PostgresBackend(os.environ['DATABASE_URL'])
print(f'Sections: {db.get_codified_law_count(\"federal-US\"):,}')
results = db.search_codified_law('federal-US', 'veterans', limit=3)
for r in results: print(f'  {r[\"citation\"]}: {r[\"heading\"][:50]}')
"
```

## Success Criteria

- [ ] Parser handles appendix XML structure (title_number not null)
- [ ] All 4 appendices ingested (5a, 11a, 18a, 28a)
- [ ] Total sections ~51k+ (currently 50,783)

## Infrastructure Created This Session

| Script | Purpose |
|--------|---------|
| `scripts/download_uscode.sh` | Parallel download all titles (10 connections) |
| `scripts/upload_uscode_r2.py` | Upload zips to R2 for fast Modal access |
| `scripts/modal_uscode.py` | Cloud ingestion with R2 source, dedup, resume |

## Also P1 (if time permits)

- `ca_codes_ingestion` - California's 29 codes from leginfo.legislature.ca.gov
- U.S. Code vector indexing - embed 50k sections to pgvector for semantic search

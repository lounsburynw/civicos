# Recommended: Ingest All 54 U.S. Code Titles

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-02

> This is recommended context from Session 428. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 428 completed the codified law pipeline for Title 42 (Public Health & Welfare):
- ✅ 6,651 sections ingested to PostgreSQL
- ✅ Batched COPY (500 rows/batch) avoids Supabase timeout
- ✅ `search_codified_law()` with full-text search
- ✅ `what_applies()` now returns U.S. Code sections

Now we need to ingest the remaining 53 titles (~100k sections total).

## Recommended Task

Ingest all 54 U.S. Code titles to complete the federal codified law corpus.

## Key Files

- `scripts/modal_uscode.py` - Modal script for cloud ingestion (URL already fixed to PL 119-59)
- `packages/civic/src/civic/storage/postgres_backend.py:3487` - `store_codified_law()` with batched COPY
- `packages/civic-extraction/src/civic_extraction/cli/uscode.py` - Local CLI alternative

## Available Titles

All 54 titles at: `https://uscode.house.gov/download/releasepoints/us/pl/119/59/`

Key titles for civic engagement:
| Title | Subject | Est. Sections |
|-------|---------|---------------|
| 5 | Government Organization | ~3k |
| 23 | Highways | ~500 |
| 26 | Internal Revenue | ~10k |
| 33 | Navigation/Waterways | ~1k |
| 40 | Public Buildings | ~500 |
| 42 | Public Health (DONE) | 6,651 |
| 52 | Voting and Elections | ~500 |

## Suggested Approach

1. **Test with one more title locally:**
   ```bash
   civic-extract uscode --input data/uscode/usc05.xml --cloud --dry-run
   ```

2. **Batch ingest via Modal (if network allows):**
   ```bash
   # Modal had network issues reaching uscode.house.gov - may need R2 workaround
   modal run scripts/modal_uscode.py --title 5
   ```

3. **Alternative: Local ingestion with batched COPY:**
   ```bash
   # Download XML files locally first
   curl -O https://uscode.house.gov/download/releasepoints/us/pl/119/59/xml_usc05@119-59.zip
   unzip xml_usc05@119-59.zip -d data/uscode/
   civic-extract uscode --input data/uscode/usc05.xml --cloud
   ```

4. **Loop through all titles** (script needed)

## Known Issues

- **Modal network:** Modal containers had connection timeouts to uscode.house.gov. May need to download locally and upload to R2, or run ingestion from local machine.
- **Supabase timeout:** Batched COPY (500 rows) handles this - already implemented.

## Tests to Run

```bash
# Verify Title 42 still works
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('san-rafael')
r = c.what_applies('public housing')
print([f.get('citation') for f in r.federal if f.get('type') == 'codified_law'][:3])
"
```

## Success Criteria

- [ ] All 54 U.S. Code titles ingested (~100k sections)
- [ ] `what_applies()` returns relevant sections across multiple titles
- [ ] No statement timeouts during ingestion

## Also P1 (if time permits)

- `executive_orders_ingestion` - Federal Register API
- `ca_codes_ingestion` - California's 29 codes from leginfo.legislature.ca.gov

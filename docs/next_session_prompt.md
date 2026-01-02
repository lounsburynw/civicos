# Recommended: Codified Law Ingestion (Complete Modal Pipeline)

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2026-01-01

> This is recommended context from Session 428. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 428 built the full codified law pipeline:
- ✅ Storage backend methods with COPY optimization (`store_codified_law`, `get_codified_law`, `get_codified_law_count`)
- ✅ CLI command (`civic-extract uscode`)
- ✅ Modal script for cloud ingestion (`scripts/modal_uscode.py`)

**Blocker:** Local ingestion hits Supabase statement timeout (~6 min limit). Modal script created to download directly from uscode.house.gov, but **the download URL is wrong** (expects ZIP, gets HTML).

## Recommended Task

Fix the Modal script URL and complete ingestion:

1. **Fix download URL** in `scripts/modal_uscode.py:222` - the URL format is incorrect
2. **Run Modal ingestion** - `modal run scripts/modal_uscode.py --title 42`
3. **Test what_applies()** with real codified law queries

## Key Files

- `scripts/modal_uscode.py:222` - **FIX NEEDED**: Wrong URL format for uscode.house.gov
- `packages/civic/src/civic/storage/postgres_backend.py:3452` - store_codified_law with COPY
- `packages/civic-extraction/src/civic_extraction/uscode.py` - Original USCodeParser
- `data/uscode/usc42.xml` - Local copy of Title 42 (17MB, works with parser)

## The URL Problem

Current (wrong):
```python
url = f"https://uscode.house.gov/download/releasepoints/us/pl/118/200/xml_usc{title}@118-200.zip"
```

The actual download page is: https://uscode.house.gov/download/download.shtml
You need to find the correct bulk XML download URL or use the local file via R2.

## Alternative: Use Local File via R2

If URL is hard to fix, upload local file to R2:
```python
from dotenv import load_dotenv; load_dotenv()
from civic.storage.blob import R2Backend
r2 = R2Backend.from_env()
r2.upload('uscode/usc42.xml', open('data/uscode/usc42.xml', 'rb').read(), 'application/xml')
```

Then modify Modal to download from R2 instead.

## Success Criteria

- [ ] 6,651 sections in `codified_law` table for `federal-US`
- [ ] `c.what_applies("public housing")` returns U.S. Code sections
- [ ] No statement timeouts (Modal handles ingestion)

## Commits This Session

None yet - run `/commit` after fixing and testing.

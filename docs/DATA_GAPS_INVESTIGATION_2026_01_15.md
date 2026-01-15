# Data Gaps Investigation Report

**Date:** 2026-01-15
**Session Focus:** Investigate DATA_READINESS_REPORT.md gaps and implement fixes

---

## Executive Summary

Investigated data readiness gaps. Found that **scheduled Modal functions were stale** (deployed Dec 31, code changed Jan 14) and **auto_index was not wired** to scheduled functions. Fixed both issues. However, discovered a **critical data discrepancy**: the Data Readiness Report counts don't match actual API returns, suggesting temporal filtering issues.

---

## Issue-by-Issue Analysis

### 1. Decisions Gap (30 Days Stale)

**Report Claim:** 44 decisions, latest 2025-12-15 (30 days stale)

**Root Causes Found:**
- `scheduled_low_velocity_refresh()` was deployed Dec 31 but code changed Jan 14
- Weekly scheduler calls `extract_decisions.local()` without `auto_index=True`
- Decision extraction only found **3 meetings with agendas** (not 123 as report claimed)

**Fixes Applied:**
- Added `auto_index=True` to `extract_decisions.local()` call
- Added `openai` and `google-generativeai` to Modal image (was missing)
- Redeployed Modal app

**Status:** PARTIALLY FIXED
- Automation now works correctly
- But only 3 meetings have agendas, so 0 new decisions extracted
- **Needs investigation:** Why does API return 3 meetings when report says 123?

---

### 2. Transcript Coverage Gap (31%)

**Report Claim:** 38/123 meetings have transcripts (31%)

**Root Causes Found:**
- Pipeline is **audio-availability-driven**: `YouTube Videos → Audio Download → Transcription`
- Oct-Nov 2025 meetings have videos but **no downloadable audio** on YouTube
- Cost constraint: AssemblyAI = $0.02/min (~$2.40 per 2-hour meeting)
- Only recent meetings (Dec 29 - Jan 13) have been transcribed

**Fixes Applied:**
- Added `auto_index=True` to `extract_transcripts.local()` in scheduled function

**Status:** NOT FIXABLE VIA AUTOMATION
- This is a **data source limitation** - audio files don't exist for older meetings
- San Rafael may not upload audio for older meetings, or audio expires
- Cannot backfill what doesn't exist at source

---

### 3. Embedding Gaps (Meetings 10%, Issues 58%, Elections 11%)

**Report Claims:**
- Meetings: 12/123 (10%)
- Issues: 1,537/2,630 (58%)
- Elections: 4/38 (11%)

**Root Causes Found:**
- Scheduled functions used `index_vectors.local(reindex=False)`
- Incremental logic skips corpora it thinks are "complete"
- Initial indexing was partial; subsequent runs assumed completeness
- `auto_index=True` was added to functions but **not wired to scheduled functions**

**Fixes Applied:**
- Added `auto_index=True` to ALL fetch/extract calls in scheduled functions
- Removed redundant `index_vectors()` calls at end of scheduled functions
- Ran one-time reindex for issues, elections, meetings

**Reindex Results:**
| Corpus | Before | After | Expected (Report) |
|--------|--------|-------|-------------------|
| Elections | 4 | **8** | 38 |
| Issues | 1,537 | **1,521** | 2,630 |
| Meetings | 12 | **3** | 123 |

**Status:** AUTOMATION FIXED, BUT DATA DISCREPANCY EXISTS
- Auto-indexing now works
- But actual data counts much lower than report claimed
- **Critical finding:** Report counts don't match API returns

---

### 4. Elected Officials Gap (0 Records)

**Report Claim:** 0 records in elected_officials table

**Root Cause Found:**
- Code exists: `extract_elected_officials_to_storage()` in `representatives.py:1188`
- Hardcoded officials in `SAN_RAFAEL_LOCAL_OFFICIALS` constant
- **Never integrated into any ingestion pipeline** - not in `modal_ingest.py`

**Fixes Applied:** NONE

**Status:** NOT ADDRESSED
- Requires adding to Modal ingestion pipeline
- Or creating one-time script to populate
- Lower priority (P2) per report

---

## Critical Discovery: Data Discrepancy

The Data Readiness Report shows counts that **do not match** what the API functions return:

| Data Type | Report Count | API Returns | Discrepancy |
|-----------|--------------|-------------|-------------|
| Meetings | 123 | 3 | **97% missing** |
| Issues | 2,630 | 1,521 | **42% missing** |
| Elections | 38 | 8 | **79% missing** |

**Hypothesis:** The report was generated using direct SQL queries:
```sql
SELECT COUNT(*) FROM meetings WHERE jurisdiction_id = 'city-san-rafael'
```

But the API functions use temporal filtering:
```python
# get_meetings() in postgres_backend.py:1625
WHERE valid_from <= %s AND (valid_to IS NULL OR valid_to > %s)
```

**Implication:** Records may exist in DB but are filtered out by `valid_from`/`valid_to` constraints. This could be:
1. A bug in how records are inserted (wrong `valid_from` timestamps)
2. Records incorrectly marked as superseded (`valid_to` set)
3. Intentional behavior that wasn't accounted for in report

**Action Required:** Investigate temporal validity filtering in `PostgresBackend.get_meetings()` and related methods.

---

## Code Changes Made

### File: `scripts/modal_ingest.py`

1. **Added dependencies to Modal image** (lines 118-119):
   ```python
   "openai>=1.0.0",
   "google-generativeai>=0.8.0",
   ```

2. **Updated `scheduled_high_velocity_refresh()`** (lines 2579-2657):
   - Added `auto_index=True` to: `fetch_meetings`, `fetch_issues`, `extract_transcripts`, `extract_chunks`
   - Removed redundant `index_vectors()` loop at end

3. **Updated `scheduled_low_velocity_refresh()`** (lines 2421-2522):
   - Added `auto_index=True` to: `fetch_legislation`, `fetch_executive_orders`, `fetch_municipal_code`, `extract_agenda_items`, `extract_decisions`
   - Removed redundant `index_vectors()` call at end

4. **Updated `scheduled_election_refresh()`** (lines 2718-2728):
   - Added `auto_index=True` to `fetch_elections`

---

## Deployments

| App | Deployed | Status |
|-----|----------|--------|
| civic-ingest | 2026-01-15 17:44 | ✅ Live with auto_index |
| civic-vectors | 2026-01-15 17:42 | ✅ Live |

---

## Next Steps for Future Session

1. **P0: Investigate data discrepancy**
   - Query DB directly to verify actual record counts
   - Check `valid_from`/`valid_to` values on meetings table
   - Determine if filtering is intentional or bug

2. **P1: Fix meetings visibility**
   - If records exist but filtered, fix temporal constraints
   - May need migration to reset `valid_from`/`valid_to`

3. **P2: Add elected officials to pipeline**
   - Wire `extract_elected_officials_to_storage()` into scheduled refresh
   - Or create one-time population script

4. **P3: Update Data Readiness Report**
   - Report should use same query paths as API
   - Or document that counts are raw DB vs API-visible

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `scripts/modal_ingest.py` | Scheduled ingestion functions (MODIFIED) |
| `scripts/modal_vectors.py` | Vector indexing |
| `packages/civic/src/civic/storage/postgres_backend.py:1625` | `get_meetings()` with temporal filter |
| `packages/civic/src/civic/storage/pgvector_backend.py:1234` | `get_stats()` for coverage calculation |
| `packages/civic-extraction/src/civic_extraction/clients/representatives.py:1188` | Elected officials extraction |
| `docs/DATA_READINESS_REPORT.md` | Original gap report |

---

*Report generated by Claude Code session 2026-01-15*

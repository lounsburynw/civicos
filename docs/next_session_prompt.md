# Recommended: temporal_versioning_review

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-04

> This is recommended context from Session 470. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## The Problem

`store_meetings()` in `postgres_backend.py` has a **blocking bug**:

1. When meetings are scraped, it **closes ALL existing records** (sets `valid_to` timestamp)
2. Then inserts only meetings in the current scrape window (~30 days past to ~90 days ahead)
3. `get_meetings()` only returns records where `valid_to IS NULL`
4. **Result**: Only ~1 meeting is visible, even though 97 exist in the database

This breaks:
- `extract_chunks()` - can only see 1 meeting, can't process historical agendas
- `extract_decisions()` - same issue with minutes
- Any future extraction that relies on `get_meetings()`

## Current State

```
Meetings in database:     97 records
Meetings visible:          1 record  (valid_to IS NULL)
Chunks extracted:       5,084        (extracted before bug)
Chunks possible now:        0        (can't see historical meetings)
```

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py` - `store_meetings()` method
- `packages/civic-extraction/src/civic_extraction/cli/chunks.py` - `find_meetings()` function

## Suggested Fix

Change `store_meetings()` from "close all, insert window" to proper upsert:

```python
# Current (broken):
1. UPDATE meetings SET valid_to = NOW() WHERE jurisdiction_id = X  # Closes ALL
2. INSERT new meetings from scrape window

# Fixed:
1. For each scraped meeting:
   - If meeting_id exists and unchanged: skip (leave valid_to NULL)
   - If meeting_id exists and changed: close old, insert new
   - If meeting_id is new: insert
2. DON'T close meetings outside scrape window
```

**Natural key**: `meeting_id` from source (e.g., ProudCity event ID)

## Implementation Steps

1. **Read current `store_meetings()`** implementation
2. **Understand the schema** - meetings table structure, valid_from/valid_to columns
3. **Write proper upsert logic** - compare by meeting_id, only close if data changed
4. **Test with real data** - verify historical meetings remain visible
5. **Run chunk extraction** - confirm it can now see all 97 meetings

## Tests to Run

```bash
# Before fix - should show only 1 meeting
python3 -c "from civic.storage import get_storage_backend; print(len(get_storage_backend().get_meetings('city-san-rafael')))"

# After fix - should show ~46 unique meetings
python3 -c "from civic.storage import get_storage_backend; print(len(get_storage_backend().get_meetings('city-san-rafael')))"

# Then run chunk extraction
modal run scripts/modal_ingest.py --chunks
```

## Success Criteria

- [ ] `get_meetings()` returns all historical meetings (not just current window)
- [ ] Running `store_meetings()` doesn't close unchanged historical records
- [ ] `extract_chunks()` can process meetings from Oct 2025 onward
- [ ] pilot.json updated: `temporal_versioning_review` → ready

## Scope Boundaries

**This session:** Fix store_meetings() temporal versioning only.

**Blocked items (fix first):**
- `automated_decision_extraction` - depends on this fix
- `automated_chunk_extraction` - already coded but ineffective until this fix

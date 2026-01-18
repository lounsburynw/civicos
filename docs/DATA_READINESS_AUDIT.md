# Data Readiness Audit: San Rafael Pilot (Jan 2026)

**Audit Date:** 2026-01-15
**Auditor:** Claude Code Session
**Status:** NEEDS ATTENTION

## Executive Summary

The San Rafael pilot data has significant quality issues that should be addressed before launch:

| Issue | Severity | Impact |
|-------|----------|--------|
| 60% duplicate meetings | **Critical** | Inflated counts, duplicate search results |
| 315 orphan videos | High | Missing meeting-video linkage |
| 85% meetings lack transcripts | High | Limited `what_was_said()` coverage |
| 75% meetings lack decisions | High | Limited `what_happened()` coverage |
| Decisions extraction 17 days stale | High | Jan 2026 has 0 decisions |
| Vector schema inconsistency | Medium | Transcript vectors use video_id |

## 1. Source Reconciliation

### Meeting Counts (Oct 2025 - Jan 2026)

| Month | Raw Count | Unique Count | Duplicates |
|-------|-----------|--------------|------------|
| Oct 2025 | 18 | 18 | 0 |
| Nov 2025 | 14 | 12 | 2 |
| Dec 2025 | 66 | 15 | 51 |
| Jan 2026 | 28 | 5 | 23 |
| **Total** | **126** | **50** | **76 (60%)** |

**Analysis:** December 2025 and January 2026 show severe duplication. Some meetings have up to 11 copies:
- City Council – January 5, 2026 (Cancelled): 11 copies
- Fire Commission – January 14, 2026 (Cancelled): 9 copies
- Planning Commission – January 13, 2026: 6 copies

### Meeting Bodies Present

| Body | Oct | Nov | Dec | Jan | Expected |
|------|-----|-----|-----|-----|----------|
| city_council | 2 | 3 | 3 | 1 | 2/month |
| planning_commission | 2 | 3 | 1 | 1 | 2/month |
| zoning_administrator | 5 | 0 | 2 | 0 | Variable |
| council_subcommittees | 1 | 1 | 3 | 1 | Variable |

**Finding:** City Council and Planning Commission frequencies roughly match expected patterns. 17 distinct meeting bodies identified.

### Source Comparison

Unable to directly compare with San Rafael's Legistar calendar (API returned invalid parameters). Manual reconciliation needed.

**Recommendation:** Add source reconciliation check to `/ingest` command.

## 2. Coverage Analysis

### Meeting Data Coverage

| Corpus Link | Meetings With | Coverage % |
|-------------|---------------|------------|
| Videos | 19 | 15.1% |
| Transcripts | 15 | 11.9% |
| Decisions | 32 | 25.4% |
| Chunks (PDFs) | 36 | 28.6% |

**Critical Gap:** Only ~12% of meetings have full transcript coverage. For an AI-powered civic tool, this severely limits functionality.

### Orphan Data

| Data Type | Orphan Count | Notes |
|-----------|--------------|-------|
| Videos without meeting link | 315 | YouTube videos not linked to meetings |
| Transcripts from orphan videos | 15 | Transcripts exist but meeting link broken |
| Chunks without meeting | 0 | Good referential integrity |

### Vector Embedding Coverage

| Corpus | Source Count | Vector Count | Coverage % | Gap |
|--------|--------------|--------------|------------|-----|
| meetings | 50 (unique) | 3 | 6% | 47 |
| decisions | 44 | 44 | 100% | 0 |
| chunks | 5,146 | 5,146 | 100% | 0 |
| transcripts | 38 | 4,608* | N/A | Schema issue |
| issues | 2,630 | 1,521 | 58% | 1,109 |
| municipal_code | 19,986 | 5,857 | 29% | 14,129 |

*Transcripts are chunked into multiple vectors per source document.

**Finding:** Transcript vectors store video_id in the meeting_id field, breaking FK relationship.

## 3. Freshness Check

### Last Updated Timestamps

| Corpus | Last Ingested | Latest Record | Days Since |
|--------|---------------|---------------|------------|
| Meetings | 2026-01-15 | 2026-01-20 | 0 (current) |
| Decisions | 2025-12-28 | 2025-12-15 | **17 (STALE)** |
| Transcripts | 2026-01-13 | - | 2 |
| Chunks | 2026-01-15 | - | 0 |
| Issues | 2026-01-14 | 2026-01-13 | 1 |
| Videos | 2026-01-12 | 2026-01-13 | 3 |

### January 2026 Data Completeness

| Corpus | Count | Assessment |
|--------|-------|------------|
| Meetings | 5 | Partial (month in progress) |
| Decisions | 0 | **MISSING** - extraction stale |
| Transcripts | 19 | Good coverage |

**Critical:** Decisions extraction has not run since Dec 28. January 2026 has zero extracted decisions.

## 4. Quality Audit

### Duplicates

| Table | Duplicate Instances | Sample |
|-------|---------------------|--------|
| meetings | 76 (60% of total) | City Council Jan 5: 11 copies |
| transcripts | 9 video_ids | Multiple transcripts per video |
| decisions | 0 | Clean |
| videos | 0 | Clean |

### Referential Integrity

| Check | Status | Count |
|-------|--------|-------|
| Chunks → Meetings | PASS | 0 invalid |
| Videos → Meetings | WARNING | 315 NULL meeting_id |
| Vectors → Meetings | FAIL | 4,608 invalid (uses video_id) |

### Schema Issues

1. **Transcript vectors**: The `meeting_id` field contains YouTube video IDs (e.g., `-6jDc6NAKPc`) instead of meeting IDs (e.g., `proudcity-city-san-rafael-city-council-...`)

2. **Decisions**: Uses `meeting_date` (text) instead of `meeting_id` FK, making joins fragile

## 5. Failure Mode Analysis

### Current Failure Modes (Detected)

| Mode | Detection Method | Status |
|------|------------------|--------|
| Duplicate ingestion | This audit | ACTIVE - 60% duplication |
| Orphan videos | FK check | ACTIVE - 315 orphans |
| Stale extraction | Timestamp check | ACTIVE - 17 days |
| Schema mismatch | FK validation | ACTIVE - vectors |

### Potential Failure Modes (Need Monitoring)

| Mode | Detection | Recommendation |
|------|-----------|----------------|
| Source unavailable | Scrape failures | Add health check to `/ingest` |
| Embedding failures | Vector gaps | Add gap detection to `/vectors` |
| Transcript quality | Word count anomalies | Add duration validation |
| Decision extraction errors | Zero counts | Alert when extraction produces 0 results |

### Recommended Automated Checks

1. **Pre-ingest**: Source availability check
2. **Post-ingest**: Duplicate detection with automatic dedup
3. **Daily**: Freshness check for all corpora (alert if >7 days stale)
4. **Weekly**: Coverage report (% meetings with transcript/decision/chunk)
5. **On-demand**: FK integrity validation

## Recommendations

### Immediate Actions (Run Existing Commands)

| Priority | Action | Command |
|----------|--------|---------|
| P0 | Refresh decisions | `modal run scripts/modal_ingest.py --decisions --jurisdiction city-san-rafael` |
| P1 | Index meetings | `/vectors reindex --corpus meetings` |
| P1 | Index issues | `/vectors reindex --corpus issues` |

### Bug Fixes Required

1. **Fix `store_meetings()` upsert logic** - 76 duplicates exist despite claimed idempotency
2. **Run one-time dedup SQL** - After fixing upsert, clean existing duplicates

### New Development (pilot.json items)

3. **Link orphan videos** - 315 videos need meeting_id via date/title matching
4. **Fix transcript vector schema** - Re-index with correct meeting_id lookup
5. **Add `--coverage` flag to `/data-status`** - Show % meetings with linked data

### Recommended pilot.json Items

After cross-referencing with existing tooling, these are the actual gaps:

```json
{
  "name": "store_meetings_upsert_fix",
  "category": "data_integrity",
  "description": "Fix upsert logic in store_meetings() to prevent duplicate insertion",
  "priority": 1,
  "artifact": "Bug fix in PostgresBackend.store_meetings()",
  "note": "76 duplicates exist despite /ingest claiming 'upsert semantics prevent duplicates'. Root cause: unique constraint missing or ON CONFLICT clause incorrect. After fix, run one-time dedup SQL."
},
{
  "name": "orphan_video_linkage",
  "category": "data_integrity",
  "description": "Link 315 orphan videos to meetings via date/title matching",
  "priority": 2,
  "artifact": "One-time linking script",
  "note": "Videos have meeting date in title. Parse and match to meetings by date + body type. Updates meeting_id column. Restores transcript→meeting linkage."
},
{
  "name": "transcript_vector_meeting_id_fix",
  "category": "data_architecture",
  "description": "Fix transcript vectors storing video_id in meeting_id field",
  "priority": 2,
  "artifact": "Re-index with correct meeting_id lookup",
  "note": "4,608 transcript vectors have YouTube video IDs in meeting_id. Depends on orphan_video_linkage completing first."
},
{
  "name": "data_status_coverage_flag",
  "category": "data_readiness",
  "description": "Add --coverage flag to /data-status for relational coverage",
  "priority": 3,
  "artifact": "DataStatus.relational_coverage() method",
  "note": "Shows % of meetings with linked transcript/decision/chunk. Currently not covered by any command."
}
```

### Immediate Actions (Use Existing Commands)

These don't need new pilot.json items - just run existing commands:

| Action | Command |
|--------|---------|
| Refresh decisions | `modal run scripts/modal_ingest.py --decisions --jurisdiction city-san-rafael` |
| Index meetings | `/vectors reindex --corpus meetings` |
| Index issues | `/vectors reindex --corpus issues` |
| Check freshness | `/checkpoint status` |

### Cross-Reference with Existing Tooling

| Need | Existing Tool | Gap? |
|------|---------------|------|
| Corpus counts | `/data-status` | Covered |
| Vector gaps | `/vector-coverage` | Covered |
| Freshness/staleness | `/checkpoint status` | **Covered** - shows ingestion age |
| Duplicate detection | `/ingest` claims upsert dedup | **BUG** - 76 duplicates exist |
| Relational coverage | None | **GAP** |
| Orphan detection | None | **GAP** |

### Bug Fix Required

**`/ingest` documentation claims:** "Idempotency: Upsert semantics prevent duplicates"

**Reality:** 76 duplicate meetings exist. The upsert logic in `store_meetings()` is not working correctly.

**Fix:** Debug and fix the upsert semantics in `PostgresBackend.store_meetings()`. The unique key should be `(jurisdiction_id, title, meeting_datetime)`.

### Extend `/data-status`

Add one new flag to cover actual gaps:

| Flag | Purpose | What It Adds |
|------|---------|--------------|
| `--coverage` | Relational coverage | % meetings with transcript/decision/chunk |

**Implementation:**
```python
class DataStatus:
    def relational_coverage(self) -> dict[str, float]:
        """Return % of meetings with linked data (transcript, decision, chunk)."""
```

### One-Time Cleanup Scripts

These are cleanup tasks, not ongoing commands:

1. **Deduplicate meetings** (one-time SQL):
   ```sql
   DELETE FROM meetings m1
   WHERE EXISTS (
     SELECT 1 FROM meetings m2
     WHERE m2.title = m1.title
       AND m2.meeting_datetime = m1.meeting_datetime
       AND m2.jurisdiction_id = m1.jurisdiction_id
       AND m2.id < m1.id
   );
   ```

2. **Link orphan videos** (one-time script):
   - Parse date from video title
   - Match to meetings by date + jurisdiction
   - Update `meeting_id` column

## Appendix: API vs Raw Database Counts

The system uses temporal versioning (`valid_from`/`valid_to`) to filter records. This explains count differences:

| Corpus | Raw DB | API-Visible | Notes |
|--------|--------|-------------|-------|
| Meetings | 126 | 50 | 76 duplicates/superseded |
| Transcripts | 38 | 29 | 9 superseded versions |
| Issues | 2,630 | 1,547 | Historical issues filtered |
| Municipal code | 19,986 | 3,811 | Older code versions |

The DataStatus output (API counts) reflects what users actually see:

```
Corpus                  Storage    Indexed      Gap   Coverage
--------------------------------------------------------------
Agenda Chunks              5146       5146        0       100%
Decisions                    44         44        0       100%
Community Issues           1547       1521       26        98%
Meetings                     49        n/a      n/a        n/a
Transcripts                  29       4608    -4579     15890%
```

Note: Transcripts show -4579 gap because each transcript is chunked into ~150 vector embeddings.

## Appendix: Raw Data

### Corpus Counts (city-san-rafael)

| Table | Count |
|-------|-------|
| meetings | 126 (50 unique) |
| decisions | 44 |
| chunks | 5,146 |
| transcripts | 38 |
| issues | 2,630 |
| municipal_code | 19,986 |
| legislation | 0 |
| budget_items | 58 |
| videos | 335 |

### Vector Embedding Totals

| Corpus Type | Count |
|-------------|-------|
| chunks | 5,146 |
| decisions | 44 |
| elections | 8 |
| issues | 1,521 |
| meetings | 3 |
| municipal_code | 5,857 |
| state_programs | 147 |
| transcripts | 4,608 |
| **Total** | **17,334** |

### Date Ranges

| Corpus | Earliest | Latest |
|--------|----------|--------|
| Meetings | 2025-10-01 | 2026-01-20 |
| Issues | 2009-08-14 | 2026-01-13 |
| Videos | 2018-12-03 | 2026-01-13 |

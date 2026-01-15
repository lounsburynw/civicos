# Data Readiness Report

**Jurisdiction:** city-san-rafael
**Report Date:** 2026-01-14
**Purpose:** Assess data completeness and freshness for Jan 2026 pilot launch

---

## Executive Summary

The backend contains substantial data for the San Rafael pilot, with strong coverage in legal/regulatory content and community issues. However, there are notable gaps in transcript coverage, decision freshness, and vector embedding completeness that should be addressed before launch.

**Overall Readiness: 75%** - Core functionality supported, but gaps in transcript and decision data may limit some features.

---

## 1. Data Types Ingested

### Core Governance (San Rafael-specific)

| Data Type | Records | Date Range | Description |
|-----------|---------|------------|-------------|
| Meetings | 123 | 2025-10-01 to 2026-01-14 | City council, planning commission, boards |
| Decisions | 44 | 2025-10-01 to 2025-12-15 | Official votes, resolutions, approvals |
| Transcripts | 38 | 2025-12-29 to 2026-01-13 | AI-generated meeting transcriptions |
| Chunks | 5,140 | - | PDF/agenda packet extracted content |
| Videos | 335 | - | Meeting video recordings (YouTube links) |

### Community Data

| Data Type | Records | Date Range | Description |
|-----------|---------|------------|-------------|
| Issues (SeeClickFix) | 2,630 | 2009-08-14 to 2026-01-13 | Citizen-reported problems, requests |

### Legal/Regulatory (Broader Scope)

| Data Type | Records | Scope | Description |
|-----------|---------|-------|-------------|
| Municipal Code | 19,986 | San Rafael | City ordinances and regulations |
| Legislation | 17,719 | CA + Federal | Active and recent bills |
| Executive Orders | 1,506 | Federal | Presidential executive orders |
| Codified Law | 250,950 | California | State law sections |

### Financial Data

| Data Type | Records | Description |
|-----------|---------|-------------|
| Budget Items | 58 | FY25-26 city budget line items |
| Federal Awards | 5 | Federal grants received |
| State Passthrough Funds | 287 | State funding allocations |

### Election Data

| Data Type | Records | Description |
|-----------|---------|-------------|
| Elections | 38 | Historical and upcoming elections |
| Elected Officials | 0 | **GAP - Not yet populated** |

### Vector Embeddings (Semantic Search)

| Corpus Type | Embeddings | Source Records | Coverage |
|-------------|------------|----------------|----------|
| municipal_code | 5,857 | 19,986 | 29% |
| chunks | 5,140 | 5,140 | 100% |
| transcripts | 4,608 | 38 | 100% |
| issues | 1,537 | 2,630 | 58% |
| state_programs | 147 | - | - |
| decisions | 44 | 44 | 100% |
| meetings | 12 | 123 | 10% |
| elections | 4 | 38 | 11% |

**Total Embeddings: 17,349**

---

## 2. Completeness Assessment

### Strong Coverage

| Category | Assessment | Notes |
|----------|------------|-------|
| Municipal Code | Excellent | 19,986 sections - comprehensive |
| State Law | Excellent | 250,950 sections - full CA code |
| Legislation | Good | 17,719 bills tracked |
| Issues | Excellent | 16+ years of history, 2,630 records |
| Chunks | Good | 5,140 agenda packet extracts |

### Gaps Identified

| Category | Issue | Impact | Priority |
|----------|-------|--------|----------|
| **Decisions** | Only 44 for 3.5 months | `what_happened()` may miss recent actions | P1 |
| **Transcripts** | 38/123 meetings (31%) | `what_was_said()` limited coverage | P1 |
| **Elected Officials** | 0 records | Cannot answer "who represents me" | P2 |
| **Budget** | Only 58 items | May not reflect full budget detail | P2 |
| **Meeting Embeddings** | 10% coverage | Meeting search degraded | P2 |
| **Issue Embeddings** | 58% coverage | `whos_with_me()` misses ~1,100 issues | P2 |

---

## 3. Data Freshness

| Data Type | Latest Record | Days Stale | Status |
|-----------|---------------|------------|--------|
| Meetings | 2026-01-14 | 0 | Current |
| Transcripts | 2026-01-13 | 1 | Current |
| Issues | 2026-01-13 | 1 | Current |
| **Decisions** | **2025-12-15** | **30** | **STALE** |

### Freshness Concerns

1. **Decisions 30 days behind** - Meetings from late Dec and Jan 2026 likely contain decisions not yet extracted. This is a significant gap for "what happened recently" queries.

2. **Transcript lag** - While recent transcripts are current, only 31% of meetings have transcripts. Many Oct-Nov meetings may never be transcribed if audio is unavailable.

---

## 4. Recommendations

### P0 - Critical for Pilot

| Item | Action | Rationale |
|------|--------|-----------|
| Decision extraction | Re-run extraction for Dec 16 - Jan 14 meetings | 30-day gap unacceptable for pilot |

### P1 - High Priority

| Item | Action | Rationale |
|------|--------|-----------|
| Transcript backfill | Transcribe available audio for Oct-Nov meetings | Improve 31% coverage |
| Issue embedding sync | Embed remaining 1,093 issues | Full semantic search |
| Meeting embedding sync | Embed remaining 111 meetings | Meeting search coverage |

### P2 - Before Launch

| Item | Action | Rationale |
|------|--------|-----------|
| Elected officials | Ingest current city council, boards | Basic "who represents me" |
| Election embeddings | Embed remaining elections | Election search |

### P3 - Post-Launch

| Item | Action | Rationale |
|------|--------|-----------|
| Budget granularity | Consider more detailed budget extraction | Better financial queries |
| Municipal code embeddings | Embed remaining 14K sections | Full legal search |

---

## 5. Feature Impact Matrix

| Feature | Data Required | Current Readiness | Notes |
|---------|---------------|-------------------|-------|
| `whats_next()` | meetings | ✅ Ready | 123 meetings, current |
| `what_happened()` | decisions | ⚠️ Degraded | 30-day gap |
| `what_was_said()` | transcripts | ⚠️ Limited | 31% coverage |
| `what_applies()` | municipal_code, legislation | ✅ Ready | Strong coverage |
| `whos_with_me()` | issues + embeddings | ⚠️ Partial | 58% embedded |
| Budget queries | budget_items | ⚠️ Limited | Only 58 items |
| Election info | elections, officials | ⚠️ Partial | No officials |

---

## 6. Data Sources

| Data Type | Source | Extraction Method |
|-----------|--------|-------------------|
| Meetings | Legistar API | civic-extraction |
| Decisions | Legistar + AI | civic-extraction |
| Transcripts | YouTube audio | Whisper transcription |
| Issues | SeeClickFix API | civic-extraction |
| Municipal Code | Municode | Web scraping |
| Legislation | LegiScan API | civic-extraction |
| Budget | City PDF | Manual extraction |

---

## Appendix: Query Reference

```sql
-- Verify current counts
SELECT
    (SELECT COUNT(*) FROM meetings WHERE jurisdiction_id = 'city-san-rafael') as meetings,
    (SELECT COUNT(*) FROM decisions WHERE jurisdiction_id = 'city-san-rafael') as decisions,
    (SELECT COUNT(*) FROM transcripts WHERE jurisdiction_id = 'city-san-rafael') as transcripts,
    (SELECT COUNT(*) FROM issues WHERE jurisdiction_id = 'city-san-rafael') as issues;

-- Check decision freshness
SELECT MAX(meeting_date) as latest_decision
FROM decisions
WHERE jurisdiction_id = 'city-san-rafael';

-- Embedding coverage
SELECT corpus_type, COUNT(*)
FROM vector_embeddings
WHERE jurisdiction_id = 'city-san-rafael'
GROUP BY corpus_type;
```

---

*Last updated: 2026-01-14*

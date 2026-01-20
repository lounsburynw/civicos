# Architecture Re-Audit Follow-Up - January 2026

**Date:** 2026-01-10
**Context:** Follow-up to Session 491 audit (2026-01-08)
**Original Document:** `docs/ARCHITECTURE_AUDIT_2026_01.md`

## Status Summary

| Issue | Original Status | Current Status | Change |
|-------|-----------------|----------------|--------|
| 1. Vector Backend Fragmentation | Critical | ✅ Resolved | Fixed in context.py |
| 2. civic.py Dataclass Extraction | Critical | ✅ Resolved | Extracted to types.py |
| 3. StorageBackend Protocol Size | P3 | ❌ Regressed | +1,272 lines |
| 4. LangGraph Workflow Usage | P3 | ⏳ Not Started | Still speculative |
| 5. TODO Debt | P3 | ⏳ Not Started | 20 TODOs remain |
| 6. Jurisdiction Hardcoding | P2 | ⏳ Not Started | 28 prod refs remain |
| 7. pilot.json Granularity | P3 | ⏳ Not Started | Now 351 items |

**Updated Verdict: B+ (unchanged)**

The two critical issues were resolved. One P3 issue regressed. One new critical issue emerged.

---

## Detailed Findings

### 1. Vector Backend Fragmentation — ✅ RESOLVED

**Evidence:** `packages/civic/src/civic/context.py:217-276`

The `get_regulatory_context()` function now uses `PgVectorBackend` directly for municipal_code searches:

```python
from civic.storage.pgvector_backend import PgVectorBackend
pgvector = PgVectorBackend(database_url, provider_type="fastembed")
results = pgvector.search(
    query=topic,
    jurisdiction_id=jurisdiction,
    corpus_type="municipal_code",
    top_k=5,
)
```

The 5,857 municipal_code embeddings are now accessible via `what_applies()`.

---

### 2. civic.py Dataclass Extraction — ✅ RESOLVED

**Evidence:**

| File | Lines Before | Lines After |
|------|-------------|-------------|
| civic.py | 2,073 | 1,770 |
| types.py | N/A (new) | 23 classes |

All 22 original dataclasses plus `FederalProgram` are now in `packages/civic/src/civic/types.py`:

```
RegulatoryStack, Decision, TranscriptExcerpt, TranscriptLink,
DecisionWithContext, Meeting, UpcomingElection, Community, Initiative,
Voice, Subscription, Preparation, Suggestion, CoordinationPlan,
Outcome, BudgetItem, BudgetSummary, FundingFlow, FundingFlowImpact,
FederalExpenditure, IntergovernmentalRevenue, IntergovernmentalRevenueSummary,
FederalProgram
```

---

### 3. StorageBackend Protocol Size — ❌ REGRESSED

**Evidence:**

| File | Lines (Jan 8) | Lines (Jan 10) | Delta |
|------|---------------|----------------|-------|
| backend.py | 1,742 | 1,899 | +157 |
| postgres_backend.py | 6,800 | 7,556 | +756 |
| sqlite_backend.py | 3,100 | 3,459 | +359 |
| **Total** | **11,642** | **12,914** | **+1,272** |

Methods grew from ~75 to ~82:
- `store_federal_programs` / `get_federal_programs` / `get_federal_programs_count`
- `store_federal_program_allocations` / `get_federal_program_allocations` / `get_federal_program_allocations_count`

**Assessment:** This is expected growth during pilot feature development. The pattern continues to work but friction increases. Post-pilot decomposition remains recommended.

---

### 4. LangGraph Workflow Usage — ⏳ NOT STARTED

**Evidence:** 5 workflow types exist, only 1 used from main API:

| Workflow | Exported | Used in Civic facade | Used in tests |
|----------|----------|---------------------|---------------|
| coordination | ✅ | ✅ `run_coordination` | ✅ |
| suggestion | ✅ | ❌ | ✅ test_mcp.py |
| preparation | ✅ | ❌ | ✅ test_mcp.py |
| pattern | ✅ | ❌ | ✅ test_mcp.py |
| strategy | ✅ | ❌ | ✅ test_mcp.py |

The `__init__.py` exports 80+ symbols across all workflows. Only `run_coordination` and `get_campaign_state` are imported by `civic.py`.

**Assessment:** Four speculative workflows await API integration. Not blocking pilot, but adds maintenance surface area.

---

### 5. TODO Debt — ⏳ NOT STARTED

**Evidence:** 20 TODOs across 13 files (was 18+ in original audit)

| Package | Files | TODOs |
|---------|-------|-------|
| civic/src | 4 | 10 |
| civicos-services/src | 9 | 10 |

Notable stale TODOs:
- `california.py`: 6 TODOs about HTML parsing (unchanged since audit)
- `civic_api.py`: `# TODO: Extract from source` for 'city': 'San Rafael'
- `civicclerk_client.py`: `# TODO: Make configurable` for timezone

---

### 6. Jurisdiction Hardcoding — ⏳ NOT STARTED

**Evidence:** 28 "San Rafael" references in production code (non-test files):

| Location | Count | Type |
|----------|-------|------|
| `_internal/meetings/` | 6 | Format docs/comments |
| `_internal/jurisdiction.py` | 4 | Config data |
| `storage/` | 5 | Examples in docstrings |
| `civic.py` | 3 | Display name mapping |
| `civicos-services/` | 10 | Various |

Most are documentation/examples, but some are hardcoded logic:
- `minutes.py:306`: `return "San Rafael City Hall"`
- `civic_api.py:62`: `'city': 'San Rafael'`

**Assessment:** Not blocking pilot. Will need config system for second city.

---

### 7. pilot.json Granularity — ⏳ NOT STARTED

**Current State:**
- 351 total items
- 316 ready, 34 not_ready, 1 blocked

The granularity has grown significantly. Post-launch consolidation remains appropriate.

---

## New Issues Identified

### 8. civic_api_integrated.py God Class — **CRITICAL (NEW)**

**Evidence:** `packages/civicos-services/src/civic_services/servers/civic_api_integrated.py`

| Metric | Value |
|--------|-------|
| Lines | 10,456 |
| Rank | Largest file in codebase |

This is a FastAPI server combining all endpoints. At 10K+ lines, it's difficult to navigate, test, and modify.

**Recommendation:** Post-pilot, decompose into domain-specific routers:
- `meetings_router.py` — meeting/agenda endpoints
- `legislation_router.py` — what_applies endpoints
- `community_router.py` — voices/initiatives endpoints
- `admin_router.py` — admin/ingestion endpoints

**Priority:** P2 (post-pilot, before feature expansion)

---

## Updated Recommendations

### Completed (Pre-Pilot) ✅

| Item | Status |
|------|--------|
| Vector backend unification | ✅ Done |
| civic.py type extraction | ✅ Done |

### Post-Pilot Priority List

| Priority | Item | Effort | When |
|----------|------|--------|------|
| P2 | civic_api_integrated.py decomposition | High | Q1 2026 |
| P2 | Jurisdiction config system | Medium | Before 2nd city |
| P3 | StorageBackend decomposition | High | After 2+ new content types |
| P3 | LangGraph workflow audit | Low | Q1 2026 |
| P3 | TODO cleanup | Low | Anytime |
| P3 | pilot.json consolidation | Low | After launch stabilization |

---

## Metrics Comparison

| Metric | Jan 8 | Jan 10 | Trend |
|--------|-------|--------|-------|
| civic.py lines | 2,073 | 1,770 | ✅ -15% |
| types.py classes | 0 | 23 | ✅ Extracted |
| StorageBackend methods | ~75 | ~82 | ⚠️ +9% |
| Storage code (total) | 11,642 | 12,914 | ⚠️ +11% |
| civic_api_integrated.py | ~9,500 | 10,456 | ⚠️ +10% |
| TODO count | 18+ | 20 | → Same |
| pilot.json items | ~42K tokens | 351 items | → Same |

---

## Verdict: B+ (Unchanged)

The two critical issues identified in Session 491 are now resolved:
1. Vector backend fragmentation — `what_applies()` accesses municipal_code vectors
2. civic.py dataclass sprawl — types extracted to dedicated module

The StorageBackend continues to grow as expected during pilot feature work. A new critical issue (civic_api_integrated.py at 10K lines) should be addressed post-pilot.

The codebase remains well-engineered with clear architecture, disciplined practices, and principled growth. Post-pilot refactoring priorities are correctly identified.

---

*Follow-up audit conducted 2026-01-10. For questions, reference this document alongside the original audit.*

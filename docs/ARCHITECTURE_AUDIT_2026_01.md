# Architecture Audit - January 2026

**Date:** 2026-01-08
**Session:** 491
**Context:** Pre-pilot architecture review prompted by broader industry discussion of AI-assisted development quality

## Executive Summary

This codebase is **well-engineered software**, not "AI slop." It demonstrates intentional architectural thinking, disciplined project management (490 sessions, phase gates), and infrastructure sophistication (parallel CI, domain-specific critics). However, several areas would benefit from refactoring—some before pilot, most after.

## Verdict: B+ / A-

| Aspect | Assessment |
|--------|------------|
| API Design | Excellent — user-centric verbs (`what_happened`, `whats_next`) |
| Domain Model | Strong — clear ontology (jurisdictions, legal layers, content types) |
| Test Infrastructure | Strong — parallel isolation, session-scoped fixtures |
| Project Management | Strong — P0/P1/P2 system, session discipline, critics |
| Storage Abstraction | Needs work — god protocol, 75+ methods |
| Vector Integration | Needs work — ChromaDB/pgvector fragmentation |
| Code Organization | Minor issues — civic.py has inline dataclasses |

---

## Critical Issues (Pre-Pilot Candidates)

### 1. Vector Backend Fragmentation

**Status:** Already tracked as `vector_backend_unification` (P1)

**Problem:** Two parallel vector systems that don't interoperate:

| Corpus | Backend | Access Pattern |
|--------|---------|----------------|
| transcripts, chunks, meetings, issues, decisions | ChromaDB (`CivicEmbeddings`) | `what_was_said()`, `what_happened()` |
| municipal_code, codified_law, executive_orders | pgvector (`PgVectorBackend`) | Direct queries only |

Session 490 discovered: `what_applies()` cannot use municipal_code vectors because the API layer uses `CivicEmbeddings` (ChromaDB), but municipal code vectors are in pgvector.

**Impact:** Users can't semantically search municipal code through the API. The 5,857 municipal_code embeddings are orphaned.

**Recommendation:** Elevate priority. This blocks real value from the vector indexing work.

### 2. civic.py Dataclass Extraction

**Status:** Not tracked

**Problem:** `packages/civic/src/civic/civic.py` is 2,073 lines containing 22 dataclasses inline with the `Civic` facade class:

```python
# All defined in civic.py:
RegulatoryStack, Decision, TranscriptExcerpt, DecisionWithContext,
TranscriptLink, HybridSearchResult, Meeting, Community, Initiative,
Voice, Subscription, Preparation, Suggestion, CoordinationPlan,
Outcome, BudgetItem, BudgetSummary, FundingFlow, FundingFlowImpact,
FederalExpenditure, IntergovernmentalRevenue, IntergovernmentalRevenueSummary
```

**Impact:** Cognitive load when reading the main API file. Types are harder to import independently.

**Recommendation:** Extract to `packages/civic/src/civic/types.py`. Low effort (~30 min), high clarity improvement. Good candidate for pre-pilot cleanup.

---

## Post-Pilot Improvements

### 3. StorageBackend God Protocol

**Priority:** P3 (post-pilot)

**Problem:** `StorageBackend` protocol is 1,742 lines with ~75 methods. Every new content type requires adding 3-5 methods to the protocol, and both implementations must be updated:

- `postgres_backend.py`: 250KB (6,800+ lines)
- `sqlite_backend.py`: 115KB (3,100+ lines)

Method pattern repeats for each content type:
```python
store_X(jurisdiction_id, items, as_of) -> int
get_X(jurisdiction_id, filters...) -> List[Dict]
get_X_count(jurisdiction_id) -> int
```

**Impact:** Adding new content types (e.g., CFR, executive orders) requires touching 3 files and adding 4+ methods each time. High friction for expansion.

**Recommendation:** Consider generic pattern:
```python
def store(self, corpus_type: str, jurisdiction_id: str, items: List[Dict]) -> int
def query(self, corpus_type: str, jurisdiction_id: str, **filters) -> List[Dict]
def count(self, corpus_type: str, jurisdiction_id: str) -> int
```

Or decompose into smaller protocols (`MeetingStorage`, `LegislationStorage`, etc.) composed together.

**Why post-pilot:** The current approach works. Refactoring is risky pre-launch and the payoff is future velocity, not current functionality.

### 4. LangGraph Workflow Audit

**Priority:** P3 (post-pilot)

**Problem:** 6 separate LangGraph state/node files in `_internal/coordination/`:

```
state.py, strategy_state.py, preparation_state.py,
pattern_state.py, suggestion_state.py
strategy_nodes.py, preparation_nodes.py, pattern_nodes.py,
suggestion_nodes.py, nodes.py
strategy_graph.py, preparation_graph.py, pattern_graph.py,
suggestion_graph.py, graph.py
```

**Question:** Are all workflows actively used from the API? Or are some speculative?

**Recommendation:** Audit usage. Remove unused graphs. Premature abstraction adds maintenance burden.

### 5. TODO Debt Cleanup

**Priority:** P3 (30-minute task)

**Problem:** 18+ stale TODOs scattered through codebase:

```python
# packages/civic/src/civic/_internal/legal/corpus/california.py
# TODO: Scrape from website for dynamic discovery
# TODO: Implement HTML parsing (appears 4 times)
# TODO: Implement bill enumeration via search API

# packages/civic/src/civic/_internal/legal/enrichment/semantic.py
"federal_program_refs": [],  # TODO: Add federal search

# packages/civic-services/src/civic_services/
# TODO: Make configurable (timezone)
# TODO: Track from Instructor (token usage)
# TODO: Implement true streaming
```

**Recommendation:** Either implement, delete with issue reference, or convert to tracked items. Stale TODOs are noise that erodes trust in comments.

### 6. Jurisdiction Hardcoding

**Priority:** P2 (pre-second-city)

**Problem:** San Rafael assumptions scattered through code:

```python
'city': 'San Rafael',  # TODO: Extract from source
'timezone': 'America/Los_Angeles',  # TODO: Make configurable
```

**Impact:** None for pilot (San Rafael only). Becomes blocking when adding second city.

**Recommendation:** Create jurisdiction config system before second city onboarding. Not urgent for Jan 2026.

### 7. pilot.json Granularity

**Priority:** P3 (meta-improvement)

**Problem:** The 42K-token pilot.json tracks very granular items:

```json
"pytest_xdist_setup": { "status": "ready" },
"parallel_safe_fixtures": { "status": "ready" },
"loadscope_distribution": { "status": "ready" }
```

These three items are really one thing: "parallel test infrastructure."

**Impact:** Overhead in session handoffs. Harder to see forest for trees.

**Recommendation:** Consider grouping related items post-pilot. The granularity served AI session handoff well during development, but may be excessive for maintenance phase.

---

## Package Boundary Testing

**Priority:** P2 (post-pilot)

**Problem:** Clean package separation (`civic`, `civic-extraction`, `civic-services`) but no integration tests verifying contracts between packages.

**Risk:** If `civic-extraction` changes output format, nothing catches it until runtime.

**Recommendation:** Add lightweight contract tests at package boundaries:
- "extraction output parses correctly in civic"
- "civic types serialize correctly for civic-services"

---

## What's Working Well (Don't Change)

1. **API Design** — `what_happened()`, `whats_next()`, `what_applies()` is genuinely user-centric
2. **Session Discipline** — P0/P1/P2 system with enforcement works
3. **Critics System** — Domain-specific linting catches architectural issues (`pipeline.critic.md`)
4. **Test Infrastructure** — Parallel isolation, session-scoped model caching, marker system
5. **Phase Gates** — implementation → hardening → integration → pilot progression is principled
6. **Progress Tracking** — 490 sessions logged with decisions and learnings

---

## Recommended Actions

### Pre-Pilot (Before Jan 2026)

| Item | Effort | Impact | Recommendation |
|------|--------|--------|----------------|
| Vector backend unification | Medium | High | Bump to P0 after current P0 completes |
| civic.py type extraction | Low | Medium | Add as P2, do if time permits |

### Post-Pilot

| Item | Effort | Impact | When |
|------|--------|--------|------|
| StorageBackend decomposition | High | High | Before adding 3rd content type |
| LangGraph audit | Low | Medium | Q1 2026 |
| TODO cleanup | Low | Low | Anytime |
| Jurisdiction config | Medium | High | Before 2nd city |
| Package boundary tests | Medium | Medium | Q1 2026 |
| pilot.json consolidation | Low | Low | After launch stabilization |

---

## References

- Session 490: Municipal code vector indexing, discovered API integration gap
- Session 315: Storage gap bug discovery, led to `pipeline.critic.md`
- Session 480: Soft delete implementation across 19 tables
- Session 481: LegiScan migration after Open States acquisition

---

*This audit was conducted in Session 491. For questions or updates, reference this document in future sessions.*

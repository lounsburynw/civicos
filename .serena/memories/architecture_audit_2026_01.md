# Architecture Audit Summary (Session 491)

Full analysis: `docs/ARCHITECTURE_AUDIT_2026_01.md`

## Quick Reference

### Pre-Pilot Priority Items

1. **vector_backend_unification** (existing P1 item)
   - ChromaDB and pgvector don't interoperate
   - municipal_code, codified_law vectors unreachable from API
   - Blocks value from 5,857+ vector embeddings
   - Recommendation: Bump priority when current P0 completes

2. **civic_types_extraction** (new item, P2)
   - 22 dataclasses inline in civic.py (2,073 lines)
   - Extract to `packages/civic/src/civic/types.py`
   - ~30 min effort, improves readability

### Post-Pilot Tech Debt

| Issue | File(s) | Effort | Trigger |
|-------|---------|--------|---------|
| StorageBackend god protocol | backend.py (1,742 lines) | High | Before 3rd content type |
| LangGraph workflow sprawl | _internal/coordination/ (15 files) | Low | Q1 2026 audit |
| Stale TODOs | 18+ across codebase | Low | Anytime |
| Jurisdiction hardcoding | Various | Medium | Before 2nd city |
| Package boundary tests | None exist | Medium | Q1 2026 |

### Key Metrics

- StorageBackend: ~75 methods, 1,742 lines
- postgres_backend.py: 250KB
- sqlite_backend.py: 115KB
- civic.py: 2,073 lines, 22 inline dataclasses
- _internal/coordination/: 15 files (6 state, 5 nodes, 4 graphs)
- Stale TODOs: 18+

### What's Working (Don't Touch)

- API design (`what_happened`, `whats_next`, `what_applies`)
- Session discipline (P0/P1/P2 system)
- Critics system (pipeline, protocol, architecture, session)
- Test infrastructure (parallel, isolated, cached)
- Phase gates (implementation → hardening → integration → pilot)

## When to Read This Memory

- Before major refactoring decisions
- When adding new content types to StorageBackend
- When planning post-pilot roadmap
- When onboarding second city

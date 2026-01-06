# Recommended: vector_sql_sync_verification

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-05

> This is recommended context from Session 475. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 475 completed `automated_decision_extraction` - added `extract_decisions()` to Modal pipeline with weekly scheduling. Decision extraction now runs automatically on Sundays alongside municipal code and legislation refresh.

The vector-SQL sync verification is needed to ensure pgvector indices stay in sync with SQL data. Session 469 found mismatches (meetings: 46 vectors vs 97 SQL, issues: 1430 vectors vs 1630 SQL). The meetings mismatch is expected (SQL includes historical versions), but issues mismatch needs investigation.

## Recommended Task

Add post-refresh validation to `vector-refresh.yml` GitHub Action that compares vector counts to SQL row counts (with `valid_to IS NULL` filter for temporal tables).

## Key Files

- `.github/workflows/vector-refresh.yml` - Current vector refresh workflow
- `packages/civic/src/civic/storage/pgvector_backend.py` - PgVectorBackend.get_stats()
- `packages/civic/src/civic/storage/postgres_backend.py` - PostgresBackend for SQL counts

## Suggested Approach

1. **Review current workflow:**
   ```bash
   cat .github/workflows/vector-refresh.yml
   ```

2. **Add verification step** that:
   - Gets vector counts per corpus type via PgVectorBackend.get_stats()
   - Gets SQL counts via PostgresBackend (filter by `valid_to IS NULL`)
   - Compares and warns on mismatches (allow tolerance for timing)
   - Fails workflow if mismatch exceeds threshold (e.g., >10%)

3. **Investigate issues mismatch:**
   - 1430 vectors vs 1630 SQL rows
   - May be stale vectors from deleted issues
   - Consider reindex if significantly out of sync

## Success Criteria

- [ ] Verification step added to vector-refresh.yml
- [ ] Step compares vector count to SQL count (with valid_to IS NULL)
- [ ] Threshold-based warning/failure for mismatches
- [ ] Issues mismatch investigated and resolved (or documented as expected)
- [ ] pilot.json updated: vector_sql_sync_verification -> ready

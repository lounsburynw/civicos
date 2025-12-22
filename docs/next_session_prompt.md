# Recommended: Data Migration Reversible

**Priority:** P0 (IMMEDIATE)
**Area:** rollback_procedures > data_safety
**Date:** 2025-12-21

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 333 completed `post_ingestion_report` - added PostIngestionReport dataclass and Pipeline.report() method that provides structured validation after city onboarding ingestion.

Next priority is ensuring schema changes can be rolled back for safe deployments.

## Recommended Task

Document and implement reversible data migration patterns. Ensure schema changes can be rolled back without data loss.

## Key Files

- `docs/critical/DAILY_BACKUP_SCHEDULE.md` - Existing backup strategy (7 daily + 4 weekly)
- `.github/workflows/daily-backup.yml` - Backup workflow
- `packages/civic/src/civic/storage/` - Storage layer with SQLite/ChromaDB

## Suggested Approach

1. **Document migration patterns** - Options:
   - Create `docs/admin/MIGRATION_GUIDE.md` with rollback procedures
   - Document forward/backward migration scripts pattern
   - Define schema versioning strategy

2. **Identify current schema dependencies**:
   - SQLite tables structure
   - ChromaDB collection schemas
   - JSON data file formats

3. **Implement reversibility**:
   - Migration script template with `up()` and `down()` methods
   - Pre-migration backup verification
   - Rollback testing procedure

## Success Criteria

- [ ] Migration patterns documented
- [ ] Schema versioning strategy defined
- [ ] Rollback procedure tested
- [ ] pilot.json updated to mark data_migration_reversible as ready

## Pilot Progress

- 137/161 items ready (85%)
- 24 items remaining

# Recommended: soft_delete_support

**Priority:** P0
**Area:** data_integrity > audit_infrastructure
**Date:** 2026-01-05

> This is recommended context from Session 479. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 479 completed `election_ingestion_pipeline` - added `fetch_elections()` Modal job to ingest election data from Google Civic API. 4 elections stored to Supabase. Note: VIP/Google publishes CA election data ~2-3 weeks before elections (CA data expected May 2026 for June primary).

The next P0 is `soft_delete_support` - adding audit trail infrastructure so we never hard-delete content.

## Recommended Task

Add `deleted_at` column to all content tables in PostgresBackend to support soft-delete. This enables audit trails of what was removed, when, and why.

## Key Files

- `packages/civic/src/civic/storage/postgres_backend.py` - Main storage implementation
- `packages/civic/src/civic/storage/protocols.py` - StorageBackend protocol
- `scripts/sql/schema.sql` - Database schema definitions (if exists)

## Suggested Approach

1. **Identify all content tables:**
   ```bash
   grep -n "CREATE TABLE" packages/civic/src/civic/storage/postgres_backend.py | head -20
   ```
   Tables likely include: meetings, issues, elections, decisions, chunks, municipal_code, legislation

2. **Add deleted_at column to schema:**
   Each table should have: `deleted_at TIMESTAMP DEFAULT NULL`
   - NULL = active record
   - Timestamp = when deleted

3. **Update get_* methods to filter:**
   All read methods should add: `AND deleted_at IS NULL`
   Consider adding `include_deleted: bool = False` parameter

4. **Create soft_delete methods:**
   ```python
   def soft_delete_meeting(self, meeting_id: str, reason: str = None) -> bool:
       cursor.execute("""
           UPDATE meetings
           SET deleted_at = NOW(), deleted_reason = %s
           WHERE id = %s AND deleted_at IS NULL
       """, (reason, meeting_id))
   ```

5. **Add deleted_reason column (optional):**
   Store why the record was deleted for audit purposes

## Tests to Run

```bash
# Core API tests (ensure reads still work)
pytest packages/civic/tests/test_civic.py -v --override-ini="addopts="

# PostgresBackend tests (add soft-delete tests)
pytest packages/civic/tests/test_postgres_backend.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] `deleted_at` column added to all content tables
- [ ] Existing get_* methods filter out soft-deleted records
- [ ] At least one soft_delete_* method implemented
- [ ] Tests verify soft-deleted records are excluded from queries
- [ ] Optional: `include_deleted` parameter for audit queries
- [ ] pilot.json updated: soft_delete_support -> ready

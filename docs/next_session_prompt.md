# Recommended: whats_next_postgres_migration

**Priority:** P0
**Area:** data_integrity > pipeline_completeness
**Date:** 2026-01-05

> This is recommended context from Session 476. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 476 ran a stress test on the data pipelines and found a critical issue:
- `whats_next()` returns **empty** despite 46 meetings and 121 agenda items in Postgres
- Root cause: `Civic.whats_next()` reads from **StateManager (local SQLite)** instead of PostgresBackend
- Also discovered: 121 agenda items exist but **0 marked `is_actionable=True`**

All other data pipelines verified working:
- Meetings: 46 total, latest Jan 6, 2026
- Decisions: 44 total, latest Dec 15, 2025
- Issues: 1,433 (vectors synced within 1.8%)
- Semantic search: Working with good relevance scores
- `what_happened()`, `what_applies()`, `whos_with_me()`: All functional

## Recommended Task

Migrate `Civic.whats_next()` to use PostgresBackend for cloud storage, and investigate why no agenda items have `is_actionable=True`.

## Key Files

- `packages/civic/src/civic/civic.py` - Civic class with `whats_next()` method
- `packages/civic/src/civic/state_manager.py` - StateManager (legacy SQLite)
- `packages/civic/src/civic/storage/postgres_backend.py` - PostgresBackend.get_agenda_items()
- `packages/civic/src/civic/storage/backend.py:461-527` - StorageBackend protocol (agenda methods)

## Suggested Approach

1. **Understand current implementation:**
   ```bash
   grep -n "whats_next" packages/civic/src/civic/civic.py
   ```
   Find where StateManager is used vs StorageBackend

2. **Update whats_next() to use PostgresBackend:**
   - Replace StateManager calls with `get_storage_backend()`
   - Use `backend.get_meetings()` filtered by future dates
   - Use `backend.get_agenda_items()` for upcoming agenda items

3. **Investigate is_actionable flag:**
   ```python
   # Check what's in the database
   items = backend.get_agenda_items("city-san-rafael")
   actionable = [i for i in items if i.get('is_actionable')]
   print(f"Actionable: {len(actionable)} / {len(items)}")
   ```
   - May need to update extraction to set this flag
   - Or update API query to not filter by this flag

4. **Test the fix:**
   ```python
   from civic import Civic
   c = Civic("san-rafael")
   result = c.whats_next()
   print(f"Upcoming items: {len(result)}")
   ```

## Tests to Run

```bash
# Smoke test
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Integration test with cloud data
TOKENIZERS_PARALLELISM=false python3 -c "
from civic import Civic
c = Civic('san-rafael')
print(f'whats_next: {len(c.whats_next())} items')
"
```

## Success Criteria

- [ ] `whats_next()` returns upcoming meetings from PostgresBackend
- [ ] `whats_next()` returns agenda items (or documents why none are actionable)
- [ ] Works with cloud DATABASE_URL (not just local SQLite)
- [ ] pilot.json updated: whats_next_postgres_migration -> ready

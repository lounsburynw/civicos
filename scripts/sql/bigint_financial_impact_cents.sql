-- Migration: financial_impact_cents INTEGER -> BIGINT
--
-- Background: decisions.financial_impact_cents and agenda_items.financial_impact_cents
-- were declared INTEGER. PostgreSQL INTEGER is a 4-byte signed int with max value
-- 2,147,483,647 ($21,474,836.47 in cents). Any agenda item with a larger dollar amount
-- (routine for large contracts, annual budgets, pension obligations, etc.) overflowed.
--
-- To avoid database-level overflow errors, the Python insert path at
-- packages/civicos/src/civicos/storage/postgres_backend.py:2748 silently clamped
-- incoming values via `min(value, 2_147_483_647)`. Result: 486 decisions (19.3% of
-- those with financial data) lost their true amounts to the INT32_MAX sentinel.
--
-- Before this migration:
--   decisions:       4,532 rows / 2,498 with financial_impact_cents / 486 at INT32_MAX sentinel
--   agenda_items:   594,639 rows / 0 with financial_impact_cents   / 0   at INT32_MAX sentinel
--
-- After this migration:
--   1. The sentinel rows are cleared to NULL so the next weekly decision-extraction
--      run repopulates them with real values. Leaving the sentinel would cause
--      idempotent extraction to skip the rows (hash matches), locking in the bug.
--   2. Both columns are widened to BIGINT (8-byte, max ~9.2 quintillion).
--
-- The application-level clamp at postgres_backend.py:2748 is removed in the same
-- commit. The CREATE TABLE statements at :376 and :472 are also updated to BIGINT
-- so fresh local installs (SQLite path unaffected — SQLite INTEGER is dynamic)
-- match the production schema.
--
-- Rollout: run against the production Supabase Postgres in a single transaction.
-- decisions ALTER COLUMN is effectively instant (4K rows). agenda_items is the
-- larger operation (~600K rows) but still a single-digit-seconds table rewrite.
-- Weekly cron does not run mid-Friday so there is no contention window to worry
-- about.

BEGIN;

-- 1. Clear the clamped sentinel values so re-extraction replaces them.
--    Only current rows (valid_to IS NULL) are cleared; historical versions
--    keep their sentinel as an accurate audit record of what the DB claimed
--    at that point in time, even though it was a clamped lie.
UPDATE decisions
   SET financial_impact_cents = NULL
 WHERE financial_impact_cents = 2147483647
   AND valid_to IS NULL;

UPDATE agenda_items
   SET financial_impact_cents = NULL
 WHERE financial_impact_cents = 2147483647
   AND valid_to IS NULL;

-- 2. Widen both columns to BIGINT
ALTER TABLE decisions
  ALTER COLUMN financial_impact_cents TYPE BIGINT;

ALTER TABLE agenda_items
  ALTER COLUMN financial_impact_cents TYPE BIGINT;

COMMIT;

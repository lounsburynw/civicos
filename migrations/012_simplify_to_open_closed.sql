-- Migration 012: Simplify to Open/Closed Status
-- NOTE: This migration was designed for an older issues schema with user_id column.
-- The current StateManager-defined schema already has closed_reason and uses
-- a different structure. This migration now only normalizes status values.

-- Normalize any legacy 'escalated' status values to 'open' (safe for current schema)
UPDATE issues SET status = 'open' WHERE status = 'escalated';

-- Normalize any 'resolved' status to 'closed' if the status field supports it
-- Otherwise just leave as-is since current schema already handles this properly
UPDATE issues SET status = 'closed' WHERE status = 'resolved';

-- Clean up any issues_new table that might have been left from a failed migration
DROP TABLE IF EXISTS issues_new;

-- Ensure indexes exist (idempotent)
CREATE INDEX IF NOT EXISTS idx_issues_jurisdiction ON issues(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_created ON issues(created_at);
CREATE INDEX IF NOT EXISTS idx_issues_short_name ON issues(short_name_keyword, short_name_number);

-- Migration 011: Simplify Issue Status
-- NOTE: This migration was designed for an older issues schema with user_id column.
-- The current StateManager-defined schema does not have user_id.
-- This migration now only normalizes status values if they exist.
-- The schema recreation is skipped as the current schema is authoritative.

-- Normalize any legacy status values to 'open' (safe for current schema)
UPDATE issues SET status = 'open' WHERE status = 'matched';
UPDATE issues SET status = 'open' WHERE status = 'community_formed';

-- Ensure indexes exist (idempotent)
CREATE INDEX IF NOT EXISTS idx_issues_jurisdiction ON issues(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_created ON issues(created_at);
CREATE INDEX IF NOT EXISTS idx_issues_short_name ON issues(short_name_keyword, short_name_number);

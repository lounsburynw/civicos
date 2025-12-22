-- Rollback: Remove short_name fields from issues table
-- WARNING: This will lose any short_name data. Ensure backup exists before running.

-- Drop indexes first
DROP INDEX IF EXISTS idx_issues_short_name_full;
DROP INDEX IF EXISTS idx_issues_short_name_keyword;

-- SQLite doesn't support DROP COLUMN directly before 3.35.0
-- For compatibility, we recreate the table without the columns

-- Create temporary table without the columns
CREATE TABLE issues_temp AS
SELECT
    id,
    jurisdiction_id,
    source_platform,
    source_id,
    title,
    description,
    status,
    category,
    latitude,
    longitude,
    address,
    reported_at,
    resolved_at,
    ai_title,
    ai_summary,
    created_at,
    updated_at,
    valid_from,
    valid_to
FROM issues;

-- Drop original table
DROP TABLE issues;

-- Rename temp table
ALTER TABLE issues_temp RENAME TO issues;

-- Recreate essential indexes (from original schema)
CREATE INDEX IF NOT EXISTS idx_issues_jurisdiction ON issues(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_category ON issues(category);
CREATE INDEX IF NOT EXISTS idx_issues_reported_at ON issues(reported_at);
CREATE INDEX IF NOT EXISTS idx_issues_temporal ON issues(jurisdiction_id, valid_from, valid_to);

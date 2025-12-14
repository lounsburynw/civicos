-- Migration 013: Add Structured Comment Metadata (Session 42)
-- Enables admin dashboards, analytics, and comment filtering

-- Add structured_summary column to comments table
ALTER TABLE comments ADD COLUMN structured_summary TEXT;

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_comments_position ON comments(
  json_extract(structured_summary, '$.position')
) WHERE structured_summary IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_comments_primary_archetype ON comments(
  json_extract(structured_summary, '$.primary_archetype')
) WHERE structured_summary IS NOT NULL;

-- Verify
SELECT
  COUNT(*) as total_comments,
  COUNT(structured_summary) as comments_with_metadata
FROM comments;

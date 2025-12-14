-- Migration 009: Add AI-generated title and summary to issues
-- Created: 2025-10-25
-- Purpose: Enable AI-generated titles and summaries for better issue scanning and navigation

-- Add ai_title column (AI-generated short title)
ALTER TABLE issues ADD COLUMN ai_title TEXT;

-- Add ai_summary column (AI-generated 2-3 sentence summary)
ALTER TABLE issues ADD COLUMN ai_summary TEXT;

-- Add timestamp for when AI content was generated
ALTER TABLE issues ADD COLUMN ai_generated_at TIMESTAMP;

-- Add index on ai_title for faster searching (optional, for future search features)
CREATE INDEX IF NOT EXISTS idx_issues_ai_title ON issues(ai_title);

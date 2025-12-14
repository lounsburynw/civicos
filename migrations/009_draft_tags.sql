-- Migration 009: Draft Tags (Session 48)
-- Add tags column to comment_drafts for topic-based organization

ALTER TABLE comment_drafts ADD COLUMN tags TEXT;  -- JSON array: ["housing", "transportation"]
CREATE INDEX idx_draft_tags ON comment_drafts(tags);

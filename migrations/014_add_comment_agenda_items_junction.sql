-- Migration 014: Add junction table for many-to-many comment-agenda_item relationship
-- Purpose: Properly track multiple agenda items per comment (not just the first one)
-- Date: 2025-10-30

-- Create junction table for comment-agenda_item relationships
CREATE TABLE IF NOT EXISTS comment_agenda_items (
    comment_id TEXT NOT NULL,
    agenda_item_id TEXT NOT NULL,
    item_order INTEGER NOT NULL,  -- Preserve selection order (0-indexed)
    created_at TEXT NOT NULL,
    PRIMARY KEY (comment_id, agenda_item_id),
    FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE CASCADE
);

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_comment_agenda_items_comment_id
ON comment_agenda_items(comment_id);

CREATE INDEX IF NOT EXISTS idx_comment_agenda_items_agenda_item_id
ON comment_agenda_items(agenda_item_id);

-- Migrate existing data from comments.agenda_item_id to junction table
-- (Only for rows that have a non-null agenda_item_id)
INSERT INTO comment_agenda_items (comment_id, agenda_item_id, item_order, created_at)
SELECT
    id,
    agenda_item_id,
    0,  -- First (and only) item has order 0
    created_at
FROM comments
WHERE agenda_item_id IS NOT NULL;

-- Note: We keep the agenda_item_id column in comments for backward compatibility
-- New code will use junction table, but old queries won't break
-- A future migration could remove the column after verifying all queries are updated

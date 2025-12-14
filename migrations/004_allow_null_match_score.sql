-- Migration 004: Allow NULL match_score for manual event links
-- Phase 2 - Task 1: Manual Event Linking
--
-- Changes:
-- - Remove NOT NULL constraint from match_score
-- - Remove CHECK constraint (will be applied in code instead)
-- - Allow manual links with match_score=NULL and match_reason=NULL

BEGIN TRANSACTION;

-- Create new table with updated schema
CREATE TABLE complaints_to_events_new (
    complaint_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    match_score REAL,  -- Allow NULL for manual links
    match_reason TEXT,
    matched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (complaint_id, event_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Copy existing data
INSERT INTO complaints_to_events_new (complaint_id, event_id, match_score, match_reason, matched_at)
SELECT complaint_id, event_id, match_score, match_reason, matched_at
FROM complaints_to_events;

-- Drop old table
DROP TABLE complaints_to_events;

-- Rename new table
ALTER TABLE complaints_to_events_new RENAME TO complaints_to_events;

-- Recreate indexes
CREATE INDEX idx_complaints_to_events_complaint ON complaints_to_events(complaint_id);
CREATE INDEX idx_complaints_to_events_event ON complaints_to_events(event_id);

COMMIT;

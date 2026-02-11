-- Add deadline_context column to coordination_action_events
-- This field explains why a deadline matters (e.g., "Comment period closes March 1")
ALTER TABLE coordination_action_events
ADD COLUMN IF NOT EXISTS deadline_context TEXT;

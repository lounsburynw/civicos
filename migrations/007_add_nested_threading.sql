-- Migration 007: Add nested threading support (extends 006)
-- Date: 2025-10-23
-- Description: Add reply count trigger (columns added in 006_add_nested_threading.sql)
-- NOTE: Columns parent_message_id and reply_count are added in 006_add_nested_threading.sql
--       This migration only adds the trigger and ensures data consistency.

-- Index for efficient nested retrieval (idempotent)
CREATE INDEX IF NOT EXISTS idx_messages_parent ON thread_messages(parent_message_id);

-- Trigger to update reply counts automatically (drop first if exists to be idempotent)
DROP TRIGGER IF EXISTS update_reply_count;
CREATE TRIGGER update_reply_count
AFTER INSERT ON thread_messages
FOR EACH ROW
WHEN NEW.parent_message_id IS NOT NULL
BEGIN
  UPDATE thread_messages
  SET reply_count = reply_count + 1
  WHERE message_id = NEW.parent_message_id;
END;

-- Update existing messages to have reply_count = 0 (idempotent)
UPDATE thread_messages SET reply_count = 0 WHERE reply_count IS NULL;

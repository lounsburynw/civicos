-- Migration 006: Add Nested Threading Support
-- Session 34: Phase 2 - Enable reply-to-message functionality

-- Add parent_message_id column to support nested replies
ALTER TABLE thread_messages ADD COLUMN parent_message_id TEXT;

-- Add reply_count column to track number of direct replies
ALTER TABLE thread_messages ADD COLUMN reply_count INTEGER DEFAULT 0;

-- Create index on parent_message_id for efficient retrieval of nested messages
CREATE INDEX IF NOT EXISTS idx_messages_parent ON thread_messages(parent_message_id);

-- Add foreign key constraint (SQLite version check needed)
-- parent_message_id should reference message_id in the same table
-- Note: SQLite ALTER TABLE doesn't support adding foreign keys to existing tables
-- This constraint will be enforced in application logic

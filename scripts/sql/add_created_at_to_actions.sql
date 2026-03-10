-- Migration: Add created_at column to coordination_actions table
-- Required by: require_created_at_on_writes security fix
-- All write endpoints now require created_at for signature verification

ALTER TABLE coordination_actions
ADD COLUMN IF NOT EXISTS created_at BIGINT DEFAULT 0;

COMMENT ON COLUMN coordination_actions.created_at IS 'Unix timestamp from signed Nostr event (required for signature verification)';

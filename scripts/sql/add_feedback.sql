-- Feedback table for user-submitted feedback via the relay.
-- Regular Nostr events (kind 1804) — allows multiple submissions per user.

CREATE TABLE IF NOT EXISTS coordination_feedback (
  id SERIAL PRIMARY KEY,
  public_key TEXT NOT NULL,
  feedback_type TEXT NOT NULL CHECK (feedback_type IN ('bug', 'feature', 'general')),
  content TEXT NOT NULL,
  jurisdiction TEXT NOT NULL,
  signature TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feedback_jurisdiction ON coordination_feedback(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON coordination_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_received ON coordination_feedback(received_at DESC);

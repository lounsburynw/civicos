-- Migration 008: Item Comment Cache for Memoized Per-Item Generation
-- Session 47: Enable caching of individual agenda item comments for reuse across drafts and users

CREATE TABLE IF NOT EXISTS item_comment_cache (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  event_id TEXT NOT NULL,
  item_ref TEXT NOT NULL,
  item_title TEXT,
  item_description TEXT,
  content TEXT NOT NULL,
  legislative_context TEXT,  -- JSON: {state_bills: [...], federal_programs: [...]}
  word_count INTEGER,
  generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id, item_ref)
);

CREATE INDEX idx_cache_event ON item_comment_cache(event_id);
CREATE INDEX idx_cache_generated ON item_comment_cache(generated_at);

-- Note: For future cleanup of old cache entries (optional):
-- DELETE FROM item_comment_cache WHERE generated_at < datetime('now', '-30 days');

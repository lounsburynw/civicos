-- Migration 010: Cache Metrics (Session 48)
-- Track cache hits/misses for analytics and optimization

CREATE TABLE IF NOT EXISTS cache_metrics (
  id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  event_id TEXT NOT NULL,
  item_ref TEXT NOT NULL,
  hit BOOLEAN NOT NULL,  -- 1 for cache hit, 0 for cache miss
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_metrics_timestamp ON cache_metrics(timestamp);
CREATE INDEX idx_metrics_event ON cache_metrics(event_id);

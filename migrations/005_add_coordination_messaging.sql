-- Migration 005: Add Following System and Coordination Messaging
-- Task 2: Following system (follows + coordination_threads tables)
-- Task 3: In-app coordination chat (thread_messages table)

-- Following System (Task 2)
CREATE TABLE IF NOT EXISTS follows (
    follow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    focal_type TEXT NOT NULL CHECK(focal_type IN ('complaint', 'event')),
    focal_id TEXT NOT NULL,
    jurisdiction_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, focal_type, focal_id)
);

-- Coordination Threads (Task 2 - auto-created with first follow)
CREATE TABLE IF NOT EXISTS coordination_threads (
    thread_id TEXT PRIMARY KEY,
    focal_type TEXT NOT NULL CHECK(focal_type IN ('complaint', 'event')),
    focal_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    UNIQUE(focal_type, focal_id)
);

-- Thread Messages (Task 3 - in-app messaging)
CREATE TABLE IF NOT EXISTS thread_messages (
    message_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES coordination_threads(thread_id)
);

-- Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_follows_focal ON follows(focal_type, focal_id);
CREATE INDEX IF NOT EXISTS idx_follows_user ON follows(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_focal ON coordination_threads(focal_type, focal_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread_time ON thread_messages(thread_id, created_at DESC);

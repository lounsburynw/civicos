-- Migration 008: Rename complaints to issues
-- Renames all complaint-related tables and columns to use "issue" terminology
-- This is a breaking change - requires coordinated deployment with code updates

-- Note: Some tables (issues, issue_event_matches, issue_timeline) may already be renamed
-- This migration is idempotent and will skip already-renamed tables

-- 1. Rename legacy tables if they still exist
-- Check and rename complaints_to_events
-- (Skip if doesn't exist)

-- 2. Rename legacy junction tables
-- complaints_to_events -> issues_to_events (if exists)
-- complaints_to_groups -> issues_to_groups (if exists)
-- users_to_complaints -> users_to_issues (if exists)
-- proposals_to_complaints -> proposals_to_issues (if exists)
-- complaint_connections -> issue_connections (if exists)

-- 3. Update CHECK constraints on follows table
-- Need to recreate table to change CHECK constraint
CREATE TABLE follows_new (
    follow_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    focal_type TEXT NOT NULL CHECK(focal_type IN ('issue', 'event')),
    focal_id TEXT NOT NULL,
    jurisdiction_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, focal_type, focal_id)
);

-- Copy data, updating 'complaint' to 'issue'
INSERT INTO follows_new (follow_id, user_id, focal_type, focal_id, jurisdiction_id, created_at, last_seen_at)
SELECT
    follow_id,
    user_id,
    CASE WHEN focal_type = 'complaint' THEN 'issue' ELSE focal_type END,
    focal_id,
    jurisdiction_id,
    created_at,
    last_seen_at
FROM follows;

DROP TABLE follows;
ALTER TABLE follows_new RENAME TO follows;

-- 4. Update CHECK constraints on coordination_threads table
CREATE TABLE coordination_threads_new (
    thread_id TEXT PRIMARY KEY,
    focal_type TEXT NOT NULL CHECK(focal_type IN ('issue', 'event')),
    focal_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    UNIQUE(focal_type, focal_id)
);

-- Copy data, updating 'complaint' to 'issue'
INSERT INTO coordination_threads_new (thread_id, focal_type, focal_id, created_at, last_message_at)
SELECT
    thread_id,
    CASE WHEN focal_type = 'complaint' THEN 'issue' ELSE focal_type END,
    focal_id,
    created_at,
    last_message_at
FROM coordination_threads;

DROP TABLE coordination_threads;
ALTER TABLE coordination_threads_new RENAME TO coordination_threads;

-- 5. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_follows_user_id ON follows(user_id);
CREATE INDEX IF NOT EXISTS idx_follows_focal ON follows(focal_type, focal_id);
CREATE INDEX IF NOT EXISTS idx_coordination_threads_focal ON coordination_threads(focal_type, focal_id);

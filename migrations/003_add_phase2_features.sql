-- Migration 003: Add Phase 2 Community Formation features
-- Layer 6 Phase 2: Government Response Tracking + Community Formation
-- Created: 2025-10-13

-- Complaint Timeline (Government Response Tracking)
CREATE TABLE IF NOT EXISTS complaint_timeline (
    entry_id TEXT PRIMARY KEY,
    complaint_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'filed', 'matched', 'linked', 'status_change', 'response', 'action_taken'
    )),
    description TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('user', 'system', 'admin')),
    metadata TEXT, -- JSON blob for additional context

    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Update discussion_groups to support Phase 2 features
-- Drop and recreate with new schema
DROP TABLE IF EXISTS discussion_groups_old;
ALTER TABLE discussion_groups RENAME TO discussion_groups_old;

CREATE TABLE IF NOT EXISTS discussion_groups (
    group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    jurisdiction_id TEXT NOT NULL,
    issue_type TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    privacy TEXT NOT NULL DEFAULT 'public' CHECK(privacy IN ('public', 'private')),

    FOREIGN KEY (jurisdiction_id) REFERENCES jurisdictions(jurisdiction_id)
);

-- Complaint-to-Group Mapping (Phase 2)
CREATE TABLE IF NOT EXISTS complaints_to_groups (
    complaint_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (complaint_id, group_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES discussion_groups(group_id) ON DELETE CASCADE
);

-- Connection Requests (Phase 2 - optional)
CREATE TABLE IF NOT EXISTS complaint_connections (
    connection_id TEXT PRIMARY KEY,
    source_complaint_id TEXT NOT NULL,
    target_complaint_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'accepted', 'declined')),
    message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (source_complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY (target_complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Indexes for Phase 2 queries
CREATE INDEX IF NOT EXISTS idx_complaint_timeline_complaint ON complaint_timeline(complaint_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_complaint_timeline_event_type ON complaint_timeline(event_type);

CREATE INDEX IF NOT EXISTS idx_discussion_groups_jurisdiction ON discussion_groups(jurisdiction_id, issue_type);
CREATE INDEX IF NOT EXISTS idx_complaints_to_groups_complaint ON complaints_to_groups(complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaints_to_groups_group ON complaints_to_groups(group_id);

CREATE INDEX IF NOT EXISTS idx_complaint_connections_source ON complaint_connections(source_complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaint_connections_target ON complaint_connections(target_complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaint_connections_status ON complaint_connections(status);

-- Copy old discussion groups data if needed (migration path)
-- INSERT INTO discussion_groups (group_id, name, description, jurisdiction_id, created_at)
-- SELECT id, platform || '_' || focal_point_type, NULL, NULL, created_at FROM discussion_groups_old;

-- Note: Run this migration with:
-- sqlite3 data/civic_participation.db < migrations/003_add_phase2_features.sql

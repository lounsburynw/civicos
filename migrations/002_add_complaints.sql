-- Migration 002: Add complaint-to-civic matching tables
-- Layer 2: Storage & Persistence
-- Created: 2025-10-12

-- Complaints table (ephemeral user-generated focal points)
CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL CHECK(length(description) <= 2000),
    issue_type TEXT CHECK(issue_type IN (
        'housing', 'transportation', 'environment',
        'public_safety', 'infrastructure', 'other'
    )),
    jurisdiction_id TEXT NOT NULL,

    -- Location
    address TEXT,
    latitude REAL,
    longitude REAL,

    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN (
        'open', 'matched', 'community_formed', 'escalated', 'resolved'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Reserved for Phase 2+
    ai_analysis TEXT,  -- JSON blob

    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id)
);

-- Junction table: complaints to events (many-to-many)
CREATE TABLE IF NOT EXISTS complaints_to_events (
    complaint_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    match_score REAL NOT NULL CHECK(match_score >= 0 AND match_score <= 100),
    match_reason TEXT,
    matched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (complaint_id, event_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Junction table: users to complaints (many-to-many for clustering)
CREATE TABLE IF NOT EXISTS users_to_complaints (
    user_id TEXT NOT NULL,
    complaint_id TEXT NOT NULL,
    relationship_type TEXT CHECK(relationship_type IN (
        'author', 'supporter', 'mentioned'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, complaint_id),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Discussion groups (external messaging integration)
CREATE TABLE IF NOT EXISTS discussion_groups (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK(platform IN ('slack', 'discord', 'signal')),
    platform_url TEXT,
    focal_point_type TEXT NOT NULL CHECK(focal_point_type IN (
        'CivicEvent', 'Complaint', 'ProposedAgendaItem'
    )),
    focal_point_id TEXT NOT NULL,
    member_count INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Proposed agenda items (escalation path)
CREATE TABLE IF NOT EXISTS proposed_agenda_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    target_event_id TEXT,  -- Which meeting to submit to
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN (
        'draft', 'submitted', 'accepted', 'rejected'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Junction: proposals to complaints (what led to this proposal)
CREATE TABLE IF NOT EXISTS proposals_to_complaints (
    proposal_id TEXT NOT NULL,
    complaint_id TEXT NOT NULL,

    PRIMARY KEY (proposal_id, complaint_id),
    FOREIGN KEY (proposal_id) REFERENCES proposed_agenda_items(id) ON DELETE CASCADE,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Junction: users to proposals (who supports this)
CREATE TABLE IF NOT EXISTS users_to_proposals (
    user_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    role TEXT CHECK(role IN ('author', 'supporter', 'editor')),
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, proposal_id),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id),
    FOREIGN KEY (proposal_id) REFERENCES proposed_agenda_items(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_complaints_jurisdiction ON complaints(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_created ON complaints(created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_issue_type ON complaints(issue_type);
CREATE INDEX IF NOT EXISTS idx_complaints_location ON complaints(latitude, longitude);

CREATE INDEX IF NOT EXISTS idx_complaints_to_events_complaint ON complaints_to_events(complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaints_to_events_event ON complaints_to_events(event_id);

CREATE INDEX IF NOT EXISTS idx_discussion_groups_focal ON discussion_groups(focal_point_type, focal_point_id);

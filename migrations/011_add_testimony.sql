-- Migration 011: Add retrospective decisions and testimony tracking
-- Created: 2025-11-13
-- Purpose: Store retrospective high-stakes decisions and testimony for coalition discovery

-- Decisions table: Store high-stakes decisions from retrospective analysis
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction_id TEXT NOT NULL,
    item_ref TEXT,
    title TEXT NOT NULL,
    description TEXT,
    meeting_date DATETIME NOT NULL,
    meeting_type TEXT,
    is_high_stakes BOOLEAN,
    stakes_score INTEGER,
    decision_type TEXT,
    budget_amount INTEGER,
    budget_description TEXT,
    affected_population_estimate INTEGER,
    geographic_scope TEXT,
    project_types TEXT,  -- JSON array
    keywords_for_matching TEXT,  -- JSON array
    agenda_url TEXT,
    minutes_url TEXT,
    meeting_title TEXT,
    meeting_url TEXT,
    legistar_event_item_id INTEGER,  -- For Legistar API testimony lookup
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for decisions
CREATE INDEX IF NOT EXISTS idx_decisions_jurisdiction ON decisions(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_decisions_meeting_date ON decisions(meeting_date);
CREATE INDEX IF NOT EXISTS idx_decisions_item_ref ON decisions(jurisdiction_id, meeting_date, item_ref);
CREATE INDEX IF NOT EXISTS idx_decisions_legistar_id ON decisions(legistar_event_item_id);

-- Testimony table: Track who testified at council meetings
CREATE TABLE IF NOT EXISTS testimony (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    speaker_name TEXT,
    position TEXT,  -- support/oppose/neutral/comment (inferred or null)
    organization TEXT,
    testimony_text TEXT,  -- if available from minutes
    speaking_order INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
);

-- Indexes for testimony (coalition discovery queries)
CREATE INDEX IF NOT EXISTS idx_testimony_decision ON testimony(decision_id);
CREATE INDEX IF NOT EXISTS idx_testimony_speaker ON testimony(speaker_name);
CREATE INDEX IF NOT EXISTS idx_testimony_org ON testimony(organization);
CREATE INDEX IF NOT EXISTS idx_testimony_created ON testimony(created_at);
CREATE INDEX IF NOT EXISTS idx_testimony_speaker_org ON testimony(speaker_name, organization);

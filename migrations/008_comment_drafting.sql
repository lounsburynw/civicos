-- Migration 008: Comment Drafting System
-- Enables structured input for AI-powered comment generation

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    event_id TEXT NOT NULL,
    agenda_item_id TEXT,

    -- Structured input
    position TEXT NOT NULL CHECK(position IN ('support', 'oppose', 'neutral', 'questions')),
    key_concern TEXT NOT NULL,

    -- Personal context (JSON)
    personal_context TEXT,  -- JSON: {stakes, yearsInArea, district, expertise}

    -- AI generation
    ai_draft_generated BOOLEAN DEFAULT FALSE,
    ai_draft TEXT,
    final_comment TEXT,

    -- Metadata
    submission_format TEXT CHECK(submission_format IN ('written', 'oral', 'letter', 'email')),
    submitted BOOLEAN DEFAULT FALSE,
    submitted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE INDEX idx_comments_event ON comments(event_id);
CREATE INDEX idx_comments_position ON comments(position);
CREATE INDEX idx_comments_user ON comments(user_id);

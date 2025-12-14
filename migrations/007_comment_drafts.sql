-- Draft comment storage with version history and autosave support
CREATE TABLE IF NOT EXISTS comment_drafts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    content TEXT NOT NULL,
    structured_summary TEXT,  -- JSON: {tldr, position, key_topics, legislative_references}
    personal_context TEXT,    -- JSON: {stakes, yearsInArea, district, expertise}
    selected_agenda_items TEXT,  -- JSON: ["item-7.2", "item-9.1"]
    is_template BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted BOOLEAN DEFAULT FALSE,
    submitted_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drafts_user_event ON comment_drafts(user_id, event_id);
CREATE INDEX IF NOT EXISTS idx_drafts_updated ON comment_drafts(updated_at DESC);

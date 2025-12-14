-- Migration 011: Conversation Store
-- Session 79 Phase 1
--
-- Purpose: Add persistent conversation storage with full LLM message format support
-- Fixes: Conversation history bug where tool_calls were stripped (causing DeepSeek to repeat old parameters)
-- Architecture: Hybrid approach - clean conversations + optional UI snapshots + ephemeral active context injection
--
-- Tables:
-- 1. conversations - Core conversation metadata
-- 2. messages - Full OpenAI format messages (including tool_calls)
-- 3. ui_snapshots - Optional UI state capture for debugging/analytics
-- 4. sessions - Active session tracking with current UI state

-- Core conversations table (always populated)
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT,  -- Link to user accounts (nullable for now)
    title TEXT,  -- Auto-generated from first message or user-set
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,  -- {model, total_tokens, context_length, etc.}
    archived BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);

-- Messages table with full OpenAI format support
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT,  -- Optional for assistant messages with only tool_calls

    -- Function calling support (OpenAI format)
    -- For assistant messages: [{"id": "call_abc", "type": "function", "function": {"name": "search", "arguments": "{...}"}}]
    tool_calls JSON,

    -- For tool result messages
    tool_call_id TEXT,  -- References tool_calls[].id from assistant message
    name TEXT,  -- Function name

    -- Message metadata
    metadata JSON,  -- {model, tokens, provider, timestamp, etc.}
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(conversation_id, created_at);

-- Optional UI snapshots table (for debugging/analytics - Phase 2+)
-- Separate retention policy: conversations stored long-term, snapshots purged after 30 days
CREATE TABLE IF NOT EXISTS ui_snapshots (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
    snapshot_data JSON NOT NULL,  -- Full UI state at this turn: {artifacts, filters, tabs, etc.}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshots_conversation ON ui_snapshots(conversation_id, created_at DESC);

-- Session metadata table (tracks active sessions - Phase 2+)
-- Links browser sessions to conversations, tracks current UI state
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    user_id TEXT,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ui_state JSON,  -- Current UI state: {open_tabs, current_filters, active_artifact, etc.}
    metadata JSON  -- {browser, ip, user_agent, etc.}
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, last_active DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(last_active DESC);

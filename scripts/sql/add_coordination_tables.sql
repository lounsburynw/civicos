-- Core coordination tables for relay storage
-- Tables: voices, subscriptions, provenance, initiatives, events_log, sync_cursors
--
-- Run this migration on the database (DATABASE_URL or RELAY_DATABASE_URL)
-- The action tables (coordination_actions, coordination_action_events, etc.)
-- are created by add_action_events.sql

-- ============================================================================
-- Voices - civic stance on entities
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_voices (
    entity TEXT NOT NULL,                          -- Entity being voiced on
    stance TEXT NOT NULL,                          -- support, oppose, abstain
    public_key TEXT NOT NULL,                      -- Voter's public key (hex)
    signature TEXT NOT NULL,                       -- Signature of voice (hex)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (public_key, entity),

    CONSTRAINT valid_stance CHECK (
        stance IN ('support', 'oppose', 'abstain')
    )
);

CREATE INDEX IF NOT EXISTS idx_voices_entity
    ON coordination_voices(entity);
CREATE INDEX IF NOT EXISTS idx_voices_public_key
    ON coordination_voices(public_key);
CREATE INDEX IF NOT EXISTS idx_voices_timestamp
    ON coordination_voices(timestamp);

-- ============================================================================
-- Subscriptions - notification subscriptions
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_subscriptions (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    match_criteria JSONB NOT NULL DEFAULT '{}',
    delivery_method TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    public_key TEXT,

    CONSTRAINT valid_delivery_method CHECK (
        delivery_method IN ('email', 'webhook', 'websocket')
    )
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_jurisdiction
    ON coordination_subscriptions(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_subscriptions_active
    ON coordination_subscriptions(active);

-- ============================================================================
-- Provenance - key activity tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_provenance (
    public_key TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    total_voices INTEGER NOT NULL DEFAULT 0,
    entities_touched INTEGER NOT NULL DEFAULT 0,
    first_voice_at TIMESTAMP WITH TIME ZONE,
    last_voice_at TIMESTAMP WITH TIME ZONE,
    jurisdictions JSONB NOT NULL DEFAULT '[]'
);

-- ============================================================================
-- Initiatives - community initiatives
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_initiatives (
    id TEXT PRIMARY KEY,
    jurisdiction TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    coordination_url TEXT,
    public_key TEXT NOT NULL,
    signature TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'proposed',
    voice_count INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT valid_initiative_status CHECK (
        status IN ('proposed', 'active', 'completed', 'archived')
    )
);

-- Migration: add coordination_url column if it doesn't exist
ALTER TABLE coordination_initiatives ADD COLUMN IF NOT EXISTS coordination_url TEXT;

CREATE INDEX IF NOT EXISTS idx_initiatives_jurisdiction
    ON coordination_initiatives(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_initiatives_topic
    ON coordination_initiatives(topic);
CREATE INDEX IF NOT EXISTS idx_initiatives_status
    ON coordination_initiatives(status);
CREATE INDEX IF NOT EXISTS idx_initiatives_voice_count
    ON coordination_initiatives(voice_count DESC);

-- ============================================================================
-- Events log - coordination event history
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_events_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    jurisdiction TEXT,
    entity TEXT,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL DEFAULT '{}',
    deliveries_attempted INTEGER DEFAULT 0,
    deliveries_succeeded INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_log_type
    ON coordination_events_log(event_type);
CREATE INDEX IF NOT EXISTS idx_events_log_jurisdiction
    ON coordination_events_log(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_events_log_timestamp
    ON coordination_events_log(timestamp);

-- ============================================================================
-- Sync cursors - federation sync state
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_sync_cursors (
    peer_url TEXT PRIMARY KEY,
    cursor TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Enable RLS for new tables
-- ============================================================================

ALTER TABLE coordination_voices ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_initiatives ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_events_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_sync_cursors ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (bypasses RLS by default, but explicit for clarity)
CREATE POLICY "Service role has full access to voices"
    ON coordination_voices FOR ALL
    USING (true);

CREATE POLICY "Service role has full access to subscriptions"
    ON coordination_subscriptions FOR ALL
    USING (true);

CREATE POLICY "Service role has full access to provenance"
    ON coordination_provenance FOR ALL
    USING (true);

CREATE POLICY "Service role has full access to initiatives"
    ON coordination_initiatives FOR ALL
    USING (true);

CREATE POLICY "Service role has full access to events_log"
    ON coordination_events_log FOR ALL
    USING (true);

CREATE POLICY "Service role has full access to sync_cursors"
    ON coordination_sync_cursors FOR ALL
    USING (true);

-- ============================================================================
-- Peer health state - persisted across relay restarts
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_peer_health (
    peer_url TEXT PRIMARY KEY,
    healthy BOOLEAN NOT NULL DEFAULT TRUE,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_health_check TIMESTAMP WITH TIME ZONE,
    last_successful_sync TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE coordination_peer_health ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to peer_health"
    ON coordination_peer_health FOR ALL
    USING (true);

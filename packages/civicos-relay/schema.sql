-- Coordination Protocol Schema
-- Tables for voice, subscriptions, and provenance

-- Voices: public expressions of civic interest
CREATE TABLE IF NOT EXISTS coordination_voices (
    id SERIAL PRIMARY KEY,
    entity VARCHAR(255) NOT NULL,
    stance VARCHAR(20) NOT NULL CHECK (stance IN ('support', 'oppose', 'watching')),
    public_key VARCHAR(255) NOT NULL,
    signature TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    -- One voice per key per entity
    UNIQUE (public_key, entity)
);

CREATE INDEX IF NOT EXISTS idx_voices_entity ON coordination_voices(entity);
CREATE INDEX IF NOT EXISTS idx_voices_public_key ON coordination_voices(public_key);
CREATE INDEX IF NOT EXISTS idx_voices_timestamp ON coordination_voices(timestamp);

-- Subscriptions: event routing preferences
CREATE TABLE IF NOT EXISTS coordination_subscriptions (
    id VARCHAR(50) PRIMARY KEY,
    jurisdiction VARCHAR(100) NOT NULL,
    match_criteria JSONB NOT NULL,
    delivery_method VARCHAR(20) NOT NULL CHECK (delivery_method IN ('email', 'webhook')),
    delivery_address VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    public_key VARCHAR(255),  -- Optional link to voice key

    CONSTRAINT valid_email CHECK (
        delivery_method != 'email' OR delivery_address ~ '^[^@]+@[^@]+\.[^@]+$'
    )
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_jurisdiction ON coordination_subscriptions(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON coordination_subscriptions(active);
CREATE INDEX IF NOT EXISTS idx_subscriptions_public_key ON coordination_subscriptions(public_key);

-- Provenance: trust signals for keys
CREATE TABLE IF NOT EXISTS coordination_provenance (
    public_key VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_voices INTEGER NOT NULL DEFAULT 0,
    entities_touched INTEGER NOT NULL DEFAULT 0,
    first_voice_at TIMESTAMPTZ,
    last_voice_at TIMESTAMPTZ,
    jurisdictions JSONB NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_provenance_created_at ON coordination_provenance(created_at);
CREATE INDEX IF NOT EXISTS idx_provenance_total_voices ON coordination_provenance(total_voices);

-- Events log (for debugging and audit)
CREATE TABLE IF NOT EXISTS coordination_events_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    jurisdiction VARCHAR(100) NOT NULL,
    entity VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL DEFAULT '{}',
    deliveries_attempted INTEGER NOT NULL DEFAULT 0,
    deliveries_succeeded INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_log_jurisdiction ON coordination_events_log(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_events_log_timestamp ON coordination_events_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_log_entity ON coordination_events_log(entity);

-- Enable RLS (follows existing pattern)
ALTER TABLE coordination_voices ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_events_log ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY coordination_voices_service ON coordination_voices
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY coordination_subscriptions_service ON coordination_subscriptions
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY coordination_provenance_service ON coordination_provenance
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY coordination_events_log_service ON coordination_events_log
    FOR ALL TO service_role USING (true) WITH CHECK (true);

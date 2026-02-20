-- Platform Billing Migration
-- Creates tables for API key management, usage logging, and usage rollups.
-- Run against the Platform DB (PLATFORM_DATABASE_URL):
--   psql $PLATFORM_DATABASE_URL -f scripts/sql/add_platform_billing.sql

BEGIN;

-- =============================================================================
-- platform_api_keys: Database-backed API key management
-- =============================================================================
CREATE TABLE IF NOT EXISTS platform_api_keys (
    key_id TEXT PRIMARY KEY,                         -- "cvk_live_..." prefix for identification
    key_hash TEXT NOT NULL UNIQUE,                    -- SHA-256 of the actual key (raw key never stored)
    name TEXT NOT NULL,                               -- "Marin IJ Newsroom", "League of Women Voters"
    email TEXT NOT NULL,                              -- Contact email
    tier TEXT NOT NULL DEFAULT 'free',                -- free, journalist, organization, city, api
    stripe_customer_id TEXT,                          -- "cus_..." links to Stripe
    stripe_subscription_id TEXT,                      -- "sub_..." links to Stripe subscription
    jurisdictions JSONB NOT NULL DEFAULT '[]',        -- Which jurisdictions this key can access
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',            -- active, suspended, revoked, expired
    metadata JSONB NOT NULL DEFAULT '{}',

    CONSTRAINT valid_tier CHECK (tier IN ('free', 'journalist', 'organization', 'city', 'api')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'suspended', 'revoked', 'expired'))
);

CREATE INDEX IF NOT EXISTS idx_platform_api_keys_key_hash ON platform_api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_platform_api_keys_email ON platform_api_keys(email);
CREATE INDEX IF NOT EXISTS idx_platform_api_keys_stripe_customer ON platform_api_keys(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_platform_api_keys_status ON platform_api_keys(status);

-- =============================================================================
-- platform_usage_logs: Request-level usage tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS platform_usage_logs (
    id BIGSERIAL PRIMARY KEY,
    key_id TEXT REFERENCES platform_api_keys(key_id),  -- NULL for unauthenticated requests
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'GET',
    status_code INTEGER,
    response_time_ms INTEGER,
    jurisdiction TEXT,                                   -- Which jurisdiction was queried
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_platform_usage_logs_key_id ON platform_usage_logs(key_id);
CREATE INDEX IF NOT EXISTS idx_platform_usage_logs_timestamp ON platform_usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_platform_usage_logs_endpoint_ts ON platform_usage_logs(endpoint, timestamp);

-- =============================================================================
-- platform_usage_daily: Aggregated daily usage (for retention)
-- =============================================================================
CREATE TABLE IF NOT EXISTS platform_usage_daily (
    key_id TEXT REFERENCES platform_api_keys(key_id),
    endpoint TEXT NOT NULL,
    date DATE NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    avg_response_ms INTEGER,
    error_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key_id, endpoint, date)
);

-- =============================================================================
-- RLS: Enable row-level security (service_role only)
-- =============================================================================
ALTER TABLE platform_api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_usage_daily ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'platform_api_keys_service_role') THEN
        CREATE POLICY platform_api_keys_service_role ON platform_api_keys
            FOR ALL USING (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'platform_usage_logs_service_role') THEN
        CREATE POLICY platform_usage_logs_service_role ON platform_usage_logs
            FOR ALL USING (auth.role() = 'service_role');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'platform_usage_daily_service_role') THEN
        CREATE POLICY platform_usage_daily_service_role ON platform_usage_daily
            FOR ALL USING (auth.role() = 'service_role');
    END IF;
END $$;

COMMIT;

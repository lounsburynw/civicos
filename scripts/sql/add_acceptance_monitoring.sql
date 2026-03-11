-- Acceptance policy monitoring tables
-- Logs every acceptance decision for observability (rejections, tier distribution, rate limit hits)
--
-- Run this in Supabase SQL Editor or via psql against the relay DB

CREATE TABLE IF NOT EXISTS coordination_acceptance_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    acceptance_tier TEXT NOT NULL,
    accepted BOOLEAN NOT NULL,
    reason TEXT,
    public_key_hash TEXT NOT NULL
);

-- Time-range queries by tier (primary monitoring query)
CREATE INDEX IF NOT EXISTS idx_acceptance_logs_ts_tier
    ON coordination_acceptance_logs(timestamp, acceptance_tier);

-- Filter by outcome (accepted vs rejected)
CREATE INDEX IF NOT EXISTS idx_acceptance_logs_ts_accepted
    ON coordination_acceptance_logs(timestamp, accepted);

-- Event type breakdown
CREATE INDEX IF NOT EXISTS idx_acceptance_logs_event_type
    ON coordination_acceptance_logs(event_type, timestamp);

-- Enable RLS (following enable_rls.sql pattern)
DO $$
BEGIN
    EXECUTE 'ALTER TABLE public.coordination_acceptance_logs ENABLE ROW LEVEL SECURITY';
    EXECUTE 'DROP POLICY IF EXISTS service_role_only ON public.coordination_acceptance_logs';
    EXECUTE 'CREATE POLICY service_role_only ON public.coordination_acceptance_logs FOR ALL TO public USING (false)';
    RAISE NOTICE 'Secured table: coordination_acceptance_logs';
END $$;

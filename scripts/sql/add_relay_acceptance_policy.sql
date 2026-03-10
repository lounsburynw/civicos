-- Relay acceptance policy tables
-- Rate limiting and write metadata for relay write endpoints
--
-- Run this in Supabase SQL Editor or via psql against the relay DB

CREATE TABLE IF NOT EXISTS coordination_rate_limits (
    public_key_hash TEXT NOT NULL,
    event_type TEXT NOT NULL,
    day DATE NOT NULL DEFAULT CURRENT_DATE,
    count INT NOT NULL DEFAULT 1,
    PRIMARY KEY (public_key_hash, event_type, day)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_day ON coordination_rate_limits(day);

CREATE TABLE IF NOT EXISTS coordination_write_metadata (
    public_key_hash TEXT NOT NULL,
    entity TEXT NOT NULL,
    acceptance_tier TEXT NOT NULL CHECK (acceptance_tier IN ('attested', 'paid', 'rate_limited', 'legacy')),
    accepted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (public_key_hash, entity)
);

CREATE INDEX IF NOT EXISTS idx_write_metadata_tier ON coordination_write_metadata(acceptance_tier);

-- Enable RLS (following enable_rls.sql pattern)
DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY[
        'coordination_rate_limits',
        'coordination_write_metadata'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS service_role_only ON public.%I', tbl);
        EXECUTE format('CREATE POLICY service_role_only ON public.%I FOR ALL TO public USING (false)', tbl);
        RAISE NOTICE 'Secured table: %', tbl;
    END LOOP;
END $$;

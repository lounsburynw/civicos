-- Spent token tracking for blind signature token scheme
-- Prevents double-spending by recording token hashes atomically with writes
--
-- Run this in Supabase SQL Editor or via psql against the relay DB

CREATE TABLE IF NOT EXISTS coordination_spent_tokens (
    token_hash TEXT PRIMARY KEY,                    -- SHA-256(message || signature)
    spent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    relay_write_id TEXT                             -- FK to the write this token paid for
);

CREATE INDEX IF NOT EXISTS idx_spent_tokens_spent_at ON coordination_spent_tokens(spent_at);

-- Enable RLS (following enable_rls.sql pattern)
DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY['coordination_spent_tokens'];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS service_role_full_access ON %I', tbl);
        EXECUTE format(
            'CREATE POLICY service_role_full_access ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)',
            tbl
        );
    END LOOP;
END $$;

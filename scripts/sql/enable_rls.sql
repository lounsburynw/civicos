-- Enable Row Level Security on ALL public tables (dynamically discovered)
-- Policy: DENY all access via Supabase REST API (anon/authenticated roles)
-- Only service_role (used by Python backend via DATABASE_URL) can access
--
-- This is REAL security, not just silencing warnings.
-- Safe to re-run: idempotent (drops + recreates policies, skips already-enabled tables).
--
-- Run this in Supabase SQL Editor or via psql

DO $$
DECLARE
    rec RECORD;
    secured INT := 0;
    skipped INT := 0;
BEGIN
    FOR rec IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename NOT LIKE 'pg_%'
        ORDER BY tablename
    LOOP
        -- Enable RLS (no-op if already enabled)
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', rec.tablename);

        -- Drop any existing policies from prior runs
        EXECUTE format('DROP POLICY IF EXISTS allow_all ON public.%I', rec.tablename);
        EXECUTE format('DROP POLICY IF EXISTS service_role_only ON public.%I', rec.tablename);

        -- Create policy: ONLY service_role can access (bypasses RLS by default)
        -- anon and authenticated roles get NOTHING
        -- This means: REST API = blocked, Python backend = works
        EXECUTE format(
            'CREATE POLICY service_role_only ON public.%I FOR ALL TO public USING (false)',
            rec.tablename
        );

        secured := secured + 1;
        RAISE NOTICE 'Secured table: %', rec.tablename;
    END LOOP;

    RAISE NOTICE '--- RLS enabled on % tables ---', secured;
END $$;

-- Note: service_role bypasses RLS by default in Supabase, so our Python backend
-- (which connects via DATABASE_URL with service_role privileges) still works.
-- But anon/authenticated keys via REST API are now blocked.

-- Verify: all public tables should show rowsecurity = true
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename NOT LIKE 'pg_%'
ORDER BY tablename;

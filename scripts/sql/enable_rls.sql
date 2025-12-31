-- Enable Row Level Security on all public tables
-- Policy: DENY all access via Supabase REST API (anon/authenticated roles)
-- Only service_role (used by Python backend via DATABASE_URL) can access
--
-- This is REAL security, not just silencing warnings.
--
-- Run this in Supabase SQL Editor or via psql

DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY[
        'agenda_items',
        'chunks',
        'city_states',
        'decisions',
        'etl_costs',
        'issues',
        'legislation',
        'meetings',
        'municipal_code',
        'operations',
        'transcripts',
        'vector_embeddings',
        'videos'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables
    LOOP
        -- Enable RLS
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);

        -- Drop any existing policies
        EXECUTE format('DROP POLICY IF EXISTS allow_all ON public.%I', tbl);
        EXECUTE format('DROP POLICY IF EXISTS service_role_only ON public.%I', tbl);

        -- Create policy: ONLY service_role can access (bypasses RLS by default)
        -- anon and authenticated roles get NOTHING
        -- This means: REST API = blocked, Python backend = works
        EXECUTE format('CREATE POLICY service_role_only ON public.%I FOR ALL TO public USING (false)', tbl);

        RAISE NOTICE 'Secured table: %', tbl;
    END LOOP;
END $$;

-- Note: service_role bypasses RLS by default in Supabase, so our Python backend
-- (which connects via DATABASE_URL with service_role privileges) still works.
-- But anon/authenticated keys via REST API are now blocked.

-- Verify RLS is enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename NOT LIKE 'pg_%'
ORDER BY tablename;

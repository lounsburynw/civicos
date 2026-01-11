# Recommended: federal_programs_postgres_migration

**Priority:** P0
**Area:** data_architecture > data_source_unification
**Date:** 2026-01-10

> This is recommended context from Session 503. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 503 completed `federal_programs_2026_refresh` and discovered that federal programs data is stored in static JSON files, not in PostgreSQL like other corpus types. This creates gaps:
- Not semantically searchable via vectors
- Siloed from main data query paths
- No temporal versioning for FY tracking

## Recommended Task

Migrate federal programs data from static JSON to PostgreSQL with proper schema.

## Current Data Locations

```
data/funding/federal/{topic}.json          # National program info (CDBG, HOME descriptions)
data/jurisdiction_overrides/{city}.json    # Local allocations, contacts, deadlines
```

## Suggested Schema

```sql
CREATE TABLE federal_programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id TEXT NOT NULL,              -- e.g., 'cdbg', 'home', 'section_8_hcv'
    program_name TEXT NOT NULL,
    administering_agency TEXT,             -- e.g., 'HUD'
    description TEXT,

    -- Scope: national vs jurisdiction-specific
    scope TEXT NOT NULL,                   -- 'national' or 'jurisdiction'
    jurisdiction_id TEXT,                  -- NULL for national, 'city-san-rafael' for local

    -- Program details (JSONB for flexibility)
    eligible_activities JSONB,
    compliance_requirements JSONB,
    citizen_participation JSONB,

    -- Allocations (jurisdiction-specific)
    fiscal_year TEXT,                      -- 'FY2026'
    allocation_amount INTEGER,
    allocation_source TEXT,
    allocation_status TEXT,                -- 'CONFIRMED', 'UNCERTAIN', 'DRAFT'

    -- Contacts and URLs
    key_contacts JSONB,
    official_url TEXT,

    -- Temporal versioning
    valid_from TIMESTAMP DEFAULT NOW(),
    valid_to TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_federal_programs_jurisdiction ON federal_programs(jurisdiction_id);
CREATE INDEX idx_federal_programs_fiscal_year ON federal_programs(fiscal_year);
```

## Implementation Steps

1. **Create migration script** - `scripts/sql/create_federal_programs_table.sql`
2. **Create data loader** - Parse existing JSON files into new table
3. **Update storage backend** - Add methods to `PostgresBackend`
4. **Create API methods** - `get_federal_programs()`, `get_jurisdiction_allocations()`
5. **Test with San Rafael data** - Verify the data we just updated loads correctly

## Files to Modify

- `packages/civic/src/civic/storage/postgres_backend.py` - Add table + methods
- `packages/civic/src/civic/storage/protocol.py` - Add protocol methods
- `scripts/sql/` - Migration script
- `packages/civic-extraction/` - Consider data loader

## Follow-up Item

After this is complete: `federal_programs_vector_embeddings` (P1) - Add to pgvector for semantic search

## Success Criteria

- [ ] PostgreSQL table created with proper schema
- [ ] Existing JSON data migrated
- [ ] API methods working
- [ ] pilot.json item updated to "ready"

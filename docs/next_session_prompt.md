# Session 366: Decisions from SQL (P0)

## Context

Session 365 completed **dashboard_visual_hierarchy**:
- Added sortable columns to DataBrowserWidget
- Added quick-filter by cell value (hover to see filter icon)
- Added SQL/Corpus source badges to distinguish data types

Session 364 completed **data architecture unification**:
- Issues endpoint now queries SQL (1340 records)
- Agenda items properly filtered by jurisdiction via JOIN
- Vector stats show `issues: 1340/1340 (100%) - linked`

## Current P0: decisions_from_sql

Build the decisions table in SQL via ETL pipeline.

**Current state:**
- Decisions exist in vector DB (corpus_only)
- Vector stats show `decisions: corpus_only`
- No SQL table for decisions → can't browse in DataBrowser
- ERD shows decisions as 0 records

**Goal:**
- Create decisions table in SQL schema
- Populate via ETL from meeting minutes/transcripts
- Link to agenda_items table (decisions.agenda_item_id → agenda_items.id)
- Enable DataBrowser to show actual decision records

## Key Files

- `packages/civic/src/civic/storage.py` - StorageBackend with table definitions
- `packages/civic-extraction/src/civic_extraction/decisions/` - Decision extraction
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py` - API endpoints
- Schema in `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md`

## Data Flow

```
meeting transcript/minutes → decision extraction → SQL decisions table → vector index
```

The current flow extracts decisions to JSON files. We need:
1. SQL table schema for decisions
2. ETL step to insert into SQL during extraction
3. API endpoint to query decisions from SQL
4. Vector reindex from SQL source (future: vector_rebuild_from_sql)

## Success Criteria

- [ ] decisions table exists in SQLite schema
- [ ] ETL populates decisions from existing extracted data
- [ ] DataBrowser shows decision records (not just 0)
- [ ] Vector stats show `decisions: linked` (not corpus_only)

## Architecture Notes

Follow the 4-stage pipeline pattern:
1. **Discover** - Find meeting sources
2. **Ingest** - Extract decisions from transcripts
3. **Store** - Persist to SQL decisions table
4. **Index** - Update vector embeddings

Use StorageBackend protocol for SQL operations.

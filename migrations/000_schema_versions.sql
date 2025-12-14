-- Migration 000: Schema version tracking
-- Purpose: Create table to track applied migrations
-- This migration is applied automatically by migrate.py
-- Created: 2025-12-11

-- Schema versions table (tracks which migrations have been applied)
-- This enables:
--   - Safe re-running of migrations (idempotent)
--   - Detection of modified migrations
--   - Audit trail of when migrations were applied
CREATE TABLE IF NOT EXISTS schema_versions (
    version TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INTEGER,
    applied_by TEXT DEFAULT 'migrate.py'
);

-- Index for applied_at to support recent migration queries
CREATE INDEX IF NOT EXISTS idx_schema_versions_applied ON schema_versions(applied_at);

-- Migration: Partition vector_embeddings by corpus_type
--
-- Why: HNSW index maintenance during bulk inserts is O(n log n) on the full
-- table. With 630K vectors and a 2.9 GB HNSW index, batch inserts hit
-- Supabase's 2-minute statement_timeout. Partitioning by corpus_type gives
-- each partition its own small HNSW index, so bulk inserts only contend with
-- the partition's index (e.g., 3.6K federal_rules vs 630K total).
--
-- All queries already filter by corpus_type, so PostgreSQL prunes to a single
-- partition every time — no cross-partition scan overhead.
--
-- Run with: psql $DATABASE_URL -f scripts/sql/partition_vector_embeddings.sql
-- Estimated time: 5-10 minutes (mostly HNSW index creation)
--
-- IMPORTANT: Run during a maintenance window. Queries will use sequential
-- scan (slower but correct) while HNSW indexes are being created.

BEGIN;

-- Step 1: Rename the existing table
ALTER TABLE vector_embeddings RENAME TO vector_embeddings_old;

-- Step 2: Drop the old HNSW index (it belongs to the old table)
DROP INDEX IF EXISTS idx_vector_embeddings_embedding_hnsw;

-- Step 3: Create the partitioned table with identical schema
CREATE TABLE vector_embeddings (
    id TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL,
    corpus_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    embedding_model TEXT NOT NULL DEFAULT 'unknown',
    meeting_id TEXT,
    meeting_title TEXT,
    meeting_datetime TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, corpus_type)
) PARTITION BY LIST (corpus_type);

-- Step 4: Create partitions for all known corpus types
CREATE TABLE vector_embeddings_agenda_items PARTITION OF vector_embeddings FOR VALUES IN ('agenda_items');
CREATE TABLE vector_embeddings_budget_items PARTITION OF vector_embeddings FOR VALUES IN ('budget_items');
CREATE TABLE vector_embeddings_chunks PARTITION OF vector_embeddings FOR VALUES IN ('chunks');
CREATE TABLE vector_embeddings_codified_law PARTITION OF vector_embeddings FOR VALUES IN ('codified_law');
CREATE TABLE vector_embeddings_decisions PARTITION OF vector_embeddings FOR VALUES IN ('decisions');
CREATE TABLE vector_embeddings_elections PARTITION OF vector_embeddings FOR VALUES IN ('elections');
CREATE TABLE vector_embeddings_executive_orders PARTITION OF vector_embeddings FOR VALUES IN ('executive_orders');
CREATE TABLE vector_embeddings_federal_rules PARTITION OF vector_embeddings FOR VALUES IN ('federal_rules');
CREATE TABLE vector_embeddings_issues PARTITION OF vector_embeddings FOR VALUES IN ('issues');
CREATE TABLE vector_embeddings_legislation PARTITION OF vector_embeddings FOR VALUES IN ('legislation');
CREATE TABLE vector_embeddings_meetings PARTITION OF vector_embeddings FOR VALUES IN ('meetings');
CREATE TABLE vector_embeddings_municipal_code PARTITION OF vector_embeddings FOR VALUES IN ('municipal_code');
CREATE TABLE vector_embeddings_programs PARTITION OF vector_embeddings FOR VALUES IN ('programs');
CREATE TABLE vector_embeddings_state_programs PARTITION OF vector_embeddings FOR VALUES IN ('state_programs');
CREATE TABLE vector_embeddings_transcripts PARTITION OF vector_embeddings FOR VALUES IN ('transcripts');

-- Default partition for any future corpus types (prevents insert failures)
CREATE TABLE vector_embeddings_default PARTITION OF vector_embeddings DEFAULT;

-- Step 5: Copy data from old table to partitioned table
-- PostgreSQL automatically routes each row to the correct partition
INSERT INTO vector_embeddings
    SELECT * FROM vector_embeddings_old;

-- Step 6: Create per-partition indexes (non-HNSW first)
CREATE INDEX idx_vector_embeddings_jurisdiction_corpus
    ON vector_embeddings (jurisdiction_id, corpus_type);

CREATE INDEX idx_vector_embeddings_model
    ON vector_embeddings (embedding_model);

COMMIT;

-- Step 7: Drop old table (after verifying data)
-- Run this AFTER confirming the partitioned table has the same row count
-- DO NOT include in the transaction above — verify first
--
-- Verification:
--   SELECT COUNT(*) FROM vector_embeddings;
--   SELECT COUNT(*) FROM vector_embeddings_old;
--
-- If counts match:
--   DROP TABLE vector_embeddings_old;

-- Step 8: Create per-partition HNSW indexes (outside transaction, can be concurrent)
-- These are created separately so they can be built with parallel workers
-- and without holding a long transaction open.
--
-- Run these one at a time (each takes 10s-2min depending on partition size):

SET maintenance_work_mem = '256MB';
SET statement_timeout = '30min';

-- Largest partitions first
CREATE INDEX idx_ve_codified_law_hnsw ON vector_embeddings_codified_law
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_legislation_hnsw ON vector_embeddings_legislation
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_executive_orders_hnsw ON vector_embeddings_executive_orders
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_programs_hnsw ON vector_embeddings_programs
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_municipal_code_hnsw ON vector_embeddings_municipal_code
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_transcripts_hnsw ON vector_embeddings_transcripts
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_chunks_hnsw ON vector_embeddings_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_federal_rules_hnsw ON vector_embeddings_federal_rules
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_issues_hnsw ON vector_embeddings_issues
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_agenda_items_hnsw ON vector_embeddings_agenda_items
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_decisions_hnsw ON vector_embeddings_decisions
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_meetings_hnsw ON vector_embeddings_meetings
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_budget_items_hnsw ON vector_embeddings_budget_items
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_elections_hnsw ON vector_embeddings_elections
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_ve_state_programs_hnsw ON vector_embeddings_state_programs
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Data integrity infrastructure: content hashing, source provenance, and audit trail
-- See docs/decisions/data_integrity_infrastructure.md for rationale
-- These fields are foundational for future federation, legal defense, and anti-tampering

-- =============================================================================
-- CONTENT HASHING: SHA-256 hashes of record content for verification
-- =============================================================================

-- Transcripts: hash of utterances JSON
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS audio_hash TEXT;

-- Chunks: hash of extracted text
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source_pdf_hash TEXT;

-- Decisions: hash of decision JSON
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- =============================================================================
-- SOURCE PROVENANCE: Track extraction version for re-processing
-- =============================================================================

ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS extraction_version TEXT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS extraction_version TEXT;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS extraction_version TEXT;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS extraction_version TEXT;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS extraction_version TEXT;
ALTER TABLE municipal_code ADD COLUMN IF NOT EXISTS extraction_version TEXT;

-- =============================================================================
-- SOFT DELETE: Never hard-delete, preserve audit trail
-- =============================================================================

ALTER TABLE transcripts ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE issues ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE municipal_code ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- =============================================================================
-- ENGAGEMENT TRACKING: Schema stub for future anti-astroturf measures
-- Don't populate until coordination features are built
-- =============================================================================

CREATE TABLE IF NOT EXISTS civic_engagement (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    engagement_type TEXT NOT NULL,  -- '311_report', 'meeting_testimony', 'thread_participation'
    external_id TEXT,               -- Reference to source record
    actor_hash TEXT,                -- Pseudonymous identifier (hashed email/address)
    engaged_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_civic_engagement_jurisdiction ON civic_engagement(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_civic_engagement_type ON civic_engagement(engagement_type);
CREATE INDEX IF NOT EXISTS idx_civic_engagement_actor ON civic_engagement(actor_hash);

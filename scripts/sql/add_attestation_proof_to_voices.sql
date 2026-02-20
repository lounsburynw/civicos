-- Migration: Embed attestation proof on voice/comment events
-- This moves attestation verification from read-time JOINs to write-time embedding.
-- Each voice/comment now carries the full kind-30850 attestation event, allowing
-- any relay to independently verify attestation via Schnorr signature check.

-- Add attestation_proof and jurisdiction columns to voices
ALTER TABLE coordination_voices ADD COLUMN IF NOT EXISTS attestation_proof JSONB;
ALTER TABLE coordination_voices ADD COLUMN IF NOT EXISTS jurisdiction TEXT;
ALTER TABLE coordination_voices ADD COLUMN IF NOT EXISTS created_at INTEGER;

-- Add attestation_proof to comments
ALTER TABLE coordination_comments ADD COLUMN IF NOT EXISTS attestation_proof JSONB;

-- Fix stance CHECK constraint: model uses 'watching', DB says 'abstain'
ALTER TABLE coordination_voices DROP CONSTRAINT IF EXISTS valid_stance;
ALTER TABLE coordination_voices ADD CONSTRAINT valid_stance
    CHECK (stance IN ('support', 'oppose', 'watching'));

-- Index for attestation queries
CREATE INDEX IF NOT EXISTS idx_voices_has_attestation
    ON coordination_voices((attestation_proof IS NOT NULL));

-- Backfill existing voices from attestation table
UPDATE coordination_voices v
SET attestation_proof = a.nostr_event
FROM coordination_attestations a
WHERE a.public_key = v.public_key
  AND a.revoked = FALSE
  AND v.attestation_proof IS NULL;

-- Attestation revocation blocklist
-- Stores revoked attestation event IDs so they can no longer be used for access
-- Used by AcceptancePolicy._verify_attestation() to reject revoked proofs

CREATE TABLE IF NOT EXISTS coordination_attestation_revocations (
    event_id TEXT PRIMARY KEY,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT NOT NULL DEFAULT ''
);

-- Index on revoked_at for cleanup queries
CREATE INDEX IF NOT EXISTS idx_attestation_revocations_revoked_at
    ON coordination_attestation_revocations (revoked_at);

-- RLS: only service_role can access
ALTER TABLE coordination_attestation_revocations ENABLE ROW LEVEL SECURITY;

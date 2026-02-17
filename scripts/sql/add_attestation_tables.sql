-- Attestation tables for sybil resistance via single-use codes.
-- Codes are generated in batches and distributed at in-person events.
-- When redeemed, a code binds permanently to a pubkey for a jurisdiction.

-- Attestation codes: generated in batches, single-use
CREATE TABLE IF NOT EXISTS coordination_attestation_codes (
    code TEXT PRIMARY KEY,                    -- e.g. "SR-2026-02-A7K9"
    jurisdiction TEXT NOT NULL,               -- e.g. "city-san-rafael"
    batch_id TEXT NOT NULL,                   -- groups codes from same generation event
    redeemed_by TEXT,                         -- pubkey hex, NULL if unredeemed
    redeemed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ                   -- optional expiry
);
CREATE INDEX IF NOT EXISTS idx_attest_codes_jurisdiction ON coordination_attestation_codes(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_attest_codes_redeemed_by ON coordination_attestation_codes(redeemed_by);

-- Attestation records: one per pubkey per jurisdiction
CREATE TABLE IF NOT EXISTS coordination_attestations (
    id TEXT PRIMARY KEY,                      -- "attest:{jurisdiction}:{pubkey}"
    public_key TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    attestation_type TEXT NOT NULL DEFAULT 'physical',
    code_used TEXT REFERENCES coordination_attestation_codes(code),
    nostr_event JSONB NOT NULL,              -- full kind-30850 event (signed by issuer)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(public_key, jurisdiction)
);
CREATE INDEX IF NOT EXISTS idx_attestations_pubkey ON coordination_attestations(public_key);
CREATE INDEX IF NOT EXISTS idx_attestations_jurisdiction ON coordination_attestations(jurisdiction);

-- RLS
ALTER TABLE coordination_attestation_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_attestations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access attestation_codes" ON coordination_attestation_codes FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access attestations" ON coordination_attestations FOR ALL USING (auth.role() = 'service_role');

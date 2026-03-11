-- Issuer registry for multi-issuer attestation.
-- Organizations (civic groups, libraries, city offices) register their
-- signer service with the relay. When a code is redeemed, the relay
-- calls the issuer's /sign endpoint to produce the attestation.

-- Trusted issuer registry
CREATE TABLE IF NOT EXISTS coordination_issuer_registry (
    issuer_id TEXT PRIMARY KEY,                     -- "issuer:{jurisdiction}:{org-slug}"
    jurisdiction TEXT NOT NULL,
    issuer_pubkey TEXT NOT NULL,                     -- 64-char hex (secp256k1 x-only)
    organization TEXT NOT NULL,                      -- Human-readable name
    signing_url TEXT NOT NULL,                       -- e.g. "https://signer.civic-group.org"
    bearer_token TEXT NOT NULL,                       -- Shared secret (DB secured via RLS/service_role)
    allowed_types TEXT[] NOT NULL DEFAULT '{physical}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified BOOLEAN NOT NULL DEFAULT FALSE,         -- Admin must verify before codes work
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(issuer_pubkey, jurisdiction)
);
CREATE INDEX IF NOT EXISTS idx_issuer_registry_jurisdiction
    ON coordination_issuer_registry(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_issuer_registry_pubkey
    ON coordination_issuer_registry(issuer_pubkey);

-- Link codes to their issuing organization
ALTER TABLE coordination_attestation_codes
    ADD COLUMN IF NOT EXISTS issuer_id TEXT
    REFERENCES coordination_issuer_registry(issuer_id);
CREATE INDEX IF NOT EXISTS idx_attest_codes_issuer
    ON coordination_attestation_codes(issuer_id);

-- RLS
ALTER TABLE coordination_issuer_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access issuer_registry"
    ON coordination_issuer_registry FOR ALL
    USING (auth.role() = 'service_role');

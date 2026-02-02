-- Nostr event storage for CivicOS relay
-- Implements NIP-01 event storage with civic-specific indexes

-- Main Nostr events table
CREATE TABLE IF NOT EXISTS nostr_events (
    -- Core NIP-01 fields
    id VARCHAR(64) PRIMARY KEY,           -- 32-byte hex event ID (SHA256)
    pubkey VARCHAR(64) NOT NULL,          -- 32-byte hex x-only public key
    created_at BIGINT NOT NULL,           -- Unix timestamp in seconds
    kind INTEGER NOT NULL,                 -- Event kind number
    tags JSONB NOT NULL DEFAULT '[]',     -- Event tags as JSON array
    content TEXT NOT NULL DEFAULT '',     -- Event content
    sig VARCHAR(128) NOT NULL,            -- 64-byte hex Schnorr signature

    -- Relay metadata
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Extracted civic tags for efficient querying (denormalized from tags)
    d_tag VARCHAR(512),                   -- Addressable event identifier
    j_tag VARCHAR(128),                   -- Jurisdiction
    stance VARCHAR(32),                   -- Voice stance (support/oppose/watching)

    -- Constraints
    CONSTRAINT valid_id_hex CHECK (id ~ '^[0-9a-f]{64}$'),
    CONSTRAINT valid_pubkey_hex CHECK (pubkey ~ '^[0-9a-f]{64}$'),
    CONSTRAINT valid_sig_hex CHECK (sig ~ '^[0-9a-f]{128}$')
);

-- Addressable event uniqueness (kinds 30000-39999)
-- Only one event per kind:pubkey:d_tag combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_nostr_addressable_unique
ON nostr_events (kind, pubkey, d_tag)
WHERE kind >= 30000 AND kind < 40000 AND d_tag IS NOT NULL;

-- Replaceable event uniqueness (kinds 10000-19999)
-- Only one event per kind:pubkey combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_nostr_replaceable_unique
ON nostr_events (kind, pubkey)
WHERE kind >= 10000 AND kind < 20000;

-- Standard query indexes
CREATE INDEX IF NOT EXISTS idx_nostr_pubkey ON nostr_events (pubkey);
CREATE INDEX IF NOT EXISTS idx_nostr_kind ON nostr_events (kind);
CREATE INDEX IF NOT EXISTS idx_nostr_created_at ON nostr_events (created_at);
CREATE INDEX IF NOT EXISTS idx_nostr_received_at ON nostr_events (received_at);

-- Civic-specific indexes
CREATE INDEX IF NOT EXISTS idx_nostr_jurisdiction ON nostr_events (j_tag) WHERE j_tag IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nostr_stance ON nostr_events (stance) WHERE stance IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nostr_d_tag ON nostr_events (d_tag) WHERE d_tag IS NOT NULL;

-- Combined civic query index (jurisdiction + kind + created_at)
CREATE INDEX IF NOT EXISTS idx_nostr_civic_query
ON nostr_events (j_tag, kind, created_at DESC)
WHERE j_tag IS NOT NULL;

-- JSONB GIN index for flexible tag queries
CREATE INDEX IF NOT EXISTS idx_nostr_tags_gin ON nostr_events USING GIN (tags jsonb_path_ops);

-- Voice count materialized view
-- Aggregates voice counts per entity from kind 30800 events
CREATE MATERIALIZED VIEW IF NOT EXISTS nostr_voice_counts AS
SELECT
    d_tag AS entity_id,
    j_tag AS jurisdiction,
    COUNT(*) FILTER (WHERE stance = 'support' AND content != 'revoked') AS support_count,
    COUNT(*) FILTER (WHERE stance = 'oppose' AND content != 'revoked') AS oppose_count,
    COUNT(*) FILTER (WHERE stance = 'watching' AND content != 'revoked') AS watching_count,
    COUNT(*) FILTER (WHERE content != 'revoked') AS total_count,
    MAX(created_at) AS last_voice_at
FROM nostr_events
WHERE kind = 30800 AND d_tag IS NOT NULL
GROUP BY d_tag, j_tag;

-- Unique index for efficient refresh
CREATE UNIQUE INDEX IF NOT EXISTS idx_nostr_voice_counts_pk
ON nostr_voice_counts (entity_id, jurisdiction);

-- Key link attestations table for tracking old->new key mappings
CREATE TABLE IF NOT EXISTS nostr_key_links (
    id SERIAL PRIMARY KEY,
    old_key VARCHAR(128) NOT NULL,        -- Old SECP256R1 pubkey hex
    new_key VARCHAR(64) NOT NULL,         -- New secp256k1 Nostr pubkey
    attestation_event_id VARCHAR(64) NOT NULL REFERENCES nostr_events(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure one link per old key
    CONSTRAINT unique_old_key UNIQUE (old_key),
    CONSTRAINT valid_new_key_hex CHECK (new_key ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_nostr_key_links_new ON nostr_key_links (new_key);

-- Function to refresh voice counts
CREATE OR REPLACE FUNCTION refresh_voice_counts()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY nostr_voice_counts;
END;
$$ LANGUAGE plpgsql;

-- Trigger function to extract civic tags on insert
CREATE OR REPLACE FUNCTION extract_civic_tags()
RETURNS TRIGGER AS $$
DECLARE
    tag JSONB;
BEGIN
    -- Extract d, j, and stance tags from the tags array
    FOR tag IN SELECT jsonb_array_elements(NEW.tags)
    LOOP
        IF tag->>0 = 'd' AND jsonb_array_length(tag) >= 2 THEN
            NEW.d_tag := tag->>1;
        ELSIF tag->>0 = 'j' AND jsonb_array_length(tag) >= 2 THEN
            NEW.j_tag := tag->>1;
        ELSIF tag->>0 = 'stance' AND jsonb_array_length(tag) >= 2 THEN
            NEW.stance := tag->>1;
        END IF;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for civic tag extraction
DROP TRIGGER IF EXISTS trg_extract_civic_tags ON nostr_events;
CREATE TRIGGER trg_extract_civic_tags
BEFORE INSERT OR UPDATE ON nostr_events
FOR EACH ROW
EXECUTE FUNCTION extract_civic_tags();

-- Comments for documentation
COMMENT ON TABLE nostr_events IS 'NIP-01 compliant Nostr event storage with CivicOS extensions';
COMMENT ON COLUMN nostr_events.d_tag IS 'Extracted d-tag for addressable events (denormalized)';
COMMENT ON COLUMN nostr_events.j_tag IS 'Extracted jurisdiction tag (denormalized)';
COMMENT ON COLUMN nostr_events.stance IS 'Extracted stance for voice events (denormalized)';
COMMENT ON VIEW nostr_voice_counts IS 'Aggregated voice counts per entity, refreshed periodically';

-- Add coordination_comments table for public comment board (Kind 30803)
-- One comment per public_key per entity (addressable)

CREATE TABLE IF NOT EXISTS coordination_comments (
    entity TEXT NOT NULL,
    comment_text TEXT NOT NULL,
    public_key TEXT NOT NULL,
    signature TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    jurisdiction TEXT,
    stance TEXT,
    created_at INTEGER,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (public_key, entity)
);

CREATE INDEX IF NOT EXISTS idx_comments_entity ON coordination_comments(entity);
CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON coordination_comments(timestamp DESC);

ALTER TABLE coordination_comments ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'coordination_comments'
        AND policyname = 'Service role has full access to comments'
    ) THEN
        CREATE POLICY "Service role has full access to comments"
            ON coordination_comments FOR ALL USING (auth.role() = 'service_role');
    END IF;
END
$$;

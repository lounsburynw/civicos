-- Add local relevance scoring columns to federal_rules table
-- Part of: local_impact_relevance (launch.json)

ALTER TABLE federal_rules ADD COLUMN IF NOT EXISTS local_relevance_score FLOAT DEFAULT 0.0;
ALTER TABLE federal_rules ADD COLUMN IF NOT EXISTS relevance_reasons JSONB;

-- Index for sorting by relevance (most relevant first)
CREATE INDEX IF NOT EXISTS idx_federal_rules_local_relevance_score
    ON federal_rules(local_relevance_score DESC);

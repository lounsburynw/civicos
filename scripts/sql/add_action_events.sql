-- Add action events tables for Nostr action event specification
-- Kind 30810: CivicActionEvent - defines the action itself
-- Kind 30811: CivicCommitment - user commits to action
-- Kind 30812: CivicCompletion - user reports completion
--
-- Run this migration on the coordination database (RELAY_DATABASE_URL)

-- ============================================================================
-- Simple Action Table (for Action model - older API)
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_actions (
    action_id TEXT NOT NULL,                       -- Action identifier
    action_type TEXT NOT NULL,                     -- 'commitment' or 'completion'
    public_key TEXT NOT NULL,                      -- User's public key (hex)
    signature TEXT NOT NULL,                       -- Signature of action (hex)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    evidence_url TEXT,                             -- URL to evidence (for completions)
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    -- One action per user per action_id per type
    PRIMARY KEY (public_key, action_id, action_type),

    CONSTRAINT valid_simple_action_type CHECK (
        action_type IN ('commitment', 'completion')
    )
);

CREATE INDEX IF NOT EXISTS idx_actions_action_id
    ON coordination_actions(action_id);
CREATE INDEX IF NOT EXISTS idx_actions_public_key
    ON coordination_actions(public_key);
CREATE INDEX IF NOT EXISTS idx_actions_type
    ON coordination_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_actions_timestamp
    ON coordination_actions(timestamp);

-- ============================================================================
-- Kind 30810: CivicActionEvent
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_action_events (
    id TEXT PRIMARY KEY,                           -- d-tag: action:{initiative}:{type}:{hash}
    initiative_id TEXT NOT NULL,                   -- Reference to initiative
    action_type TEXT NOT NULL,                     -- CivicActionType enum value
    description TEXT NOT NULL,                     -- Human-readable description
    target TEXT,                                   -- Target of action (email, meeting room)
    deadline TIMESTAMP WITH TIME ZONE,             -- Deadline for completion
    template TEXT,                                 -- Template text for action
    target_count INTEGER,                          -- Target number of completions
    public_key TEXT NOT NULL,                      -- Creator's public key (hex)
    signature TEXT NOT NULL,                       -- Signature of action data (hex)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    -- Indexes
    CONSTRAINT valid_action_type CHECK (
        action_type IN ('written_comment', 'attend_meeting', 'public_comment',
                       'contact_official', 'signature', 'share', 'custom')
    )
);

CREATE INDEX IF NOT EXISTS idx_action_events_initiative
    ON coordination_action_events(initiative_id);
CREATE INDEX IF NOT EXISTS idx_action_events_type
    ON coordination_action_events(action_type);
CREATE INDEX IF NOT EXISTS idx_action_events_public_key
    ON coordination_action_events(public_key);
CREATE INDEX IF NOT EXISTS idx_action_events_timestamp
    ON coordination_action_events(timestamp);

-- ============================================================================
-- Kind 30811: CivicCommitment
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_commitments (
    id TEXT PRIMARY KEY,                           -- d-tag: commit:{pubkey}:{action-d-tag}
    action_ref TEXT NOT NULL,                      -- a-tag: 30810:{pubkey}:{d-tag}
    status TEXT NOT NULL DEFAULT 'committed',      -- committed, completed, withdrawn
    public_key TEXT NOT NULL,                      -- Committer's public key (hex)
    signature TEXT NOT NULL,                       -- Signature of commitment (hex)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    -- One commitment per user per action
    UNIQUE(public_key, action_ref),

    CONSTRAINT valid_commitment_status CHECK (
        status IN ('committed', 'completed', 'withdrawn')
    )
);

CREATE INDEX IF NOT EXISTS idx_commitments_action_ref
    ON coordination_commitments(action_ref);
CREATE INDEX IF NOT EXISTS idx_commitments_public_key
    ON coordination_commitments(public_key);
CREATE INDEX IF NOT EXISTS idx_commitments_status
    ON coordination_commitments(status);
CREATE INDEX IF NOT EXISTS idx_commitments_timestamp
    ON coordination_commitments(timestamp);

-- ============================================================================
-- Kind 30812: CivicCompletion
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_completions (
    id TEXT PRIMARY KEY,                           -- d-tag: complete:{pubkey}:{action-d-tag}
    action_ref TEXT NOT NULL,                      -- a-tag: 30810:{pubkey}:{d-tag}
    evidence_type TEXT NOT NULL,                   -- self_report, email_confirmation, etc.
    evidence_content TEXT,                         -- Evidence URL or content
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    public_key TEXT NOT NULL,                      -- Completer's public key (hex)
    signature TEXT NOT NULL,                       -- Signature of completion (hex)
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    revoked BOOLEAN NOT NULL DEFAULT FALSE,

    -- One completion per user per action
    UNIQUE(public_key, action_ref),

    CONSTRAINT valid_evidence_type CHECK (
        evidence_type IN ('self_report', 'email_confirmation',
                         'attendance_check', 'verified')
    )
);

CREATE INDEX IF NOT EXISTS idx_completions_action_ref
    ON coordination_completions(action_ref);
CREATE INDEX IF NOT EXISTS idx_completions_public_key
    ON coordination_completions(public_key);
CREATE INDEX IF NOT EXISTS idx_completions_evidence_type
    ON coordination_completions(evidence_type);
CREATE INDEX IF NOT EXISTS idx_completions_timestamp
    ON coordination_completions(timestamp);

-- ============================================================================
-- Enable RLS (Row Level Security) for these tables
-- ============================================================================

ALTER TABLE coordination_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_action_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_commitments ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_completions ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access
CREATE POLICY "Service role has full access to actions"
    ON coordination_actions FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to action_events"
    ON coordination_action_events FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to commitments"
    ON coordination_commitments FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to completions"
    ON coordination_completions FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- Migration: Add coordination_url to action events
-- ============================================================================

ALTER TABLE coordination_action_events ADD COLUMN IF NOT EXISTS coordination_url TEXT;

-- ============================================================================
-- Migration: Add deadline_context to action events
-- ============================================================================

ALTER TABLE coordination_action_events ADD COLUMN IF NOT EXISTS deadline_context TEXT;

-- ============================================================================
-- Initiative Outcomes
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_outcomes (
    id TEXT PRIMARY KEY,
    initiative_id TEXT NOT NULL,                    -- Reference to initiative
    outcome TEXT NOT NULL,                          -- passed, failed, continued, modified, partial
    notes TEXT,                                     -- Additional context
    vote_breakdown JSONB,                           -- Vote details (e.g., {"yes": 4, "no": 1})
    decision_reference TEXT,                        -- Link to civic data decision
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_outcome CHECK (
        outcome IN ('passed', 'failed', 'continued', 'modified', 'partial')
    )
);

CREATE INDEX IF NOT EXISTS idx_outcomes_initiative
    ON coordination_outcomes(initiative_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_recorded_at
    ON coordination_outcomes(recorded_at);

-- ============================================================================
-- Action Attributions
-- ============================================================================

CREATE TABLE IF NOT EXISTS coordination_attributions (
    id TEXT PRIMARY KEY,
    outcome_id TEXT REFERENCES coordination_outcomes(id),  -- NULL for activity-based
    action_id TEXT NOT NULL REFERENCES coordination_action_events(id),
    public_key TEXT NOT NULL,                       -- User's public key (hex)
    contribution_type TEXT NOT NULL,                -- commitment or completion
    message TEXT,                                   -- Personalized attribution message
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_contribution_type CHECK (
        contribution_type IN ('commitment', 'completion')
    )
);

-- Outcome-based: one attribution per user per action per outcome
CREATE UNIQUE INDEX IF NOT EXISTS idx_attributions_outcome_unique
    ON coordination_attributions(outcome_id, action_id, public_key)
    WHERE outcome_id IS NOT NULL;

-- Activity-based: one attribution per user per action (no outcome)
CREATE UNIQUE INDEX IF NOT EXISTS idx_attributions_activity_unique
    ON coordination_attributions(action_id, public_key)
    WHERE outcome_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_attributions_outcome
    ON coordination_attributions(outcome_id);
CREATE INDEX IF NOT EXISTS idx_attributions_public_key
    ON coordination_attributions(public_key);
CREATE INDEX IF NOT EXISTS idx_attributions_action
    ON coordination_attributions(action_id);

-- RLS for new tables
ALTER TABLE coordination_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE coordination_attributions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to outcomes"
    ON coordination_outcomes FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to attributions"
    ON coordination_attributions FOR ALL
    USING (auth.role() = 'service_role');

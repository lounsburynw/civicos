-- Migration 006: Personalization Service (2025-10-29)
-- Adds user profiles, civic history tracking, and inferred interests cache
-- See docs/PERSONALIZATION_SERVICE_ARCHITECTURE.md for complete architecture

-- ========================================
-- PART 1: User Profiles Table
-- ========================================

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,

    -- Identity
    display_name TEXT,
    avatar_url TEXT,

    -- Demographics (Civic Context)
    stakes TEXT,                    -- JSON array: ["homeowner", "parent"]
    years_in_area INTEGER,
    district TEXT,
    neighborhood TEXT,
    jurisdiction_id TEXT NOT NULL,  -- Primary city/county
    expertise TEXT,

    -- Civic Interests (Explicit)
    civic_interests TEXT,           -- JSON array: ["housing", "transportation"]
    topics_following TEXT,          -- JSON array: state bill topics

    -- Preferences
    notification_preferences TEXT,  -- JSON object
    privacy_settings TEXT,          -- JSON object: {profileVisibility, showCivicHistory, allowBehavioralInference}

    -- Metadata
    profile_completeness INTEGER DEFAULT 0,  -- 0-100
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_jurisdiction ON user_profiles(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_completeness ON user_profiles(profile_completeness);

-- ========================================
-- PART 2: Civic History Table
-- ========================================

CREATE TABLE IF NOT EXISTS civic_history (
    action_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,

    -- Action classification
    action_type TEXT NOT NULL,      -- 'comment_drafted', 'meeting_attended', 'issue_filed', etc.
    entity_type TEXT NOT NULL,      -- 'event', 'issue', 'bill', 'official'
    entity_id TEXT NOT NULL,

    -- Context
    metadata TEXT,                  -- JSON object with action-specific data
    jurisdiction_id TEXT,
    topic TEXT,                     -- housing, transportation, etc.

    -- Timestamp
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_civic_history_user ON civic_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_civic_history_action_type ON civic_history(action_type);
CREATE INDEX IF NOT EXISTS idx_civic_history_topic ON civic_history(topic);
CREATE INDEX IF NOT EXISTS idx_civic_history_jurisdiction ON civic_history(jurisdiction_id);

-- ========================================
-- PART 3: Inferred Interests Cache Table
-- ========================================

CREATE TABLE IF NOT EXISTS inferred_interests (
    user_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    confidence_score REAL NOT NULL,  -- 0.0 to 1.0

    -- Metadata
    last_computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actions_analyzed INTEGER,        -- How many actions went into this inference

    PRIMARY KEY (user_id, topic),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inferred_interests_confidence ON inferred_interests(user_id, confidence_score DESC);

-- ========================================
-- PART 4: Data Migration (Optional)
-- ========================================

-- Migrate existing comment personalContext to user_profiles
-- NOTE: Only run this AFTER verifying comments table exists and has data
-- This is commented out to prevent errors on fresh installations

/*
INSERT OR IGNORE INTO user_profiles (user_id, jurisdiction_id, stakes, years_in_area, district, neighborhood, expertise)
SELECT DISTINCT
    user_id,
    COALESCE(
        (SELECT jurisdiction_id FROM events WHERE id = comments.event_id LIMIT 1),
        'city-berkeley'
    ) as jurisdiction_id,
    json_extract(personal_context, '$.stakes') as stakes,
    json_extract(personal_context, '$.yearsInArea') as years_in_area,
    json_extract(personal_context, '$.district') as district,
    json_extract(personal_context, '$.neighborhood') as neighborhood,
    json_extract(personal_context, '$.expertise') as expertise
FROM comments
WHERE user_id IS NOT NULL AND personal_context IS NOT NULL;
*/

-- ========================================
-- PART 5: Verification Queries
-- ========================================

-- Verify tables created
SELECT 'user_profiles' as table_name, COUNT(*) as row_count FROM user_profiles
UNION ALL
SELECT 'civic_history', COUNT(*) FROM civic_history
UNION ALL
SELECT 'inferred_interests', COUNT(*) FROM inferred_interests;

-- Verify indexes created
SELECT name, tbl_name, sql FROM sqlite_master
WHERE type = 'index' AND (
    tbl_name IN ('user_profiles', 'civic_history', 'inferred_interests')
) ORDER BY tbl_name, name;

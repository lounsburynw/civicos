-- Migration 007: Privacy Update - Remove Political Data Storage
-- Date: 2025-10-29
-- Purpose: Implement browser-only archetype storage (Tier 1 Privacy)
--
-- CRITICAL: Political preferences should NEVER be stored in the backend database.
-- This migration marks civic_interests as DEPRECATED to enforce privacy-first architecture.
--
-- Privacy Threat Model:
--   - Government subpoenas can access centralized political data
--   - Data breaches expose user political preferences
--   - Political targeting/discrimination based on civic interests
--   - Chilling effect on civic participation
--
-- Solution: Browser-only storage (localStorage) with optional export/import

-- NOTE: SQLite doesn't support DROP COLUMN easily, so we mark the field as deprecated
-- instead of removing it. Backend code should NEVER write to this field.
--
-- civic_interests field is DEPRECATED (DO NOT USE)
-- Political preferences now live in browser localStorage as archetypes

-- Clear any existing civic_interests data (privacy cleanup)
UPDATE user_profiles SET civic_interests = '[]';

-- Add privacy_tier field to track user's chosen privacy level
-- Default: 'browser-only' (Tier 1 - maximum privacy)
-- Future: 'encrypted-sync' (Tier 2), 'zero-knowledge' (Tier 3)
ALTER TABLE user_profiles ADD COLUMN privacy_tier TEXT DEFAULT 'browser-only';

-- Add onboarding_completed timestamp (but NOT swipe data)
-- We track completion for UX purposes, but never store political decisions
ALTER TABLE user_profiles ADD COLUMN onboarding_completed_at DATETIME;

-- PRIVACY POLICY:
-- - civic_interests field is DEPRECATED and must remain empty
-- - Political data NEVER stored on server
-- - User archetypes live in browser localStorage only
-- - Optional encrypted sync (Tier 2) and zero-knowledge (Tier 3) in future
--
-- DO NOT create onboarding_swipes table
-- DO NOT create civic_preferences table
-- DO NOT create user_archetypes table
-- Political data stays in browser localStorage ONLY

-- Verification query:
-- SELECT privacy_tier, onboarding_completed_at, civic_interests FROM user_profiles;
-- civic_interests should be empty ('[]') for all users

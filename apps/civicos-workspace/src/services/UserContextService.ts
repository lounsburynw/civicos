import type {
  CivicUserContext,
  UserContextForRequest,
  UserNeighborhood,
  ReminderPreferences,
  UserAttestations
} from '@/types/civic'

/**
 * UserContextService
 *
 * Manages user context stored in browser localStorage.
 * Privacy-first design: context is transmitted per-request but never stored server-side.
 *
 * Storage keys:
 * - civic_user_context: Main context object (JSON)
 * - civic_user_context_updated: Last update timestamp
 * - civic_private_key_encrypted: Nostr private key (encrypted, separate storage)
 *
 * Privacy tiers:
 * - Tier 1 (browser-only): archetypes, private key - NEVER transmitted
 * - Tier 2 (per-request): interests, filtering_instructions - transmitted but not stored server-side
 * - Tier 3 (server-stored): user_id, demographics - stored for coordination
 */

const USER_CONTEXT_STORAGE_KEY = 'civic_user_context'
const USER_CONTEXT_TIMESTAMP_KEY = 'civic_user_context_updated'
const PRIVATE_KEY_STORAGE_KEY = 'civic_private_key_encrypted'

/**
 * Default empty context for new users.
 */
function createEmptyContext(jurisdiction: string = ''): CivicUserContext {
  return {
    jurisdiction,
    interests: [],
    filtering_instructions: '',
    voice_history: [],
    commitment_history: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
}

/**
 * Load user context from browser localStorage.
 *
 * @returns User context or null if not found/invalid
 */
export function loadUserContext(): CivicUserContext | null {
  try {
    const stored = localStorage.getItem(USER_CONTEXT_STORAGE_KEY)
    if (!stored) {
      console.log('[UserContext] No saved context found')
      return null
    }

    const context: CivicUserContext = JSON.parse(stored)

    // Validate essential fields exist
    if (!context.jurisdiction || !Array.isArray(context.interests)) {
      console.warn('[UserContext] Invalid context structure, ignoring')
      return null
    }

    console.log('[UserContext] Loaded from browser:', {
      jurisdiction: context.jurisdiction,
      interests: context.interests.length,
      hasLocation: !!context.location,
      hasNostrPubkey: !!context.nostr_pubkey
    })

    return context
  } catch (err) {
    console.error('[UserContext] Error loading from localStorage:', err)
    return null
  }
}

/**
 * Save user context to browser localStorage.
 *
 * @param context Full user context object
 */
export function saveUserContext(context: CivicUserContext): void {
  try {
    // Update timestamp
    context.updated_at = new Date().toISOString()

    localStorage.setItem(USER_CONTEXT_STORAGE_KEY, JSON.stringify(context))
    localStorage.setItem(USER_CONTEXT_TIMESTAMP_KEY, context.updated_at)

    console.log('[UserContext] Saved to browser (never sent to server for storage)')
  } catch (err) {
    console.error('[UserContext] Error saving to localStorage:', err)
    throw new Error('Failed to save user context to browser storage')
  }
}

/**
 * Initialize user context for first-time users.
 *
 * @param jurisdiction Default jurisdiction from location detection
 * @returns New context object
 */
export function initializeUserContext(jurisdiction: string = ''): CivicUserContext {
  const context = createEmptyContext(jurisdiction)
  saveUserContext(context)
  console.log('[UserContext] Initialized new context for jurisdiction:', jurisdiction)
  return context
}

/**
 * Clear user context from browser (for reset/logout).
 */
export function clearUserContext(): void {
  try {
    localStorage.removeItem(USER_CONTEXT_STORAGE_KEY)
    localStorage.removeItem(USER_CONTEXT_TIMESTAMP_KEY)
    localStorage.removeItem(PRIVATE_KEY_STORAGE_KEY)
    console.log('[UserContext] Cleared from browser')
  } catch (err) {
    console.error('[UserContext] Error clearing:', err)
  }
}

/**
 * Check if user has completed onboarding (has context with interests).
 */
export function hasCompletedOnboarding(): boolean {
  const context = loadUserContext()
  return context !== null && context.interests.length > 0
}

/**
 * Get timestamp of last context update.
 */
export function getLastUpdated(): string | null {
  return localStorage.getItem(USER_CONTEXT_TIMESTAMP_KEY)
}

// ============================================================================
// Update Methods (Partial Updates)
// ============================================================================

/**
 * Update jurisdiction (e.g., when user moves or selects different city).
 */
export function updateJurisdiction(jurisdiction: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.jurisdiction = jurisdiction
  saveUserContext(context)
  return context
}

/**
 * Update neighborhood location.
 */
export function updateLocation(location: UserNeighborhood): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.location = location
  saveUserContext(context)
  return context
}

/**
 * Update interests (replaces existing list).
 */
export function updateInterests(interests: string[]): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.interests = interests
  saveUserContext(context)
  return context
}

/**
 * Add an interest to the list (if not already present).
 */
export function addInterest(interest: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  if (!context.interests.includes(interest)) {
    context.interests.push(interest)
    saveUserContext(context)
  }
  return context
}

/**
 * Remove an interest from the list.
 */
export function removeInterest(interest: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.interests = context.interests.filter(i => i !== interest)
  saveUserContext(context)
  return context
}

/**
 * Update filtering instructions (natural language preferences).
 */
export function updateFilteringInstructions(instructions: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.filtering_instructions = instructions
  saveUserContext(context)
  return context
}

/**
 * Update Nostr public key.
 */
export function updateNostrPubkey(pubkey: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.nostr_pubkey = pubkey
  saveUserContext(context)
  return context
}

/**
 * Update notification email.
 */
export function updateNotificationEmail(email: string | undefined): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.notification_email = email
  saveUserContext(context)
  return context
}

/**
 * Update reminder preferences.
 */
export function updateReminderPreferences(prefs: ReminderPreferences): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.reminder_preferences = prefs
  saveUserContext(context)
  return context
}

/**
 * Update attestations.
 */
export function updateAttestations(attestations: UserAttestations): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  context.attestations = attestations
  saveUserContext(context)
  return context
}

// ============================================================================
// History Tracking (Nostr Event IDs)
// ============================================================================

/**
 * Add a voice event ID to history.
 */
export function addVoiceToHistory(eventId: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  if (!context.voice_history.includes(eventId)) {
    context.voice_history.push(eventId)
    saveUserContext(context)
  }
  return context
}

/**
 * Add a commitment event ID to history.
 */
export function addCommitmentToHistory(eventId: string): CivicUserContext {
  const context = loadUserContext() || createEmptyContext()
  if (!context.commitment_history.includes(eventId)) {
    context.commitment_history.push(eventId)
    saveUserContext(context)
  }
  return context
}

// ============================================================================
// API Serialization
// ============================================================================

/**
 * Serialize user context for API requests.
 *
 * Returns only the fields needed for agent reasoning:
 * - jurisdiction, location, interests, filtering_instructions
 *
 * NEVER includes:
 * - Private keys (Tier 1)
 * - Full attestation data
 * - History arrays (just references)
 *
 * @returns Context subset safe for per-request transmission
 */
export function serializeForRequest(): UserContextForRequest | null {
  const context = loadUserContext()
  if (!context) {
    return null
  }

  return {
    jurisdiction: context.jurisdiction,
    location: context.location,
    interests: context.interests,
    filtering_instructions: context.filtering_instructions,
    notification_email: context.notification_email
  }
}

/**
 * Check if context is valid for API requests.
 * Requires at minimum a jurisdiction.
 */
export function isValidForRequest(): boolean {
  const context = loadUserContext()
  return context !== null && !!context.jurisdiction
}

// ============================================================================
// Export/Import (Cross-Device Sync)
// ============================================================================

/**
 * Export user context for manual backup.
 * User can download this and import on another device.
 *
 * @returns JSON blob for download
 */
export function exportContext(): Blob {
  const context = loadUserContext()
  const data = {
    version: '1.0',
    privacy_tier: 'per-request',
    exported_at: new Date().toISOString(),
    context
  }

  return new Blob(
    [JSON.stringify(data, null, 2)],
    { type: 'application/json' }
  )
}

/**
 * Import user context from backup file.
 *
 * @param json JSON string from exported file
 * @throws Error if format is invalid
 */
export function importContext(json: string): CivicUserContext {
  try {
    const data = JSON.parse(json)

    if (!data.context || !data.context.jurisdiction) {
      throw new Error('Invalid context format: missing jurisdiction')
    }

    const context: CivicUserContext = {
      ...data.context,
      // Reset timestamps for imported context
      created_at: data.context.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString()
    }

    saveUserContext(context)
    console.log('[UserContext] Imported from backup')
    return context
  } catch (err) {
    console.error('[UserContext] Import error:', err)
    throw new Error('Failed to import user context: invalid format')
  }
}

// ============================================================================
// Singleton Service (for direct imports)
// ============================================================================

export const UserContextService = {
  // Load/Save
  load: loadUserContext,
  save: saveUserContext,
  initialize: initializeUserContext,
  clear: clearUserContext,

  // Status
  hasCompletedOnboarding,
  isValidForRequest,
  getLastUpdated,

  // Updates
  updateJurisdiction,
  updateLocation,
  updateInterests,
  addInterest,
  removeInterest,
  updateFilteringInstructions,
  updateNostrPubkey,
  updateNotificationEmail,
  updateReminderPreferences,
  updateAttestations,

  // History
  addVoiceToHistory,
  addCommitmentToHistory,

  // API
  serializeForRequest,

  // Export/Import
  exportContext,
  importContext
}

export default UserContextService

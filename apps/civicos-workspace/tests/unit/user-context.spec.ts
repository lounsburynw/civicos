import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  loadUserContext,
  saveUserContext,
  initializeUserContext,
  clearUserContext,
  hasCompletedOnboarding,
  updateJurisdiction,
  updateLocation,
  updateInterests,
  addInterest,
  removeInterest,
  updateFilteringInstructions,
  addVoiceToHistory,
  addCommitmentToHistory,
  serializeForRequest,
  isValidForRequest,
  exportContext,
  importContext
} from '@/services/UserContextService'
import type { CivicUserContext } from '@/types/civic'

/**
 * UserContextService Unit Tests
 *
 * Tests the privacy-first user context management:
 * - localStorage load/save
 * - Partial updates
 * - API serialization (what gets transmitted)
 * - Export/import for cross-device sync
 */

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key]
    }),
    clear: vi.fn(() => {
      store = {}
    }),
    get length() {
      return Object.keys(store).length
    },
    key: vi.fn((index: number) => Object.keys(store)[index] ?? null)
  }
})()

Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageMock
})

describe('UserContextService', () => {
  beforeEach(() => {
    // Clear localStorage and reset mocks before each test
    localStorageMock.clear()
    vi.clearAllMocks()
  })

  describe('loadUserContext', () => {
    it('returns null when no context exists', () => {
      const result = loadUserContext()
      expect(result).toBeNull()
    })

    it('loads valid context from localStorage', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: ['housing', 'transportation'],
        filtering_instructions: 'focus on housing',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      const result = loadUserContext()

      expect(result).not.toBeNull()
      expect(result?.jurisdiction).toBe('city-san-rafael')
      expect(result?.interests).toEqual(['housing', 'transportation'])
    })

    it('returns null for invalid JSON', () => {
      localStorageMock.setItem('civic_user_context', 'not valid json')

      const result = loadUserContext()

      expect(result).toBeNull()
    })

    it('returns null for context missing required fields', () => {
      const invalidContext = { interests: [] } // missing jurisdiction
      localStorageMock.setItem('civic_user_context', JSON.stringify(invalidContext))

      const result = loadUserContext()

      expect(result).toBeNull()
    })
  })

  describe('saveUserContext', () => {
    it('saves context to localStorage with timestamp', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }

      saveUserContext(context)

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'civic_user_context',
        expect.any(String)
      )
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'civic_user_context_updated',
        expect.any(String)
      )
    })

    it('updates the updated_at timestamp', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }

      const before = new Date().toISOString()
      saveUserContext(context)
      const after = new Date().toISOString()

      expect(context.updated_at).toBeDefined()
      expect(context.updated_at! >= before).toBe(true)
      expect(context.updated_at! <= after).toBe(true)
    })
  })

  describe('initializeUserContext', () => {
    it('creates empty context with jurisdiction', () => {
      const result = initializeUserContext('city-oakland')

      expect(result.jurisdiction).toBe('city-oakland')
      expect(result.interests).toEqual([])
      expect(result.filtering_instructions).toBe('')
      expect(result.voice_history).toEqual([])
      expect(result.commitment_history).toEqual([])
    })

    it('saves the new context to localStorage', () => {
      initializeUserContext('city-san-rafael')

      expect(localStorageMock.setItem).toHaveBeenCalled()
    })
  })

  describe('clearUserContext', () => {
    it('removes all context keys from localStorage', () => {
      localStorageMock.setItem('civic_user_context', '{}')
      localStorageMock.setItem('civic_user_context_updated', 'timestamp')
      localStorageMock.setItem('civic_private_key_encrypted', 'key')

      clearUserContext()

      expect(localStorageMock.removeItem).toHaveBeenCalledWith('civic_user_context')
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('civic_user_context_updated')
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('civic_private_key_encrypted')
    })
  })

  describe('hasCompletedOnboarding', () => {
    it('returns false when no context exists', () => {
      expect(hasCompletedOnboarding()).toBe(false)
    })

    it('returns false when interests are empty', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      expect(hasCompletedOnboarding()).toBe(false)
    })

    it('returns true when interests are present', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      expect(hasCompletedOnboarding()).toBe(true)
    })
  })

  describe('partial updates', () => {
    const setupContext = () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
        filtering_instructions: 'test',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))
      return context
    }

    it('updateJurisdiction changes only jurisdiction', () => {
      setupContext()

      const result = updateJurisdiction('city-oakland')

      expect(result.jurisdiction).toBe('city-oakland')
      expect(result.interests).toEqual(['housing']) // preserved
    })

    it('updateLocation sets neighborhood location', () => {
      setupContext()

      const result = updateLocation({
        neighborhood: 'Terra Linda',
        lat: 37.9,
        lng: -122.5
      })

      expect(result.location?.neighborhood).toBe('Terra Linda')
      expect(result.location?.lat).toBe(37.9)
    })

    it('updateInterests replaces interests array', () => {
      setupContext()

      const result = updateInterests(['transportation', 'environment'])

      expect(result.interests).toEqual(['transportation', 'environment'])
    })

    it('addInterest adds new interest', () => {
      setupContext()

      const result = addInterest('transportation')

      expect(result.interests).toContain('housing')
      expect(result.interests).toContain('transportation')
    })

    it('addInterest does not duplicate existing interest', () => {
      setupContext()

      const result = addInterest('housing')

      expect(result.interests.filter(i => i === 'housing').length).toBe(1)
    })

    it('removeInterest removes specific interest', () => {
      setupContext()

      const result = removeInterest('housing')

      expect(result.interests).not.toContain('housing')
    })

    it('updateFilteringInstructions sets instructions', () => {
      setupContext()

      const result = updateFilteringInstructions('aggressive on housing, ignore parking')

      expect(result.filtering_instructions).toBe('aggressive on housing, ignore parking')
    })
  })

  describe('history tracking', () => {
    beforeEach(() => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))
    })

    it('addVoiceToHistory adds event ID', () => {
      const result = addVoiceToHistory('nostr:event123')

      expect(result.voice_history).toContain('nostr:event123')
    })

    it('addVoiceToHistory does not duplicate IDs', () => {
      addVoiceToHistory('nostr:event123')
      const result = addVoiceToHistory('nostr:event123')

      expect(result.voice_history.filter(id => id === 'nostr:event123').length).toBe(1)
    })

    it('addCommitmentToHistory adds commitment ID', () => {
      const result = addCommitmentToHistory('nostr:commit456')

      expect(result.commitment_history).toContain('nostr:commit456')
    })
  })

  describe('API serialization', () => {
    it('serializeForRequest returns null when no context', () => {
      expect(serializeForRequest()).toBeNull()
    })

    it('serializeForRequest returns only safe fields', () => {
      const context: CivicUserContext = {
        nostr_pubkey: 'pub123',
        jurisdiction: 'city-san-rafael',
        location: { neighborhood: 'Terra Linda' },
        interests: ['housing'],
        filtering_instructions: 'focus on housing',
        voice_history: ['event1', 'event2'],
        commitment_history: ['commit1'],
        notification_email: 'test@example.com',
        attestations: {
          physical: { event_id: 'att1', expires: '2025-12-31' }
        }
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      const result = serializeForRequest()

      // Should include these fields
      expect(result?.jurisdiction).toBe('city-san-rafael')
      expect(result?.location?.neighborhood).toBe('Terra Linda')
      expect(result?.interests).toEqual(['housing'])
      expect(result?.filtering_instructions).toBe('focus on housing')
      expect(result?.notification_email).toBe('test@example.com')

      // Should NOT include these fields (not in UserContextForRequest)
      expect((result as any).nostr_pubkey).toBeUndefined()
      expect((result as any).voice_history).toBeUndefined()
      expect((result as any).commitment_history).toBeUndefined()
      expect((result as any).attestations).toBeUndefined()
    })

    it('isValidForRequest returns false without jurisdiction', () => {
      const context: CivicUserContext = {
        jurisdiction: '',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      expect(isValidForRequest()).toBe(false)
    })

    it('isValidForRequest returns true with jurisdiction', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: [],
        filtering_instructions: '',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      expect(isValidForRequest()).toBe(true)
    })
  })

  describe('export/import', () => {
    it('exportContext creates JSON blob with context', () => {
      const context: CivicUserContext = {
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
        filtering_instructions: 'test',
        voice_history: [],
        commitment_history: []
      }
      localStorageMock.setItem('civic_user_context', JSON.stringify(context))

      const blob = exportContext()

      expect(blob.type).toBe('application/json')
    })

    it('importContext restores context from JSON', () => {
      const exportData = {
        version: '1.0',
        privacy_tier: 'per-request',
        exported_at: '2025-01-01T00:00:00Z',
        context: {
          jurisdiction: 'city-oakland',
          interests: ['transportation'],
          filtering_instructions: 'focus on transit',
          voice_history: [],
          commitment_history: []
        }
      }

      const result = importContext(JSON.stringify(exportData))

      expect(result.jurisdiction).toBe('city-oakland')
      expect(result.interests).toEqual(['transportation'])
    })

    it('importContext throws on invalid format', () => {
      expect(() => importContext('not json')).toThrow()
      expect(() => importContext(JSON.stringify({ no_context: true }))).toThrow()
    })
  })
})

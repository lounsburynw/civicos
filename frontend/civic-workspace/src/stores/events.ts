import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { CivicEvent, ProjectType } from '../types/civic'
import { api } from '../services/api'

/**
 * Events Store
 *
 * Manages event data including:
 * - Events cache (by jurisdiction)
 * - Loading and error states
 * - Project type filter
 * - Last fetch timestamps
 */

interface EventsCache {
  [jurisdictionId: string]: {
    events: CivicEvent[]
    timestamp: number
    loading: boolean
    error: string | null
  }
}

const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

export const useEventsStore = defineStore('events', () => {
  // State
  const cache = ref<EventsCache>({})
  const selectedProjectType = ref<ProjectType | 'all'>('all')

  // Computed
  const isLoading = computed(() => {
    return Object.values(cache.value).some(entry => entry.loading)
  })

  const hasError = computed(() => {
    return Object.values(cache.value).some(entry => entry.error !== null)
  })

  // Actions
  function getEventsForJurisdiction(jurisdictionId: string): CivicEvent[] {
    const entry = cache.value[jurisdictionId]
    if (!entry) return []
    return entry.events
  }

  function getFilteredEvents(jurisdictionId: string): CivicEvent[] {
    const events = getEventsForJurisdiction(jurisdictionId)
    if (selectedProjectType.value === 'all') {
      return events
    }
    return events.filter(event => event.project_type === selectedProjectType.value)
  }

  function isLoadingForJurisdiction(jurisdictionId: string): boolean {
    return cache.value[jurisdictionId]?.loading ?? false
  }

  function getErrorForJurisdiction(jurisdictionId: string): string | null {
    return cache.value[jurisdictionId]?.error ?? null
  }

  function isCacheValid(jurisdictionId: string): boolean {
    const entry = cache.value[jurisdictionId]
    if (!entry) return false
    const age = Date.now() - entry.timestamp
    return age < CACHE_TTL
  }

  async function fetchEventsForJurisdiction(jurisdictionId: string, forceRefresh = false) {
    // Check cache first
    if (!forceRefresh && isCacheValid(jurisdictionId)) {
      return getEventsForJurisdiction(jurisdictionId)
    }

    // Initialize or update cache entry
    if (!cache.value[jurisdictionId]) {
      cache.value[jurisdictionId] = {
        events: [],
        timestamp: 0,
        loading: false,
        error: null
      }
    }

    const entry = cache.value[jurisdictionId]
    entry.loading = true
    entry.error = null

    try {
      const events = await api.getEvents({
        jurisdiction_id: jurisdictionId,
        // Don't filter by project type here - let the UI handle filtering
      })

      entry.events = events
      entry.timestamp = Date.now()
      return events
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch events'
      entry.error = errorMessage
      throw error
    } finally {
      entry.loading = false
    }
  }

  function setProjectTypeFilter(projectType: ProjectType | 'all') {
    selectedProjectType.value = projectType
  }

  function clearCache(jurisdictionId?: string) {
    if (jurisdictionId) {
      delete cache.value[jurisdictionId]
    } else {
      cache.value = {}
    }
  }

  function invalidateCache(jurisdictionId?: string) {
    if (jurisdictionId) {
      const entry = cache.value[jurisdictionId]
      if (entry) {
        entry.timestamp = 0
      }
    } else {
      Object.values(cache.value).forEach(entry => {
        entry.timestamp = 0
      })
    }
  }

  return {
    // State
    cache,
    selectedProjectType,

    // Computed
    isLoading,
    hasError,

    // Actions
    getEventsForJurisdiction,
    getFilteredEvents,
    isLoadingForJurisdiction,
    getErrorForJurisdiction,
    isCacheValid,
    fetchEventsForJurisdiction,
    setProjectTypeFilter,
    clearCache,
    invalidateCache
  }
})

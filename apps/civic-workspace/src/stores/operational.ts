import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { OperationalIssue } from '../types/civic'
import { api } from '../services/api'

/**
 * Operational Issues Store (Session 91 - SeeClickFix Integration)
 *
 * Manages operational issue data from SeeClickFix including:
 * - Issues cache (by jurisdiction)
 * - Loading and error states
 * - Status filters
 * - 1-hour cache TTL (operational issues update frequently)
 */

interface OperationalCache {
  [jurisdictionId: string]: {
    issues: OperationalIssue[]
    timestamp: number
    loading: boolean
    error: string | null
    metadata: {
      total: number
      page: number
      per_page: number
    } | null
  }
}

const CACHE_TTL = 60 * 60 * 1000 // 1 hour (operational issues update frequently)

export const useOperationalStore = defineStore('operational', () => {
  // State
  const cache = ref<OperationalCache>({})
  const selectedStatus = ref<'all' | 'open' | 'closed' | 'acknowledged'>('all')

  // Computed
  const isLoading = computed(() => {
    return Object.values(cache.value).some(entry => entry.loading)
  })

  const hasError = computed(() => {
    return Object.values(cache.value).some(entry => entry.error !== null)
  })

  // Actions
  function getIssuesForJurisdiction(jurisdictionId: string): OperationalIssue[] {
    const entry = cache.value[jurisdictionId]
    if (!entry) return []
    return entry.issues
  }

  function getFilteredIssues(jurisdictionId: string): OperationalIssue[] {
    const issues = getIssuesForJurisdiction(jurisdictionId)
    if (selectedStatus.value === 'all') {
      return issues
    }
    return issues.filter(issue => issue.status === selectedStatus.value)
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

  async function fetchOperationalIssues(
    jurisdictionId: string,
    options?: {
      status?: 'open' | 'closed' | 'acknowledged'
      perPage?: number
      page?: number
      forceRefresh?: boolean
    }
  ) {
    const forceRefresh = options?.forceRefresh ?? false

    // Check cache first
    if (!forceRefresh && isCacheValid(jurisdictionId)) {
      return getIssuesForJurisdiction(jurisdictionId)
    }

    // Initialize or update cache entry
    if (!cache.value[jurisdictionId]) {
      cache.value[jurisdictionId] = {
        issues: [],
        timestamp: 0,
        loading: false,
        error: null,
        metadata: null
      }
    }

    const entry = cache.value[jurisdictionId]
    entry.loading = true
    entry.error = null

    try {
      const response = await api.getOperationalIssues(jurisdictionId, {
        status: options?.status,
        perPage: options?.perPage ?? 50, // Default to 50 issues
        page: options?.page ?? 1
      })

      entry.issues = response.issues
      entry.metadata = response.metadata
      entry.timestamp = Date.now()
      return response.issues
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch operational issues'
      entry.error = errorMessage
      throw error
    } finally {
      entry.loading = false
    }
  }

  function setStatusFilter(status: 'all' | 'open' | 'closed' | 'acknowledged') {
    selectedStatus.value = status
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
    selectedStatus,

    // Computed
    isLoading,
    hasError,

    // Actions
    getIssuesForJurisdiction,
    getFilteredIssues,
    isLoadingForJurisdiction,
    getErrorForJurisdiction,
    isCacheValid,
    fetchOperationalIssues,
    setStatusFilter,
    clearCache,
    invalidateCache
  }
})

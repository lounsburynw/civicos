import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StateBill, FederalProgram } from '../types/civic'
import { api } from '@/services/api'

/**
 * Legislative Context Store
 *
 * Manages legislative data browsing including:
 * - State bills by topic
 * - Federal programs by topic
 * - Cache with TTL
 * - Filter/search functionality
 * - Loading/error states
 */

export type LegislativeTopic = 'housing' | 'transportation' | 'environment' | 'budget' | 'education'

interface LegislativeCache {
  stateBills: Record<LegislativeTopic, StateBill[]>
  federalPrograms: Record<LegislativeTopic, FederalProgram[]>
  lastFetch: Record<LegislativeTopic, number>
}

interface LegislativeState {
  selectedTopic: LegislativeTopic | null
  searchQuery: string
  loading: Record<LegislativeTopic, boolean>
  errors: Record<LegislativeTopic, string | null>
}

const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

export const useLegislativeStore = defineStore('legislative', () => {
  // State
  const selectedTopic = ref<LegislativeTopic | null>(null)
  const searchQuery = ref('')

  const cache = ref<LegislativeCache>({
    stateBills: {
      housing: [],
      transportation: [],
      environment: [],
      budget: [],
      education: []
    },
    federalPrograms: {
      housing: [],
      transportation: [],
      environment: [],
      budget: [],
      education: []
    },
    lastFetch: {
      housing: 0,
      transportation: 0,
      environment: 0,
      budget: 0,
      education: 0
    }
  })

  const loading = ref<Record<LegislativeTopic, boolean>>({
    housing: false,
    transportation: false,
    environment: false,
    budget: false,
    education: false
  })

  const errors = ref<Record<LegislativeTopic, string | null>>({
    housing: null,
    transportation: null,
    environment: null,
    budget: null,
    education: null
  })

  // Computed
  const currentStateBills = computed(() => {
    if (!selectedTopic.value) return []

    const bills = cache.value.stateBills[selectedTopic.value]

    if (!searchQuery.value) return bills

    const query = searchQuery.value.toLowerCase()
    return bills.filter(bill =>
      bill.bill.toLowerCase().includes(query) ||
      bill.title.toLowerCase().includes(query) ||
      bill.leverage_point.toLowerCase().includes(query)
    )
  })

  const currentFederalPrograms = computed(() => {
    if (!selectedTopic.value) return []

    const programs = cache.value.federalPrograms[selectedTopic.value]

    if (!searchQuery.value) return programs

    const query = searchQuery.value.toLowerCase()
    return programs.filter(program =>
      program.program_name.toLowerCase().includes(query) ||
      program.agency.toLowerCase().includes(query) ||
      program.leverage_point.toLowerCase().includes(query)
    )
  })

  const isLoading = computed(() => {
    return selectedTopic.value ? loading.value[selectedTopic.value] : false
  })

  const currentError = computed(() => {
    return selectedTopic.value ? errors.value[selectedTopic.value] : null
  })

  const hasData = computed(() => {
    if (!selectedTopic.value) return false
    return cache.value.stateBills[selectedTopic.value].length > 0 ||
           cache.value.federalPrograms[selectedTopic.value].length > 0
  })

  // Actions
  function setSelectedTopic(topic: LegislativeTopic | null) {
    selectedTopic.value = topic
    searchQuery.value = '' // Clear search when changing topics

    // Auto-fetch if not cached or stale
    if (topic && !isCacheFresh(topic)) {
      fetchLegislativeData(topic)
    }
  }

  function setSearchQuery(query: string) {
    searchQuery.value = query
  }

  function clearSearch() {
    searchQuery.value = ''
  }

  function isCacheFresh(topic: LegislativeTopic): boolean {
    const lastFetch = cache.value.lastFetch[topic]
    if (lastFetch === 0) return false

    const now = Date.now()
    return (now - lastFetch) < CACHE_TTL
  }

  async function fetchLegislativeData(topic: LegislativeTopic) {
    // If already loading, don't fetch again
    if (loading.value[topic]) return

    // If cache is fresh, don't fetch
    if (isCacheFresh(topic)) return

    loading.value[topic] = true
    errors.value[topic] = null

    try {
      // Fetch both state bills and federal programs in parallel using API service
      const [stateBillsData, federalProgramsData] = await Promise.all([
        api.getStateBills(topic),
        api.getFederalPrograms(topic)
      ])

      // Update cache
      cache.value.stateBills[topic] = stateBillsData.bills || []
      cache.value.federalPrograms[topic] = federalProgramsData.programs || []
      cache.value.lastFetch[topic] = Date.now()

    } catch (error) {
      console.error(`Failed to fetch legislative data for ${topic}:`, error)
      errors.value[topic] = error instanceof Error ? error.message : 'Unknown error'
    } finally {
      loading.value[topic] = false
    }
  }

  async function refreshTopic(topic: LegislativeTopic) {
    // Force refresh by invalidating cache
    cache.value.lastFetch[topic] = 0
    await fetchLegislativeData(topic)
  }

  async function refreshAll() {
    const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']

    // Invalidate all caches
    topics.forEach(topic => {
      cache.value.lastFetch[topic] = 0
    })

    // Fetch in parallel
    await Promise.all(topics.map(topic => fetchLegislativeData(topic)))
  }

  function clearCache() {
    cache.value = {
      stateBills: {
        housing: [],
        transportation: [],
        environment: [],
        budget: [],
        education: []
      },
      federalPrograms: {
        housing: [],
        transportation: [],
        environment: [],
        budget: [],
        education: []
      },
      lastFetch: {
        housing: 0,
        transportation: 0,
        environment: 0,
        budget: 0,
        education: 0
      }
    }
  }

  // Get bill by ID (for opening as artifact)
  function getBillById(billId: string): StateBill | null {
    // Search across all topics
    const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']

    for (const topic of topics) {
      const bill = cache.value.stateBills[topic].find(b =>
        b.bill === billId || b.official_url.includes(billId)
      )
      if (bill) return bill
    }

    return null
  }

  // Get program by name (for opening as artifact)
  function getProgramByName(programName: string): FederalProgram | null {
    // Search across all topics
    const topics: LegislativeTopic[] = ['housing', 'transportation', 'environment', 'budget', 'education']

    for (const topic of topics) {
      const program = cache.value.federalPrograms[topic].find(p =>
        p.program_name === programName
      )
      if (program) return program
    }

    return null
  }

  return {
    // State
    selectedTopic,
    searchQuery,
    cache,
    loading,
    errors,

    // Computed
    currentStateBills,
    currentFederalPrograms,
    isLoading,
    currentError,
    hasData,

    // Actions
    setSelectedTopic,
    setSearchQuery,
    clearSearch,
    fetchLegislativeData,
    refreshTopic,
    refreshAll,
    clearCache,
    getBillById,
    getProgramByName,
    isCacheFresh
  }
})

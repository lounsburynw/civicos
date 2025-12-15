import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { UserLocation } from '../types/civic'

/**
 * User Store
 *
 * Manages user-level state including:
 * - User location (city, county, jurisdictions)
 * - Anonymous user ID
 * - LocalStorage persistence
 */

const LOCATION_STORAGE_KEY = 'civic_user_location'
const USER_ID_STORAGE_KEY = 'civic_user_id'
const ENGAGEMENT_STORAGE_KEY = 'civic_engagement'
const ARCHETYPES_STORAGE_KEY = 'civic-archetypes' // Match archetypeMatching.ts utility
const ARCHETYPE_TIMESTAMP_KEY = 'civic-archetypes-updated' // Match archetypeMatching.ts utility

interface EngagementData {
  eventsViewed: number
  issuesFiledCount: number
  unlockedFeatures: string[]
}

interface CivicArchetype {
  id: string
  name: string
  score: number
  description: string
  icon: string
  iconColor: string
}

export const useUserStore = defineStore('user', () => {
  // State
  const location = ref<UserLocation | null>(null)
  const userId = ref<string>('')

  // Engagement tracking state
  const eventsViewed = ref<number>(0)
  const issuesFiledCount = ref<number>(0)
  const unlockedFeatures = ref<Set<string>>(new Set())

  // Archetype state (Privacy Tier 1 - browser-only)
  const archetypes = ref<CivicArchetype[]>([])
  const archetypeTimestamp = ref<string | null>(null)

  // Initialize userId
  function initializeUserId() {
    const storedUserId = localStorage.getItem(USER_ID_STORAGE_KEY)
    if (storedUserId) {
      userId.value = storedUserId
    } else {
      // Generate anonymous user ID
      const newUserId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      userId.value = newUserId
      localStorage.setItem(USER_ID_STORAGE_KEY, newUserId)
    }
  }

  // Initialize location from localStorage
  function loadLocation() {
    try {
      const storedLocation = localStorage.getItem(LOCATION_STORAGE_KEY)
      if (storedLocation) {
        location.value = JSON.parse(storedLocation)
      }
    } catch (error) {
      console.error('Failed to load user location from localStorage:', error)
      location.value = null
    }
  }

  // Initialize engagement from localStorage
  function loadEngagement() {
    try {
      const stored = localStorage.getItem(ENGAGEMENT_STORAGE_KEY)
      if (stored) {
        const data: EngagementData = JSON.parse(stored)
        eventsViewed.value = data.eventsViewed || 0
        issuesFiledCount.value = data.issuesFiledCount || 0
        unlockedFeatures.value = new Set(data.unlockedFeatures || [])
        console.log('[Engagement] Loaded from localStorage:', {
          eventsViewed: eventsViewed.value,
          issuesFiledCount: issuesFiledCount.value,
          showMyIssues: eventsViewed.value >= 1,
          showLegislative: issuesFiledCount.value >= 1
        })
      } else {
        console.log('[Engagement] No saved data - new user state')
      }
    } catch (error) {
      console.error('Failed to load engagement data:', error)
    }
  }

  // Initialize archetypes from localStorage (Privacy Tier 1)
  function loadArchetypes() {
    try {
      const stored = localStorage.getItem(ARCHETYPES_STORAGE_KEY)
      const timestamp = localStorage.getItem(ARCHETYPE_TIMESTAMP_KEY)
      if (stored) {
        archetypes.value = JSON.parse(stored)
        archetypeTimestamp.value = timestamp
        console.log('[Archetypes] Loaded from browser localStorage:', {
          count: archetypes.value.length,
          timestamp: archetypeTimestamp.value,
          topArchetype: archetypes.value[0]?.name
        })
      }
    } catch (error) {
      console.error('Failed to load archetypes from localStorage:', error)
      archetypes.value = []
    }
  }

  // Save engagement to localStorage
  function saveEngagement() {
    try {
      const data: EngagementData = {
        eventsViewed: eventsViewed.value,
        issuesFiledCount: issuesFiledCount.value,
        unlockedFeatures: Array.from(unlockedFeatures.value)
      }
      localStorage.setItem(ENGAGEMENT_STORAGE_KEY, JSON.stringify(data))
    } catch (error) {
      console.error('Failed to save engagement data:', error)
    }
  }

  // Actions
  function setLocation(loc: UserLocation) {
    location.value = loc
    localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(loc))
  }

  function clearLocation() {
    location.value = null
    localStorage.removeItem(LOCATION_STORAGE_KEY)
  }

  // Engagement tracking actions
  function incrementEventsViewed() {
    eventsViewed.value++
    console.log('[Engagement] Event viewed. Total:', eventsViewed.value)
    saveEngagement()
  }

  function incrementIssuesFiled() {
    issuesFiledCount.value++
    console.log('[Engagement] Issue filed. Total:', issuesFiledCount.value)
    saveEngagement()
  }

  // Reset engagement (for testing)
  function resetEngagement() {
    eventsViewed.value = 0
    issuesFiledCount.value = 0
    unlockedFeatures.value = new Set()
    localStorage.removeItem(ENGAGEMENT_STORAGE_KEY)
    console.log('[Engagement] Reset to new user state')
  }

  function isNewlyUnlocked(feature: string): boolean {
    // Feature is newly unlocked if it's visible but not yet in unlockedFeatures
    const shouldShow =
      (feature === 'myissues' && showMyIssuesTab.value) ||
      (feature === 'legislative' && showLegislativeTab.value)

    if (shouldShow && !unlockedFeatures.value.has(feature)) {
      // Mark as unlocked after 3 seconds (time for animation)
      setTimeout(() => {
        unlockedFeatures.value.add(feature)
        saveEngagement()
      }, 3000)
      return true
    }
    return false
  }

  // Computed properties
  const hasLocation = computed(() => location.value !== null)

  const cityName = computed(() => location.value?.city || '')

  const countyName = computed(() => location.value?.county || '')

  const jurisdictionIds = computed(() => {
    if (!location.value) return []
    const ids: string[] = []
    if (location.value.jurisdictions.city) {
      ids.push(location.value.jurisdictions.city)
    }
    if (location.value.jurisdictions.county) {
      ids.push(location.value.jurisdictions.county)
    }
    return ids
  })

  // Primary jurisdiction ID (city takes precedence over county)
  const jurisdictionId = computed(() => {
    if (!location.value) return ''
    return location.value.jurisdictions.city || location.value.jurisdictions.county || ''
  })

  const displayName = computed(() => {
    if (!location.value) return 'Civic OS'
    return `${location.value.city} Civic OS`
  })

  // Engagement-based computed properties
  const showMyIssuesTab = computed(() => eventsViewed.value >= 1)
  const showLegislativeTab = computed(() => issuesFiledCount.value >= 1)

  // Archetype computed properties
  const hasCompletedOnboarding = computed(() => archetypes.value.length > 0)
  const primaryArchetype = computed(() => archetypes.value[0] || null)
  const secondaryArchetype = computed(() => archetypes.value[1] || null)
  const tertiaryArchetype = computed(() => archetypes.value[2] || null)

  // Watch location changes and persist
  watch(
    location,
    () => {
      if (location.value) {
        localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(location.value))
      }
    },
    { deep: true }
  )

  // Initialize on store creation
  initializeUserId()
  loadLocation()
  loadEngagement()
  loadArchetypes()

  return {
    // State
    location,
    userId,
    eventsViewed,
    issuesFiledCount,
    archetypes,
    archetypeTimestamp,

    // Computed
    hasLocation,
    cityName,
    countyName,
    jurisdictionId,
    jurisdictionIds,
    displayName,
    showMyIssuesTab,
    showLegislativeTab,
    hasCompletedOnboarding,
    primaryArchetype,
    secondaryArchetype,
    tertiaryArchetype,

    // Actions
    setLocation,
    clearLocation,
    loadLocation,
    incrementEventsViewed,
    incrementIssuesFiled,
    isNewlyUnlocked,
    resetEngagement,
    loadArchetypes
  }
})

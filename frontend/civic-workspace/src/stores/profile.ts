import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/services/api'
import {
  loadArchetypesFromBrowser,
  archetypesToInterests,
  type ArchetypeMatch
} from '@/utils/archetypeMatching'

interface UserProfile {
  user_id: string
  display_name: string | null
  stakes: string[]
  years_in_area: number | null
  district: string | null
  neighborhood: string | null
  jurisdiction_id: string
  expertise: string | null
  civic_interests: string[] // Derived from archetypes (display only, not sent to backend)
  topics_following: string[]
  notification_preferences: Record<string, any>
  privacy_settings: Record<string, any>
  profile_completeness: number
  created_at: string
  updated_at: string
  archetypes?: ArchetypeMatch[] // Client-side only (from localStorage)
}

export const useProfileStore = defineStore('profile', () => {
  const profile = ref<UserProfile | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const discoveredInterests = ref<string[] | null>(null)
  const profileFormDraft = ref<Partial<UserProfile> | null>(null)

  const isProfileComplete = computed(() => {
    return profile.value && profile.value.profile_completeness >= 80
  })

  async function fetchProfile() {
    loading.value = true
    error.value = null
    try {
      // Load from backend (demographics only, no political data)
      const data = await api.getUserProfile()

      // Load archetypes from localStorage (NEVER sent to backend)
      const archetypes = loadArchetypesFromBrowser()

      // Derive civic_interests from archetypes (for UI display only)
      const civic_interests = archetypes ? archetypesToInterests(archetypes) : []

      profile.value = {
        user_id: data.user_id,
        display_name: data.display_name || null,
        stakes: data.stakes || [],
        years_in_area: data.years_in_area || null,
        district: data.district || null,
        neighborhood: null, // Not returned by API
        jurisdiction_id: data.jurisdiction_id || '',
        expertise: data.expertise || null,
        civic_interests,
        topics_following: [], // Not returned by API
        notification_preferences: {}, // Not returned by API
        privacy_settings: {}, // Not returned by API
        profile_completeness: data.profile_completeness || 0,
        created_at: '', // Not returned by API
        updated_at: '', // Not returned by API
        archetypes: archetypes || undefined
      }
    } catch (err: any) {
      if (err.message === 'Profile not found') {
        // Profile doesn't exist yet
        profile.value = null
      } else {
        error.value = err.message
        throw err
      }
    } finally {
      loading.value = false
    }
  }

  async function createOrUpdateProfile(data: Partial<UserProfile>) {
    loading.value = true
    error.value = null
    try {
      // NEVER send civic_interests or archetypes to backend
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { civic_interests, archetypes, ...safeData } = data

      // Save demographics to backend (no political data)
      const result = await api.createOrUpdateProfile(safeData)

      // Load archetypes from localStorage
      const localArchetypes = loadArchetypesFromBrowser()
      const derivedInterests = localArchetypes ? archetypesToInterests(localArchetypes) : []

      profile.value = {
        ...result,
        civic_interests: derivedInterests,
        archetypes: localArchetypes || undefined
      }

      return profile.value
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  async function deleteAccount() {
    loading.value = true
    error.value = null
    try {
      await api.deleteUserAccount()
      profile.value = null
    } catch (err: any) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  async function exportData() {
    const data = await api.exportUserData()
    return data
  }

  function setDiscoveredInterests(interests: string[]) {
    discoveredInterests.value = interests
  }

  function clearDiscoveredInterests() {
    discoveredInterests.value = null
  }

  function saveProfileFormDraft(draft: Partial<UserProfile>) {
    profileFormDraft.value = draft
    console.log('[ProfileStore] Saved profile form draft:', draft)
  }

  function clearProfileFormDraft() {
    profileFormDraft.value = null
    console.log('[ProfileStore] Cleared profile form draft')
  }

  return {
    profile,
    loading,
    error,
    discoveredInterests,
    profileFormDraft,
    isProfileComplete,
    fetchProfile,
    createOrUpdateProfile,
    deleteAccount,
    exportData,
    setDiscoveredInterests,
    clearDiscoveredInterests,
    saveProfileFormDraft,
    clearProfileFormDraft
  }
})

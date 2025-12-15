import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/**
 * Sidebar Store (Session 63)
 *
 * Single source of truth for sidebar section expand/collapse state.
 * Each section can be independently expanded or collapsed.
 * Supports programmatic expansion via chat navigation and manual user toggles.
 */

const STORAGE_KEY = 'civic_sidebar_sections'

interface SectionState {
  profile: boolean
  jurisdictions: boolean
  events: boolean
  discussions: boolean
  myIssues: boolean
  legislative: boolean
}

const defaultState: SectionState = {
  profile: false,         // Collapsed by default
  jurisdictions: true,    // Expanded by default
  events: true,           // Expanded by default (NEW)
  discussions: true,      // Expanded by default
  myIssues: false,        // Collapsed by default
  legislative: false      // Collapsed by default
}

export const useSidebarStore = defineStore('sidebar', () => {
  // State: track which sections are expanded
  const sections = ref<SectionState>({ ...defaultState })

  /**
   * Toggle a section's expanded/collapsed state
   */
  function toggleSection(sectionName: keyof SectionState) {
    sections.value[sectionName] = !sections.value[sectionName]
  }

  /**
   * Expand a specific section
   */
  function expandSection(sectionName: keyof SectionState) {
    sections.value[sectionName] = true
  }

  /**
   * Expand a specific section and collapse all others (for chat navigation)
   * Session 50 fix: When chat navigates to a section, make it the only visible one
   */
  function expandSectionExclusive(sectionName: keyof SectionState) {
    console.log('[sidebar] expandSectionExclusive called for:', sectionName)
    console.log('[sidebar] Before:', { ...sections.value })

    // Collapse all sections first
    Object.keys(sections.value).forEach(key => {
      sections.value[key as keyof SectionState] = false
    })
    // Then expand the target section
    sections.value[sectionName] = true

    console.log('[sidebar] After:', { ...sections.value })
  }

  /**
   * Collapse a specific section
   */
  function collapseSection(sectionName: keyof SectionState) {
    sections.value[sectionName] = false
  }

  /**
   * Load saved state from localStorage
   */
  function loadFromLocalStorage() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved) as SectionState

        // Session 63: Filter out legacy ghost keys (e.g., lowercase 'myissues')
        // Only merge keys that exist in defaultState to prevent pollution
        const cleanParsed: Partial<SectionState> = {}
        const validKeys = Object.keys(defaultState) as Array<keyof SectionState>

        validKeys.forEach(key => {
          if (key in parsed) {
            cleanParsed[key] = parsed[key]
          }
        })

        sections.value = { ...defaultState, ...cleanParsed }
      }
    } catch (err) {
      console.error('Failed to load sidebar state from localStorage:', err)
    }
  }

  /**
   * Save state to localStorage
   */
  function saveToLocalStorage() {
    try {
      // Session 63: Only save valid keys (prevents ghost keys from persisting)
      const validKeys = Object.keys(defaultState) as Array<keyof SectionState>
      const cleanState: Partial<SectionState> = {}

      validKeys.forEach(key => {
        cleanState[key] = sections.value[key]
      })

      localStorage.setItem(STORAGE_KEY, JSON.stringify(cleanState))
    } catch (err) {
      console.error('Failed to save sidebar state to localStorage:', err)
    }
  }

  /**
   * Reset to default state
   */
  function reset() {
    sections.value = { ...defaultState }
    saveToLocalStorage()
  }

  // Watch sections for changes and persist to localStorage
  watch(
    sections,
    () => {
      saveToLocalStorage()
    },
    { deep: true }
  )

  // Load initial state from localStorage
  loadFromLocalStorage()

  return {
    // State
    sections,

    // Actions
    toggleSection,
    expandSection,
    expandSectionExclusive,
    collapseSection,
    reset
  }
})

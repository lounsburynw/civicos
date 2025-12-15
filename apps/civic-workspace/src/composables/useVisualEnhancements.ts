/**
 * Visual Enhancements Composable (Session 59)
 *
 * Provides coordinated visual effects for teaching users that AI uses the same UI:
 * - Section header pulse animations (600ms)
 * - Filter button highlight animations (800ms)
 */

import { ref } from 'vue'

const pulsingSections = ref<Set<string>>(new Set())
const highlightedFilters = ref<Map<string, Set<string>>>(new Map())

export function useVisualEnhancements() {
  /**
   * Trigger a pulse animation on a section header
   * @param sectionId - Section identifier ('events', 'legislative', etc.)
   */
  function triggerSectionPulse(sectionId: string) {
    pulsingSections.value.add(sectionId)

    setTimeout(() => {
      pulsingSections.value.delete(sectionId)
    }, 600) // 600ms pulse duration
  }

  /**
   * Check if a section is currently pulsing
   * @param sectionId - Section identifier
   * @returns True if section is pulsing
   */
  function isSectionPulsing(sectionId: string): boolean {
    return pulsingSections.value.has(sectionId)
  }

  /**
   * Trigger filter highlight animation for a specific filter
   * @param panelId - Panel identifier ('events', 'legislative', etc.)
   * @param filterKey - Filter key ('topic', 'jurisdiction', 'search')
   */
  function triggerFilterHighlight(panelId: string, filterKey: string) {
    if (!highlightedFilters.value.has(panelId)) {
      highlightedFilters.value.set(panelId, new Set())
    }
    highlightedFilters.value.get(panelId)!.add(filterKey)

    // Auto-remove after 800ms
    setTimeout(() => {
      highlightedFilters.value.get(panelId)?.delete(filterKey)
      if (highlightedFilters.value.get(panelId)?.size === 0) {
        highlightedFilters.value.delete(panelId)
      }
    }, 800)
  }

  /**
   * Check if a filter is highlighted
   * @param panelId - Panel identifier
   * @param filterKey - Filter key
   * @returns True if filter is highlighted
   */
  function isFilterHighlighted(panelId: string, filterKey: string): boolean {
    return highlightedFilters.value.get(panelId)?.has(filterKey) || false
  }

  /**
   * Clear all highlighted filters for a panel
   * @param panelId - Panel identifier
   */
  function clearHighlightedFilters(panelId: string) {
    highlightedFilters.value.delete(panelId)
  }

  return {
    // Section pulse animations
    triggerSectionPulse,
    isSectionPulsing,

    // Filter highlight animations
    triggerFilterHighlight,
    isFilterHighlighted,
    clearHighlightedFilters
  }
}

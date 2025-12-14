/**
 * Privacy-First Archetype Matching (Tier 1: Browser-Only)
 *
 * This module matches user swipe decisions to civic archetypes CLIENT-SIDE ONLY.
 * Political preferences NEVER leave the user's browser.
 *
 * Storage: Browser localStorage (user-controlled)
 * Privacy: Maximum (zero server storage)
 * Subpoena risk: Zero (no data exists on server)
 */

export interface SwipeResult {
  card: {
    id: string
    type: 'topic' | 'event'
    title: string
    metadata?: {
      topic?: string
      project_type?: string
      jurisdiction?: string
    }
  }
  direction: 'left' | 'right'
}

export interface Archetype {
  id: string
  name: string
  icon: string // Lucide icon name
  iconColor: string // Solarized color
  description: string
  topics: string[]
  weights: Record<string, number> // topic → weight mapping
}

export interface ArchetypeMatch {
  id: string
  name: string
  icon: string // Lucide icon name
  iconColor: string // Solarized color
  score: number
  rank: number
  description?: string
}

// 12 Civic Archetypes with topic weights
export const ARCHETYPES: Archetype[] = [
  {
    id: 'housing_champion',
    name: 'Housing Champion',
    icon: 'Home',
    iconColor: '#268bd2', // Blue
    description: 'Affordable housing, tenant rights, zoning reform',
    topics: ['housing', 'development', 'zoning'],
    weights: {
      'housing': 1.0,
      'development': 0.6,
      'budget': 0.3,
      'community': 0.4
    }
  },
  {
    id: 'transit_advocate',
    name: 'Transit Advocate',
    icon: 'Train',
    iconColor: '#859900', // Green
    description: 'Public transit, bike infrastructure, walkability',
    topics: ['transportation', 'environment', 'development'],
    weights: {
      'transportation': 1.0,
      'environment': 0.5,
      'budget': 0.3,
      'community': 0.3
    }
  },
  {
    id: 'environmental_steward',
    name: 'Environmental Steward',
    icon: 'Leaf',
    iconColor: '#2aa198', // Cyan
    description: 'Climate action, sustainability, green infrastructure',
    topics: ['environment', 'transportation', 'development'],
    weights: {
      'environment': 1.0,
      'transportation': 0.4,
      'development': 0.3,
      'housing': 0.2
    }
  },
  {
    id: 'fiscal_conservative',
    name: 'Fiscal Conservative',
    icon: 'DollarSign',
    iconColor: '#b58900', // Yellow
    description: 'Budget oversight, tax policy, government efficiency',
    topics: ['budget', 'governance', 'development'],
    weights: {
      'budget': 1.0,
      'governance': 0.6,
      'development': 0.4,
      'transportation': 0.3
    }
  },
  {
    id: 'community_builder',
    name: 'Community Builder',
    icon: 'Heart',
    iconColor: '#d33682', // Magenta
    description: 'Arts, culture, public spaces, social programs',
    topics: ['community', 'education', 'budget'],
    weights: {
      'community': 1.0,
      'education': 0.5,
      'budget': 0.3,
      'housing': 0.3
    }
  },
  {
    id: 'safety_first',
    name: 'Safety First',
    icon: 'Shield',
    iconColor: '#dc322f', // Red
    description: 'Public safety, emergency services, crime prevention',
    topics: ['public_safety', 'budget', 'community'],
    weights: {
      'public_safety': 1.0,
      'budget': 0.4,
      'community': 0.3,
      'governance': 0.2
    }
  },
  {
    id: 'education_advocate',
    name: 'Education Advocate',
    icon: 'GraduationCap',
    iconColor: '#6c71c4', // Violet
    description: 'Schools, youth programs, libraries',
    topics: ['education', 'community', 'budget'],
    weights: {
      'education': 1.0,
      'community': 0.5,
      'budget': 0.4,
      'housing': 0.2
    }
  },
  {
    id: 'small_business_booster',
    name: 'Small Business Booster',
    icon: 'Store',
    iconColor: '#cb4b16', // Orange
    description: 'Local economy, business development',
    topics: ['development', 'budget', 'community'],
    weights: {
      'development': 1.0,
      'budget': 0.5,
      'community': 0.4,
      'governance': 0.3
    }
  },
  {
    id: 'government_watchdog',
    name: 'Government Watchdog',
    icon: 'Eye',
    iconColor: '#657b83', // Base00
    description: 'Transparency, accountability, electoral integrity',
    topics: ['governance', 'elections', 'budget'],
    weights: {
      'governance': 1.0,
      'elections': 0.8,
      'budget': 0.5,
      'public_safety': 0.3
    }
  },
  {
    id: 'neighborhood_protector',
    name: 'Neighborhood Protector',
    icon: 'Users',
    iconColor: '#2aa198', // Cyan
    description: 'Local character, traffic calming, quality of life',
    topics: ['housing', 'transportation', 'community'],
    weights: {
      'housing': 0.6,
      'transportation': 0.6,
      'community': 0.8,
      'environment': 0.4
    }
  },
  {
    id: 'justice_reformer',
    name: 'Justice Reformer',
    icon: 'Scale',
    iconColor: '#6c71c4', // Violet
    description: 'Criminal justice, police accountability, equity',
    topics: ['public_safety', 'governance', 'community'],
    weights: {
      'public_safety': 0.8,
      'governance': 0.7,
      'community': 0.5,
      'budget': 0.3
    }
  },
  {
    id: 'regional_thinker',
    name: 'Regional Thinker',
    icon: 'Globe',
    iconColor: '#268bd2', // Blue
    description: 'Cross-jurisdictional issues, regional planning',
    topics: ['transportation', 'environment', 'housing'],
    weights: {
      'transportation': 0.7,
      'environment': 0.7,
      'housing': 0.6,
      'governance': 0.5
    }
  }
]

/**
 * Match swipe results to civic archetypes (CLIENT-SIDE ONLY)
 *
 * @param swipes - Array of swipe results from Values Explorer
 * @param topN - Number of top archetypes to return (default: 3)
 * @returns Array of top N archetype matches with scores
 */
export function matchToArchetypes(
  swipes: SwipeResult[],
  topN: number = 3
): ArchetypeMatch[] {
  // Initialize scores for each archetype
  const scores: Record<string, number> = {}
  ARCHETYPES.forEach(archetype => {
    scores[archetype.id] = 0
  })

  // Process right-swipes only (liked cards)
  const likedSwipes = swipes.filter(s => s.direction === 'right')

  if (likedSwipes.length === 0) {
    // No liked cards - return empty array
    return []
  }

  // Calculate weighted scores
  likedSwipes.forEach(swipe => {
    const topic = swipe.card.metadata?.project_type || swipe.card.metadata?.topic
    if (!topic) return

    // Add weighted scores to each archetype
    ARCHETYPES.forEach(archetype => {
      const weight = archetype.weights[topic] || 0
      scores[archetype.id] += weight
    })
  })

  // Normalize scores to 0-1 range
  const maxScore = Math.max(...Object.values(scores))
  if (maxScore > 0) {
    Object.keys(scores).forEach(id => {
      scores[id] = scores[id] / maxScore
    })
  }

  // Filter out archetypes with zero score and return top N
  return Object.entries(scores)
    .filter(([_, score]) => score > 0)
    .map(([id, score]) => {
      const archetype = ARCHETYPES.find(a => a.id === id)!
      return {
        id,
        name: archetype.name,
        icon: archetype.icon,
        iconColor: archetype.iconColor,
        score,
        rank: 0
      }
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, topN)
    .map((match, index) => ({
      ...match,
      rank: index + 1
    }))
}

/**
 * Store archetypes in browser localStorage (NEVER SENT TO SERVER)
 */
export function saveArchetypesToBrowser(archetypes: ArchetypeMatch[]): void {
  try {
    localStorage.setItem('civic-archetypes', JSON.stringify(archetypes))
    localStorage.setItem('civic-archetypes-updated', new Date().toISOString())
    console.log('[Privacy] Archetypes saved to browser (never sent to server)')
  } catch (err) {
    console.error('[Privacy] Error saving archetypes to localStorage:', err)
    throw new Error('Failed to save archetypes to browser storage')
  }
}

/**
 * Load archetypes from browser localStorage (with migration support)
 */
export function loadArchetypesFromBrowser(): ArchetypeMatch[] | null {
  try {
    const stored = localStorage.getItem('civic-archetypes')
    if (!stored) return null

    const archetypes: ArchetypeMatch[] = JSON.parse(stored)

    // Migrate old emoji icons to new Lucide icon names
    // Check if any archetype is missing iconColor (indicates old format)
    const needsMigration = archetypes.some(a => !a.iconColor)

    if (needsMigration) {
      console.log('[Privacy] Migrating old archetype format to new icon system')
      const migrated = archetypes.map(archetype => {
        // Find the archetype definition by ID
        const def = ARCHETYPES.find(a => a.id === archetype.id)
        if (def) {
          return {
            ...archetype,
            icon: def.icon,
            iconColor: def.iconColor
          }
        }
        return archetype
      })

      // Save migrated data back to localStorage
      saveArchetypesToBrowser(migrated)
      return migrated
    }

    return archetypes
  } catch (err) {
    console.error('[Privacy] Error loading archetypes from localStorage:', err)
    return null
  }
}

/**
 * Clear archetypes from browser (for reset/logout)
 */
export function clearArchetypes(): void {
  try {
    localStorage.removeItem('civic-archetypes')
    localStorage.removeItem('civic-archetypes-updated')
    console.log('[Privacy] Archetypes cleared from browser')
  } catch (err) {
    console.error('[Privacy] Error clearing archetypes:', err)
  }
}

/**
 * Export user profile for backup (includes archetypes + demographics)
 *
 * Returns JSON blob that user can download and import on another device.
 * This enables manual cross-device sync without server storage.
 */
export function exportProfile(): Blob {
  const data = {
    version: '1.0',
    privacy_tier: 'browser-only',
    exported_at: new Date().toISOString(),
    archetypes: loadArchetypesFromBrowser(),
    profile: JSON.parse(localStorage.getItem('civic-profile') || '{}')
  }

  return new Blob(
    [JSON.stringify(data, null, 2)],
    { type: 'application/json' }
  )
}

/**
 * Import user profile from backup (restores archetypes + demographics)
 *
 * @param json - JSON string from exported profile file
 */
export function importProfile(json: string): void {
  try {
    const data = JSON.parse(json)

    // Validate version
    if (data.version !== '1.0') {
      throw new Error('Unsupported profile version')
    }

    // Validate privacy tier
    if (data.privacy_tier !== 'browser-only') {
      throw new Error('This profile uses a different privacy tier')
    }

    // Restore archetypes
    if (data.archetypes) {
      saveArchetypesToBrowser(data.archetypes)
    }

    // Restore profile metadata (non-political data)
    if (data.profile) {
      localStorage.setItem('civic-profile', JSON.stringify(data.profile))
    }

    console.log('[Privacy] Profile imported successfully (browser-only)')
  } catch (err) {
    console.error('[Privacy] Error importing profile:', err)
    throw new Error('Failed to import profile. Please check the file format.')
  }
}

/**
 * Map archetypes to civic interests (for UI compatibility)
 *
 * Converts archetype IDs to civic interest categories used in ProfileForm.
 * This mapping is for UI display only - no data sent to server.
 */
export function archetypesToInterests(archetypes: ArchetypeMatch[]): string[] {
  const interestMap: Record<string, string> = {
    'housing_champion': 'housing',
    'transit_advocate': 'transportation',
    'environmental_steward': 'environment',
    'fiscal_conservative': 'budget',
    'community_builder': 'community',
    'safety_first': 'public_safety',
    'education_advocate': 'education',
    'small_business_booster': 'development',
    'government_watchdog': 'governance',
    'neighborhood_protector': 'community',
    'justice_reformer': 'public_safety',
    'regional_thinker': 'transportation'
  }

  const interests = archetypes
    .map(a => interestMap[a.id])
    .filter((interest, index, arr) => interest && arr.indexOf(interest) === index) // deduplicate

  return interests
}

/**
 * Get archetype by ID (for display)
 */
export function getArchetypeById(id: string): Archetype | undefined {
  return ARCHETYPES.find(a => a.id === id)
}

/**
 * Check if user has completed Values Explorer
 */
export function hasCompletedValuesExplorer(): boolean {
  const archetypes = loadArchetypesFromBrowser()
  return archetypes !== null && archetypes.length > 0
}

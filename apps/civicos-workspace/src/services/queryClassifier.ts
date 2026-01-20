/**
 * Query Classifier
 *
 * Determines whether a search query is "simple" (mappable to UI controls)
 * or "complex" (requires backend search with custom presentation).
 *
 * This abstraction allows the chat routing logic to remain flexible
 * and easy to extend as new filter capabilities are added.
 */

import type { ProjectType } from '../types/civic'

export interface SimpleQuery {
  type: 'simple'
  topic?: ProjectType
  dateRange?: 'past' | 'upcoming' | 'all'
  searchQuery?: string
}

export interface ComplexQuery {
  type: 'complex'
  topics?: ProjectType[]           // Multiple topics (OR condition)
  specificDateRange?: {             // Custom date ranges
    start?: string
    end?: string
  }
  itemCountMin?: number             // Agenda item count filters
  searchQuery?: string
  jurisdiction?: string
  // Extensible for future complex filters
  customConditions?: Record<string, any>
}

export type ClassifiedQuery = SimpleQuery | ComplexQuery

/**
 * Classify a search query based on chat routing parameters
 *
 * Simple queries:
 * - Single topic OR no topic
 * - Basic date range (past/upcoming/all) OR no date filter
 * - Optional simple text search
 *
 * Complex queries:
 * - Multiple topics (e.g., "housing or transportation")
 * - Specific date ranges (e.g., "next 2 weeks")
 * - Item count filters (e.g., "meetings with 5+ items")
 * - Jurisdiction-specific searches (when user location is different)
 * - Any custom conditions
 */
export function classifySearchQuery(params: {
  topic?: ProjectType | ProjectType[]
  query?: string
  date_range?: 'past' | 'upcoming' | 'all' | string
  jurisdiction?: string
  item_count_min?: number
  // Extensible
  [key: string]: any
}): ClassifiedQuery {
  // Check for complex conditions
  const isMultipleTopics = Array.isArray(params.topic) && params.topic.length > 1
  const hasCustomDateRange = params.date_range && !['past', 'upcoming', 'all'].includes(params.date_range)
  const hasItemCountFilter = params.item_count_min !== undefined
  const hasJurisdictionFilter = params.jurisdiction !== undefined

  // Additional extensible check: any unknown parameters suggest complexity
  const knownSimpleParams = new Set(['topic', 'query', 'date_range'])
  const hasUnknownParams = Object.keys(params).some(key => !knownSimpleParams.has(key))

  // Determine if query is complex
  if (isMultipleTopics || hasCustomDateRange || hasItemCountFilter || hasJurisdictionFilter || hasUnknownParams) {
    return {
      type: 'complex',
      topics: Array.isArray(params.topic) ? params.topic : params.topic ? [params.topic] : undefined,
      searchQuery: params.query,
      itemCountMin: params.item_count_min,
      jurisdiction: params.jurisdiction,
      specificDateRange: hasCustomDateRange ? { start: params.date_range } : undefined,
      customConditions: hasUnknownParams ? params : undefined
    }
  }

  // Simple query - maps cleanly to UI controls
  return {
    type: 'simple',
    topic: Array.isArray(params.topic) ? params.topic[0] : params.topic,
    dateRange: params.date_range === 'past' || params.date_range === 'upcoming' ? params.date_range : 'all',
    searchQuery: params.query
  }
}

/**
 * Format a query description for user-facing messages
 */
export function formatQueryDescription(query: ClassifiedQuery): string {
  const parts: string[] = []

  if (query.type === 'simple') {
    if (query.searchQuery) parts.push(`"${query.searchQuery}"`)
    if (query.topic) parts.push(query.topic)
    if (query.dateRange && query.dateRange !== 'all') parts.push(query.dateRange)
  } else {
    if (query.searchQuery) parts.push(`"${query.searchQuery}"`)
    if (query.topics && query.topics.length > 0) {
      parts.push(query.topics.join(' or '))
    }
    if (query.itemCountMin) parts.push(`${query.itemCountMin}+ items`)
    if (query.jurisdiction) parts.push(`in ${query.jurisdiction}`)
  }

  return parts.length > 0 ? parts.join(' ') : 'events'
}

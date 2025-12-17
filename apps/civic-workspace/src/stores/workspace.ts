import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Jurisdiction, CivicEvent, ProjectType } from '../types/civic'
import { isValidArtifactId, getArtifactIdFormat } from '../utils/artifactIds'

/**
 * Workspace Store
 *
 * Manages workspace-level state including:
 * - Selected jurisdiction and event
 * - Active sidebar tab
 * - Sidebar collapsed state
 * - Open artifacts (tabs)
 * - Event filters (for chat-driven filtering)
 * - LocalStorage persistence
 */

export type SidebarTab = 'jurisdictions' | 'legislative' | 'myissues' | 'events'
export type ViewMode = 'chat-first' | 'workspace-first'

// Session 77: Query result mode for complex multi-operation queries
export type EventsViewMode = 'filtered' | 'query_results'

export interface QueryOperation {
  action: string
  parameters: Record<string, any>
}

export interface ActiveQuery {
  rawQuery: string
  operations: QueryOperation[]
  resultCount: number
}

export interface OpenArtifact {
  id: string
  type: 'event' | 'bill' | 'program' | 'issue' | 'issue-form' | 'thread' | 'comment-draft' | 'profile-form' | 'values-explorer' | 'admin-status'
  title: string
  data: any
  initialTab?: string // Optional: specify which tab to open (e.g., 'discussion' for IssueArtifact)
}

interface WorkspaceState {
  selectedJurisdictionId: string | null
  selectedEventId: string | null
  activeTab: SidebarTab
  sidebarCollapsed: boolean
  openArtifacts: OpenArtifact[]
  activeArtifactIndex: number
  viewMode: ViewMode
  workspaceVisible: boolean
}

const STORAGE_KEY = 'civic-workspace-state'

export const useWorkspaceStore = defineStore('workspace', () => {
  // State
  const selectedJurisdiction = ref<Jurisdiction | null>(null)
  const selectedEvent = ref<CivicEvent | null>(null)
  const selectedEventInList = ref<CivicEvent | null>(null) // For split-pane detail view (NOT a tab)
  const activeTab = ref<SidebarTab>('jurisdictions')
  const sidebarCollapsed = ref(false)
  const openArtifacts = ref<OpenArtifact[]>([])
  const activeArtifactIndex = ref(-1)
  const viewMode = ref<ViewMode>('chat-first') // Default to chat-first for new users
  const workspaceVisible = ref(false) // Workspace hidden initially in chat-first mode

  // Issue form trigger (for chat-based complaint filing)
  const issueFormTrigger = ref<{
    open: boolean
    initialData?: {
      title?: string
      description?: string
      address?: string
      category?: string
    }
  }>({
    open: false
  })

  // Event filters (for chat-driven filtering of EventsPanel)
  const eventFilters = ref<{
    searchQuery?: string
    topics?: ProjectType[]
    dateRange?: 'past' | 'upcoming' | 'all'
    // Trigger flag to notify EventsPanel of external filter changes
    _trigger?: number
  }>({})

  // Session 50: Draft research content (from chat messages)
  const draftResearchContent = ref<string | null>(null)

  // Session 77: Query result mode for complex multi-operation queries
  const eventsViewMode = ref<EventsViewMode>('filtered')
  const activeQuery = ref<ActiveQuery | null>(null)

  // Computed
  const hasJurisdiction = computed(() => selectedJurisdiction.value !== null)
  const hasEvent = computed(() => selectedEvent.value !== null)
  const hasSelectedEventInList = computed(() => selectedEventInList.value !== null)
  const selectedJurisdictionId = computed(() => selectedJurisdiction.value?.id ?? null)
  const selectedEventId = computed(() => selectedEvent.value?.id ?? null)
  const hasOpenArtifacts = computed(() => openArtifacts.value.length > 0)
  const activeArtifact = computed(() => {
    if (activeArtifactIndex.value >= 0 && activeArtifactIndex.value < openArtifacts.value.length) {
      return openArtifacts.value[activeArtifactIndex.value]
    }
    return null
  })

  // Actions
  function selectJurisdiction(jurisdiction: Jurisdiction | null) {
    selectedJurisdiction.value = jurisdiction
    // Clear event selection when jurisdiction changes
    if (selectedEvent.value && jurisdiction?.id !== selectedJurisdiction.value?.id) {
      selectedEvent.value = null
    }
  }

  function selectEvent(event: CivicEvent | null) {
    selectedEvent.value = event
  }

  function selectEventInList(event: CivicEvent | null) {
    // This is for the split-pane detail view (NOT opening as a tab)
    selectedEventInList.value = event
  }

  function setActiveTab(tab: SidebarTab) {
    activeTab.value = tab
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setSidebarCollapsed(collapsed: boolean) {
    sidebarCollapsed.value = collapsed
  }

  function clearSelection() {
    selectedJurisdiction.value = null
    selectedEvent.value = null
  }

  function clearEvent() {
    selectedEvent.value = null
  }

  function clearEventInList() {
    selectedEventInList.value = null
  }

  // View Mode Management
  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
    if (mode === 'workspace-first') {
      // In workspace-first mode, workspace is always visible
      workspaceVisible.value = true
    }
  }

  function revealWorkspace() {
    // Show workspace (triggered by opening artifacts in chat-first mode)
    workspaceVisible.value = true
  }

  function hideWorkspace() {
    // Hide workspace (only applicable in chat-first mode)
    if (viewMode.value === 'chat-first') {
      workspaceVisible.value = false
    }
  }

  function toggleWorkspaceVisibility() {
    // Toggle workspace visibility (only in chat-first mode)
    if (viewMode.value === 'chat-first') {
      workspaceVisible.value = !workspaceVisible.value
    }
  }

  // Artifact Management (Tabs)
  const MAX_TABS = 10

  function openArtifact(artifact: OpenArtifact) {
    // Session 49: Deprecate comment-draft artifact type
    if (artifact.type === 'comment-draft') {
      console.warn('[workspace] comment-draft artifacts are deprecated (Session 49). Use Drafts tab in EventArtifact instead.')

      // Redirect to event artifact with drafts tab open
      if (artifact.data?.event) {
        const eventArtifact: OpenArtifact = {
          id: artifact.data.event.id,
          type: 'event',
          title: artifact.data.event.title,
          data: artifact.data.event,
          initialTab: 'drafts'
        }
        openArtifact(eventArtifact)
      }
      return
    }

    // Session 53.5: Validate artifact ID format
    if (!isValidArtifactId(artifact.type, artifact.id)) {
      console.warn(
        `[workspace] Artifact ID format mismatch detected!\n` +
        `  Type: ${artifact.type}\n` +
        `  Provided ID: ${artifact.id}\n` +
        `  Expected format: ${getArtifactIdFormat(artifact.type)}\n` +
        `  This may cause context management issues. Use ArtifactIds.${artifact.type}() helper.`
      );
    }

    // Check if artifact is already open
    const existingIndex = openArtifacts.value.findIndex(a => a.id === artifact.id)
    if (existingIndex >= 0) {
      // Session 50 fix: Update initialTab and trigger reactivity properly
      if (artifact.initialTab !== undefined) {
        // Create a new object to trigger reactivity
        openArtifacts.value[existingIndex] = {
          ...openArtifacts.value[existingIndex],
          initialTab: artifact.initialTab
        }
        console.log('[workspace] Updated initialTab to:', artifact.initialTab)
      }
      // Just switch to the existing tab
      activeArtifactIndex.value = existingIndex
      // Reveal workspace when switching to existing artifact
      revealWorkspace()
      return
    }

    // Check max tabs limit
    if (openArtifacts.value.length >= MAX_TABS) {
      console.warn(`Maximum of ${MAX_TABS} tabs allowed`)
      return
    }

    // Add new artifact
    openArtifacts.value.push(artifact)
    activeArtifactIndex.value = openArtifacts.value.length - 1

    // Automatically reveal workspace when opening an artifact (in chat-first mode)
    revealWorkspace()
  }

  function closeArtifact(index: number) {
    if (index < 0 || index >= openArtifacts.value.length) return

    openArtifacts.value.splice(index, 1)

    // Adjust active index
    if (openArtifacts.value.length === 0) {
      activeArtifactIndex.value = -1
    } else if (activeArtifactIndex.value >= openArtifacts.value.length) {
      activeArtifactIndex.value = openArtifacts.value.length - 1
    } else if (activeArtifactIndex.value > index) {
      activeArtifactIndex.value--
    }
  }

  function setActiveArtifact(index: number) {
    if (index >= 0 && index < openArtifacts.value.length) {
      activeArtifactIndex.value = index
    }
  }

  function closeAllArtifacts() {
    openArtifacts.value = []
    activeArtifactIndex.value = -1
  }

  function closeActiveArtifact() {
    if (activeArtifactIndex.value >= 0) {
      closeArtifact(activeArtifactIndex.value)
    }
  }

  function clearActiveArtifact() {
    // Deactivate current artifact without closing it
    // This returns user to the event list while keeping tabs open
    activeArtifactIndex.value = -1
  }

  function nextTab() {
    if (openArtifacts.value.length === 0) return
    const nextIndex = (activeArtifactIndex.value + 1) % openArtifacts.value.length
    setActiveArtifact(nextIndex)
  }

  function previousTab() {
    if (openArtifacts.value.length === 0) return
    const prevIndex = activeArtifactIndex.value <= 0
      ? openArtifacts.value.length - 1
      : activeArtifactIndex.value - 1
    setActiveArtifact(prevIndex)
  }

  function switchToTab(tabNumber: number) {
    // Tab numbers are 1-indexed (Cmd+1, Cmd+2, etc.)
    const index = tabNumber - 1
    if (index >= 0 && index < openArtifacts.value.length) {
      setActiveArtifact(index)
    }
  }

  // Issue Form Management
  function openIssueForm(initialData?: {
    title?: string
    description?: string
    address?: string
    category?: string
  }) {
    issueFormTrigger.value = {
      open: true,
      initialData
    }
  }

  function closeIssueForm() {
    issueFormTrigger.value = {
      open: false
    }
  }

  // Event Filter Management
  function setEventFilters(filters: {
    searchQuery?: string
    topics?: ProjectType[]
    dateRange?: 'past' | 'upcoming' | 'all'
  }) {
    eventFilters.value = {
      ...filters,
      // Increment trigger to notify EventsPanel of change
      _trigger: (eventFilters.value._trigger || 0) + 1
    }
  }

  function clearEventFilters() {
    eventFilters.value = {
      _trigger: (eventFilters.value._trigger || 0) + 1
    }
  }

  // Session 50: Draft Research Content Management
  function setDraftResearchContent(content: string) {
    draftResearchContent.value = content
  }

  function clearDraftResearchContent() {
    draftResearchContent.value = null
  }

  // Session 77: Query Result Mode Management
  function setActiveQuery(query: ActiveQuery) {
    eventsViewMode.value = 'query_results'
    activeQuery.value = query
  }

  function clearActiveQuery() {
    eventsViewMode.value = 'filtered'
    activeQuery.value = null
  }

  // Persistence
  function loadFromStorage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const state: WorkspaceState = JSON.parse(stored)
        activeTab.value = state.activeTab
        sidebarCollapsed.value = state.sidebarCollapsed

        // Restore view mode and workspace visibility
        if (state.viewMode) {
          viewMode.value = state.viewMode
        }
        if (typeof state.workspaceVisible === 'boolean') {
          workspaceVisible.value = state.workspaceVisible
        }

        // Restore open artifacts (with migration for complaint → issue)
        if (state.openArtifacts && Array.isArray(state.openArtifacts)) {
          // Migrate old 'complaint' and 'complaint-form' types to 'issue' and 'issue-form'
          openArtifacts.value = state.openArtifacts.map(artifact => {
            if ((artifact as any).type === 'complaint') {
              return { ...artifact, type: 'issue' as const }
            }
            if ((artifact as any).type === 'complaint-form') {
              return { ...artifact, type: 'issue-form' as const }
            }
            return artifact
          })
        }
        if (typeof state.activeArtifactIndex === 'number') {
          activeArtifactIndex.value = state.activeArtifactIndex
        }

        // Note: We don't restore selected jurisdiction/event from storage
        // because they need to be fetched fresh from the API
      }
    } catch (error) {
      console.error('Failed to load workspace state from localStorage:', error)
    }
  }

  function saveToStorage() {
    try {
      const state: WorkspaceState = {
        selectedJurisdictionId: selectedJurisdictionId.value,
        selectedEventId: selectedEventId.value,
        activeTab: activeTab.value,
        sidebarCollapsed: sidebarCollapsed.value,
        openArtifacts: openArtifacts.value,
        activeArtifactIndex: activeArtifactIndex.value,
        viewMode: viewMode.value,
        workspaceVisible: workspaceVisible.value
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch (error) {
      console.error('Failed to save workspace state to localStorage:', error)
    }
  }

  // Watch for changes and persist
  watch(
    [activeTab, sidebarCollapsed, selectedJurisdictionId, selectedEventId, openArtifacts, activeArtifactIndex, viewMode, workspaceVisible],
    () => {
      saveToStorage()
    },
    { deep: true } // Deep watch for openArtifacts array changes
  )

  // Load from storage on initialization
  loadFromStorage()

  return {
    // State
    selectedJurisdiction,
    selectedEvent,
    selectedEventInList,
    activeTab,
    sidebarCollapsed,
    openArtifacts,
    activeArtifactIndex,
    viewMode,
    workspaceVisible,
    issueFormTrigger,
    eventFilters,

    // Computed
    hasJurisdiction,
    hasEvent,
    hasSelectedEventInList,
    selectedJurisdictionId,
    selectedEventId,
    hasOpenArtifacts,
    activeArtifact,

    // Actions
    selectJurisdiction,
    selectEvent,
    selectEventInList,
    setActiveTab,
    toggleSidebar,
    setSidebarCollapsed,
    clearSelection,
    clearEvent,
    clearEventInList,

    // View Mode Management
    setViewMode,
    revealWorkspace,
    hideWorkspace,
    toggleWorkspaceVisibility,

    // Artifact Management
    openArtifact,
    closeArtifact,
    setActiveArtifact,
    closeAllArtifacts,
    closeActiveArtifact,
    clearActiveArtifact,
    nextTab,
    previousTab,
    switchToTab,

    // Issue Form Management
    openIssueForm,
    closeIssueForm,

    // Event Filter Management
    setEventFilters,
    clearEventFilters,

    // Session 50: Draft Research Content Management
    draftResearchContent,
    setDraftResearchContent,
    clearDraftResearchContent,

    // Session 77: Query Result Mode Management
    eventsViewMode,
    activeQuery,
    setActiveQuery,
    clearActiveQuery,

    // Persistence
    loadFromStorage,
    saveToStorage
  }
})

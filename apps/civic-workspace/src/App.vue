<script setup lang="ts">
import { ref, onMounted, watch, provide } from 'vue';
import { MapPin, Calendar, MessageCircle, FileText, Scale, CircleAlert, Plus, User, HelpCircle, Activity } from 'lucide-vue-next';
import JurisdictionTree from '@/components/sidebar/JurisdictionTree.vue';
import LegislativePanel from '@/components/sidebar/LegislativePanel.vue';
import IssueList from '@/components/workspace/IssueList.vue';
import DiscussionsPanel from '@/components/sidebar/DiscussionsPanel.vue';
import EventsPanel from '@/components/sidebar/EventsPanel.vue';
import ProfilePanel from '@/components/sidebar/ProfilePanel.vue';
import CollapsibleSection from '@/components/shared/CollapsibleSection.vue';
import EventArtifact from '@/components/workspace/EventArtifact.vue';
import BillArtifact from '@/components/workspace/BillArtifact.vue';
import ProgramArtifact from '@/components/workspace/ProgramArtifact.vue';
import IssueArtifact from '@/components/workspace/IssueArtifact.vue';
import ThreadArtifact from '@/components/workspace/ThreadArtifact.vue';
import CommentDraftArtifact from '@/components/workspace/CommentDraftArtifact.vue';
import IssueForm from '@/components/workspace/IssueForm.vue';
import ProfileForm from '@/components/workspace/ProfileForm.vue';
import ValuesExplorerArtifact from '@/components/workspace/ValuesExplorerArtifact.vue';
import AdminStatusPage from '@/components/workspace/AdminStatusPage.vue';
import LocationEntry from '@/components/LocationEntry.vue';
import ChatPanel from '@/components/chat/ChatPanel.vue';
import TabBar from '@/components/workspace/TabBar.vue';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import { useSidebarStore } from '@/stores/sidebar';
import { useProfileStore } from '@/stores/profile';
import { useDeveloperStore } from '@/stores/developer';
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts';
import { api } from '@/services/api';
import { ArtifactIds } from '@/utils/artifactIds';
import type { Jurisdiction, CivicEvent, FileIssueResponse, Issue, OperationalIssue } from '@/types/civic';

const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();
const sidebarStore = useSidebarStore();
const profileStore = useProfileStore();
const developerStore = useDeveloperStore();

// Location entry modal state
const showLocationEntry = ref(false);

// Issue form modal state
const showIssueForm = ref(false);
const issueInitialData = ref<{
  title?: string;
  description?: string;
  address?: string;
  category?: string;
} | undefined>(undefined);

// EventsPanel ref for AI assistant to apply filters programmatically
const eventsPanelRef = ref<InstanceType<typeof EventsPanel> | null>(null);

// LegislativePanel ref for AI assistant to apply filters programmatically
const legislativePanelRef = ref<InstanceType<typeof LegislativePanel> | null>(null);

// IssueList ref for refreshing after filing issue
const issueListRef = ref<InstanceType<typeof IssueList> | null>(null);

// DiscussionsPanel ref for refreshing after filing issue
const discussionsPanelRef = ref<InstanceType<typeof DiscussionsPanel> | null>(null);

// Resizable panes state
const chatPaneWidth = ref(55); // Default 55%
const sidebarWidth = ref(280); // Default 280px
const isResizing = ref(false);
const isResizingSidebar = ref(false);

// Load saved split ratios from localStorage
onMounted(() => {
  const savedChatWidth = localStorage.getItem('civic-chat-pane-width');
  if (savedChatWidth) {
    chatPaneWidth.value = parseFloat(savedChatWidth);
  }

  const savedSidebarWidth = localStorage.getItem('civic-sidebar-width');
  if (savedSidebarWidth) {
    sidebarWidth.value = parseFloat(savedSidebarWidth);
  }
});

// Check if user needs location entry on mount
onMounted(() => {
  // Show location entry if not set (users can browse without a profile)
  if (!userStore.hasLocation) {
    showLocationEntry.value = true;
  }

  // Initialize profile store
  profileStore.fetchProfile().catch(() => {
    // Profile doesn't exist yet - that's okay, user can create one
    console.log('[App] No profile found - user can create one from ProfilePanel');
  });

  // Initialize developer mode from URL parameter (Session 68)
  // Launch with ?dev=true to enable LLM provider info
  developerStore.initFromUrl();

  // Expose reset functions for testing (browser console access)
  // @ts-ignore
  window.resetEngagement = () => {
    userStore.resetEngagement();
    location.reload();
  };
  console.log('[Dev] Use window.resetEngagement() to reset');
});

// Enable keyboard shortcuts with issue form callback
useKeyboardShortcuts(() => {
  showIssueForm.value = true;
});

// Provide EventsPanel ref to descendants (for ChatPanel to access)
provide('eventsPanelRef', eventsPanelRef);

// Provide LegislativePanel ref to descendants (for ChatPanel to access)
provide('legislativePanelRef', legislativePanelRef);

// Session 61: Provide IssueList ref to descendants (for ChatPanel to access)
provide('issuesPanelRef', issueListRef);

// Watch for issue form trigger from workspace store (from chat)
watch(
  () => workspaceStore.issueFormTrigger,
  (trigger) => {
    if (trigger.open) {
      showIssueForm.value = true;
      issueInitialData.value = trigger.initialData;
      // Reset the trigger
      workspaceStore.closeIssueForm();
    }
  },
  { deep: true }
);

function handleJurisdictionSelect(jurisdiction: Jurisdiction) {
  workspaceStore.selectJurisdiction(jurisdiction);
  // Clear any open artifacts - user will browse events in sidebar
  workspaceStore.clearActiveArtifact();
  console.log('Selected jurisdiction:', jurisdiction);
}

function handleEventOpenAsTab(event: CivicEvent) {
  // Track event view for progressive disclosure
  userStore.incrementEventsViewed();

  // Open event as an artifact (tab)
  workspaceStore.openArtifact({
    id: event.id,
    type: 'event',
    title: event.title,
    data: event
  });
  console.log('Opened event artifact:', event);
}

function handleCloseEvent() {
  // Return to event list without closing the tab
  // This keeps the tab open so user can switch back to it
  workspaceStore.clearActiveArtifact();
}

function openIssueForm() {
  // Open issue form as an artifact (not a modal)
  workspaceStore.openArtifact({
    id: 'new-issue-form',
    type: 'issue-form',
    title: 'Report Issue',
    data: {
      initialData: undefined
    }
  });
}

function closeIssueForm() {
  showIssueForm.value = false;
  issueInitialData.value = undefined;
}

// Handle issue selection from IssueList (Session 92)
function handleIssueSelect(issue: Issue | OperationalIssue) {
  // IssueList already opens the artifact, this is just for additional logic if needed
  console.log('[App] Issue selected:', issue);
}

async function handleIssueFiled(response: FileIssueResponse) {
  console.log('[App] Issue filed:', response);

  // Track issue filing for progressive disclosure
  userStore.incrementIssuesFiled();

  // Close the form immediately (handles both modal and artifact versions)
  closeIssueForm();

  // Also close artifact if form was opened as a tab
  const issueFormArtifact = workspaceStore.openArtifacts.find(a => a.type === 'issue-form');
  if (issueFormArtifact) {
    const index = workspaceStore.openArtifacts.indexOf(issueFormArtifact);
    workspaceStore.closeArtifact(index);
  }

  // IssueList will auto-refresh via its watchers when jurisdiction changes
  // No manual refresh needed

  // Refresh DiscussionsPanel to show new threads (issue + matched events)
  if (discussionsPanelRef.value) {
    discussionsPanelRef.value.loadThreads();
  }

  // Fetch and open the newly filed issue as an artifact
  try {
    console.log('[App] Fetching full issue data:', response.issue_id);
    const fullIssue = await api.getIssue(response.issue_id);

    // Construct tab title (same logic as IssueList)
    const tabTitle = fullIssue.short_name || fullIssue.ai_title || fullIssue.description?.substring(0, 50) + '...';

    workspaceStore.openArtifact({
      id: ArtifactIds.issue(fullIssue.id),
      type: 'issue',
      title: tabTitle,
      data: fullIssue,
      initialTab: 'details' // Open to details tab
    });

    console.log('[App] Opened newly filed issue:', tabTitle);
  } catch (error) {
    console.error('[App] Failed to fetch filed issue:', error);
    // If fetch fails, don't open anything - user can access from sidebar
  }
}

async function handleOpenFocalPoint(focalType: 'issue' | 'event', focalId: string) {
  // Open focal point (event or issue) as a tab when clicked from ThreadArtifact
  try {
    if (focalType === 'event') {
      const event = await api.getEvent(focalId);
      workspaceStore.openArtifact({
        id: event.id,
        type: 'event',
        title: event.title,
        data: event
      });
    } else if (focalType === 'issue') {
      const issue = await api.getIssue(focalId);
      workspaceStore.openArtifact({
        id: issue.id,
        type: 'issue',
        title: issue.short_name || issue.ai_title || issue.description?.substring(0, 50) + '...',
        data: issue
      });
    }
  } catch (err: any) {
    console.error('Error opening focal point:', err);
    alert(`Failed to open ${focalType}: ${err.message}`);
  }
}

function handleLocationSet() {
  console.log('[App] Location set:', userStore.cityName);
  showLocationEntry.value = false;
}

// Open Admin Status Page (Session 301 - Pilot status_page artifact)
function openAdminStatus() {
  workspaceStore.openArtifact({
    id: 'admin-status',
    type: 'admin-status',
    title: 'Pipeline Status',
    data: { jurisdiction: userStore.jurisdictionId || 'san-rafael' }
  });
}

// Session 63: Handle sidebar section toggle (Pinia store as single source of truth)
function handleSectionToggle(sectionName: 'profile' | 'jurisdictions' | 'events' | 'discussions' | 'myIssues' | 'legislative') {
  sidebarStore.toggleSection(sectionName);
}

// Resize handle functions
function startResize(e: MouseEvent) {
  isResizing.value = true;
  e.preventDefault();
  document.addEventListener('mousemove', handleResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function handleResize(e: MouseEvent) {
  if (!isResizing.value) return;

  const sidebar = document.querySelector('.workspace-sidebar') as HTMLElement;
  const sidebarWidth = sidebar?.offsetWidth || 280;
  const containerWidth = window.innerWidth - sidebarWidth;
  const mouseX = e.clientX - sidebarWidth;

  // Calculate percentage (between 30% and 70%)
  let newWidth = (mouseX / containerWidth) * 100;
  newWidth = Math.max(30, Math.min(70, newWidth));

  chatPaneWidth.value = newWidth;
}

function stopResize() {
  isResizing.value = false;
  document.removeEventListener('mousemove', handleResize);
  document.removeEventListener('mouseup', stopResize);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';

  // Save to localStorage
  localStorage.setItem('civic-chat-pane-width', chatPaneWidth.value.toString());
}

// Sidebar resize handle functions
function startResizeSidebar(e: MouseEvent) {
  isResizingSidebar.value = true;
  e.preventDefault();
  document.addEventListener('mousemove', handleResizeSidebar);
  document.addEventListener('mouseup', stopResizeSidebar);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function handleResizeSidebar(e: MouseEvent) {
  if (!isResizingSidebar.value) return;

  // Calculate new width (between 200px and 500px)
  let newWidth = e.clientX;
  newWidth = Math.max(200, Math.min(500, newWidth));

  sidebarWidth.value = newWidth;
}

function stopResizeSidebar() {
  isResizingSidebar.value = false;
  document.removeEventListener('mousemove', handleResizeSidebar);
  document.removeEventListener('mouseup', stopResizeSidebar);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';

  // Save to localStorage
  localStorage.setItem('civic-sidebar-width', sidebarWidth.value.toString());
}
</script>

<template>
  <div
    class="workspace-root"
    :class="{ 'chat-first-layout': workspaceStore.viewMode === 'chat-first' }"
    :style="{ '--sidebar-width': `${sidebarWidth}px` }"
  >
    <!-- Chat-First Mode: Side-by-side layout (chat left, artifacts right) -->
    <template v-if="workspaceStore.viewMode === 'chat-first'">
      <!-- Sidebar -->
      <aside class="workspace-sidebar" :style="{ width: `${sidebarWidth}px` }">
        <div class="sidebar-header">
          <h1 class="logo-text">{{ userStore.displayName }}</h1>
          <div class="header-actions">
            <button
              class="header-icon-btn"
              @click="openAdminStatus"
              title="Pipeline Status"
            >
              <Activity :size="18" />
            </button>
            <a
              href="/help"
              target="_blank"
              rel="noopener noreferrer"
              class="help-link"
              title="Getting Started Guide"
            >
              <HelpCircle :size="20" />
            </a>
          </div>
        </div>

        <!-- Sidebar Content (collapsible sections) -->
        <div class="sidebar-content">
          <!-- Always visible: Profile -->
          <CollapsibleSection
            title="Profile"
            :icon="User"
            iconColor="#268bd2"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.profile"
            storageKey="sidebar-profile"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('profile')"
          >
            <ProfilePanel />
          </CollapsibleSection>

          <!-- Always visible: Jurisdictions -->
          <CollapsibleSection
            title="Jurisdictions"
            :icon="MapPin"
            iconColor="#2aa198"
            :defaultExpanded="true"
            :externalExpanded="sidebarStore.sections.jurisdictions"
            storageKey="sidebar-jurisdictions"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('jurisdictions')"
          >
            <JurisdictionTree @jurisdiction-select="handleJurisdictionSelect" />
          </CollapsibleSection>

          <!-- Always visible: Events -->
          <CollapsibleSection
            title="Events"
            :icon="Calendar"
            iconColor="#859900"
            :defaultExpanded="true"
            :externalExpanded="sidebarStore.sections.events"
            storageKey="sidebar-events"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('events')"
          >
            <EventsPanel ref="eventsPanelRef" />
          </CollapsibleSection>

          <!-- Always visible: Discussions -->
          <CollapsibleSection
            title="Discussions"
            :icon="MessageCircle"
            iconColor="#cb4b16"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.discussions"
            storageKey="sidebar-discussions"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('discussions')"
          >
            <DiscussionsPanel ref="discussionsPanelRef" />
          </CollapsibleSection>

          <!-- Always visible: Issues (Three-tier: Operational + Policy) -->
          <CollapsibleSection
            title="Issues"
            :icon="CircleAlert"
            iconColor="#dc322f"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.myIssues"
            storageKey="sidebar-myissues"
            :actionIcon="Plus"
            actionTooltip="Report a new issue"
            :noMaxHeight="true"
            @action="openIssueForm"
            @toggle="() => handleSectionToggle('myIssues')"
          >
            <IssueList
              ref="issueListRef"
              :jurisdictionId="userStore.jurisdictionId"
              :userId="userStore.userId"
              @issue-select="handleIssueSelect"
            />
          </CollapsibleSection>

          <!-- Always visible: Legislation -->
          <CollapsibleSection
            title="Legislation"
            :icon="Scale"
            iconColor="#6c71c4"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.legislative"
            storageKey="sidebar-legislative"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('legislative')"
          >
            <LegislativePanel ref="legislativePanelRef" />
          </CollapsibleSection>
        </div>
      </aside>

      <!-- Sidebar Resize Handle -->
      <div class="sidebar-resize-handle" @mousedown="startResizeSidebar">
        <div class="resize-indicator"></div>
      </div>

      <!-- Center Area: Chat + Artifact split -->
      <div class="center-area">
        <!-- Chat Pane (always visible) -->
        <div
          class="chat-pane"
          :class="{ 'narrowed': workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact }"
          :style="(workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact) ? { flex: `0 0 ${chatPaneWidth}%` } : {}"
        >
          <ChatPanel />
        </div>

        <!-- Resize Handle (only visible when artifact pane is open) -->
        <div
          v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact"
          class="resize-handle"
          @mousedown="startResize"
        >
          <div class="resize-indicator"></div>
        </div>

        <!-- Artifact Pane (slides in from right) - shows only when artifacts are open -->
        <transition name="slide-in-right">
          <div
            v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact"
            class="artifact-pane"
            :style="{ flex: `0 0 ${100 - chatPaneWidth}%` }"
          >
            <!-- Tab Bar (only show when tabs are open) -->
            <TabBar v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact" />

            <!-- Artifact Content -->
            <div class="artifact-content">
              <!-- Session 53 Fix: Render ALL open artifacts (v-show instead of v-if) -->
              <!-- This keeps all artifacts mounted so contexts remain registered -->
              <template v-for="(artifact, index) in workspaceStore.openArtifacts" :key="artifact.id">
                <!-- EventArtifact -->
                <EventArtifact
                  v-if="artifact.type === 'event'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :event="artifact.data"
                  :mode="'full'"
                  @close="() => workspaceStore.closeArtifact(index)"
                />

                <!-- BillArtifact -->
                <BillArtifact
                  v-else-if="artifact.type === 'bill'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :bill="artifact.data"
                  @close="() => workspaceStore.closeArtifact(index)"
                />

                <!-- ProgramArtifact -->
                <ProgramArtifact
                  v-else-if="artifact.type === 'program'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :program="artifact.data"
                  @close="() => workspaceStore.closeArtifact(index)"
                />

                <!-- IssueArtifact -->
                <IssueArtifact
                  v-else-if="artifact.type === 'issue'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :issue="artifact.data"
                  @close="() => workspaceStore.closeArtifact(index)"
                />

                <!-- ThreadArtifact -->
                <ThreadArtifact
                  v-else-if="artifact.type === 'thread'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :threadId="artifact.id"
                  @close="() => workspaceStore.closeArtifact(index)"
                  @open-focal-point="handleOpenFocalPoint"
                />

                <!-- CommentDraftArtifact -->
                <CommentDraftArtifact
                  v-else-if="artifact.type === 'comment-draft'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :event="artifact.data.event"
                  :selected-agenda-items="artifact.data.selectedAgendaItems"
                  @close="() => workspaceStore.closeArtifact(index)"
                />

                <!-- IssueForm -->
                <IssueForm
                  v-else-if="artifact.type === 'issue-form'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :initial-data="artifact.data.initialData"
                  :as-artifact="true"
                  @close="workspaceStore.closeActiveArtifact"
                  @issue-filed="handleIssueFiled"
                />

                <!-- ProfileForm -->
                <ProfileForm
                  v-else-if="artifact.type === 'profile-form'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :artifact="artifact"
                  @close="workspaceStore.closeActiveArtifact"
                  @saved="workspaceStore.closeActiveArtifact"
                />

                <!-- ValuesExplorerArtifact -->
                <ValuesExplorerArtifact
                  v-else-if="artifact.type === 'values-explorer'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  @close="workspaceStore.closeActiveArtifact"
                />

                <!-- AdminStatusPage (Session 301) -->
                <AdminStatusPage
                  v-else-if="artifact.type === 'admin-status'"
                  v-show="workspaceStore.activeArtifactIndex === index"
                  :jurisdiction="artifact.data?.jurisdiction"
                  @close="workspaceStore.closeActiveArtifact"
                />
              </template>

              <!-- Empty State: No Artifacts Open -->
              <div v-if="workspaceStore.openArtifacts.length === 0" class="empty-state-artifact">
                <h3>No artifact selected</h3>
                <p>Browse events from the sidebar or search via chat</p>
              </div>
            </div>
          </div>
        </transition>
      </div>
    </template>

    <!-- Workspace-First Mode: Traditional layout -->
    <template v-else>
      <!-- Sidebar -->
      <aside class="workspace-sidebar" :style="{ width: `${sidebarWidth}px` }">
        <div class="sidebar-header">
          <h1 class="logo-text">{{ userStore.displayName }}</h1>
          <div class="header-actions">
            <button
              class="header-icon-btn"
              @click="openAdminStatus"
              title="Pipeline Status"
            >
              <Activity :size="18" />
            </button>
            <a
              href="/help"
              target="_blank"
              rel="noopener noreferrer"
              class="help-link"
              title="Getting Started Guide"
            >
              <HelpCircle :size="20" />
            </a>
          </div>
        </div>

        <!-- Sidebar Content (collapsible sections) -->
        <div class="sidebar-content">
          <!-- Always visible: Profile -->
          <CollapsibleSection
            title="Profile"
            :icon="User"
            iconColor="#268bd2"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.profile"
            storageKey="sidebar-profile"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('profile')"
          >
            <ProfilePanel />
          </CollapsibleSection>

          <!-- Always visible: Jurisdictions -->
          <CollapsibleSection
            title="Jurisdictions"
            :icon="MapPin"
            iconColor="#2aa198"
            :defaultExpanded="true"
            :externalExpanded="sidebarStore.sections.jurisdictions"
            storageKey="sidebar-jurisdictions"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('jurisdictions')"
          >
            <JurisdictionTree @jurisdiction-select="handleJurisdictionSelect" />
          </CollapsibleSection>

          <!-- Always visible: Events -->
          <CollapsibleSection
            title="Events"
            :icon="Calendar"
            iconColor="#859900"
            :defaultExpanded="true"
            :externalExpanded="sidebarStore.sections.events"
            storageKey="sidebar-events"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('events')"
          >
            <EventsPanel ref="eventsPanelRef" />
          </CollapsibleSection>

          <!-- Always visible: Discussions -->
          <CollapsibleSection
            title="Discussions"
            :icon="MessageCircle"
            iconColor="#cb4b16"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.discussions"
            storageKey="sidebar-discussions"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('discussions')"
          >
            <DiscussionsPanel ref="discussionsPanelRef" />
          </CollapsibleSection>

          <!-- Always visible: Issues (Three-tier: Operational + Policy) -->
          <CollapsibleSection
            title="Issues"
            :icon="CircleAlert"
            iconColor="#dc322f"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.myIssues"
            storageKey="sidebar-myissues"
            :actionIcon="Plus"
            actionTooltip="Report a new issue"
            :noMaxHeight="true"
            @action="openIssueForm"
            @toggle="() => handleSectionToggle('myIssues')"
          >
            <IssueList
              ref="issueListRef"
              :jurisdictionId="userStore.jurisdictionId"
              :userId="userStore.userId"
              @issue-select="handleIssueSelect"
            />
          </CollapsibleSection>

          <!-- Always visible: Legislation -->
          <CollapsibleSection
            title="Legislation"
            :icon="Scale"
            iconColor="#6c71c4"
            :defaultExpanded="false"
            :externalExpanded="sidebarStore.sections.legislative"
            storageKey="sidebar-legislative"
            :noMaxHeight="true"
            @toggle="() => handleSectionToggle('legislative')"
          >
            <LegislativePanel ref="legislativePanelRef" />
          </CollapsibleSection>
        </div>
      </aside>

      <!-- Sidebar Resize Handle (only show when workspace is visible) -->
      <div
        v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact"
        class="sidebar-resize-handle"
        @mousedown="startResizeSidebar"
      >
        <div class="resize-indicator"></div>
      </div>

      <!-- Main Content (only show when artifacts are open) -->
      <main v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact" class="workspace-main">
        <!-- Tab Bar (when tabs are open) -->
        <TabBar v-if="workspaceStore.hasOpenArtifacts && workspaceStore.activeArtifact" />

        <!-- Content Area -->
        <div class="workspace-content">
          <!-- Session 53 Fix: Render ALL open artifacts (v-show instead of v-if) -->
          <template v-for="(artifact, index) in workspaceStore.openArtifacts" :key="artifact.id">
            <!-- EventArtifact -->
            <EventArtifact
              v-if="artifact.type === 'event'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :event="artifact.data"
              :mode="'full'"
              @close="() => workspaceStore.closeArtifact(index)"
            />

            <!-- BillArtifact -->
            <BillArtifact
              v-else-if="artifact.type === 'bill'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :bill="artifact.data"
              @close="() => workspaceStore.closeArtifact(index)"
            />

            <!-- ProgramArtifact -->
            <ProgramArtifact
              v-else-if="artifact.type === 'program'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :program="artifact.data"
              @close="() => workspaceStore.closeArtifact(index)"
            />

            <!-- IssueArtifact -->
            <IssueArtifact
              v-else-if="artifact.type === 'issue'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :issue="artifact.data"
              @close="() => workspaceStore.closeArtifact(index)"
            />

            <!-- CommentDraftArtifact -->
            <CommentDraftArtifact
              v-else-if="artifact.type === 'comment-draft'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :event="artifact.data.event"
              :selected-agenda-items="artifact.data.selectedAgendaItems"
              @close="() => workspaceStore.closeArtifact(index)"
            />

            <!-- IssueForm -->
            <IssueForm
              v-else-if="artifact.type === 'issue-form'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :initial-data="artifact.data.initialData"
              :as-artifact="true"
              @close="workspaceStore.closeActiveArtifact"
              @issue-filed="handleIssueFiled"
            />

            <!-- ProfileForm -->
            <ProfileForm
              v-else-if="artifact.type === 'profile-form'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :artifact="artifact"
              @close="workspaceStore.closeActiveArtifact"
              @saved="workspaceStore.closeActiveArtifact"
            />

            <!-- ValuesExplorerArtifact -->
            <ValuesExplorerArtifact
              v-else-if="artifact.type === 'values-explorer'"
              v-show="workspaceStore.activeArtifactIndex === index"
              @close="workspaceStore.closeActiveArtifact"
            />

            <!-- AdminStatusPage (Session 301) -->
            <AdminStatusPage
              v-else-if="artifact.type === 'admin-status'"
              v-show="workspaceStore.activeArtifactIndex === index"
              :jurisdiction="artifact.data?.jurisdiction"
              @close="workspaceStore.closeActiveArtifact"
            />
          </template>

          <!-- Empty State: No Artifacts Open -->
          <div v-if="workspaceStore.openArtifacts.length === 0" class="empty-state">
            <h1 class="civic-title">Civic Conversational OS</h1>
            <p class="subtitle">
              Select a jurisdiction from the sidebar to get started
            </p>
          </div>
        </div>
      </main>

      <!-- Chat Panel (bottom panel in workspace-first mode) -->
      <ChatPanel />
    </template>

    <!-- Issue Form Modal -->
    <IssueForm
      v-if="showIssueForm"
      :initial-data="issueInitialData"
      @close="closeIssueForm"
      @issue-filed="handleIssueFiled"
    />

    <!-- Location Entry Modal (shown on first visit if no location) -->
    <LocationEntry
      v-if="showLocationEntry"
      @location-set="handleLocationSet"
    />
  </div>
</template>

<style scoped>
.workspace-root {
  display: flex;
  height: 100vh;
  background: var(--background-secondary);
  overflow: hidden;
}

/* Sidebar */
.workspace-sidebar {
  /* Width set via inline style (default: 280px) */
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  background: var(--sidebar-bg);
  flex-shrink: 0;
}

/* Sidebar Resize Handle */
.sidebar-resize-handle {
  width: 8px;
  cursor: col-resize;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  transition: background-color 0.2s ease;
  border-right: 1px solid var(--border);
}

.sidebar-resize-handle:hover {
  background-color: var(--primary);
  opacity: 0.3;
}

.sidebar-resize-handle .resize-indicator {
  width: 2px;
  height: 40px;
  background-color: var(--border);
  border-radius: 2px;
  transition: all 0.2s ease;
}

.sidebar-resize-handle:hover .resize-indicator {
  background-color: var(--primary);
  height: 60px;
}

.sidebar-header {
  padding: var(--space-lg);
  border-bottom: 1px solid var(--border);
  background: var(--background); /* Light background for header */
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo-text {
  font-size: 24px;
  font-weight: 700;
  color: var(--primary);
  margin: 0;
  letter-spacing: -0.02em;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: none;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.header-icon-btn:hover {
  color: var(--primary);
  background: rgba(33, 150, 243, 0.1);
}

.help-link {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  padding: 6px;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.help-link:hover {
  color: var(--primary);
  background: rgba(33, 150, 243, 0.1);
}

/* Progressive Disclosure Animations */
.new-feature {
  animation: slideInDown 0.3s ease-out;
}

@keyframes slideInDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Sidebar Content */
.sidebar-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  padding: 0; /* Flush with left edge */
}

/* Main Content */
.workspace-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workspace-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: var(--space-2xl);
}

.civic-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: var(--space-md);
  background: var(--gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  color: var(--text-secondary);
  font-size: var(--font-size-base);
}

/* Event Detail Empty State (right pane of split view) */
.event-detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: var(--space-2xl);
  background: var(--background-secondary);
}

.event-detail-empty h3 {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-md);
}

.event-detail-empty p {
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  margin: 0;
}

/* Responsive */
@media (max-width: 768px) {
  /* Sidebar width still adjustable on mobile */
}

/* Workspace-First Mode: Chat panel at bottom */
.workspace-root:not(.chat-first-layout) {
  display: grid;
  grid-template-columns: var(--sidebar-width, 280px) 8px 1fr;
  grid-template-rows: 1fr auto;
  height: 100vh;
  overflow: hidden;
}

.workspace-root:not(.chat-first-layout) .workspace-sidebar {
  grid-column: 1;
  grid-row: 1 / 3;
}

.workspace-root:not(.chat-first-layout) .sidebar-resize-handle {
  grid-column: 2;
  grid-row: 1 / 3;
}

.workspace-root:not(.chat-first-layout) .workspace-main {
  grid-column: 3;
  grid-row: 1;
}

.workspace-root:not(.chat-first-layout) .chat-panel-container {
  grid-column: 3;
  grid-row: 2;
  max-height: 400px;
  border-top: 1px solid var(--border);
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
}

/* Chat-First Layout: Side-by-side (Perplexity/Claude.ai style) */
.workspace-root.chat-first-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Center Area: Chat + Artifact split */
.center-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
  background: var(--background-secondary);
}

/* Chat Pane (always visible) */
.chat-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  transition: flex 0.3s ease;
  background: var(--background-extra-light);
  overflow: hidden;
  position: relative;
  z-index: 1;
}

/* Narrowed when artifact pane is open (width set via inline style) */
.chat-pane.narrowed {
  border-right: 1px solid var(--border);
}

/* Resize Handle */
.resize-handle {
  width: 8px;
  cursor: col-resize;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 3; /* Above both panes */
  transition: background-color 0.2s ease;
}

.resize-handle:hover {
  background-color: var(--primary);
  opacity: 0.3;
}

.resize-indicator {
  width: 2px;
  height: 40px;
  background-color: var(--border);
  border-radius: 2px;
  transition: all 0.2s ease;
}

.resize-handle:hover .resize-indicator {
  background-color: var(--primary);
  height: 60px;
}

/* Artifact Pane (slides in from right) */
.artifact-pane {
  display: flex;
  flex-direction: column;
  background: var(--background);
  overflow: hidden;
  position: relative;
  z-index: 2; /* Above chat pane */
}

.artifact-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Slide-in animation for artifact pane */
.slide-in-right-enter-active,
.slide-in-right-leave-active {
  transition: all 0.3s ease;
}

.slide-in-right-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-in-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* Empty state for artifact pane */
.empty-state-artifact {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: var(--space-2xl);
  background: var(--background);
}

.empty-state-artifact h3 {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--space-md);
}

.empty-state-artifact p {
  color: var(--text-secondary);
  font-size: var(--font-size-base);
  margin: 0;
}

/* Mobile responsive: Stack vertically */
@media (max-width: 768px) {
  .center-area {
    flex-direction: column;
  }

  .chat-pane,
  .chat-pane.narrowed {
    flex: 1;
    border-right: none;
  }

  .artifact-pane {
    flex: 1;
    border-left: none;
    border-top: 1px solid var(--border);
  }

  .slide-in-right-enter-from,
  .slide-in-right-leave-to {
    transform: translateY(100%);
  }
}
</style>

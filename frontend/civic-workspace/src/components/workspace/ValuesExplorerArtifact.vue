<template>
  <div class="values-explorer-artifact">
    <!-- Artifact Header -->
    <div class="artifact-header">
      <div class="header-content">
        <h2 class="artifact-title">Explore Your Political Values</h2>
        <p class="artifact-subtitle">
          Swipe through real civic decisions to discover what matters most to you
        </p>
      </div>
    </div>

    <!-- SwipeOnboarding Component (embedded without modal styling) -->
    <div class="artifact-content">
      <SwipeOnboarding
        @complete="handleComplete"
        @skip="handleSkip"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import SwipeOnboarding from '@/components/onboarding/SwipeOnboarding.vue'
import { useProfileStore } from '@/stores/profile'
import { useWorkspaceStore } from '@/stores/workspace'

const profileStore = useProfileStore()
const workspaceStore = useWorkspaceStore()

const emit = defineEmits<{
  (e: 'close'): void
}>()

function handleComplete(interests: string[]) {
  console.log('[ValuesExplorerArtifact] Completed with interests:', interests)

  // Store discovered interests in ProfileStore
  profileStore.setDiscoveredInterests(interests)

  // Check if ProfileForm is already open (to preserve user's entered data)
  const existingProfileFormIndex = workspaceStore.openArtifacts.findIndex(
    a => a.type === 'profile-form'
  )

  if (existingProfileFormIndex >= 0) {
    // ProfileForm already exists - just switch to it (preserves user data)
    console.log('[ValuesExplorerArtifact] ProfileForm already open at index:', existingProfileFormIndex)
    console.log('[ValuesExplorerArtifact] Switching to existing ProfileForm (preserving user data)')
    workspaceStore.setActiveArtifact(existingProfileFormIndex)
  } else {
    // No existing ProfileForm - create a new one
    const profileArtifact = {
      id: 'profile-form',
      type: 'profile-form' as const,
      title: 'Complete Your Profile',
      data: {
        fromOnboarding: true  // Flag to indicate this came from onboarding
      }
    }
    console.log('[ValuesExplorerArtifact] Opening new ProfileForm with artifact:', JSON.stringify(profileArtifact))
    workspaceStore.openArtifact(profileArtifact)
  }

  // THEN close this artifact (Values Explorer)
  // Find the index AFTER switching/opening ProfileForm
  setTimeout(() => {
    const valuesExplorerIndex = workspaceStore.openArtifacts.findIndex(
      a => a.type === 'values-explorer'
    )
    console.log('[ValuesExplorerArtifact] Closing Values Explorer at index:', valuesExplorerIndex)
    if (valuesExplorerIndex >= 0) {
      workspaceStore.closeArtifact(valuesExplorerIndex)
    }
  }, 50)
}

function handleSkip() {
  console.log('[ValuesExplorerArtifact] Skipped')

  // Close this artifact
  workspaceStore.closeActiveArtifact()
  emit('close')
}
</script>

<style scoped>
.values-explorer-artifact {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--background);
}

/* Artifact Header */
.artifact-header {
  padding: var(--space-xl);
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
}

.header-content {
  max-width: 600px;
  margin: 0 auto;
}

.artifact-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-xs) 0;
  letter-spacing: -0.01em;
}

.artifact-subtitle {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.4;
}

/* Artifact Content */
.artifact-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}

/* Override SwipeOnboarding modal styles to fit artifact mode */
.artifact-content :deep(.swipe-onboarding-modal) {
  position: static;
  background: transparent;
  backdrop-filter: none;
  padding: 0;
  z-index: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}

.artifact-content :deep(.swipe-onboarding-container) {
  background: transparent;
  max-width: 600px;
  width: 100%;
  padding: var(--space-xl);
  max-height: none;
  overflow-y: visible;
}

/* Scrollbar */
.artifact-content::-webkit-scrollbar {
  width: 8px;
}

.artifact-content::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.artifact-content::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-sm);
}

.artifact-content::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

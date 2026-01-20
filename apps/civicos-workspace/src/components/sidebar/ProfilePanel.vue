<template>
  <div class="profile-panel">
    <!-- Loading State -->
    <div v-if="profileStore.loading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading profile...</p>
    </div>

    <!-- No Profile State -->
    <div v-else-if="!profileStore.profile" class="no-profile-state">
      <div class="avatar-placeholder">
        <img :src="getAvatarUrl('guest', 80)" alt="Guest avatar" />
      </div>
      <h3 class="no-profile-title">Welcome!</h3>
      <p class="no-profile-text">
        Create your profile to get personalized civic recommendations and draft better public comments.
      </p>
      <button class="btn-primary" @click="openProfileForm">
        Create Profile
      </button>
    </div>

    <!-- Profile Exists -->
    <div v-else class="profile-content">
      <!-- Avatar & Name -->
      <div class="profile-header">
        <img
          :src="getAvatarUrl(profileStore.profile.user_id, 80)"
          :alt="`${displayName}'s avatar`"
          class="profile-avatar"
        />
        <h3 class="profile-name">{{ displayName }}</h3>
        <p class="profile-jurisdiction">{{ jurisdictionName }}</p>
      </div>

      <!-- Profile Completeness -->
      <div class="completeness-section">
        <div class="completeness-header">
          <span class="completeness-label">Profile Completeness</span>
          <span class="completeness-percentage">{{ profileStore.profile.profile_completeness }}%</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: `${profileStore.profile.profile_completeness}%` }"
          ></div>
        </div>
        <p v-if="profileStore.profile.profile_completeness < 80" class="completeness-hint">
          Complete your profile for better recommendations
        </p>
      </div>

      <!-- Profile Stats -->
      <div class="profile-stats">
        <div v-if="profileStore.profile.years_in_area" class="stat-item">
          <span class="stat-label">Years in Area</span>
          <span class="stat-value">{{ profileStore.profile.years_in_area }}</span>
        </div>
        <div v-if="profileStore.profile.civic_interests?.length" class="stat-item">
          <span class="stat-label">Interests</span>
          <span class="stat-value">{{ profileStore.profile.civic_interests.length }} topics</span>
        </div>
        <div v-if="profileStore.profile.stakes?.length" class="stat-item">
          <span class="stat-label">Stakes</span>
          <span class="stat-value">{{ profileStore.profile.stakes.length }} selected</span>
        </div>
      </div>

      <!-- CivicOS Archetypes (Privacy-First) -->
      <div v-if="localArchetypes && localArchetypes.length > 0" class="archetypes-section">
        <div class="section-header">
          <h4 class="section-title">Your CivicOS Archetypes</h4>
          <span class="privacy-badge">🔒 Device only</span>
        </div>
        <div class="archetypes-list">
          <div
            v-for="archetype in localArchetypes"
            :key="archetype.id"
            class="archetype-item"
          >
            <component
              :is="getIconComponent(archetype.icon)"
              :size="18"
              class="archetype-icon"
              :style="{ color: archetype.iconColor }"
            />
            <div class="archetype-info">
              <div class="archetype-name">{{ archetype.name }}</div>
              <div class="archetype-rank">Rank #{{ archetype.rank }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="profile-actions">
        <button class="action-btn primary" @click="openProfileForm">
          Edit Profile
        </button>

        <!-- Data Management (compact) -->
        <div class="data-management-row">
          <!-- Help icon on the left -->
          <button
            class="help-icon-btn"
            @click="toggleDataHint"
            title="What's the difference?"
          >
            <HelpCircle :size="16" />
          </button>

          <!-- Buttons -->
          <div class="data-management">
            <button class="action-btn-compact secondary" @click="handleExportProfile" title="Export your political values (stored on this device only)">
              Export Values
            </button>
            <button class="action-btn-compact secondary" @click="handleImportProfile" title="Import values from a backup file">
              Import Values
            </button>
            <button class="action-btn-compact secondary" @click="handleExportData" title="Export your demographics and civic history from our server">
              Export History
            </button>
          </div>
        </div>

        <!-- Help hint (shown when clicked) -->
        <transition name="fade">
          <p v-if="showDataHint" class="data-hint">
            Values stay on device • History from server
          </p>
        </transition>

        <button class="action-btn danger" @click="handleDeleteAccount">
          Delete Account
        </button>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="errorMessage" class="error-message">
      {{ errorMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useProfileStore } from '@/stores/profile'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAvatars } from '@/composables/useAvatars'
import {
  loadArchetypesFromBrowser,
  exportProfile,
  importProfile,
  type ArchetypeMatch
} from '@/utils/archetypeMatching'
import * as LucideIcons from 'lucide-vue-next'
import { HelpCircle } from 'lucide-vue-next'

const profileStore = useProfileStore()
const workspaceStore = useWorkspaceStore()
const { getAvatarUrl } = useAvatars()

const errorMessage = ref('')
const localArchetypes = ref<ArchetypeMatch[] | null>(null)
const showDataHint = ref(false)

// Computed
const displayName = computed(() => {
  return profileStore.profile?.display_name || 'CivicOS User'
})

const jurisdictionName = computed(() => {
  if (!profileStore.profile?.jurisdiction_id) return ''
  // TODO: Look up jurisdiction name from workspace store
  return profileStore.profile.jurisdiction_id
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
})

// Lifecycle
onMounted(() => {
  // Profile is loaded in App.vue
  // Load archetypes from browser localStorage
  loadLocalArchetypes()
})

// Methods
function loadLocalArchetypes() {
  localArchetypes.value = loadArchetypesFromBrowser()
}

// Get Lucide icon component by name
function getIconComponent(iconName: string) {
  return (LucideIcons as any)[iconName] || LucideIcons.Circle
}

// Toggle data hint visibility
function toggleDataHint() {
  showDataHint.value = !showDataHint.value
}

// Methods
function openProfileForm() {
  workspaceStore.openArtifact({
    id: 'profile-form',
    type: 'profile-form',
    title: 'Edit Profile',
    data: {}
  })
}

async function handleExportData() {
  try {
    errorMessage.value = ''
    const data = await profileStore.exportData()

    // Create blob and download
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `civic-backend-export-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (error: any) {
    console.error('[ProfilePanel] Export error:', error)
    errorMessage.value = 'Failed to export data. Please try again.'
  }
}

function handleExportProfile() {
  try {
    errorMessage.value = ''

    // Export browser-only profile (includes archetypes)
    const blob = exportProfile()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `civic-profile-${new Date().toISOString().split('T')[0]}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    console.log('[Privacy] Profile exported (browser-only data)')
  } catch (error: any) {
    console.error('[ProfilePanel] Export profile error:', error)
    errorMessage.value = 'Failed to export profile. Please try again.'
  }
}

function handleImportProfile() {
  try {
    errorMessage.value = ''

    // Create file input
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/json'

    input.onchange = async (e: Event) => {
      try {
        const target = e.target as HTMLInputElement
        const file = target.files?.[0]
        if (!file) return

        const text = await file.text()
        importProfile(text)

        // Reload archetypes from localStorage
        loadLocalArchetypes()

        // Reload profile from store (in case demographics were updated)
        await profileStore.fetchProfile()

        alert('Profile imported successfully!')
        console.log('[Privacy] Profile imported (browser-only data)')
      } catch (error: any) {
        console.error('[ProfilePanel] Import profile error:', error)
        errorMessage.value = error.message || 'Failed to import profile. Please check the file format.'
      }
    }

    input.click()
  } catch (error: any) {
    console.error('[ProfilePanel] Import profile error:', error)
    errorMessage.value = 'Failed to import profile. Please try again.'
  }
}

async function handleDeleteAccount() {
  const confirmed = confirm(
    'Are you sure you want to delete your account? This action cannot be undone.\n\n' +
    'All your profile data, issues, and civic history will be permanently deleted.'
  )

  if (!confirmed) return

  // Double confirmation for safety
  const doubleConfirmed = confirm(
    'This is your final warning. Deleting your account is PERMANENT and IRREVERSIBLE.\n\n' +
    'Type your confirmation by clicking OK.'
  )

  if (!doubleConfirmed) return

  try {
    errorMessage.value = ''
    await profileStore.deleteAccount()
    alert('Your account has been deleted.')
  } catch (error: any) {
    console.error('[ProfilePanel] Delete error:', error)
    errorMessage.value = 'Failed to delete account. Please try again.'
  }
}
</script>

<style scoped>
.profile-panel {
  display: flex;
  flex-direction: column;
  background: var(--background);
  padding: 0;
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl) var(--space-md);
  gap: var(--space-md);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-state p {
  font-size: 13px;
  color: var(--text-secondary);
}

/* No Profile State */
.no-profile-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-xl) var(--space-md);
  gap: var(--space-md);
  text-align: center;
}

.avatar-placeholder {
  margin-bottom: var(--space-sm);
}

.avatar-placeholder img {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 2px solid var(--border);
}

.no-profile-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.no-profile-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

/* Profile Content */
.profile-content {
  display: flex;
  flex-direction: column;
  padding: 0;
}

/* Profile Header */
.profile-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
}

.profile-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 3px solid var(--primary);
}

.profile-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.profile-jurisdiction {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Completeness Section */
.completeness-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
}

.completeness-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.completeness-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.completeness-percentage {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
}

.progress-bar {
  height: 6px;
  background: var(--background-secondary);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary);
  transition: width var(--transition-base);
}

.completeness-hint {
  font-size: 12px;
  color: var(--text-secondary);
  font-style: italic;
  margin: 0;
}

/* Profile Stats */
.profile-stats {
  display: flex;
  flex-direction: column;
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.stat-item:not(:last-child) {
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Archetypes Section */
.archetypes-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-bottom: 1px solid var(--border);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.privacy-badge {
  font-size: 10px;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.04);
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.archetypes-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.archetype-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  transition: background 0.12s ease;
}

.archetype-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.archetype-icon {
  flex-shrink: 0;
  opacity: 0.8;
}

.archetype-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.archetype-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.archetype-rank {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Actions */
.profile-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--space-md);
}

.data-management-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.data-management {
  display: flex;
  gap: 6px;
  flex: 1;
}

.help-icon-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 6px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.7;
  transition: all 0.12s ease;
  flex-shrink: 0;
}

.help-icon-btn:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.08);
  color: var(--primary);
}

.data-hint {
  font-size: 11px;
  color: var(--text-secondary);
  text-align: center;
  margin: 6px 0 0 0;
  opacity: 0.8;
  font-style: italic;
  line-height: 1.3;
}

/* Fade transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.action-btn-compact {
  flex: 1;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  border: 1px solid transparent;
  text-align: center;
  white-space: nowrap;
}

.action-btn-compact.secondary {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}

.action-btn-compact.secondary:hover {
  background: rgba(0, 0, 0, 0.04);
  border-color: var(--text-secondary);
}

.action-btn {
  width: 100%;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  border: 1px solid transparent;
  text-align: center;
}

.action-btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.action-btn.primary:hover {
  background: #1c6fa0;
  transform: translateY(-1px);
}

.action-btn.secondary {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}

.action-btn.secondary:hover {
  background: rgba(0, 0, 0, 0.04);
  border-color: var(--text-secondary);
}

.action-btn.danger {
  background: transparent;
  color: var(--accent-red);
  border-color: var(--accent-red);
}

.action-btn.danger:hover {
  background: var(--accent-red);
  color: white;
}

.btn-primary {
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s ease;
  background: var(--primary);
  color: white;
  border: 1px solid var(--primary);
}

.btn-primary:hover {
  background: #1c6fa0;
  transform: translateY(-1px);
}

/* Error Message */
.error-message {
  padding: 10px var(--space-md);
  margin: var(--space-md);
  background: #ffeaea;
  color: var(--accent-red);
  border-left: 3px solid var(--accent-red);
  font-size: 12px;
  line-height: 1.4;
}
</style>

<template>
  <div class="artifact-wrapper">
    <div class="artifact-form-container">
      <!-- Header -->
      <div class="artifact-header">
        <h2 class="artifact-title">Your Profile</h2>
        <p class="artifact-subtitle">
          Help us personalize your civic experience by sharing more about yourself.
        </p>
        <!-- Profile Completeness -->
        <div v-if="profileStore.profile" class="completeness-indicator">
          <div class="completeness-label">
            Profile Completeness: {{ profileStore.profile.profile_completeness }}%
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: `${profileStore.profile.profile_completeness}%` }"
            ></div>
          </div>
        </div>
      </div>

      <!-- Privacy Notice (if from onboarding) -->
      <div v-if="props.artifact?.data?.fromOnboarding" class="privacy-notice-banner">
        <div class="notice-icon">🔒</div>
        <div class="notice-content">
          <div class="notice-title">Your CivicOS Values Are Saved</div>
          <div class="notice-text">
            Your political preferences are stored on <strong>this device only</strong> and will never be sent to our servers.
            This form only collects basic demographics to help personalize your experience.
          </div>
        </div>
      </div>

      <!-- Form Body -->
      <form @submit.prevent="handleSubmit" class="artifact-form-body">
        <!-- Display Name -->
        <div class="form-group">
          <label for="display_name" class="form-label">
            Display Name
            <span class="optional">(optional)</span>
          </label>
          <input
            id="display_name"
            v-model="formData.display_name"
            type="text"
            class="form-input"
            placeholder="How should we address you?"
            maxlength="100"
          />
          <p class="form-hint">This name will be used throughout the app</p>
        </div>

        <!-- Stakes (Multi-select) -->
        <div class="form-group">
          <label class="form-label">
            Your Stakes in the Community
            <span class="optional">(optional)</span>
          </label>
          <div class="checkbox-group">
            <label class="checkbox-item" v-for="stake in availableStakes" :key="stake.value">
              <input
                type="checkbox"
                :value="stake.value"
                v-model="formData.stakes"
              />
              <span>{{ stake.label }}</span>
            </label>
          </div>
          <p class="form-hint">Select all that apply</p>
        </div>

        <!-- Years in Area -->
        <div class="form-group">
          <label for="years_in_area" class="form-label">
            Years in Area
            <span class="optional">(optional)</span>
          </label>
          <input
            id="years_in_area"
            v-model.number="formData.years_in_area"
            type="number"
            class="form-input"
            placeholder="How long have you lived here?"
            min="0"
            max="100"
          />
        </div>

        <!-- Jurisdiction -->
        <div class="form-group">
          <label for="jurisdiction_id" class="form-label">
            Primary City
            <span class="required">*</span>
          </label>
          <select
            id="jurisdiction_id"
            v-model="formData.jurisdiction_id"
            class="form-select"
            required
          >
            <option value="">Select your city...</option>
            <option
              v-for="jurisdiction in availableJurisdictions"
              :key="jurisdiction.id"
              :value="jurisdiction.id"
            >
              {{ jurisdiction.name }}
            </option>
          </select>
          <p class="form-hint">Your primary city for civic engagement</p>
        </div>

        <!-- Values Explorer Callout (Optional) -->
        <div class="values-explorer-callout">
          <div class="callout-header">
            <span class="callout-icon">💡</span>
            <span class="callout-title">Get Personalized Recommendations</span>
          </div>
          <p class="callout-text">
            Not sure where you stand on civic issues? Swipe through real decisions to discover your political values.
          </p>
          <button
            type="button"
            class="btn-values-explorer"
            @click="openValuesExplorer"
          >
            Explore Your Values
          </button>

          <!-- Display discovered civic interests -->
          <div v-if="formData.civic_interests.length > 0" class="discovered-interests">
            <div class="discovered-header">
              <span class="icon">✨</span>
              <span class="text">Your CivicOS Values</span>
            </div>
            <div class="interest-tags">
              <span
                v-for="interest in formData.civic_interests"
                :key="interest"
                class="interest-tag"
              >
                {{ formatInterest(interest) }}
              </span>
            </div>
            <p class="discovered-hint">
              These values were discovered from your swipe choices and will help personalize your experience.
            </p>
          </div>
        </div>

        <!-- District -->
        <div class="form-group">
          <label for="district" class="form-label">
            District
            <span class="optional">(optional)</span>
          </label>
          <input
            id="district"
            v-model="formData.district"
            type="text"
            class="form-input"
            placeholder="e.g., District 5, Ward 3"
            maxlength="100"
          />
        </div>

        <!-- Neighborhood -->
        <div class="form-group">
          <label for="neighborhood" class="form-label">
            Neighborhood
            <span class="optional">(optional)</span>
          </label>
          <input
            id="neighborhood"
            v-model="formData.neighborhood"
            type="text"
            class="form-input"
            placeholder="e.g., Downtown, North Berkeley"
            maxlength="100"
          />
        </div>

        <!-- Expertise -->
        <div class="form-group">
          <label for="expertise" class="form-label">
            Your Expertise
            <span class="optional">(optional)</span>
          </label>
          <textarea
            id="expertise"
            v-model="formData.expertise"
            class="form-textarea"
            placeholder="What expertise do you bring? (e.g., urban planning, environmental science, community organizing)"
            rows="3"
            maxlength="500"
          />
          <div class="char-count">
            {{ formData.expertise?.length || 0 }} / 500
          </div>
        </div>

        <!-- Error Summary -->
        <div v-if="submitError" class="submit-error">
          <span class="icon">⚠️</span>
          {{ submitError }}
        </div>

        <!-- Success Message -->
        <div v-if="submitSuccess" class="submit-success">
          <span class="icon">✅</span>
          {{ submitSuccess }}
        </div>

        <!-- Actions -->
        <div class="form-actions">
          <button
            type="button"
            class="btn-secondary"
            @click="$emit('close')"
            :disabled="isSubmitting"
          >
            Cancel
          </button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="isSubmitting || !isFormValid"
          >
            <span v-if="isSubmitting">
              <span class="spinner">⏳</span>
              Saving...
            </span>
            <span v-else>
              Save Profile
            </span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/services/api'
import { useProfileStore } from '@/stores/profile'
import { useWorkspaceStore } from '@/stores/workspace'
import type { Jurisdiction } from '@/types/civic'

// Props for artifact data
const props = withDefaults(defineProps<{
  artifact?: {
    id: string
    type: string
    title: string
    data?: {
      fromOnboarding?: boolean
      [key: string]: any
    }
  }
}>(), {
  artifact: undefined
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved'): void
}>()

const workspaceStore = useWorkspaceStore()

const profileStore = useProfileStore()

// Debug logging
console.log('[ProfileForm] Mounted with artifact:', props.artifact)
console.log('[ProfileForm] Artifact data:', props.artifact?.data)
console.log('[ProfileForm] From onboarding?', props.artifact?.data?.fromOnboarding)
console.log('[ProfileForm] Full artifact structure:', JSON.stringify(props.artifact, null, 2))

// Available options
const availableStakes = [
  { value: 'homeowner', label: 'Homeowner' },
  { value: 'renter', label: 'Renter' },
  { value: 'parent', label: 'Parent' },
  { value: 'business_owner', label: 'Business Owner' },
  { value: 'activist', label: 'Activist' }
]

// Form data
interface ProfileFormData {
  display_name: string | null
  stakes: string[]
  years_in_area: number | null
  district: string | null
  neighborhood: string | null
  jurisdiction_id: string
  expertise: string | null
  civic_interests: string[]
}

const formData = ref<ProfileFormData>({
  display_name: null,
  stakes: [],
  years_in_area: null,
  district: null,
  neighborhood: null,
  jurisdiction_id: '',
  expertise: null,
  civic_interests: []
})

// State
const availableJurisdictions = ref<Jurisdiction[]>([])
const isSubmitting = ref(false)
const submitError = ref('')
const submitSuccess = ref('')

// Computed
const isFormValid = computed(() => {
  return formData.value.jurisdiction_id !== ''
})

// Lifecycle
onMounted(async () => {
  await loadJurisdictions()

  // Pre-fill form if profile exists
  if (profileStore.profile) {
    formData.value = {
      display_name: profileStore.profile.display_name,
      stakes: profileStore.profile.stakes || [],
      years_in_area: profileStore.profile.years_in_area,
      district: profileStore.profile.district,
      neighborhood: profileStore.profile.neighborhood,
      jurisdiction_id: profileStore.profile.jurisdiction_id,
      expertise: profileStore.profile.expertise,
      civic_interests: profileStore.profile.civic_interests || []
    }
  } else {
    // No saved profile - check for draft in Pinia store
    if (profileStore.profileFormDraft) {
      console.log('[ProfileForm] Restoring draft from Pinia store:', profileStore.profileFormDraft)
      formData.value = profileStore.profileFormDraft as ProfileFormData
    }
  }

  // Check if there are discovered interests waiting to be merged
  if (profileStore.discoveredInterests && profileStore.discoveredInterests.length > 0) {
    console.log('[ProfileForm] Merging discovered interests on mount:', profileStore.discoveredInterests)
    formData.value.civic_interests = profileStore.discoveredInterests
    submitSuccess.value = `Discovered ${profileStore.discoveredInterests.length} values! Review and save your profile below.`

    // Clear success message after 5 seconds
    setTimeout(() => {
      submitSuccess.value = ''
    }, 5000)

    // Clear discovered interests from store
    profileStore.clearDiscoveredInterests()
  }
})

// Watch for discovered interests from SwipeOnboarding artifact
watch(
  () => profileStore.discoveredInterests,
  (newInterests) => {
    if (newInterests && newInterests.length > 0) {
      console.log('[ProfileForm] Received discovered interests:', newInterests)
      formData.value.civic_interests = newInterests
      submitSuccess.value = `Discovered ${newInterests.length} values! Review and save your profile below.`

      // Clear success message after 5 seconds
      setTimeout(() => {
        submitSuccess.value = ''
      }, 5000)

      // Clear discovered interests from store
      profileStore.clearDiscoveredInterests()
    }
  }
)

// Watch formData and save draft to Pinia store
watch(
  formData,
  (newData) => {
    // Only save draft if no profile exists yet
    if (!profileStore.profile) {
      console.log('[ProfileForm] Saving draft to Pinia store')
      profileStore.saveProfileFormDraft(newData)
    }
  },
  { deep: true }
)

// Methods
async function loadJurisdictions() {
  try {
    const jurisdictions = await api.getJurisdictions()
    availableJurisdictions.value = jurisdictions.filter(
      (j: Jurisdiction) => j.event_count && j.event_count > 0
    )
  } catch (error) {
    console.error('[ProfileForm] Error loading jurisdictions:', error)
    submitError.value = 'Failed to load jurisdictions. Please try again.'
  }
}

function formatInterest(interest: string): string {
  // Convert interest slug to readable format
  return interest
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function openValuesExplorer() {
  // Open SwipeOnboarding as an artifact
  workspaceStore.openArtifact({
    id: 'values-explorer',
    type: 'values-explorer',
    title: 'Explore Your Political Values',
    data: {}
  })
}

async function handleSubmit() {
  submitError.value = ''
  submitSuccess.value = ''

  if (!formData.value.jurisdiction_id) {
    submitError.value = 'Please select your primary city'
    return
  }

  isSubmitting.value = true

  try {
    // Prepare payload with camelCase field names (backend expects camelCase)
    const payload: any = {
      jurisdictionId: formData.value.jurisdiction_id
    }

    // Add optional fields if provided
    if (formData.value.display_name?.trim()) {
      payload.displayName = formData.value.display_name.trim()
    }
    if (formData.value.stakes.length > 0) {
      payload.stakes = formData.value.stakes
    }
    if (formData.value.years_in_area !== null && formData.value.years_in_area >= 0) {
      payload.yearsInArea = formData.value.years_in_area
    }
    if (formData.value.district?.trim()) {
      payload.district = formData.value.district.trim()
    }
    if (formData.value.neighborhood?.trim()) {
      payload.neighborhood = formData.value.neighborhood.trim()
    }
    if (formData.value.expertise?.trim()) {
      payload.expertise = formData.value.expertise.trim()
    }
    if (formData.value.civic_interests.length > 0) {
      payload.civicInterests = formData.value.civic_interests
    }

    console.log('[ProfileForm] Saving profile (camelCase):', payload)

    await profileStore.createOrUpdateProfile(payload)

    // Clear draft from Pinia store after successful save
    profileStore.clearProfileFormDraft()
    console.log('[ProfileForm] Cleared draft from Pinia store after successful save')

    submitSuccess.value = 'Profile saved successfully!'
    emit('saved')

    // Auto-close after 1.5 seconds
    setTimeout(() => {
      emit('close')
    }, 1500)
  } catch (error: any) {
    console.error('[ProfileForm] Error saving profile:', error)
    submitError.value = error.message || 'Failed to save profile. Please try again.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
/* Artifact mode styles */
.artifact-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.artifact-form-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--background);
}

.artifact-header {
  padding: var(--space-xl);
  border-bottom: 1px solid var(--border);
  background: var(--background-secondary);
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
  margin: 0 0 var(--space-md) 0;
  line-height: 1.4;
}

/* Profile Completeness */
.completeness-indicator {
  margin-top: var(--space-md);
}

.completeness-label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}

.progress-bar {
  height: 8px;
  background: var(--background);
  border-radius: var(--radius-pill);
  overflow: hidden;
  border: 1px solid var(--border);
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-green) 0%, var(--primary) 100%);
  transition: width var(--transition-base);
}

/* Privacy Notice Banner */
.privacy-notice-banner {
  display: flex;
  gap: var(--space-md);
  padding: var(--space-lg);
  margin: var(--space-lg) var(--space-xl) 0 var(--space-xl);
  background: rgba(38, 139, 210, 0.1);
  border: 1px solid var(--primary);
  border-radius: var(--radius-lg);
}

.notice-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.notice-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.notice-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--primary);
}

.notice-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
}

.notice-text strong {
  color: var(--text-primary);
  font-weight: 600;
}

/* Form Body */
.artifact-form-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xl);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.form-label {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-primary);
}

.required {
  color: var(--accent-red);
  margin-left: var(--space-xs);
}

.optional {
  font-weight: 400;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.form-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-style: italic;
}

/* Input Fields */
.form-input,
.form-textarea,
.form-select {
  width: 100%;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--background-extra-light);
  color: var(--text-primary);
  font-size: var(--font-size-base);
  font-family: var(--font-family);
  transition: all var(--transition-fast);
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(38, 139, 210, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
  line-height: 1.5;
}

.char-count {
  text-align: right;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* Checkbox Group */
.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  background: var(--background-extra-light);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  cursor: pointer;
  padding: var(--space-xs);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.checkbox-item:hover {
  background: var(--hover-bg);
}

.checkbox-item input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--primary);
}

.checkbox-item span {
  font-size: var(--font-size-base);
  color: var(--text-primary);
}

/* Messages */
.submit-error,
.submit-success {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.submit-error {
  background: #ffeaea;
  color: var(--accent-red);
  border: 1px solid var(--accent-red);
}

.submit-success {
  background: #e8f5e9;
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
}

/* Form Actions */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding-top: var(--space-md);
  border-top: 1px solid var(--border);
}

.btn-primary,
.btn-secondary {
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.btn-primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.btn-primary:hover:not(:disabled) {
  background: #1c6fa0;
  border-color: #1c6fa0;
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--background-secondary);
  color: var(--text-primary);
  border-color: var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--text-secondary);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.icon {
  font-style: normal;
}

/* Values Explorer Callout */
.values-explorer-callout {
  padding: var(--space-lg);
  background: var(--background-extra-light);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.callout-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.callout-icon {
  font-size: 20px;
}

.callout-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--text-primary);
}

.callout-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
}

.btn-values-explorer {
  padding: var(--space-sm) var(--space-lg);
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  align-self: flex-start;
}

.btn-values-explorer:hover {
  background: #1c6fa0;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(38, 139, 210, 0.2);
}

/* Discovered Interests Display */
.discovered-interests {
  margin-top: var(--space-md);
  padding: var(--space-md);
  background: var(--background);
  border: 2px solid var(--primary);
  border-radius: var(--radius-base);
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.discovered-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.discovered-header .icon {
  font-size: 18px;
}

.discovered-header .text {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--primary);
}

.interest-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.interest-tag {
  display: inline-block;
  padding: var(--space-xs) var(--space-md);
  background: var(--primary);
  color: white;
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.discovered-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.4;
}

.values-discovered {
  font-size: var(--font-size-sm);
  color: var(--accent-green);
  font-weight: 500;
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

/* Scrollbar */
.artifact-form-body::-webkit-scrollbar {
  width: 8px;
}

.artifact-form-body::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.artifact-form-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-sm);
}

.artifact-form-body::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>

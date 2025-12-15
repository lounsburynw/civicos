<template>
  <div class="structured-input-form">
    <!-- Position Selector -->
    <div class="form-section">
      <label class="section-label">
        Your Position
        <span class="required">*</span>
      </label>
      <PositionSelector v-model="position" />
    </div>

    <!-- Key Concern -->
    <div class="form-section">
      <label class="section-label">
        Key Concern
        <span class="required">*</span>
      </label>
      <KeyConcernInput
        v-model="keyConcern"
        :min-chars="20"
        :max-chars="300"
      />
    </div>

    <!-- Personal Context (collapsible) -->
    <div class="form-section">
      <button
        class="collapsible-header"
        @click="personalContextExpanded = !personalContextExpanded"
      >
        <span class="section-label">
          Personal Context
          <span v-if="!isLoadingProfile && (personalContext.stakes?.length || personalContext.yearsInArea)" class="auto-filled-badge">
            Auto-filled
          </span>
          <span v-else class="optional-badge">Optional</span>
        </span>
        <ChevronDown
          :size="18"
          :class="['chevron', { expanded: personalContextExpanded }]"
        />
      </button>

      <transition name="expand">
        <div v-show="personalContextExpanded" class="collapsible-content">
          <div v-if="isLoadingProfile" class="loading-placeholder">
            <Loader :size="16" class="spinner" />
            <span>Loading your profile...</span>
          </div>
          <PersonalContextForm v-else v-model="personalContext" />
        </div>
      </transition>
    </div>

    <!-- Generate Button -->
    <button
      @click="handleGenerate"
      :disabled="!canGenerate || isGenerating"
      class="btn-primary btn-large"
    >
      <Sparkles v-if="!isGenerating" :size="18" />
      <Loader v-else :size="18" class="spinner" />
      <span>{{ isGenerating ? 'Generating...' : 'Generate AI Draft' }}</span>
    </button>

    <!-- Error Message -->
    <div v-if="errorMessage" class="error-banner">
      <AlertCircle :size="16" />
      <span>{{ errorMessage }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ChevronDown, Sparkles, Loader, AlertCircle } from 'lucide-vue-next'
import PositionSelector from './PositionSelector.vue'
import KeyConcernInput from './KeyConcernInput.vue'
import PersonalContextForm from './PersonalContextForm.vue'
import { api } from '@/services/api'
import { useUserStore } from '@/stores/user'

type Position = 'support' | 'oppose' | 'neutral' | 'questions'

interface PersonalContext {
  stakes?: string[]
  yearsInArea?: number
  district?: string
  expertise?: string
}

export interface StructuredInput {
  position: Position | null
  keyConcern: string
  personalContext: PersonalContext
}

const emit = defineEmits<{
  generate: [input: StructuredInput]
}>()

const userStore = useUserStore()

const position = ref<Position | null>(null)
const keyConcern = ref('')
const personalContext = ref<PersonalContext>({})
const personalContextExpanded = ref(false)
const isGenerating = ref(false)
const errorMessage = ref('')
const isLoadingProfile = ref(true)

const canGenerate = computed(() => {
  return (
    position.value !== null &&
    keyConcern.value.length >= 20 &&
    keyConcern.value.length <= 300
  )
})

// Map archetype to stakes
function mapArchetypeToStakes(archetypeName: string): string[] {
  const lowerName = archetypeName.toLowerCase()
  const stakes: string[] = []

  // Map archetype characteristics to stakes
  if (lowerName.includes('parent') || lowerName.includes('guardian')) {
    stakes.push('parent')
  }
  if (lowerName.includes('homeowner') || lowerName.includes('property')) {
    stakes.push('homeowner')
  }
  if (lowerName.includes('renter') || lowerName.includes('tenant')) {
    stakes.push('renter')
  }
  if (lowerName.includes('business') || lowerName.includes('entrepreneur')) {
    stakes.push('business_owner')
  }
  if (lowerName.includes('educator') || lowerName.includes('teacher')) {
    stakes.push('educator')
  }
  if (lowerName.includes('caregiver') || lowerName.includes('care')) {
    stakes.push('caregiver')
  }

  // Default to community member if no specific stake matched
  if (stakes.length === 0) {
    stakes.push('community_member')
  }

  return stakes
}

// Load user profile and archetype data
async function loadProfile() {
  try {
    isLoadingProfile.value = true

    // Try to fetch profile from backend
    const profile = await api.getUserProfile()

    if (profile.user_id) {
      // Use profile data
      personalContext.value = {
        stakes: profile.stakes || [],
        yearsInArea: profile.years_in_area,
        district: profile.district || userStore.cityName || '',
        expertise: profile.expertise || ''
      }
      console.log('[StructuredInputForm] Loaded profile:', personalContext.value)
    } else {
      // No profile - use archetype data
      const primaryArchetype = userStore.primaryArchetype
      if (primaryArchetype) {
        const inferredStakes = mapArchetypeToStakes(primaryArchetype.name)
        personalContext.value = {
          stakes: inferredStakes,
          district: userStore.cityName || ''
        }
        console.log('[StructuredInputForm] Inferred from archetype:', {
          archetype: primaryArchetype.name,
          stakes: inferredStakes
        })
      } else {
        // Fallback - use location only
        personalContext.value = {
          district: userStore.cityName || ''
        }
      }
    }

    // Auto-expand if we have data
    if (personalContext.value.stakes?.length || personalContext.value.yearsInArea || personalContext.value.expertise) {
      personalContextExpanded.value = true
    }
  } catch (error) {
    console.error('[StructuredInputForm] Failed to load profile:', error)
    // Use archetype fallback on error
    const primaryArchetype = userStore.primaryArchetype
    if (primaryArchetype) {
      personalContext.value = {
        stakes: mapArchetypeToStakes(primaryArchetype.name),
        district: userStore.cityName || ''
      }
    }
  } finally {
    isLoadingProfile.value = false
  }
}

const handleGenerate = () => {
  if (!canGenerate.value) {
    errorMessage.value = 'Please select a position and provide a key concern (20-300 characters)'
    return
  }

  errorMessage.value = ''
  isGenerating.value = true

  emit('generate', {
    position: position.value!,
    keyConcern: keyConcern.value,
    personalContext: personalContext.value
  })

  // Reset generating state after a delay (will be set back by parent on response)
  setTimeout(() => {
    isGenerating.value = false
  }, 10000)
}

// Load profile on mount
onMounted(() => {
  loadProfile()
})

// Expose method to reset generating state
defineExpose({
  setGenerating: (value: boolean) => {
    isGenerating.value = value
  },
  setError: (message: string) => {
    errorMessage.value = message
    isGenerating.value = false
  }
})
</script>

<style scoped>
.structured-input-form {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.required {
  color: var(--accent-red);
  margin-left: 2px;
}

.auto-filled-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.optional-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(147, 161, 161, 0.15);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Collapsible Section */
.collapsible-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 0;
  background: none;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.collapsible-header:hover {
  opacity: 0.8;
}

.chevron {
  color: var(--text-secondary);
  transition: transform 0.2s ease;
}

.chevron.expanded {
  transform: rotate(180deg);
}

.collapsible-content {
  padding-top: 12px;
}

.loading-placeholder {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px;
  color: var(--text-secondary);
  font-size: 14px;
  font-style: italic;
}

/* Expand Transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.expand-enter-to,
.expand-leave-from {
  opacity: 1;
  max-height: 600px;
}

/* Generate Button */
.btn-primary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 24px;
  border: none;
  border-radius: 8px;
  background: var(--primary);
  color: var(--surface-default);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(38, 139, 210, 0.3);
}

.btn-primary:active:not(:disabled) {
  transform: translateY(0);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-large {
  padding: 16px 32px;
  font-size: 16px;
}

.spinner {
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

/* Error Banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 6px;
  background: rgba(220, 50, 47, 0.1);
  border: 1px solid var(--accent-red);
  color: var(--accent-red);
  font-size: 14px;
  font-weight: 500;
}
</style>

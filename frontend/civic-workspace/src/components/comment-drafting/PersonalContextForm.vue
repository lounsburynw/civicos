<template>
  <div class="personal-context-form">
    <!-- Stakes -->
    <div class="form-group">
      <label class="group-label">Your Stakes</label>
      <div class="stakes-grid">
        <button
          v-for="stake in stakeOptions"
          :key="stake.value"
          :class="['stake-chip', { active: isStakeSelected(stake.value) }]"
          @click="toggleStake(stake.value)"
        >
          <component :is="stake.icon" :size="16" />
          <span>{{ stake.label }}</span>
        </button>
      </div>
    </div>

    <!-- Residency -->
    <div class="form-group">
      <label class="group-label">Residency (Optional)</label>
      <div class="residency-inputs">
        <div class="input-with-label">
          <input
            type="number"
            :value="localContext.yearsInArea"
            @input="updateYearsInArea"
            placeholder="Years in area"
            min="0"
            max="100"
          />
          <span class="input-suffix">years</span>
        </div>
        <input
          type="text"
          :value="localContext.district"
          @input="updateDistrict"
          placeholder="District or neighborhood"
        />
      </div>
    </div>

    <!-- Expertise -->
    <div class="form-group">
      <label class="group-label">Professional Expertise (Optional)</label>
      <input
        type="text"
        :value="localContext.expertise"
        @input="updateExpertise"
        placeholder="e.g., Urban planner, Teacher, Small business owner"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Home, Baby, Briefcase, Users, GraduationCap, Heart } from 'lucide-vue-next'

interface PersonalContext {
  stakes?: string[]
  yearsInArea?: number
  district?: string
  expertise?: string
}

const props = defineProps<{
  modelValue: PersonalContext
}>()

const emit = defineEmits<{
  'update:modelValue': [value: PersonalContext]
}>()

// Initialize with provided values
const localContext = ref<PersonalContext>({
  stakes: props.modelValue.stakes || [],
  yearsInArea: props.modelValue.yearsInArea,
  district: props.modelValue.district || '',
  expertise: props.modelValue.expertise || ''
})

// Watch for external changes (e.g., when profile loads)
watch(() => props.modelValue, (newValue) => {
  // Only update if values actually changed (avoid overwriting user edits)
  if (JSON.stringify(newValue) !== JSON.stringify(localContext.value)) {
    localContext.value = {
      stakes: newValue.stakes || [],
      yearsInArea: newValue.yearsInArea,
      district: newValue.district || '',
      expertise: newValue.expertise || ''
    }
  }
}, { deep: true })

const stakeOptions = [
  { value: 'homeowner', label: 'Homeowner', icon: Home },
  { value: 'renter', label: 'Renter', icon: Home },
  { value: 'parent', label: 'Parent', icon: Baby },
  { value: 'business_owner', label: 'Business Owner', icon: Briefcase },
  { value: 'community_member', label: 'Community Member', icon: Users },
  { value: 'educator', label: 'Educator', icon: GraduationCap },
  { value: 'caregiver', label: 'Caregiver', icon: Heart }
]

const isStakeSelected = (stake: string) => {
  return localContext.value.stakes?.includes(stake) || false
}

const toggleStake = (stake: string) => {
  const stakes = localContext.value.stakes || []
  const index = stakes.indexOf(stake)

  if (index > -1) {
    stakes.splice(index, 1)
  } else {
    stakes.push(stake)
  }

  localContext.value.stakes = stakes
  emitUpdate()
}

const updateYearsInArea = (event: Event) => {
  const value = (event.target as HTMLInputElement).value
  localContext.value.yearsInArea = value ? parseInt(value) : undefined
  emitUpdate()
}

const updateDistrict = (event: Event) => {
  const value = (event.target as HTMLInputElement).value
  localContext.value.district = value || undefined
  emitUpdate()
}

const updateExpertise = (event: Event) => {
  const value = (event.target as HTMLInputElement).value
  localContext.value.expertise = value || undefined
  emitUpdate()
}

const emitUpdate = () => {
  emit('update:modelValue', { ...localContext.value })
}
</script>

<style scoped>
.personal-context-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Stakes Grid */
.stakes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}

.stake-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border: 1.5px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--surface-default);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.stake-chip:hover {
  border-color: var(--border-default);
  background: var(--surface-hover);
}

.stake-chip.active {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.1);
  color: var(--primary);
  font-weight: 600;
}

/* Residency Inputs */
.residency-inputs {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 10px;
}

.input-with-label {
  position: relative;
  display: flex;
  align-items: center;
}

.input-with-label input {
  width: 100%;
  padding-right: 50px;
}

.input-suffix {
  position: absolute;
  right: 12px;
  color: var(--text-tertiary);
  font-size: 13px;
  pointer-events: none;
}

/* Input Styles */
input[type="text"],
input[type="number"] {
  width: 100%;
  padding: 10px 12px;
  border: 1.5px solid var(--border-default);
  border-radius: 6px;
  background: var(--surface-default);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 14px;
  transition: all 0.2s ease;
}

input:focus {
  outline: none;
  border-color: var(--primary);
  background: var(--surface-hover);
}

input::placeholder {
  color: var(--text-tertiary);
}

/* Remove number input spinners */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

input[type="number"] {
  -moz-appearance: textfield;
}

@media (max-width: 600px) {
  .residency-inputs {
    grid-template-columns: 1fr;
  }

  .stakes-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}
</style>

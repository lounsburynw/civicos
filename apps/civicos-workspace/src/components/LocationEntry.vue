<template>
  <div class="location-entry-overlay">
    <div class="location-entry-modal">
      <!-- Header -->
      <div class="modal-header">
        <h1 class="modal-title">Welcome to CivicOS</h1>
        <p class="modal-subtitle">
          Enter your address to see civic meetings and opportunities in your area
        </p>
      </div>

      <!-- Form -->
      <form @submit.prevent="handleSubmit" class="modal-body">
        <div class="form-group">
          <label for="address" class="form-label">
            Your Address
            <span class="required">*</span>
          </label>
          <input
            id="address"
            v-model="address"
            type="text"
            class="address-input"
            placeholder="123 Main St, Oakland, CA"
            required
            :disabled="loading"
            autofocus
          />
          <p class="help-text">
            Example: 1 Frank H Ogawa Plaza, Oakland, CA
          </p>
        </div>

        <!-- Error Message -->
        <div v-if="errorMessage" class="error-message">
          <span class="icon">⚠️</span>
          {{ errorMessage }}
        </div>

        <!-- Validation Warning (if distance is far but not blocking) -->
        <div v-if="validationWarning" class="warning-message">
          <span class="icon">⚠️</span>
          {{ validationWarning }}
        </div>

        <!-- Submit Button -->
        <button
          type="submit"
          class="submit-btn"
          :disabled="loading || !address.trim()"
        >
          {{ loading ? 'Locating...' : 'Set Location' }}
        </button>

        <!-- Privacy Note -->
        <p class="privacy-note">
          🔒 We only store your city/county, not your full address
        </p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useUserStore } from '@/stores/user'
import { api } from '@/services/api'
import type { SetLocationResponse } from '@/types/civic'

const userStore = useUserStore()
const address = ref('')
const loading = ref(false)
const errorMessage = ref('')
const validationWarning = ref('')

const emit = defineEmits<{
  (e: 'location-set'): void
}>()

async function handleSubmit() {
  if (!address.value.trim()) {
    errorMessage.value = 'Please enter an address'
    return
  }

  loading.value = true
  errorMessage.value = ''
  validationWarning.value = ''

  try {
    const response: SetLocationResponse = await api.setUserLocation(
      userStore.userId,
      address.value.trim()
    )

    // Check validation result
    if (!response.validation.valid) {
      // Show validation warning but still allow location to be set
      validationWarning.value = `${response.validation.reason}. We've still set your location to ${response.location.city}.`
    }

    // Set location in store
    userStore.setLocation(response.location)

    // Clear form
    address.value = ''

    // Emit event to close modal
    emit('location-set')
  } catch (error: any) {
    console.error('Failed to set location:', error)
    errorMessage.value = error.message || 'Failed to geocode address. Please check the address and try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.location-entry-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(7, 54, 66, 0.7); /* Solarized base02 with opacity */
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.location-entry-modal {
  background: var(--background);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.modal-header {
  padding: var(--space-xl);
  text-align: center;
  border-bottom: 1px solid var(--border);
}

.modal-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--primary);
  margin-bottom: var(--space-sm);
}

.modal-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.6;
}

.modal-body {
  padding: var(--space-xl);
}

.form-group {
  margin-bottom: var(--space-md);
}

.form-label {
  display: block;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
}

.required {
  color: var(--accent-red);
  margin-left: var(--space-xs);
}

.address-input {
  width: 100%;
  padding: var(--space-md);
  font-size: var(--font-size-base);
  font-family: var(--font-family);
  color: var(--text-primary);
  background: var(--background);
  border: 2px solid var(--border);
  border-radius: var(--radius-base);
  transition: var(--transition-fast);
}

.address-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(38, 139, 210, 0.1);
}

.address-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.help-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--space-xs);
}

.error-message {
  padding: var(--space-md);
  background: rgba(220, 50, 47, 0.1);
  border: 1px solid var(--accent-red);
  border-radius: var(--radius-base);
  color: var(--accent-red);
  font-size: var(--font-size-sm);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.warning-message {
  padding: var(--space-md);
  background: rgba(203, 75, 22, 0.1);
  border: 1px solid var(--accent-orange);
  border-radius: var(--radius-base);
  color: var(--accent-orange);
  font-size: var(--font-size-sm);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.submit-btn {
  width: 100%;
  padding: var(--space-md);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: white;
  background: var(--primary);
  border: none;
  border-radius: var(--radius-base);
  cursor: pointer;
  transition: var(--transition-fast);
  margin-bottom: var(--space-md);
}

.submit-btn:hover:not(:disabled) {
  background: #1d6fa5;
  transform: translateY(-1px);
  box-shadow: var(--shadow-subtle);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.privacy-note {
  text-align: center;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

.icon {
  font-style: normal;
}
</style>

<template>
  <!-- Conditional outer wrapper (modal overlay or artifact container) -->
  <div :class="asArtifact ? 'artifact-wrapper' : 'issue-form-modal'" @click.self="!asArtifact && $emit('close')">
    <div :class="asArtifact ? 'artifact-form-container' : 'form-container'">
      <!-- Header -->
      <div :class="asArtifact ? 'artifact-header' : 'form-header'">
        <h2 :class="asArtifact ? 'artifact-title' : 'form-title'">File an Issue</h2>
        <p :class="asArtifact ? 'artifact-subtitle' : 'form-subtitle'">
          Report a neighborhood issue. We'll match you to relevant civic meetings.
        </p>
        <button v-if="!asArtifact" class="close-btn" @click="$emit('close')" title="Close">
          <span class="icon">×</span>
        </button>
      </div>

      <!-- Form Body -->
      <form @submit.prevent="handleSubmit" :class="asArtifact ? 'artifact-form-body' : 'form-body'">
        <!-- Description (Required) -->
        <div class="form-group">
          <label for="description" class="form-label">
            What's the issue?
            <span class="required">*</span>
          </label>
          <textarea
            id="description"
            v-model="formData.description"
            class="form-textarea"
            placeholder="Example: There is a huge pothole on Main Street near 5th Ave that needs fixing"
            rows="4"
            maxlength="2000"
            required
            @input="validateDescription"
          />
          <div class="char-count">
            {{ formData.description.length }} / 2000
          </div>
          <div v-if="errors.description" class="error-message">
            {{ errors.description }}
          </div>
        </div>

        <!-- Jurisdiction (Auto-filled from user location) -->
        <div class="form-group">
          <label class="form-label">Filing issue in</label>
          <div class="jurisdiction-display">
            <span class="icon">📍</span>
            <span class="jurisdiction-name">{{ userStore.cityName || 'Your City' }}</span>
          </div>
        </div>

        <!-- Issue Type (Optional) -->
        <div class="form-group">
          <label for="issue_type" class="form-label">
            Issue Category
            <span class="optional">(optional)</span>
          </label>
          <select
            id="issue_type"
            v-model="formData.issue_type"
            class="form-select"
          >
            <option value="">Auto-detect from description</option>
            <option value="housing">Housing</option>
            <option value="transportation">Transportation</option>
            <option value="environment">Environment</option>
            <option value="public_safety">Public Safety</option>
            <option value="infrastructure">Infrastructure</option>
            <option value="community">Community</option>
            <option value="other">Other</option>
          </select>
        </div>

        <!-- Location (Optional) - with Interactive Map -->
        <div class="form-group">
          <label class="form-label">
            Specific Location
            <span class="optional">(optional)</span>
          </label>
          <MapPicker
            v-model="formData.location"
            map-height="300px"
            :initial-zoom="15"
          />
          <p class="form-hint">📍 Click or drag the pin to mark the exact location</p>
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
          <div v-if="matchedEventCount > 0" class="match-summary">
            Found {{ matchedEventCount }} relevant civic {{ matchedEventCount === 1 ? 'meeting' : 'meetings' }}!
          </div>
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
              Filing...
            </span>
            <span v-else>
              File Issue
            </span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { api } from '@/services/api';
import type { Jurisdiction, FileIssueResponse } from '@/types/civic';
import { useWorkspaceStore } from '@/stores/workspace';
import { useUserStore } from '@/stores/user';
import MapPicker from './MapPicker.vue';

// Props for pre-filling form data (from chat)
interface Props {
  initialData?: {
    title?: string;
    description?: string;
    address?: string;
    category?: string;
  };
  asArtifact?: boolean; // If true, render without modal wrapper
}

const props = withDefaults(defineProps<Props>(), {
  asArtifact: false
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'issue-filed', response: FileIssueResponse): void;
}>();

const workspaceStore = useWorkspaceStore();
const userStore = useUserStore();

// Form data
interface ComplaintFormData {
  description: string;
  jurisdiction_id: string;
  issue_type: string;
  location: {
    address: string;
    lat: number | null;
    lng: number | null;
  };
}

const formData = ref<ComplaintFormData>({
  description: props.initialData?.description || '',
  jurisdiction_id: '',
  issue_type: props.initialData?.category || '',
  location: {
    address: props.initialData?.address || '',
    lat: null,
    lng: null
  }
});

// State
const availableJurisdictions = ref<Jurisdiction[]>([]);
const isSubmitting = ref(false);
const submitError = ref('');
const submitSuccess = ref('');
const matchedEventCount = ref(0);
const errors = ref<Record<string, string>>({});

// Computed
const isFormValid = computed(() => {
  return formData.value.description.trim().length >= 10 &&
         formData.value.jurisdiction_id !== '';
});

// Lifecycle
onMounted(() => {
  // Auto-fill user's city from their location entry
  if (userStore.jurisdictionId) {
    formData.value.jurisdiction_id = userStore.jurisdictionId;
  }
});

// Methods
async function loadJurisdictions() {
  try {
    const response = await api.getJurisdictions();
    availableJurisdictions.value = response.filter(
      (j: Jurisdiction) => j.event_count && j.event_count > 0 // Only show jurisdictions with events
    );
  } catch (error) {
    console.error('[ComplaintForm] Error loading jurisdictions:', error);
    submitError.value = 'Failed to load jurisdictions. Please try again.';
  }
}

function validateDescription() {
  if (formData.value.description.trim().length < 10) {
    errors.value.description = 'Please provide at least 10 characters';
  } else {
    delete errors.value.description;
  }
}

async function handleSubmit() {
  // Clear previous messages
  submitError.value = '';
  submitSuccess.value = '';
  errors.value = {};

  // Validate
  if (!formData.value.description.trim()) {
    errors.value.description = 'Description is required';
    return;
  }
  if (formData.value.description.trim().length < 10) {
    errors.value.description = 'Please provide at least 10 characters';
    return;
  }
  if (!formData.value.jurisdiction_id) {
    errors.value.jurisdiction_id = 'Please select a city';
    return;
  }

  isSubmitting.value = true;

  try {
    // Prepare request payload
    const payload: any = {
      user_id: 'demo_user', // TODO: Replace with actual user ID from auth
      description: formData.value.description.trim(),
      jurisdiction_id: formData.value.jurisdiction_id
    };

    // Add optional fields if provided
    if (formData.value.issue_type) {
      payload.issue_type = formData.value.issue_type;
    }
    if (formData.value.location.address ||
        formData.value.location.lat !== null ||
        formData.value.location.lng !== null) {
      payload.location = {
        address: formData.value.location.address || undefined,
        latitude: formData.value.location.lat || undefined,
        longitude: formData.value.location.lng || undefined
      };
    }

    console.log('[ComplaintForm] Filing issue:', payload);

    // Submit issue
    const response = await api.fileComplaint(payload);

    console.log('[ComplaintForm] Filed successfully:', response);

    // Auto-follow the issue (Phase 2 - Task 2)
    try {
      await api.createFollow(
        payload.user_id,
        'issue',
        response.issue_id,
        payload.jurisdiction_id
      );
      console.log('[ComplaintForm] Auto-followed issue:', response.issue_id);
    } catch (followError) {
      console.error('[ComplaintForm] Failed to auto-follow issue:', followError);
      // Don't block user if auto-follow fails - they can manually follow later
    }

    // Show success message
    submitSuccess.value = response.message;
    matchedEventCount.value = response.matched_events?.length || 0;

    // Emit event with response
    emit('issue-filed', response);

    // Auto-close after 2 seconds if there are matches
    if (matchedEventCount.value > 0) {
      setTimeout(() => {
        emit('close');
      }, 2000);
    } else {
      // If no matches, keep form open so user can see the message
      setTimeout(() => {
        emit('close');
      }, 3000);
    }
  } catch (error: any) {
    console.error('[ComplaintForm] Error filing issue:', error);
    submitError.value = error.message || 'Failed to file issue. Please try again.';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<style scoped>
/* Modal Overlay */
.issue-form-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-md);
}

/* Form Container */
.form-container {
  background: var(--background);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.form-header {
  padding: var(--space-lg);
  border-bottom: 1px solid var(--border);
  position: relative;
}

.form-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-xs) 0;
}

.form-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0;
}

.close-btn {
  position: absolute;
  top: var(--space-md);
  right: var(--space-md);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 24px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.close-btn:hover {
  background: var(--hover-bg);
  color: var(--primary);
}

/* Form Body */
.form-body {
  padding: var(--space-lg);
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: var(--space-md);
}

.form-label {
  display: block;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
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
  margin: var(--space-xs) 0 0 0;
  font-style: italic;
}

.jurisdiction-display {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-md);
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
}

.jurisdiction-display .icon {
  font-size: 20px;
}

.jurisdiction-name {
  font-weight: 600;
  color: var(--text-primary);
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
  min-height: 100px;
  line-height: 1.5;
}

.char-count {
  text-align: right;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--space-xs);
}

/* Location Details */
.location-details {
  margin-bottom: var(--space-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--background-secondary);
}

.location-summary {
  padding: var(--space-sm) var(--space-md);
  cursor: pointer;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  user-select: none;
  transition: all var(--transition-fast);
}

.location-summary:hover {
  background: var(--hover-bg);
}

.location-fields {
  padding: var(--space-md);
  border-top: 1px solid var(--border);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

/* Messages */
.error-message {
  color: var(--accent-red);
  font-size: var(--font-size-sm);
  margin-top: var(--space-xs);
}

.submit-error,
.submit-success {
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-md);
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
  flex-direction: column;
  align-items: flex-start;
}

.match-summary {
  font-weight: 600;
  margin-top: var(--space-xs);
  color: var(--accent-green);
}

/* Form Actions */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  margin-top: var(--space-lg);
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

/* Scrollbar */
.form-body::-webkit-scrollbar {
  width: 8px;
}

.form-body::-webkit-scrollbar-track {
  background: var(--background-secondary);
}

.form-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-sm);
}

.form-body::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
/* Artifact mode styles (no modal overlay) */
.artifact-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  display: block;
}

.artifact-subtitle {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0;
  display: block;
  line-height: 1.4;
}

.artifact-form-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xl);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}
</style>

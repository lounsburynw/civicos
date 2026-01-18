<template>
  <div class="capabilities-modal-overlay" @click.self="handleClose">
    <div class="modal-container">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">Welcome to Civic OS</h2>
        <p class="modal-subtitle">
          Discover what you can do with your local civic information
        </p>
        <button class="close-btn" @click="handleClose" title="Close">
          <span class="icon">&times;</span>
        </button>
      </div>

      <!-- Three Category Cards -->
      <div class="categories-grid">
        <!-- Category 1: What's Happening -->
        <div class="category-card">
          <div class="category-icon">
            <Calendar :size="32" />
          </div>
          <h3 class="category-title">What's Happening</h3>
          <p class="category-description">Upcoming meetings and agenda items</p>
          <div class="example-questions">
            <span class="example-label">Try asking:</span>
            <ul>
              <li>"What's on the agenda this week?"</li>
              <li>"When is the next council meeting about housing?"</li>
            </ul>
          </div>
        </div>

        <!-- Category 2: What Happened -->
        <div class="category-card">
          <div class="category-icon">
            <History :size="32" />
          </div>
          <h3 class="category-title">What Happened</h3>
          <p class="category-description">Past decisions and what people said</p>
          <div class="example-questions">
            <span class="example-label">Try asking:</span>
            <ul>
              <li>"What has the council decided about parking downtown?"</li>
              <li>"What did residents say about the bike lane project?"</li>
            </ul>
          </div>
        </div>

        <!-- Category 3: Take Action -->
        <div class="category-card">
          <div class="category-icon">
            <MessageCircle :size="32" />
          </div>
          <h3 class="category-title">Take Action</h3>
          <p class="category-description">Submit comments or prepare to speak</p>
          <div class="example-questions">
            <span class="example-label">Try asking:</span>
            <ul>
              <li>"How do I submit a public comment?"</li>
              <li>"Help me prepare to speak at Monday's meeting"</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <p class="footer-hint">Just ask your question naturally - I'll find the answer!</p>
        <div class="action-buttons">
          <button class="btn-primary" @click="handleClose">
            Get Started
          </button>
          <button class="btn-text" @click="handleDismissPermanently">
            Don't show again
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Calendar, History, MessageCircle } from 'lucide-vue-next'

const ONBOARDING_DISMISSED_KEY = 'civic_onboarding_dismissed'

const emit = defineEmits<{
  (e: 'close'): void
}>()

function handleClose() {
  emit('close')
}

function handleDismissPermanently() {
  localStorage.setItem(ONBOARDING_DISMISSED_KEY, 'true')
  emit('close')
}
</script>

<style scoped>
.capabilities-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(7, 54, 66, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9998; /* Below LocationEntry (9999) */
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

.modal-container {
  background: var(--background);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
  width: 90%;
  max-width: 900px;
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

/* Header */
.modal-header {
  padding: var(--space-xl);
  text-align: center;
  border-bottom: 1px solid var(--border);
  position: relative;
}

.modal-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--primary);
  margin: 0 0 var(--space-sm) 0;
}

.modal-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.6;
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

.close-btn .icon {
  font-style: normal;
}

/* Categories Grid */
.categories-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-lg);
  padding: var(--space-xl);
}

@media (max-width: 768px) {
  .categories-grid {
    grid-template-columns: 1fr;
    gap: var(--space-md);
  }
}

/* Category Card */
.category-card {
  background: var(--background-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  padding: var(--space-lg);
  transition: all var(--transition-fast);
}

.category-card:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.category-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  background: rgba(38, 139, 210, 0.1);
  border-radius: var(--radius-base);
  color: var(--primary);
  margin-bottom: var(--space-md);
}

.category-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-xs) 0;
}

.category-description {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-md) 0;
  font-style: italic;
}

.example-questions {
  font-size: var(--font-size-sm);
}

.example-label {
  color: var(--text-secondary);
  font-weight: 500;
  display: block;
  margin-bottom: var(--space-xs);
}

.example-questions ul {
  margin: 0;
  padding: 0 0 0 var(--space-md);
  list-style-type: disc;
}

.example-questions li {
  color: var(--text-primary);
  margin-bottom: var(--space-xs);
  line-height: 1.4;
}

.example-questions li:last-child {
  margin-bottom: 0;
}

/* Footer */
.modal-footer {
  padding: var(--space-lg) var(--space-xl);
  border-top: 1px solid var(--border);
  background: var(--background-secondary);
  text-align: center;
}

.footer-hint {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-md) 0;
  font-style: italic;
}

.action-buttons {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.btn-primary {
  padding: var(--space-sm) var(--space-xl);
  font-size: var(--font-size-base);
  font-weight: 600;
  color: white;
  background: var(--primary);
  border: none;
  border-radius: var(--radius-base);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: #1d6fa5;
  transform: translateY(-1px);
  box-shadow: var(--shadow-subtle);
}

.btn-text {
  padding: var(--space-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color var(--transition-fast);
}

.btn-text:hover {
  color: var(--text-primary);
  text-decoration: underline;
}
</style>

<template>
  <div class="privacy-tier-selector">
    <h3 class="selector-title">How should we store your political values?</h3>
    <p class="selector-description">
      Your civic interests are politically sensitive. Choose how you want them stored.
    </p>

    <!-- Tier 1: Browser-Only (Recommended) -->
    <div class="tier-option recommended">
      <input
        type="radio"
        value="browser-only"
        v-model="selectedTier"
        id="tier1"
        class="tier-radio"
      >
      <label for="tier1" class="tier-label">
        <div class="tier-header">
          <span class="tier-icon">📱</span>
          <span class="tier-name">This Device Only</span>
          <span class="badge badge-recommended">Recommended</span>
        </div>
        <p class="tier-description">
          Your values stay in your browser. Maximum privacy.
        </p>
        <ul class="tier-features">
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            We can't see your data
          </li>
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            No subpoena risk
          </li>
          <li class="feature-item feature-warning">
            <span class="feature-icon">⚠️</span>
            No cross-device sync (export to backup)
          </li>
        </ul>
      </label>
    </div>

    <!-- Tier 2: Encrypted Sync (Coming Soon) -->
    <div class="tier-option tier-disabled">
      <input
        type="radio"
        value="encrypted-sync"
        v-model="selectedTier"
        id="tier2"
        class="tier-radio"
        disabled
      >
      <label for="tier2" class="tier-label">
        <div class="tier-header">
          <span class="tier-icon">🔐</span>
          <span class="tier-name">Encrypted Cloud Sync</span>
          <span class="badge badge-soon">Coming Soon</span>
        </div>
        <p class="tier-description">
          We store encrypted copy. Only you have the key.
        </p>
        <ul class="tier-features">
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            Cross-device sync
          </li>
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            We can't decrypt your data
          </li>
          <li class="feature-item feature-warning">
            <span class="feature-icon">⚠️</span>
            You must back up your encryption key
          </li>
        </ul>
      </label>
    </div>

    <!-- Tier 3: Zero-Knowledge (Future) -->
    <div class="tier-option tier-disabled">
      <input
        type="radio"
        value="zero-knowledge"
        v-model="selectedTier"
        id="tier3"
        class="tier-radio"
        disabled
      >
      <label for="tier3" class="tier-label">
        <div class="tier-header">
          <span class="tier-icon">🧮</span>
          <span class="tier-name">Zero-Knowledge</span>
          <span class="badge badge-future">Future</span>
        </div>
        <p class="tier-description">
          Cryptographic privacy with community features.
        </p>
        <ul class="tier-features">
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            Mathematically proven we can't know your values
          </li>
          <li class="feature-item feature-good">
            <span class="feature-icon">✅</span>
            Find others anonymously
          </li>
          <li class="feature-item feature-warning">
            <span class="feature-icon">⚠️</span>
            Most complex option (crypto knowledge helpful)
          </li>
        </ul>
      </label>
    </div>

    <!-- Learn More -->
    <div class="learn-more">
      <a href="https://github.com/anthropics/claude-code/blob/main/docs/PRIVACY_ARCHITECTURE.md" target="_blank" class="learn-more-link">
        📖 Why does this matter? Learn about our privacy architecture
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const emit = defineEmits<{
  (e: 'select', tier: string): void
}>()

const selectedTier = ref('browser-only')

watch(selectedTier, (tier) => {
  emit('select', tier)
})

// Emit initial selection
emit('select', selectedTier.value)
</script>

<style scoped>
.privacy-tier-selector {
  max-width: 800px;
  margin: 0 auto;
}

.selector-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--space-sm) 0;
  text-align: center;
}

.selector-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  text-align: center;
  margin: 0 0 var(--space-xl) 0;
}

/* Tier Options */
.tier-option {
  background: var(--background);
  border: 2px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  margin-bottom: var(--space-md);
  transition: all var(--transition-fast);
  cursor: pointer;
}

.tier-option:hover:not(.tier-disabled) {
  border-color: var(--primary);
  box-shadow: var(--shadow);
}

.tier-option.recommended {
  border-color: var(--primary);
  background: rgba(38, 139, 210, 0.05);
}

.tier-option.tier-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tier-radio {
  display: none;
}

.tier-radio:checked + .tier-label {
  background: rgba(38, 139, 210, 0.1);
}

.tier-label {
  cursor: pointer;
  display: block;
  padding: var(--space-sm);
  border-radius: var(--radius-base);
  transition: background var(--transition-fast);
}

.tier-disabled .tier-label {
  cursor: not-allowed;
}

.tier-header {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.tier-icon {
  font-size: 32px;
}

.tier-name {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--text-primary);
  flex: 1;
}

.badge {
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-recommended {
  background: var(--primary);
  color: white;
}

.badge-soon {
  background: rgba(181, 137, 0, 0.2);
  color: var(--accent-yellow);
}

.badge-future {
  background: rgba(108, 113, 196, 0.2);
  color: var(--accent-violet);
}

.tier-description {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0 0 var(--space-md) 0;
}

.tier-features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.feature-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  font-size: var(--font-size-sm);
}

.feature-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.feature-good {
  color: var(--text-primary);
}

.feature-warning {
  color: var(--text-secondary);
}

/* Learn More */
.learn-more {
  margin-top: var(--space-xl);
  text-align: center;
  padding: var(--space-lg);
  background: var(--background);
  border-radius: var(--radius-lg);
  border: 1px dashed var(--border);
}

.learn-more-link {
  color: var(--primary);
  text-decoration: none;
  font-size: var(--font-size-base);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: var(--space-sm);
  transition: color var(--transition-fast);
}

.learn-more-link:hover {
  color: #1c6fa0;
  text-decoration: underline;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .selector-title {
    font-size: 20px;
  }

  .tier-option {
    padding: var(--space-md);
  }

  .tier-header {
    flex-wrap: wrap;
  }

  .tier-name {
    font-size: var(--font-size-base);
  }

  .tier-icon {
    font-size: 24px;
  }
}
</style>

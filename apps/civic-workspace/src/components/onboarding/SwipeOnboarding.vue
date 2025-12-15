<template>
  <div class="swipe-onboarding-container">
    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <p>Loading scenarios...</p>
    </div>

    <!-- Scenario View -->
    <div v-else-if="!isComplete" class="scenario-view">
      <!-- Header with progress -->
      <div class="onboarding-header">
        <h1 class="onboarding-title">Discover Your Civic Archetype</h1>
        <p class="onboarding-subtitle">
          Answer {{ scenarios.length }} scenarios to find your civic identity
        </p>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
        </div>
        <div class="progress-text">
          {{ currentIndex + 1 }} / {{ scenarios.length }}
        </div>
      </div>

      <!-- Current Scenario Card -->
      <div class="scenario-card" v-if="currentScenario">
        <div class="scenario-topic">
          <span class="topic-badge">{{ currentScenario.topic }}</span>
          <span class="difficulty-badge" :class="`difficulty-${currentScenario.difficulty}`">
            {{ currentScenario.difficulty }}
          </span>
        </div>

        <div class="scenario-text">
          {{ currentScenario.text }}
        </div>

        <div class="scenario-tags">
          <span v-for="tag in currentScenario.tags" :key="tag" class="tag">
            {{ tag }}
          </span>
        </div>

        <!-- Response Options -->
        <div class="response-options">
          <button
            v-for="option in responseOptions"
            :key="option.value"
            @click="recordResponse(option.value)"
            class="response-button"
            :style="{ borderColor: option.color }"
          >
            <span class="response-label">{{ option.label }}</span>
          </button>
        </div>

        <!-- Navigation -->
        <div class="scenario-nav">
          <button
            @click="goBack"
            :disabled="!canGoBack"
            class="nav-button"
          >
            <ArrowLeft :size="18" />
            Back
          </button>
          <button
            @click="goForward"
            :disabled="!canGoForward"
            class="nav-button"
          >
            Next
            <ArrowRight :size="18" />
          </button>
        </div>
      </div>
    </div>

    <!-- Results View -->
    <div v-else class="results-view">
      <div class="results-header">
        <CircleCheck :size="64" class="completion-icon" />
        <h1>Your Civic Archetypes</h1>
        <p class="results-subtitle">
          Based on your responses, you align most closely with these civic identities:
        </p>
      </div>

      <div class="archetype-results">
        <div
          v-for="(archetype, index) in archetypeResults"
          :key="archetype.id"
          class="archetype-card"
        >
          <div class="archetype-rank">{{ index + 1 }}</div>
          <div class="archetype-content">
            <div class="archetype-header">
              <h3 :style="{ color: archetype.iconColor }">
                {{ archetype.name }}
              </h3>
              <div class="archetype-score">
                {{ (archetype.score * 100).toFixed(0) }}% match
              </div>
            </div>
            <p class="archetype-description">{{ archetype.description }}</p>
          </div>
        </div>
      </div>

      <div class="privacy-notice">
        <div class="privacy-icon">🔒</div>
        <p>
          <strong>Privacy First:</strong> Your responses are stored only in your browser.
          We never send your political values to our servers.
        </p>
      </div>

      <div class="completion-actions">
        <button @click="completeOnboarding" class="btn-primary btn-large">
          <Check :size="18" />
          Start Exploring
        </button>
        <button @click="resetOnboarding" class="btn-secondary">
          Start Over
        </button>
      </div>
    </div>

    <!-- Skip Link -->
    <div v-if="!isComplete" class="skip-link">
      <button @click="skipOnboarding" class="btn-text-link">
        Skip for now
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { ArrowLeft, ArrowRight, Check, CircleCheck } from 'lucide-vue-next';
import {
  saveArchetypesToBrowser,
  archetypesToInterests,
  type ArchetypeMatch
} from '@/utils/archetypeMatching';

// ============================================================================
// Types
// ============================================================================

interface Scenario {
  id: string;
  topic: string;
  category: string;
  text: string;
  response_scale: string[];
  difficulty: string;
  tags: string[];
}

interface ScenarioResponse {
  scenario_id: string;
  position: number; // -2 to +2 (strongly oppose to strongly support)
}

interface ArchetypeResult {
  id: string;
  name: string;
  score: number;
  description?: string;
  icon: string;
  iconColor: string;
  rank: number;
}

// ============================================================================
// Emits
// ============================================================================

const emit = defineEmits<{
  (e: 'complete', interests: string[]): void;
  (e: 'skip'): void;
}>();

// ============================================================================
// State
// ============================================================================

const scenarios = ref<Scenario[]>([]);
const currentIndex = ref(0);
const responses = ref<ScenarioResponse[]>([]);
const isComplete = ref(false);
const archetypeResults = ref<ArchetypeResult[]>([]);
const isLoading = ref(true);

// ============================================================================
// Computed
// ============================================================================

const currentScenario = computed(() => scenarios.value[currentIndex.value]);
const progress = computed(() => ((currentIndex.value / scenarios.value.length) * 100).toFixed(0));
const canGoBack = computed(() => currentIndex.value > 0);
const canGoForward = computed(() => currentIndex.value < responses.value.length - 1);

// ============================================================================
// Response Options (5-point Likert scale)
// ============================================================================

const responseOptions = [
  { label: 'Strongly Support', value: 2, color: 'var(--accent-green)' },
  { label: 'Support', value: 1, color: 'var(--accent-cyan)' },
  { label: 'Neutral', value: 0, color: 'var(--text-secondary)' },
  { label: 'Oppose', value: -1, color: 'var(--accent-orange)' },
  { label: 'Strongly Oppose', value: -2, color: 'var(--accent-red)' }
];

// ============================================================================
// Methods
// ============================================================================

async function loadScenarios() {
  try {
    // Load refined scenarios (v2 - 20 scenarios)
    const response = await fetch('/data/scenarios/civic_scenarios_v2_refined.json');
    const data = await response.json();
    scenarios.value = data.scenarios;
    isLoading.value = false;
  } catch (error) {
    console.error('Failed to load scenarios:', error);
    isLoading.value = false;
  }
}

function recordResponse(position: number) {
  // Record response for current scenario
  const existingIndex = responses.value.findIndex(r => r.scenario_id === currentScenario.value.id);

  if (existingIndex >= 0) {
    // Update existing response
    responses.value[existingIndex].position = position;
  } else {
    // Add new response
    responses.value.push({
      scenario_id: currentScenario.value.id,
      position
    });
  }

  // Auto-advance to next scenario
  if (currentIndex.value < scenarios.value.length - 1) {
    currentIndex.value++;
  } else {
    // All scenarios complete - calculate archetypes
    calculateArchetypes();
  }
}

function goBack() {
  if (canGoBack.value) {
    currentIndex.value--;
  }
}

function goForward() {
  if (canGoForward.value) {
    currentIndex.value++;
  }
}

async function calculateArchetypes() {
  try {
    // Load archetype weights and definitions
    const [weightsResponse, defsResponse] = await Promise.all([
      fetch('/data/archetypes/archetype_weights_final.json'),
      fetch('/data/archetypes/archetype_definitions_v3_refined.json')
    ]);

    const weightsData = await weightsResponse.json();
    const defsData = await defsResponse.json();

    // Calculate archetype scores using the production weights
    const archetypeScores = weightsData.archetypes.map((archetype: any) => {
      let scenarioScore = 0;
      let topicScore = 0;
      let scenarioCount = 0;
      let topicCount = 0;

      // Calculate scenario-based score (70% weight)
      responses.value.forEach(response => {
        const weight = archetype.scenario_weights[response.scenario_id];
        if (weight !== undefined && weight !== null) {
          scenarioScore += Math.abs(response.position - weight);
          scenarioCount++;
        }
      });

      // Calculate topic-based score (30% weight)
      const userTopicInterests: Record<string, number> = {};
      responses.value.forEach(response => {
        const scenario = scenarios.value.find(s => s.id === response.scenario_id);
        if (scenario) {
          if (!userTopicInterests[scenario.topic]) {
            userTopicInterests[scenario.topic] = 0;
          }
          userTopicInterests[scenario.topic] += Math.abs(response.position);
        }
      });

      Object.entries(archetype.topic_weights).forEach(([topic, weight]) => {
        const userInterest = userTopicInterests[topic] || 0;
        topicScore += Math.abs(userInterest - (weight as number));
        topicCount++;
      });

      // Normalize scores (lower is better - it's a distance metric)
      const avgScenarioDistance = scenarioCount > 0 ? scenarioScore / scenarioCount : 0;
      const avgTopicDistance = topicCount > 0 ? topicScore / topicCount : 0;

      // Combined score (weighted average, inverted to make higher = better match)
      const combinedDistance = (weightsData.scenario_weight * avgScenarioDistance) +
                               (weightsData.topic_weight * avgTopicDistance);

      // Convert distance to similarity score (0-1, higher is better)
      const maxPossibleDistance = 4; // Maximum possible distance in 5-point scale
      const similarityScore = Math.max(0, 1 - (combinedDistance / maxPossibleDistance));

      return {
        ...archetype,
        score: similarityScore
      };
    });

    // Sort by score (highest first)
    archetypeScores.sort((a: any, b: any) => b.score - a.score);

    // Get top 3 archetypes with full metadata
    const topArchetypes: ArchetypeMatch[] = archetypeScores.slice(0, 3).map((result: any, index: number) => {
      const def = defsData.archetypes.find((d: any) => d.id === result.id);
      return {
        id: result.id,
        name: result.name,
        score: result.score,
        description: def?.description || '',
        icon: def?.icon || 'User',
        iconColor: def?.iconColor || 'var(--primary)',
        rank: index + 1
      };
    });

    archetypeResults.value = topArchetypes;
    isComplete.value = true;

    // Save to browser localStorage (Tier 1 Privacy - browser only)
    saveArchetypesToBrowser(topArchetypes);
    console.log('[Privacy] Archetypes saved to browser localStorage only (Tier 1)');

  } catch (error) {
    console.error('Failed to calculate archetypes:', error);
  }
}

function completeOnboarding() {
  // Extract civic interests for ProfileForm (UI display only)
  const interests = archetypesToInterests(archetypeResults.value);

  // Emit to parent component
  emit('complete', interests);
}

function skipOnboarding() {
  emit('skip');
}

function resetOnboarding() {
  currentIndex.value = 0;
  responses.value = [];
  isComplete.value = false;
  archetypeResults.value = [];
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(() => {
  loadScenarios();
});
</script>

<style scoped>
.swipe-onboarding-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-xl);
  max-width: 700px;
  margin: 0 auto;
  min-height: 600px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  color: var(--text-secondary);
  padding: var(--space-2xl);
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ============================================================================
 * Scenario View
 * ============================================================================ */

.scenario-view {
  width: 100%;
}

.onboarding-header {
  text-align: center;
  margin-bottom: var(--space-2xl);
}

.onboarding-title {
  font-size: 32px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-sm) 0;
}

.onboarding-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0 0 var(--space-lg) 0;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--background-secondary);
  border-radius: var(--radius-pill);
  overflow: hidden;
  margin-bottom: var(--space-sm);
}

.progress-fill {
  height: 100%;
  background: var(--primary);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: 500;
}

/* Scenario Card */
.scenario-card {
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  box-shadow: var(--shadow);
}

.scenario-topic {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.topic-badge {
  padding: 4px 12px;
  background: var(--cyan-bg);
  color: var(--cyan);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: 500;
  text-transform: capitalize;
}

.difficulty-badge {
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: 500;
  text-transform: capitalize;
}

.difficulty-easy {
  background: rgba(133, 153, 0, 0.15);
  color: var(--accent-green);
}

.difficulty-moderate {
  background: rgba(203, 75, 22, 0.15);
  color: var(--accent-orange);
}

.difficulty-divisive {
  background: rgba(220, 50, 47, 0.15);
  color: var(--accent-red);
}

.scenario-text {
  font-size: 18px;
  line-height: 1.6;
  color: var(--text-primary);
  margin-bottom: var(--space-lg);
}

.scenario-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  margin-bottom: var(--space-xl);
}

.tag {
  padding: 4px 10px;
  background: var(--background-secondary);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}

/* Response Options */
.response-options {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}

.response-button {
  padding: var(--space-md) var(--space-lg);
  background: white;
  border: 2px solid var(--border);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}

.response-button:hover {
  transform: translateX(4px);
  box-shadow: var(--shadow-subtle);
}

.response-label {
  color: var(--text-primary);
}

/* Navigation */
.scenario-nav {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border);
}

.nav-button {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-base);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.nav-button:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--primary);
}

.nav-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ============================================================================
 * Results View
 * ============================================================================ */

.results-view {
  width: 100%;
}

.results-header {
  text-align: center;
  margin-bottom: var(--space-2xl);
}

.completion-icon {
  color: var(--accent-green);
  margin: 0 auto var(--space-md);
}

.results-header h1 {
  font-size: 36px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-md) 0;
}

.results-subtitle {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  margin: 0;
}

.archetype-results {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  margin-bottom: var(--space-2xl);
}

.archetype-card {
  display: flex;
  gap: var(--space-lg);
  padding: var(--space-xl);
  background: white;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-subtle);
}

.archetype-rank {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: var(--primary);
  color: white;
  font-size: 24px;
  font-weight: 600;
  border-radius: 50%;
  flex-shrink: 0;
}

.archetype-content {
  flex: 1;
}

.archetype-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-sm);
}

.archetype-header h3 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.archetype-score {
  padding: 4px 12px;
  background: var(--background-secondary);
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.archetype-description {
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* Privacy Notice */
.privacy-notice {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-lg);
  background: rgba(42, 161, 152, 0.1);
  border: 1px solid var(--cyan);
  border-radius: var(--radius-base);
  margin-bottom: var(--space-xl);
}

.privacy-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.privacy-notice p {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.privacy-notice strong {
  color: var(--cyan);
}

/* Completion Actions */
.completion-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.btn-primary,
.btn-secondary {
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-base);
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
}

.btn-primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.btn-primary:hover {
  background: #1976D2;
  box-shadow: var(--shadow);
}

.btn-primary.btn-large {
  padding: var(--space-lg) var(--space-2xl);
  font-size: var(--font-size-lg);
}

.btn-secondary {
  background: transparent;
  color: var(--text-primary);
  border-color: var(--border);
}

.btn-secondary:hover {
  background: var(--hover-bg);
}

/* Skip Link */
.skip-link {
  text-align: center;
  margin-top: var(--space-lg);
}

.btn-text-link {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  text-decoration: underline;
  padding: var(--space-sm);
}

.btn-text-link:hover {
  color: var(--primary);
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .onboarding-title {
    font-size: 24px;
  }

  .scenario-card {
    padding: var(--space-lg);
  }

  .scenario-text {
    font-size: 16px;
  }

  .archetype-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .archetype-rank {
    align-self: flex-start;
  }
}
</style>

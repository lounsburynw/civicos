/**
 * Developer Mode Store
 *
 * Enables developer mode for debugging LLM provider routing.
 * Shows provider names, models, and token usage in the UI.
 *
 * Usage: Launch with ?dev=true in URL
 */

import { defineStore } from 'pinia'

export const useDeveloperStore = defineStore('developer', {
  state: () => ({
    enabled: localStorage.getItem('developerMode') === 'true',
    selectedModel: localStorage.getItem('civic_selected_model') || 'auto'
  }),

  getters: {
    isEnabled: (state) => state.enabled
  },

  actions: {
    /**
     * Enable developer mode
     */
    enable() {
      this.enabled = true
      localStorage.setItem('developerMode', 'true')
      console.log('[Developer Mode] Enabled - LLM provider info will be shown')
    },

    /**
     * Disable developer mode
     */
    disable() {
      this.enabled = false
      localStorage.setItem('developerMode', 'false')
      console.log('[Developer Mode] Disabled')
    },

    /**
     * Set selected model for chat routing
     */
    setSelectedModel(model: string) {
      this.selectedModel = model
      localStorage.setItem('civic_selected_model', model)
      console.log('[Developer Mode] Model selection changed to:', model)
    },

    /**
     * Initialize from URL parameter
     * Call this on app mount with ?dev=true or ?dev=false
     */
    initFromUrl() {
      const urlParams = new URLSearchParams(window.location.search)
      const devParam = urlParams.get('dev')

      if (devParam === 'true') {
        this.enable()
      } else if (devParam === 'false') {
        this.disable()
      }
      // If no param, keep current localStorage value
    },

    /**
     * Estimate cost for a draft or response
     * Returns cost in dollars based on token count and provider
     */
    estimateCost(tokens: number, provider: string): string {
      const rates: Record<string, number> = {
        'google': 0.075,      // Gemini Flash (per 1M tokens)
        'openai': 0.60,       // gpt-4o-mini
        'groq': 0.27,         // Llama 3.3
        'perplexity': 1.00,   // Sonar
        'anthropic': 3.00     // Claude Sonnet 4
      }

      const rate = rates[provider] || 0.60 // Default to OpenAI rate
      const cost = (tokens / 1_000_000) * rate

      return cost.toFixed(5)
    }
  }
})

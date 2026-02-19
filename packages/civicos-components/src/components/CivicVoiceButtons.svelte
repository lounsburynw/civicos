<svelte:options customElement="civic-voice-buttons" />

<script lang="ts">
  type Stance = 'support' | 'oppose' | 'watching';

  let {
    entityId = '',
    userStance = null as Stance | null,
    disabled = false,
    locked = false,
    onvoice,
  }: {
    entityId?: string;
    userStance?: Stance | null;
    disabled?: boolean;
    locked?: boolean;
    onvoice?: (detail: { entityId: string; stance: Stance }) => void;
  } = $props();

  function vote(stance: Stance) {
    if (disabled) return;
    onvoice?.({ entityId, stance });
  }
</script>

{#if locked}
  <div class="voice-locked-group">
    <span class="voice-locked">Unlock to vote</span>
    <span class="voice-disclaimer">Voices are informal signals — not official votes or testimony.</span>
  </div>
{:else}
  <div class="voice-actions">
    <button
      class="voice-btn vb-support"
      class:active={userStance === 'support'}
      {disabled}
      onclick={() => vote('support')}
    >Support</button>
    <button
      class="voice-btn vb-oppose"
      class:active={userStance === 'oppose'}
      {disabled}
      onclick={() => vote('oppose')}
    >Oppose</button>
    <button
      class="voice-btn vb-watch"
      class:active={userStance === 'watching'}
      {disabled}
      onclick={() => vote('watching')}
    >Watch</button>
  </div>
{/if}

<style>
  .voice-actions {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .voice-btn {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #374151;
    background: transparent;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
  }
  .voice-btn:hover:not(:disabled) {
    border-color: #4b5563;
    color: #eee;
  }
  .voice-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .vb-support.active {
    background: #14532d;
    border-color: #22c55e;
    color: #4ade80;
  }
  .vb-oppose.active {
    background: #7f1d1d;
    border-color: #ef4444;
    color: #f87171;
  }
  .vb-watch.active {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #60a5fa;
  }
  .voice-locked-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .voice-locked {
    font-size: 10px;
    color: #6b7280;
    font-style: italic;
  }
  .voice-disclaimer {
    font-size: 9px;
    color: #4b5563;
  }
</style>

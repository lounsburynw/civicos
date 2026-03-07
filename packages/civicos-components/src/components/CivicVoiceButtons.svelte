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
    border: 1px solid var(--civic-border-default);
    background: transparent;
    color: var(--civic-text-muted);
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
  }
  .voice-btn:hover:not(:disabled) {
    border-color: var(--civic-text-disabled);
    color: var(--civic-text-primary);
  }
  .voice-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .vb-support.active {
    background: var(--civic-status-success-bg);
    border-color: var(--civic-status-success);
    color: var(--civic-status-success-light);
  }
  .vb-oppose.active {
    background: var(--civic-status-error-bg);
    border-color: var(--civic-status-error);
    color: var(--civic-status-error-light);
  }
  .vb-watch.active {
    background: var(--civic-accent-primary-dark);
    border-color: var(--civic-accent-primary);
    color: var(--civic-accent-primary-light);
  }
  .voice-locked-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .voice-locked {
    font-size: 10px;
    color: var(--civic-text-dim);
    font-style: italic;
  }
  .voice-disclaimer {
    font-size: 9px;
    color: var(--civic-text-disabled);
  }
</style>

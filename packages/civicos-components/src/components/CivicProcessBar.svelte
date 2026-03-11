<script lang="ts">
  type ProcessLevel = 'federal' | 'state' | 'city';

  const STAGES: Record<ProcessLevel, { key: string; label: string }[]> = {
    federal: [
      { key: 'proposed', label: 'Proposed' },
      { key: 'comment', label: 'Comment' },
      { key: 'final', label: 'Final Rule' },
    ],
    state: [
      { key: 'introduced', label: 'Introduced' },
      { key: 'committee', label: 'Committee' },
      { key: 'hearing', label: 'Hearing' },
      { key: 'vote', label: 'Vote' },
      { key: 'governor', label: 'Governor' },
    ],
    city: [
      { key: 'posted', label: 'Posted' },
      { key: 'comment', label: 'Comment' },
      { key: 'vote', label: 'Vote' },
    ],
  };

  let { level, stage }: { level: ProcessLevel; stage: string } = $props();

  const stages = $derived(STAGES[level] || []);
  const activeIndex = $derived(stages.findIndex(s => s.key === stage));
</script>

{#if stages.length > 0}
  <div class="process-bar">
    {#each stages as s, i}
      {#if i > 0}
        <span class="process-sep" class:past={i <= activeIndex}></span>
      {/if}
      <span class="process-stage"
            class:active={i === activeIndex}
            class:past={i < activeIndex}
      >{s.label}</span>
    {/each}
  </div>
{/if}

<style>
  .process-bar {
    display: flex;
    align-items: center;
    gap: 0;
    margin-bottom: 6px;
  }
  .process-stage {
    font-size: 9px;
    font-weight: 500;
    color: var(--civic-text-disabled);
    letter-spacing: 0.02em;
    white-space: nowrap;
  }
  .process-stage.past {
    color: var(--civic-text-dim);
  }
  .process-stage.active {
    color: var(--civic-text-secondary);
    background: var(--civic-hover-bg);
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
  }
  .process-sep {
    width: 12px;
    height: 1px;
    background: var(--civic-border-default);
    margin: 0 3px;
    flex-shrink: 0;
  }
  .process-sep.past {
    background: var(--civic-text-dim);
  }
</style>

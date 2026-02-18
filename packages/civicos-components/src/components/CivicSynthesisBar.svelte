<svelte:options customElement="civic-synthesis-bar" />

<script lang="ts">
  let {
    support = 0,
    oppose = 0,
    neutral = 0,
  } = $props();

  let total = $derived(support + oppose + neutral);
</script>

{#if total > 0}
  <div class="synthesis-bar-wrapper">
    <div class="synthesis-bar">
      {#if support > 0}
        <div class="bar-seg bar-support" style="width: {(support / total) * 100}%" title="{support} support"></div>
      {/if}
      {#if oppose > 0}
        <div class="bar-seg bar-oppose" style="width: {(oppose / total) * 100}%" title="{oppose} oppose"></div>
      {/if}
      {#if neutral > 0}
        <div class="bar-seg bar-neutral" style="width: {(neutral / total) * 100}%" title="{neutral} neutral"></div>
      {/if}
    </div>
    <div class="synthesis-labels">
      {#if support > 0}<span class="synth-label synth-support">{support} support</span>{/if}
      {#if oppose > 0}<span class="synth-label synth-oppose">{oppose} oppose</span>{/if}
      {#if neutral > 0}<span class="synth-label synth-neutral">{neutral} neutral</span>{/if}
    </div>
  </div>
{/if}

<style>
  .synthesis-bar-wrapper { margin-bottom: 8px; }
  .synthesis-bar {
    display: flex;
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    background: #262626;
  }
  .bar-seg { min-width: 4px; }
  .bar-support { background: #22c55e; }
  .bar-oppose { background: #ef4444; }
  .bar-neutral { background: #9ca3af; }
  .synthesis-labels {
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }
  .synth-label {
    font-size: 10px;
    color: #6b7280;
  }
  .synth-support { color: #22c55e; }
  .synth-oppose { color: #ef4444; }
</style>

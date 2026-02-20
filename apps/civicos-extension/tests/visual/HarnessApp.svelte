<script lang="ts">
  import CivicReadOnlyPulse from '@civicos/components/src/components/CivicReadOnlyPulse.svelte';
  import { pulseByLevel } from './mock-data.js';

  let { level = 'city' }: { level?: string } = $props();

  const data = $derived(pulseByLevel[level] || pulseByLevel.city);

  const tabs = [
    { id: 'city', label: 'San Rafael' },
    { id: 'state', label: 'California' },
    { id: 'federal', label: 'Federal' },
  ];

  function navigate(tabLevel: string) {
    window.location.search = `?level=${tabLevel}`;
  }
</script>

<div class="panel">
  <header>
    <nav class="breadcrumb">
      {#each tabs as tab, i}
        {#if i > 0}
          <span class="breadcrumb-sep">/</span>
        {/if}
        <button
          class="breadcrumb-segment"
          class:active={level === tab.id}
          onclick={() => navigate(tab.id)}
        >
          <span class="health-dot healthy"></span>
          <span class="segment-name">{tab.label}</span>
        </button>
      {/each}
    </nav>
  </header>

  <CivicReadOnlyPulse
    {data}
    {level}
    jurisdiction={level === 'city' ? 'city-san-rafael' : level === 'state' ? 'state-california' : 'federal-us'}
  />
</div>

<style>
  /* === Base (from SidePanel.svelte:967-974) === */
  .panel {
    padding: 12px;
    min-height: 100vh;
    font-size: 13px;
    line-height: 1.4;
    background: #171717;
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
  }

  /* === Header (from SidePanel.svelte:977-1033) === */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #374151;
  }

  .breadcrumb {
    display: flex;
    align-items: center;
    gap: 0;
    min-width: 0;
    overflow: hidden;
  }

  .breadcrumb-segment {
    display: flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    color: #9ca3af;
    font-size: 12px;
    padding: 3px 6px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    transition: color 0.15s, background 0.15s;
  }
  .breadcrumb-segment:first-child {
    font-weight: 600;
    color: #d1d5db;
  }
  .breadcrumb-segment:hover {
    color: #eee;
    background: #333;
  }
  .breadcrumb-segment.active {
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    border-bottom: 2px solid #60a5fa;
    padding-bottom: 2px;
  }

  .breadcrumb-sep {
    color: #4b5563;
    font-size: 12px;
    margin: 0 2px;
    flex-shrink: 0;
  }

  .segment-name {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .health-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot.healthy { background: #4ade80; }
</style>

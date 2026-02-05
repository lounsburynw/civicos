<script lang="ts">
  import { onMount } from 'svelte';
  import {
    themes,
    currentTheme,
    themeMode,
    setTheme,
    initializeTheme,
    toggleMode
  } from './theme-store';
  import type { Theme } from './themes';

  let isOpen = false;
  let dropdownRef: HTMLDivElement;

  // Group themes by mode for organized display
  $: lightThemes = themes.filter((t) => t.mode === 'light');
  $: darkThemes = themes.filter((t) => t.mode === 'dark');

  onMount(() => {
    initializeTheme();

    // Close dropdown on outside click
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef && !dropdownRef.contains(event.target as Node)) {
        isOpen = false;
      }
    }

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  });

  function selectTheme(theme: Theme) {
    setTheme(theme.id);
    isOpen = false;
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      isOpen = false;
    }
  }
</script>

<div class="theme-switcher" bind:this={dropdownRef}>
  <button
    class="theme-toggle"
    on:click={() => (isOpen = !isOpen)}
    on:keydown={handleKeydown}
    aria-expanded={isOpen}
    aria-haspopup="listbox"
    title="Change theme"
  >
    <span class="theme-icon">
      {#if $themeMode === 'dark'}
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      {:else}
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      {/if}
    </span>
    <span class="theme-name">{$currentTheme.name}</span>
    <span class="dropdown-arrow" class:open={isOpen}>
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    </span>
  </button>

  {#if isOpen}
    <div class="theme-dropdown" role="listbox">
      <div class="theme-section">
        <div class="section-label">Light</div>
        {#each lightThemes as theme}
          <button
            class="theme-option"
            class:selected={$currentTheme.id === theme.id}
            on:click={() => selectTheme(theme)}
            role="option"
            aria-selected={$currentTheme.id === theme.id}
          >
            <span class="color-preview" style="background: {theme.colors.primary}"></span>
            <span class="option-content">
              <span class="option-name">{theme.name}</span>
              <span class="option-description">{theme.description}</span>
            </span>
            {#if $currentTheme.id === theme.id}
              <span class="check-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            {/if}
          </button>
        {/each}
      </div>

      <div class="theme-section">
        <div class="section-label">Dark</div>
        {#each darkThemes as theme}
          <button
            class="theme-option"
            class:selected={$currentTheme.id === theme.id}
            on:click={() => selectTheme(theme)}
            role="option"
            aria-selected={$currentTheme.id === theme.id}
          >
            <span class="color-preview" style="background: {theme.colors.primary}"></span>
            <span class="option-content">
              <span class="option-name">{theme.name}</span>
              <span class="option-description">{theme.description}</span>
            </span>
            {#if $currentTheme.id === theme.id}
              <span class="check-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            {/if}
          </button>
        {/each}
      </div>

      <div class="theme-actions">
        <button class="quick-toggle" on:click={toggleMode}>
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
          </svg>
          Toggle {$themeMode === 'light' ? 'Dark' : 'Light'} Mode
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .theme-switcher {
    position: relative;
    font-family: system-ui, -apple-system, sans-serif;
  }

  .theme-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--civic-surface, #ffffff);
    border: 1px solid var(--civic-border, #e2e8f0);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    color: var(--civic-text, #0f172a);
    transition: all 0.15s ease;
  }

  .theme-toggle:hover {
    background: var(--civic-surface-hover, #f1f5f9);
    border-color: var(--color-primary, #1e40af);
  }

  .theme-icon {
    display: flex;
    align-items: center;
    color: var(--color-primary, #1e40af);
  }

  .theme-name {
    font-weight: 500;
  }

  .dropdown-arrow {
    display: flex;
    align-items: center;
    transition: transform 0.15s ease;
    color: var(--civic-text-secondary, #475569);
  }

  .dropdown-arrow.open {
    transform: rotate(180deg);
  }

  .theme-dropdown {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    min-width: 280px;
    background: var(--civic-surface, #ffffff);
    border: 1px solid var(--civic-border, #e2e8f0);
    border-radius: 12px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    overflow: hidden;
  }

  .theme-section {
    padding: 8px;
  }

  .theme-section:not(:last-child) {
    border-bottom: 1px solid var(--civic-border, #e2e8f0);
  }

  .section-label {
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--civic-text-secondary, #475569);
  }

  .theme-option {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 10px 8px;
    background: transparent;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    text-align: left;
    transition: background 0.15s ease;
  }

  .theme-option:hover {
    background: var(--civic-surface-hover, #f1f5f9);
  }

  .theme-option.selected {
    background: var(--civic-surface-hover, #f1f5f9);
  }

  .color-preview {
    width: 24px;
    height: 24px;
    border-radius: 6px;
    flex-shrink: 0;
  }

  .option-content {
    flex: 1;
    min-width: 0;
  }

  .option-name {
    display: block;
    font-size: 14px;
    font-weight: 500;
    color: var(--civic-text, #0f172a);
  }

  .option-description {
    display: block;
    font-size: 12px;
    color: var(--civic-text-secondary, #475569);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .check-icon {
    color: var(--color-primary, #1e40af);
    flex-shrink: 0;
  }

  .theme-actions {
    padding: 8px;
    border-top: 1px solid var(--civic-border, #e2e8f0);
  }

  .quick-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    padding: 10px;
    background: var(--civic-surface-hover, #f1f5f9);
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    color: var(--civic-text, #0f172a);
    transition: all 0.15s ease;
  }

  .quick-toggle:hover {
    background: var(--color-primary, #1e40af);
    color: white;
  }

  /* Dark mode overrides for the dropdown itself */
  :global([data-civic-mode='dark']) .theme-dropdown {
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
  }
</style>

<script lang="ts">
  import { truncateNpub } from '../utils/civic-helpers.js';

  type IdentityInfo = {
    npub: string;
    isUnlocked?: boolean;
  };

  let {
    identity,
    loading = false,
    displayName = '',
    attestationLabels = [],
    onunlock,
    onopenoptions,
  }: {
    identity: IdentityInfo | null;
    loading?: boolean;
    displayName?: string;
    attestationLabels?: string[];
    onunlock?: (password: string) => Promise<boolean>;
    onopenoptions?: () => void;
  } = $props();

  let unlockPassword = $state('');
  let unlocking = $state(false);
  let unlockError: string | null = $state(null);

  async function handleUnlock() {
    if (!unlockPassword || !onunlock) return;
    unlocking = true;
    unlockError = null;
    const success = await onunlock(unlockPassword);
    if (!success) {
      unlockError = 'Wrong password';
    }
    unlockPassword = '';
    unlocking = false;
  }
</script>

{#if loading}
  <div class="identity-chip skeleton">&nbsp;</div>
{:else if identity}
  <div class="identity-chip">
    <div class="chip-row">
      {#if identity.isUnlocked}
        <span class="sign-in-status signed-in">Signed in</span>
      {:else}
        <span class="sign-in-status">Signed out</span>
      {/if}
      {#if identity.isUnlocked && attestationLabels.length > 0}
        <span class="attested-chips">
          {#each attestationLabels as label}
            <span class="attested-chip">{label}</span>
          {/each}
        </span>
      {/if}
    </div>
    {#if !identity.isUnlocked}
      <form class="chip-unlock-form" onsubmit={(e: Event) => { e.preventDefault(); handleUnlock(); }}>
        <input type="password" class="chip-unlock-input" placeholder="Password" bind:value={unlockPassword} autocomplete="off" />
        <button type="submit" class="chip-unlock-btn" disabled={unlocking || !unlockPassword}>{unlocking ? '...' : 'Sign in'}</button>
      </form>
      {#if unlockError}
        <div class="chip-unlock-error">{unlockError}</div>
      {/if}
    {:else}
      {#if displayName}
        <div class="display-name">{displayName}</div>
      {/if}
      <div class="npub">{truncateNpub(identity.npub)}</div>
    {/if}
  </div>
{:else}
  <div class="identity-chip empty">
    <span>No identity</span>
    <button class="link-btn" onclick={onopenoptions}>Set up</button>
  </div>
{/if}

<style>
  .identity-chip {
    background: var(--civic-surface-elevated);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .identity-chip.skeleton {
    height: 48px;
    animation: pulse 1.5s infinite;
  }
  .identity-chip.empty {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--civic-text-dim);
    font-size: 12px;
  }
  @keyframes pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 0.3; }
  }
  .chip-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 4px;
  }
  .sign-in-status { font-size: 10px; font-weight: 500; color: var(--civic-status-error); }
  .sign-in-status.signed-in { color: var(--civic-status-success); }
  .attested-chips {
    display: flex;
    gap: 4px;
    margin-left: auto;
  }
  .attested-chip {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--civic-status-success);
    background: var(--civic-status-success-bg-chip);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .chip-unlock-form {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .chip-unlock-input {
    flex: 1;
    min-width: 0;
    padding: 4px 8px;
    background: var(--civic-surface-card-alt);
    border: 1px solid var(--civic-border-input);
    border-radius: 4px;
    color: var(--civic-text-secondary);
    font-size: 12px;
    outline: none;
  }
  .chip-unlock-input:focus { border-color: var(--civic-accent-indigo); }
  .chip-unlock-btn {
    background: var(--civic-accent-indigo);
    color: white;
    border: none;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
  }
  .chip-unlock-btn:hover { background: var(--civic-accent-indigo-hover); }
  .chip-unlock-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .chip-unlock-error { font-size: 10px; color: var(--civic-status-error); margin-top: 2px; }
  .display-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--civic-text-secondary);
    margin-top: 2px;
  }
  .npub {
    font-family: var(--civic-font-family-mono);
    font-size: 11px;
    color: var(--civic-text-dim);
  }
  .link-btn {
    background: none;
    border: none;
    color: var(--civic-accent-primary);
    cursor: pointer;
    font-size: 12px;
    text-decoration: underline;
  }
  .link-btn:hover { color: var(--civic-accent-primary-light); }
</style>

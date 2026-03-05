<script lang="ts">
  import { truncateNpub } from '../utils/civic-helpers.js';

  type IdentityInfo = {
    npub: string;
    isUnlocked?: boolean;
  };

  let {
    identity,
    loading = false,
    attestationLabels = [],
    onunlock,
    onopenoptions,
  }: {
    identity: IdentityInfo | null;
    loading?: boolean;
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
      {#if attestationLabels.length > 0}
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
    background: #262626;
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
    color: #6b7280;
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
  .sign-in-status { font-size: 10px; font-weight: 500; color: #ef4444; }
  .sign-in-status.signed-in { color: #22c55e; }
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
    color: #22c55e;
    background: rgba(34, 197, 94, 0.12);
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
    background: #1a1a1a;
    border: 1px solid #404040;
    border-radius: 4px;
    color: #e5e7eb;
    font-size: 12px;
    outline: none;
  }
  .chip-unlock-input:focus { border-color: #6366f1; }
  .chip-unlock-btn {
    background: #6366f1;
    color: white;
    border: none;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
  }
  .chip-unlock-btn:hover { background: #4f46e5; }
  .chip-unlock-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .chip-unlock-error { font-size: 10px; color: #ef4444; margin-top: 2px; }
  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #6b7280;
  }
  .link-btn {
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 12px;
    text-decoration: underline;
  }
  .link-btn:hover { color: #60a5fa; }
</style>

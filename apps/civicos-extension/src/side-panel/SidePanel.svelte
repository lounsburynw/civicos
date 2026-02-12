<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo } from '../lib/providers/types.js';

  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);

  async function loadIdentity() {
    loading = true;
    const response = await sendMessage<(IdentityInfo & { isUnlocked?: boolean }) | null>({
      type: 'GET_IDENTITY',
    });
    if (response.success) {
      identity = response.data;
    }
    loading = false;
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }

  function truncateNpub(npub: string): string {
    if (npub.length <= 16) return npub;
    return npub.slice(0, 10) + '...' + npub.slice(-6);
  }

  // Load on mount
  loadIdentity();
</script>

<div class="panel">
  <header>
    <h1>CivicOS</h1>
    <button class="settings-btn" onclick={openOptions} title="Settings">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
      </svg>
    </button>
  </header>

  {#if loading}
    <div class="status">Loading...</div>
  {:else if identity}
    <div class="identity-chip">
      <div class="chip-row">
        <span class="tier-badge" class:easy={identity.tier === 'easy'} class:private={identity.tier === 'private'}>
          {identity.tier}
        </span>
        <span class="lock-status" class:unlocked={identity.isUnlocked}>
          {identity.isUnlocked ? 'unlocked' : 'locked'}
        </span>
      </div>
      <div class="npub">{truncateNpub(identity.npub)}</div>
    </div>
  {:else}
    <div class="no-identity">
      <p>No identity configured</p>
      <button class="btn-primary" onclick={openOptions}>Set up identity</button>
    </div>
  {/if}

  <div class="placeholder">
    <div class="pulse-icon">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </svg>
    </div>
    <h2>City Pulse</h2>
    <p>Real-time civic activity feed coming in Phase 1</p>
  </div>
</div>

<style>
  .panel {
    padding: 16px;
    min-height: 100vh;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #1e293b;
  }

  h1 {
    font-size: 18px;
    font-weight: 700;
    color: #f8fafc;
  }

  .settings-btn {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
  }
  .settings-btn:hover { color: #e2e8f0; background: #1e293b; }

  .status {
    text-align: center;
    padding: 24px;
    color: #94a3b8;
  }

  .identity-chip {
    background: #1e293b;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 16px;
  }

  .chip-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 6px;
  }

  .tier-badge {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 4px;
    background: #374151;
    color: #9ca3af;
  }
  .tier-badge.easy { background: #1e3a5f; color: #60a5fa; }
  .tier-badge.private { background: #3b1f4b; color: #c084fc; }

  .lock-status {
    font-size: 11px;
    color: #ef4444;
  }
  .lock-status.unlocked { color: #22c55e; }

  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #94a3b8;
  }

  .no-identity {
    text-align: center;
    padding: 24px;
  }
  .no-identity p { color: #94a3b8; margin-bottom: 12px; }

  .btn-primary {
    background: #6366f1;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
  }
  .btn-primary:hover { background: #4f46e5; }

  .placeholder {
    text-align: center;
    padding: 48px 16px;
  }

  .pulse-icon {
    margin-bottom: 12px;
  }

  .placeholder h2 {
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
    margin-bottom: 8px;
  }

  .placeholder p {
    font-size: 13px;
    color: #64748b;
  }
</style>

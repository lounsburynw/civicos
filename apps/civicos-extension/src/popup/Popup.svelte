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

  async function openSidePanel() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      await chrome.sidePanel.open({ tabId: tab.id });
    }
    window.close();
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }

  function truncateNpub(npub: string): string {
    if (npub.length <= 16) return npub;
    return npub.slice(0, 10) + '...' + npub.slice(-6);
  }

  loadIdentity();
</script>

<div class="popup">
  <header>
    <h1>CivicOS</h1>
  </header>

  {#if loading}
    <div class="status">Loading...</div>
  {:else if identity}
    <div class="identity-info">
      <div class="row">
        <span class="label">Tier</span>
        <span class="tier-badge" class:easy={identity.tier === 'easy'} class:private={identity.tier === 'private'}>
          {identity.tier}
        </span>
      </div>
      <div class="row">
        <span class="label">Status</span>
        <span class="lock-status" class:unlocked={identity.isUnlocked}>
          {identity.isUnlocked ? 'Unlocked' : 'Locked'}
        </span>
      </div>
      <div class="row">
        <span class="label">npub</span>
        <span class="npub">{truncateNpub(identity.npub)}</span>
      </div>
    </div>
  {:else}
    <div class="no-identity">
      <p>No identity configured</p>
    </div>
  {/if}

  <div class="actions">
    <button class="btn-primary" onclick={openSidePanel}>Open City Pulse</button>
    <button class="btn-secondary" onclick={openOptions}>Settings</button>
  </div>
</div>

<style>
  .popup {
    padding: 16px;
  }

  header {
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1e293b;
  }

  h1 {
    font-size: 16px;
    font-weight: 700;
    color: #f8fafc;
  }

  .status {
    text-align: center;
    padding: 16px;
    color: #94a3b8;
    font-size: 13px;
  }

  .identity-info {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .label {
    font-size: 12px;
    color: #64748b;
    text-transform: uppercase;
    font-weight: 500;
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
    font-size: 12px;
    color: #ef4444;
    font-weight: 500;
  }
  .lock-status.unlocked { color: #22c55e; }

  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #94a3b8;
  }

  .no-identity {
    text-align: center;
    padding: 16px;
  }
  .no-identity p { color: #94a3b8; font-size: 13px; }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .btn-primary {
    background: #6366f1;
    color: white;
    border: none;
    padding: 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    width: 100%;
  }
  .btn-primary:hover { background: #4f46e5; }

  .btn-secondary {
    background: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    padding: 8px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    width: 100%;
  }
  .btn-secondary:hover { background: #334155; color: #e2e8f0; }
</style>

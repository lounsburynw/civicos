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
        <span class="label">Status</span>
        <span class="sign-in-status" class:signed-in={identity.isUnlocked}>
          {identity.isUnlocked ? 'Signed in' : 'Signed out'}
        </span>
      </div>
      <div class="row">
        <span class="label">ID</span>
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
    border-bottom: 1px solid var(--civic-border-divider);
  }

  h1 {
    font-size: 16px;
    font-weight: 700;
    color: var(--civic-text-bright);
  }

  .status {
    text-align: center;
    padding: 16px;
    color: var(--civic-text-muted);
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
    color: var(--civic-text-dim);
    text-transform: uppercase;
    font-weight: 500;
  }

  .sign-in-status {
    font-size: 12px;
    color: var(--civic-status-error);
    font-weight: 500;
  }
  .sign-in-status.signed-in { color: var(--civic-status-success); }

  .npub {
    font-family: var(--civic-font-family-mono);
    font-size: 11px;
    color: var(--civic-text-muted);
  }

  .no-identity {
    text-align: center;
    padding: 16px;
  }
  .no-identity p { color: var(--civic-text-muted); font-size: 13px; }

  .actions {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .btn-primary {
    background: var(--civic-accent-indigo);
    color: white;
    border: none;
    padding: 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    width: 100%;
  }
  .btn-primary:hover { background: var(--civic-accent-indigo-hover); }

  .btn-secondary {
    background: var(--civic-border-divider);
    color: var(--civic-text-muted);
    border: 1px solid var(--civic-border-default);
    padding: 8px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    width: 100%;
  }
  .btn-secondary:hover { background: var(--civic-border-default); color: var(--civic-text-secondary); }
</style>

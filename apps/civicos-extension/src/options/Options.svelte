<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo, IdentityTier } from '../lib/providers/types.js';

  // State
  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);
  let statusMessage = $state('');
  let statusType: 'success' | 'error' | '' = $state('');

  // Create flow
  let selectedTier: IdentityTier = $state('easy');
  let email = $state('');
  let password = $state('');
  let confirmPassword = $state('');
  let mnemonic = $state('');
  let showMnemonic = $state('');
  let creating = $state(false);

  // Import flow
  let showImport = $state(false);
  let importTier: IdentityTier = $state('private');
  let importPassword = $state('');
  let importMnemonic = $state('');
  let importEmail = $state('');
  let importing = $state(false);

  // Unlock
  let unlockPassword = $state('');
  let unlocking = $state(false);

  // Status timer handle — clear old timer before setting new one
  let statusTimer: ReturnType<typeof setTimeout> | null = null;

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

  function setStatus(msg: string, type: 'success' | 'error') {
    if (statusTimer) clearTimeout(statusTimer);
    statusMessage = msg;
    statusType = type;
    statusTimer = setTimeout(() => { statusMessage = ''; statusType = ''; statusTimer = null; }, 5000);
  }

  async function createIdentity() {
    if (selectedTier === 'easy' && !email) {
      setStatus('Email is required for Easy mode', 'error');
      return;
    }
    if (selectedTier === 'private') {
      if (!password) {
        setStatus('Password is required for Private mode', 'error');
        return;
      }
      if (password !== confirmPassword) {
        setStatus('Passwords do not match', 'error');
        return;
      }
    }

    creating = true;
    const passwordOrEmail = selectedTier === 'easy' ? email : password;

    const response = await sendMessage<{ identity: IdentityInfo; mnemonic?: string }>({
      type: 'CREATE_IDENTITY',
      tier: selectedTier,
      passwordOrEmail,
    });

    if (response.success) {
      identity = { ...response.data.identity, isUnlocked: true };
      if (response.data.mnemonic) {
        showMnemonic = response.data.mnemonic;
      }
      setStatus('Identity created', 'success');
      // Clear form
      email = '';
      password = '';
      confirmPassword = '';

    } else {
      setStatus(response.error, 'error');
    }
    creating = false;
  }

  async function handleImport() {
    if (importTier === 'easy' && !importEmail) {
      setStatus('Email is required to recover Easy mode identity', 'error');
      return;
    }
    if (importTier === 'private') {
      if (!importPassword || !importMnemonic) {
        setStatus('Password and mnemonic are required to import Private mode identity', 'error');
        return;
      }
    }

    importing = true;
    const response = await sendMessage<IdentityInfo>({
      type: 'IMPORT_IDENTITY',
      tier: importTier,
      passwordOrEmail: importTier === 'easy' ? importEmail : importPassword,
      mnemonic: importTier === 'private' ? importMnemonic : undefined,
    });

    if (response.success) {
      identity = { ...response.data, isUnlocked: true };
      setStatus('Identity imported', 'success');
      showImport = false;
      importPassword = '';
      importMnemonic = '';
      importEmail = '';
    } else {
      setStatus(response.error, 'error');
    }
    importing = false;
  }

  async function unlock() {
    // Easy mode uses biometric (no password needed), Private mode requires password
    if (identity?.tier === 'private' && !unlockPassword) {
      setStatus('Enter your password to unlock', 'error');
      return;
    }
    unlocking = true;

    const response = await sendMessage<boolean>({
      type: 'UNLOCK',
      password: unlockPassword,
    });

    if (response.success && response.data) {
      if (identity) identity = { ...identity, isUnlocked: true };
      setStatus('Identity unlocked', 'success');
    } else {
      const msg = identity?.tier === 'easy'
        ? 'Failed to unlock. Passkey authentication failed.'
        : 'Failed to unlock. Wrong password?';
      setStatus(msg, 'error');
    }
    unlockPassword = '';
    unlocking = false;
  }

  async function lock() {
    await sendMessage({ type: 'LOCK' });
    if (identity) identity = { ...identity, isUnlocked: false };
  }

  async function deleteIdentity() {
    if (!confirm('Delete your identity? This cannot be undone. Make sure you have your recovery phrase backed up.')) {
      return;
    }

    await sendMessage({ type: 'DELETE_IDENTITY' });
    identity = null;
    showMnemonic = '';
    setStatus('Identity deleted', 'success');
  }

  function truncateNpub(npub: string): string {
    if (npub.length <= 20) return npub;
    return npub.slice(0, 12) + '...' + npub.slice(-8);
  }

  function formatDate(timestamp: number): string {
    return new Date(timestamp).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  }

  loadIdentity();
</script>

<div class="options">
  <h1>CivicOS Identity</h1>

  <div class="toast" class:visible={!!statusMessage} class:success={statusType === 'success'} class:error={statusType === 'error'}>
    {statusMessage}
  </div>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if identity}
    <!-- Current identity display -->
    <section class="card">
      <h2>Current Identity</h2>
      <div class="info-grid">
        <div class="info-row">
          <span class="info-label">Tier</span>
          <span class="tier-badge" class:easy={identity.tier === 'easy'} class:private={identity.tier === 'private'}>
            {identity.tier}
          </span>
        </div>
        <div class="info-row">
          <span class="info-label">Status</span>
          <span class="lock-status" class:unlocked={identity.isUnlocked}>
            {identity.isUnlocked ? 'Unlocked' : 'Locked'}
          </span>
        </div>
        <div class="info-row">
          <span class="info-label">npub</span>
          <span class="npub" title={identity.npub}>{truncateNpub(identity.npub)}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Created</span>
          <span>{formatDate(identity.createdAt)}</span>
        </div>
      </div>

      {#if showMnemonic}
        <div class="mnemonic-warning">
          <h3>Recovery Phrase - SAVE THIS NOW</h3>
          <p>Write down these 12 words in order. You will need them to recover your identity.</p>
          <div class="mnemonic-words">{showMnemonic}</div>
          <button class="btn-secondary" onclick={() => { showMnemonic = ''; }}>
            I've saved my recovery phrase
          </button>
        </div>
      {/if}

      <div class="action-buttons">
        <!-- Always render both, toggle with CSS to avoid DOM flicker -->
        <button class="btn-secondary" style:display={identity.isUnlocked ? '' : 'none'} onclick={lock}>Lock</button>

        {#if !identity.isUnlocked && identity.tier === 'easy'}
          <button class="btn-primary" onclick={unlock} disabled={unlocking}>
            {unlocking ? 'Authenticating...' : 'Unlock with Passkey'}
          </button>
        {/if}

        <form class="unlock-form" style:display={!identity.isUnlocked && identity.tier === 'private' ? 'flex' : 'none'} autocomplete="off" onsubmit={(e: Event) => { e.preventDefault(); unlock(); }}>
          <input
            id="unlock-password"
            name="unlock-password"
            type="password"
            autocomplete="off"
            placeholder="Enter password"
            bind:value={unlockPassword}
          />
          <button type="submit" class="btn-primary" disabled={unlocking}>
            {unlocking ? 'Unlocking...' : 'Unlock'}
          </button>
        </form>

        <button class="btn-danger" onclick={deleteIdentity}>Delete Identity</button>
      </div>
    </section>
  {:else}
    <!-- Create new identity -->
    <section class="card">
      <h2>Create Identity</h2>

      <div class="tier-selector">
        <label class="tier-option" class:selected={selectedTier === 'easy'}>
          <input type="radio" bind:group={selectedTier} value="easy" />
          <div class="tier-content">
            <span class="tier-name">Easy Mode</span>
            <span class="tier-desc">Passkey (TouchID/FaceID) — lowest friction, cloud-synced recovery</span>
          </div>
        </label>
        <label class="tier-option" class:selected={selectedTier === 'private'}>
          <input type="radio" bind:group={selectedTier} value="private" />
          <div class="tier-content">
            <span class="tier-name">Private Mode</span>
            <span class="tier-desc">Password + 12-word recovery phrase — local only, you control the keys</span>
          </div>
        </label>
      </div>

      {#if selectedTier === 'easy'}
        <div class="form-group">
          <label for="email">Email (used as recovery salt)</label>
          <input id="email" type="email" placeholder="you@example.com" bind:value={email} />
        </div>
      {:else}
        <div class="form-group">
          <label for="password">Password</label>
          <input id="password" type="password" placeholder="Choose a strong password" bind:value={password} />
        </div>
        <div class="form-group">
          <label for="confirmPassword">Confirm Password</label>
          <input id="confirmPassword" type="password" placeholder="Confirm password" bind:value={confirmPassword} />
        </div>
      {/if}

      <button class="btn-primary" onclick={createIdentity} disabled={creating}>
        {creating ? 'Creating...' : 'Create Identity'}
      </button>

      <div class="divider">
        <span>or</span>
      </div>

      <button class="btn-secondary" onclick={() => { showImport = !showImport; }}>
        {showImport ? 'Cancel Import' : 'Import Existing Identity'}
      </button>

      {#if showImport}
        <div class="import-form">
          <div class="tier-selector">
            <label class="tier-option" class:selected={importTier === 'easy'}>
              <input type="radio" bind:group={importTier} value="easy" />
              <div class="tier-content">
                <span class="tier-name">Easy</span>
              </div>
            </label>
            <label class="tier-option" class:selected={importTier === 'private'}>
              <input type="radio" bind:group={importTier} value="private" />
              <div class="tier-content">
                <span class="tier-name">Private</span>
              </div>
            </label>
          </div>

          {#if importTier === 'easy'}
            <div class="form-group">
              <label for="importEmail">Email</label>
              <input id="importEmail" type="email" placeholder="Same email used during creation" bind:value={importEmail} />
            </div>
          {:else}
            <div class="form-group">
              <label for="importPassword">Password</label>
              <input id="importPassword" type="password" placeholder="New password to encrypt" bind:value={importPassword} />
            </div>
            <div class="form-group">
              <label for="importMnemonic">Recovery Phrase (12 words)</label>
              <textarea id="importMnemonic" rows="3" placeholder="word1 word2 word3 ..." bind:value={importMnemonic}></textarea>
            </div>
          {/if}

          <button class="btn-primary" onclick={handleImport} disabled={importing}>
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .options {
    max-width: 480px;
    margin: 0 auto;
    padding: 32px 24px;
  }

  h1 {
    font-size: 24px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 24px;
  }

  h2 {
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
    margin-bottom: 16px;
  }

  .loading {
    text-align: center;
    padding: 32px;
    color: #94a3b8;
  }

  .toast {
    position: fixed;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 13px;
    z-index: 100;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;
  }
  .toast.visible { opacity: 1; pointer-events: auto; }
  .toast.success { background: #064e3b; color: #6ee7b7; }
  .toast.error { background: #450a0a; color: #fca5a5; }

  .card {
    background: #1e293b;
    border-radius: 12px;
    padding: 20px;
  }

  .info-grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 16px;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .info-label {
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

  .mnemonic-warning {
    background: #422006;
    border: 1px solid #854d0e;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
  }
  .mnemonic-warning h3 {
    color: #fbbf24;
    font-size: 14px;
    margin-bottom: 8px;
  }
  .mnemonic-warning p {
    font-size: 12px;
    color: #fde68a;
    margin-bottom: 12px;
  }
  .mnemonic-words {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 14px;
    color: #fef3c7;
    background: #1c1917;
    padding: 12px;
    border-radius: 6px;
    margin-bottom: 12px;
    word-spacing: 6px;
    line-height: 1.8;
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .unlock-form {
    display: flex;
    gap: 8px;
  }
  .unlock-form input {
    flex: 1;
    min-width: 0;
  }
  .unlock-form button {
    width: auto;
    flex-shrink: 0;
  }

  .tier-selector {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .tier-option {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
    border: 1px solid #334155;
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .tier-option:hover { border-color: #475569; }
  .tier-option.selected { border-color: #6366f1; background: #1e1b4b; }
  .tier-option input { margin-top: 3px; }

  .tier-content {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .tier-name { font-size: 14px; font-weight: 500; color: #f8fafc; }
  .tier-desc { font-size: 12px; color: #94a3b8; }

  .form-group {
    margin-bottom: 12px;
  }
  .form-group label {
    display: block;
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 4px;
  }

  input, textarea {
    width: 100%;
    padding: 10px 12px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 13px;
    outline: none;
  }
  input:focus, textarea:focus { border-color: #6366f1; }
  textarea { resize: vertical; font-family: 'SF Mono', 'Fira Code', monospace; }

  .btn-primary {
    background: #6366f1;
    color: white;
    border: none;
    padding: 10px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    width: 100%;
  }
  .btn-primary:hover { background: #4f46e5; }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-secondary {
    background: transparent;
    color: #94a3b8;
    border: 1px solid #334155;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    width: 100%;
  }
  .btn-secondary:hover { background: #334155; color: #e2e8f0; }

  .btn-danger {
    background: transparent;
    color: #ef4444;
    border: 1px solid #7f1d1d;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    width: 100%;
  }
  .btn-danger:hover { background: #7f1d1d; color: #fca5a5; }

  .divider {
    text-align: center;
    margin: 16px 0;
    position: relative;
  }
  .divider::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    border-top: 1px solid #334155;
  }
  .divider span {
    position: relative;
    background: #1e293b;
    padding: 0 12px;
    font-size: 12px;
    color: #64748b;
  }

  .import-form {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #334155;
  }
</style>

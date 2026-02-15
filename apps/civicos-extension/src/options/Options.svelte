<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo, IdentityTier } from '../lib/providers/types.js';
  import { AIManager } from '../lib/ai/manager.js';
  import type { AITier } from '../lib/ai/types.js';

  // State
  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);
  let statusMessage = $state('');
  let statusType: 'success' | 'error' | '' = $state('');

  // AI provider state
  const aiManager = new AIManager();
  let aiTier: AITier = $state('device');
  let aiProviderStatuses: Array<{
    id: string; name: string; tier: string;
    available: boolean; ready: boolean; active: boolean;
  }> = $state([]);
  let aiApiKey = $state('');
  let aiCloudProProvider: 'claude' | 'openai' = $state('claude');
  let aiSaving = $state(false);
  let aiTesting = $state(false);

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

  async function loadAIStatus() {
    await aiManager.initialize();
    aiProviderStatuses = await aiManager.checkStatus();

    // Reflect current active provider in tier selection
    const active = aiProviderStatuses.find(p => p.active);
    if (active) {
      aiTier = active.tier as AITier;
      if (active.tier === 'cloud-pro') {
        aiCloudProProvider = active.id as 'claude' | 'openai';
      }
    } else {
      // No active provider — default to a tier that's actionable
      const nanoAvailable = aiProviderStatuses.find(p => p.id === 'chrome-nano')?.available;
      aiTier = nanoAvailable ? 'device' : 'cloud-free';
    }

    // Load stored API key for the current view
    await loadCurrentApiKey();
  }

  async function loadCurrentApiKey() {
    const storage = aiManager.getStorage();
    if (aiTier === 'cloud-free') {
      const config = await storage.getConfig('gemini');
      aiApiKey = config.apiKey ?? '';
    } else if (aiTier === 'cloud-pro') {
      const config = await storage.getConfig(aiCloudProProvider);
      aiApiKey = config.apiKey ?? '';
    } else {
      aiApiKey = '';
    }
  }

  async function saveAIProvider() {
    aiSaving = true;
    try {
      if (aiTier === 'device') {
        const nano = aiManager.getProvider('chrome-nano');
        if (nano && await nano.isReady()) {
          await aiManager.setActiveProvider('chrome-nano');
          setStatus('AI provider set to Chrome Built-in AI', 'success');
        } else {
          setStatus('Chrome Built-in AI is not available in this browser', 'error');
        }
      } else if (aiTier === 'cloud-free') {
        if (!aiApiKey.trim()) {
          setStatus('API key is required', 'error');
          aiSaving = false;
          return;
        }
        const gemini = aiManager.getProvider('gemini');
        if (gemini) {
          await gemini.configure({ apiKey: aiApiKey.trim() });
          await aiManager.setActiveProvider('gemini');
          setStatus('AI provider set to Google Gemini', 'success');
        }
      } else if (aiTier === 'cloud-pro') {
        if (!aiApiKey.trim()) {
          setStatus('API key is required', 'error');
          aiSaving = false;
          return;
        }
        const provider = aiManager.getProvider(aiCloudProProvider);
        if (provider) {
          await provider.configure({ apiKey: aiApiKey.trim() });
          await aiManager.setActiveProvider(aiCloudProProvider);
          setStatus(`AI provider set to ${provider.name}`, 'success');
        }
      }
      aiProviderStatuses = await aiManager.checkStatus();
    } catch (err) {
      setStatus(`Failed to save: ${err instanceof Error ? err.message : 'unknown error'}`, 'error');
    }
    aiSaving = false;
  }

  async function testAIProvider() {
    aiTesting = true;
    try {
      const result = await aiManager.complete('Say "hello" in one word.', 'You are a test assistant.');
      if (result.success) {
        setStatus(`AI test passed (${result.provider}): "${result.text?.slice(0, 50)}"`, 'success');
      } else {
        setStatus(`AI test failed: ${result.error}`, 'error');
      }
    } catch (err) {
      setStatus(`AI test error: ${err instanceof Error ? err.message : 'unknown'}`, 'error');
    }
    aiTesting = false;
  }

  async function clearAIProvider() {
    const providerId = aiTier === 'cloud-free' ? 'gemini' : aiCloudProProvider;
    const provider = aiManager.getProvider(providerId);
    if (provider) {
      await provider.clearConfig();
      aiApiKey = '';
      aiProviderStatuses = await aiManager.checkStatus();
      setStatus(`Cleared ${provider.name} configuration`, 'success');
    }
  }

  loadIdentity();
  loadAIStatus();
</script>

<div class="options">
  <h1>CivicOS Settings</h1>

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

  <!-- AI Provider Configuration -->
  <section class="card ai-section">
    <h2>AI Drafting Provider</h2>
    <p class="section-desc">Choose how AI-powered comment drafting works. Higher tiers require an API key.</p>

    <div class="tier-selector">
      <label class="tier-option" class:selected={aiTier === 'device'}>
        <input type="radio" bind:group={aiTier} value="device" onchange={() => loadCurrentApiKey()} />
        <div class="tier-content">
          <div class="tier-name-row">
            <span class="tier-name">On-Device</span>
            {#if aiProviderStatuses.find(p => p.id === 'chrome-nano')?.ready}
              <span class="status-dot ready"></span>
            {:else}
              <span class="status-dot unavailable"></span>
            {/if}
          </div>
          <span class="tier-desc">Chrome Built-in AI (Gemini Nano). Free, private, no API key. Requires Chrome 138+.</span>
        </div>
      </label>
      <label class="tier-option" class:selected={aiTier === 'cloud-free'}>
        <input type="radio" bind:group={aiTier} value="cloud-free" onchange={() => loadCurrentApiKey()} />
        <div class="tier-content">
          <div class="tier-name-row">
            <span class="tier-name">Google Gemini</span>
            {#if aiProviderStatuses.find(p => p.id === 'gemini')?.ready}
              <span class="status-dot ready"></span>
            {/if}
          </div>
          <span class="tier-desc">Free API key from AI Studio. Fast cloud inference.</span>
        </div>
      </label>
      <label class="tier-option" class:selected={aiTier === 'cloud-pro'}>
        <input type="radio" bind:group={aiTier} value="cloud-pro" onchange={() => loadCurrentApiKey()} />
        <div class="tier-content">
          <div class="tier-name-row">
            <span class="tier-name">Claude / OpenAI</span>
            {#if aiProviderStatuses.find(p => p.id === 'claude')?.ready || aiProviderStatuses.find(p => p.id === 'openai')?.ready}
              <span class="status-dot ready"></span>
            {/if}
          </div>
          <span class="tier-desc">Premium models. Requires a paid API key.</span>
        </div>
      </label>
    </div>

    {#if aiTier === 'device'}
      <div class="ai-config-note">
        {#if aiProviderStatuses.find(p => p.id === 'chrome-nano')?.available}
          Chrome Built-in AI is available. No configuration needed.
        {:else}
          Chrome Built-in AI is not available. You need Chrome 138+ with the Prompt API enabled.
        {/if}
      </div>
    {:else if aiTier === 'cloud-free'}
      <div class="form-group">
        <label for="gemini-key">Gemini API Key</label>
        <input id="gemini-key" type="password" placeholder="AIza..." bind:value={aiApiKey} />
        <span class="form-hint">Free from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com</a></span>
      </div>
    {:else if aiTier === 'cloud-pro'}
      <div class="form-group">
        <label for="pro-provider">Provider</label>
        <div class="radio-row">
          <label class="radio-label">
            <input type="radio" bind:group={aiCloudProProvider} value="claude" onchange={() => loadCurrentApiKey()} />
            Claude
          </label>
          <label class="radio-label">
            <input type="radio" bind:group={aiCloudProProvider} value="openai" onchange={() => loadCurrentApiKey()} />
            OpenAI
          </label>
        </div>
      </div>
      <div class="form-group">
        <label for="pro-key">{aiCloudProProvider === 'claude' ? 'Anthropic' : 'OpenAI'} API Key</label>
        <input id="pro-key" type="password" placeholder={aiCloudProProvider === 'claude' ? 'sk-ant-...' : 'sk-...'} bind:value={aiApiKey} />
        <span class="form-hint">
          {#if aiCloudProProvider === 'claude'}
            From <a href="https://console.anthropic.com" target="_blank" rel="noopener">console.anthropic.com</a>
          {:else}
            From <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener">platform.openai.com</a>
          {/if}
        </span>
      </div>
      <div class="key-warning">API keys are stored in your browser's local storage (unencrypted).</div>
    {/if}

    <div class="ai-action-buttons">
      <button class="btn-primary" onclick={saveAIProvider} disabled={aiSaving}>
        {aiSaving ? 'Saving...' : 'Save'}
      </button>
      {#if aiTier !== 'device'}
        <button class="btn-secondary" onclick={testAIProvider} disabled={aiTesting || !aiApiKey.trim()}>
          {aiTesting ? 'Testing...' : 'Test'}
        </button>
        <button class="btn-secondary" onclick={clearAIProvider}>
          Clear
        </button>
      {/if}
    </div>

    {#if aiProviderStatuses.some(p => p.active)}
      {@const active = aiProviderStatuses.find(p => p.active)}
      <div class="active-provider-badge">
        Active: {active?.name}
      </div>
    {/if}
  </section>
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

  /* AI Provider Section */
  .ai-section {
    margin-top: 24px;
  }

  .section-desc {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 16px;
  }

  .tier-name-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-dot.ready { background: #22c55e; }
  .status-dot.unavailable { background: #64748b; }

  .ai-config-note {
    font-size: 12px;
    color: #94a3b8;
    padding: 12px;
    background: #0f172a;
    border-radius: 6px;
    margin-bottom: 12px;
  }

  .form-hint {
    display: block;
    font-size: 11px;
    color: #64748b;
    margin-top: 4px;
  }
  .form-hint a {
    color: #818cf8;
    text-decoration: none;
  }
  .form-hint a:hover {
    text-decoration: underline;
  }

  .radio-row {
    display: flex;
    gap: 16px;
    margin-top: 4px;
  }

  .radio-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: #e2e8f0;
    cursor: pointer;
  }

  .key-warning {
    font-size: 11px;
    color: #fbbf24;
    margin-bottom: 12px;
  }

  .ai-action-buttons {
    display: flex;
    gap: 8px;
  }
  .ai-action-buttons .btn-primary,
  .ai-action-buttons .btn-secondary {
    width: auto;
    flex: 1;
  }

  .active-provider-badge {
    margin-top: 12px;
    text-align: center;
    font-size: 12px;
    color: #22c55e;
    padding: 6px;
    background: rgba(34, 197, 94, 0.08);
    border-radius: 6px;
  }
</style>

<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import { createExtensionAIManager } from '../lib/ai.js';
  import { registry } from '../lib/client.js';
  import type { RegistryServer } from '@civicos/client';

  // State
  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);
  let statusMessage = $state('');
  let statusType: 'success' | 'error' | '' = $state('');

  // Jurisdiction state
  let selectedJurisdiction = $state('');
  let availableServers: RegistryServer[] = $state([]);
  let jurisdictionSaving = $state(false);

  // AI provider state
  const aiManager = createExtensionAIManager();
  let aiProviderStatuses: Array<{
    id: string; name: string; tier: string;
    available: boolean; ready: boolean; active: boolean;
  }> = $state([]);
  let aiApiKey = $state('');
  let aiCloudProProvider: 'civicos' | 'claude' | 'openai' = $state('civicos');
  let aiSaving = $state(false);
  let aiTesting = $state(false);

  // Create flow
  let password = $state('');
  let confirmPassword = $state('');
  let showMnemonic = $state('');
  let creating = $state(false);

  // Import flow
  let showImport = $state(false);
  let importPassword = $state('');
  let importMnemonic = $state('');
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
    if (!password) {
      setStatus('Password is required', 'error');
      return;
    }
    if (password !== confirmPassword) {
      setStatus('Passwords do not match', 'error');
      return;
    }

    creating = true;
    const response = await sendMessage<{ identity: IdentityInfo; mnemonic?: string }>({
      type: 'CREATE_IDENTITY',
      tier: 'private',
      passwordOrEmail: password,
    });

    if (response.success) {
      identity = { ...response.data.identity, isUnlocked: true };
      if (response.data.mnemonic) {
        showMnemonic = response.data.mnemonic;
      }
      setStatus('Identity created', 'success');
      password = '';
      confirmPassword = '';
    } else {
      setStatus(response.error, 'error');
    }
    creating = false;
  }

  async function handleImport() {
    if (!importPassword || !importMnemonic) {
      setStatus('Password and recovery phrase are required to import', 'error');
      return;
    }

    importing = true;
    const response = await sendMessage<IdentityInfo>({
      type: 'IMPORT_IDENTITY',
      tier: 'private',
      passwordOrEmail: importPassword,
      mnemonic: importMnemonic,
    });

    if (response.success) {
      identity = { ...response.data, isUnlocked: true };
      setStatus('Identity imported', 'success');
      showImport = false;
      importPassword = '';
      importMnemonic = '';
    } else {
      setStatus(response.error, 'error');
    }
    importing = false;
  }

  async function unlock() {
    if (!unlockPassword) {
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
      setStatus('Failed to unlock. Wrong password?', 'error');
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

    const active = aiProviderStatuses.find(p => p.active);
    if (active) {
      aiCloudProProvider = active.id as 'civicos' | 'claude' | 'openai';
    }

    await loadCurrentApiKey();
  }

  async function loadCurrentApiKey() {
    if (aiCloudProProvider === 'civicos') {
      aiApiKey = '';
      return;
    }
    const storage = aiManager.getStorage();
    const config = await storage.getConfig(aiCloudProProvider);
    aiApiKey = config.apiKey ?? '';
  }

  async function saveAIProvider() {
    aiSaving = true;
    try {
      if (aiCloudProProvider === 'civicos') {
        // CivicOS proxy — no API key needed, just activate
        await aiManager.setActiveProvider('civicos');
        setStatus('AI provider set to CivicOS (Built-in)', 'success');
      } else {
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
    const provider = aiManager.getProvider(aiCloudProProvider);
    if (provider) {
      await provider.clearConfig();
      aiApiKey = '';
      aiProviderStatuses = await aiManager.checkStatus();
      setStatus(`Cleared ${provider.name} configuration`, 'success');
    }
  }

  // Attestation state
  let attestationCode = $state('');
  let attestationVerifying = $state(false);
  let attestationEvent: Record<string, unknown> | null = $state(null);
  let attestationDate: string | null = $state(null);

  async function loadAttestationStatus() {
    // Check local storage first
    const stored = await chrome.storage.local.get('civicos_attestation');
    if (stored.civicos_attestation) {
      attestationEvent = stored.civicos_attestation;
      const createdAt = (attestationEvent as Record<string, unknown>)?.created_at;
      if (typeof createdAt === 'number') {
        attestationDate = new Date(createdAt * 1000).toLocaleDateString('en-US', {
          year: 'numeric', month: 'short', day: 'numeric',
        });
      }
      return;
    }

    // Check relay if identity is available
    if (identity?.isUnlocked) {
      try {
        const { api } = await import('../lib/client.js');
        // Need the hex pubkey — derive from npub
        const pubkeyResponse = await sendMessage<string | null>({ type: 'GET_PUBLIC_KEY' });
        if (pubkeyResponse.success && pubkeyResponse.data) {
          const status = await api.getAttestationStatus(pubkeyResponse.data);
          if (status.attested && status.attestation_event) {
            attestationEvent = status.attestation_event;
            attestationDate = status.attested_at
              ? new Date(status.attested_at).toLocaleDateString('en-US', {
                  year: 'numeric', month: 'short', day: 'numeric',
                })
              : null;
            await chrome.storage.local.set({ civicos_attestation: status.attestation_event });
          }
        }
      } catch {
        // Attestation check is optional
      }
    }
  }

  async function redeemAttestation() {
    if (!attestationCode.trim()) {
      setStatus('Enter a verification code', 'error');
      return;
    }
    attestationVerifying = true;
    try {
      const response = await sendMessage<Record<string, unknown>>({
        type: 'REDEEM_ATTESTATION',
        code: attestationCode.trim(),
      });
      if (response.success && response.data) {
        attestationEvent = response.data;
        const createdAt = (response.data as Record<string, unknown>)?.created_at;
        if (typeof createdAt === 'number') {
          attestationDate = new Date(createdAt * 1000).toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
          });
        }
        attestationCode = '';
        setStatus('Residency verified', 'success');
      } else {
        setStatus((response as { error?: string }).error || 'Verification failed', 'error');
      }
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Verification error', 'error');
    }
    attestationVerifying = false;
  }

  async function loadJurisdiction() {
    selectedJurisdiction = await registry.getActiveJurisdiction();
    try {
      availableServers = await registry.getRegistryServers();
    } catch {
      availableServers = [];
    }
  }

  async function saveJurisdiction() {
    if (!selectedJurisdiction) return;
    jurisdictionSaving = true;
    try {
      await registry.setActiveJurisdiction(selectedJurisdiction);
      setStatus(`Jurisdiction set to ${availableServers.find(s => s.jurisdiction_id === selectedJurisdiction)?.display_name || selectedJurisdiction}`, 'success');
    } catch (err) {
      setStatus('Failed to save jurisdiction', 'error');
    }
    jurisdictionSaving = false;
  }

  loadIdentity();
  loadAIStatus();
  loadJurisdiction();

  // Load attestation after identity loads
  $effect(() => {
    if (identity) {
      loadAttestationStatus();
    }
  });
</script>

<div class="options">
  <h1>CivicOS Settings</h1>

  <div class="toast" class:visible={!!statusMessage} class:success={statusType === 'success'} class:error={statusType === 'error'}>
    {statusMessage}
  </div>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if identity}
    <!-- Your Profile -->
    <section class="card profile-section">
      <h2>Your Profile</h2>

      <h3 class="subsection-label">Identity</h3>
      <div class="info-grid">
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
        <button class="btn-secondary" style:display={identity.isUnlocked ? '' : 'none'} onclick={lock}>Lock</button>

        <form class="unlock-form" style:display={!identity.isUnlocked ? 'flex' : 'none'} autocomplete="off" onsubmit={(e: Event) => { e.preventDefault(); unlock(); }}>
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
      </div>

      <hr class="subsection-divider" />

      <h3 class="subsection-label">Jurisdiction</h3>
      {#if availableServers.length > 0}
        <div class="form-group">
          <select id="jurisdiction-select" class="jurisdiction-select" bind:value={selectedJurisdiction}>
            {#each availableServers as server (server.jurisdiction_id)}
              <option value={server.jurisdiction_id}>
                {server.display_name} ({server.level})
              </option>
            {/each}
          </select>
        </div>

        {@const selectedServer = availableServers.find(s => s.jurisdiction_id === selectedJurisdiction)}
        {#if selectedServer?.parent_jurisdictions?.length}
          <div class="parent-info">
            Also showing: {selectedServer.parent_jurisdictions
              .map(pid => availableServers.find(s => s.jurisdiction_id === pid)?.display_name || pid)
              .join(', ')}
          </div>
        {/if}

        <button class="btn-primary" onclick={saveJurisdiction} disabled={jurisdictionSaving}>
          {jurisdictionSaving ? 'Saving...' : 'Save Jurisdiction'}
        </button>
      {:else}
        <div class="jurisdiction-loading">Loading available jurisdictions...</div>
      {/if}

      <hr class="subsection-divider" />

      <h3 class="subsection-label">Residency</h3>
      {#if attestationEvent}
        {@const selectedServer = availableServers.find(s => s.jurisdiction_id === selectedJurisdiction)}
        <div class="attested-badge">
          <span class="attested-check">&#10003;</span>
          Verified {selectedServer?.display_name || selectedJurisdiction} Resident
          {#if attestationDate}
            <span class="attested-date">{attestationDate}</span>
          {/if}
        </div>
        {#if selectedServer?.parent_jurisdictions?.length}
          <div class="residency-derived">
            Also recognized as {selectedServer.parent_jurisdictions
              .map(pid => availableServers.find(s => s.jurisdiction_id === pid)?.display_name || pid)
              .join(' and ')} resident
          </div>
        {/if}
      {:else if identity.isUnlocked}
        <p class="section-desc">Enter a code received at a civic event.</p>
        <form class="attestation-form" onsubmit={(e: Event) => { e.preventDefault(); redeemAttestation(); }}>
          <input
            type="text"
            placeholder="SR-2026-02-XXXX"
            bind:value={attestationCode}
            autocomplete="off"
          />
          <button type="submit" class="btn-primary" disabled={attestationVerifying || !attestationCode.trim()}>
            {attestationVerifying ? 'Verifying...' : 'Verify'}
          </button>
        </form>
      {:else}
        <p class="section-desc">Unlock your identity to verify your residency.</p>
      {/if}

      <hr class="subsection-divider" />

      <button class="btn-danger" onclick={deleteIdentity}>Delete Identity</button>
    </section>
  {:else}
    <!-- Create new identity -->
    <section class="card">
      <h2>Create Identity</h2>
      <p class="section-desc">Password + 12-word recovery phrase. Local only, you control the keys.</p>

      <div class="form-group">
        <label for="password">Password</label>
        <input id="password" type="password" placeholder="Choose a strong password" bind:value={password} />
      </div>
      <div class="form-group">
        <label for="confirmPassword">Confirm Password</label>
        <input id="confirmPassword" type="password" placeholder="Confirm password" bind:value={confirmPassword} />
      </div>

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
          <div class="form-group">
            <label for="importPassword">Password</label>
            <input id="importPassword" type="password" placeholder="New password to encrypt" bind:value={importPassword} />
          </div>
          <div class="form-group">
            <label for="importMnemonic">Recovery Phrase (12 words)</label>
            <textarea id="importMnemonic" rows="3" placeholder="word1 word2 word3 ..." bind:value={importMnemonic}></textarea>
          </div>

          <button class="btn-primary" onclick={handleImport} disabled={importing}>
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
      {/if}
    </section>
  {/if}

  <!-- Preferences -->
  <section class="card preferences-section">
    <h2>Preferences</h2>
    <h3 class="subsection-label">AI Drafting Provider</h3>
    <p class="section-desc">Choose an AI provider for comment drafting.</p>

    <div class="form-group">
      <label for="pro-provider">Provider</label>
      <div class="radio-row">
        <label class="radio-label">
          <input type="radio" bind:group={aiCloudProProvider} value="civicos" onchange={() => loadCurrentApiKey()} />
          CivicOS
          {#if aiProviderStatuses.find(p => p.id === 'civicos')?.ready}
            <span class="status-dot ready"></span>
          {/if}
        </label>
        <label class="radio-label">
          <input type="radio" bind:group={aiCloudProProvider} value="claude" onchange={() => loadCurrentApiKey()} />
          Claude
          {#if aiProviderStatuses.find(p => p.id === 'claude')?.ready}
            <span class="status-dot ready"></span>
          {/if}
        </label>
        <label class="radio-label">
          <input type="radio" bind:group={aiCloudProProvider} value="openai" onchange={() => loadCurrentApiKey()} />
          OpenAI
          {#if aiProviderStatuses.find(p => p.id === 'openai')?.ready}
            <span class="status-dot ready"></span>
          {/if}
        </label>
      </div>
    </div>

    {#if aiCloudProProvider === 'civicos'}
      <div class="civicos-provider-note">
        No API key needed — uses your CivicOS identity for authentication.
        {#if !identity?.isUnlocked}
          <span class="civicos-unlock-hint">Unlock your identity above to enable AI drafting.</span>
        {/if}
      </div>
    {:else}
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
      <button class="btn-secondary" onclick={testAIProvider} disabled={aiTesting || (aiCloudProProvider !== 'civicos' && !aiApiKey.trim())}>
        {aiTesting ? 'Testing...' : 'Test'}
      </button>
      {#if aiCloudProProvider !== 'civicos'}
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

  /* Subsection styles */
  .subsection-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
    margin: 0 0 12px 0;
  }

  .subsection-divider {
    border: none;
    border-top: 1px solid #334155;
    margin: 20px 0;
  }

  .residency-derived {
    font-size: 12px;
    color: #64748b;
    margin-top: 8px;
    padding-left: 26px;
  }

  .attested-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: #22c55e;
    background: rgba(34, 197, 94, 0.08);
    padding: 12px 16px;
    border-radius: 8px;
  }

  .attested-check {
    font-size: 18px;
    font-weight: bold;
  }

  .attested-date {
    margin-left: auto;
    font-size: 11px;
    color: #94a3b8;
  }

  .attestation-form {
    display: flex;
    gap: 8px;
  }
  .attestation-form input {
    flex: 1;
    min-width: 0;
    font-family: 'SF Mono', 'Fira Code', monospace;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .attestation-form .btn-primary {
    width: auto;
    flex-shrink: 0;
  }

  /* Preferences Section */
  .preferences-section {
    margin-top: 24px;
  }

  .section-desc {
    font-size: 12px;
    color: #94a3b8;
    margin-bottom: 16px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
  }
  .status-dot.ready { background: #22c55e; }

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

  .civicos-provider-note {
    font-size: 12px;
    color: #94a3b8;
    background: rgba(99, 102, 241, 0.08);
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 12px;
    line-height: 1.5;
  }

  .civicos-unlock-hint {
    display: block;
    margin-top: 4px;
    color: #fbbf24;
    font-size: 11px;
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

  .jurisdiction-select {
    width: 100%;
    padding: 10px 12px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #e2e8f0;
    font-size: 13px;
    outline: none;
    appearance: auto;
  }
  .jurisdiction-select:focus { border-color: #6366f1; }

  .jurisdiction-loading {
    font-size: 12px;
    color: #64748b;
    text-align: center;
    padding: 12px;
  }
  .parent-info {
    font-size: 12px;
    color: #94a3b8;
    margin: 8px 0;
    padding: 6px 10px;
    background: #1e293b;
    border-radius: 4px;
    border-left: 2px solid #6366f1;
  }
</style>

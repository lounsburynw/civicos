<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import { createExtensionAIManager } from '../lib/ai.js';
  import { registry } from '../lib/client.js';
  import type { RegistryServer } from '@civicos/client';
  import { personalMCP, type UserProfile } from '../lib/personal-mcp-client.js';

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

  // Ollama state
  let ollamaModel = $state('llama3.1:8b');
  let ollamaBaseUrl = $state('http://localhost:11434');
  let ollamaConnected = $state(false);
  let ollamaModels: string[] = $state([]);
  let ollamaSaving = $state(false);
  let ollamaTesting = $state(false);
  let ollamaForChat = $state(true);

  // Personal Hub state
  let hubConnected = $state(false);
  let hubLoading = $state(true);
  let hubProfile: UserProfile | null = $state(null);
  let hubName = $state('');
  let hubNeighborhood = $state('');
  let hubInterestsList: string[] = $state([]);
  let hubInterestInput = $state('');
  let hubSaving = $state(false);

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

  // Unlock (Sign in)
  let unlockPassword = $state('');
  let unlocking = $state(false);

  // Advanced section collapse
  let showAdvanced = $state(false);

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

  async function loadOllamaStatus() {
    // Load saved config
    const storage = aiManager.getStorage();
    const config = await storage.getConfig('ollama');
    if (config.apiKey) ollamaBaseUrl = config.apiKey; // apiKey field stores base URL
    if (config.model) ollamaModel = config.model;

    // Load chat preference (default: true)
    const prefs = await storage.getPreferences();
    ollamaForChat = prefs.useOllamaForChat !== false;

    // Check connection and list models
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      const resp = await fetch(`${ollamaBaseUrl}/api/tags`, { signal: controller.signal });
      clearTimeout(timeout);
      if (resp.ok) {
        const data = await resp.json();
        ollamaConnected = true;
        ollamaModels = (data.models || []).map((m: { name: string }) => m.name);
      } else {
        ollamaConnected = false;
        ollamaModels = [];
      }
    } catch {
      ollamaConnected = false;
      ollamaModels = [];
    }
  }

  async function saveOllama() {
    ollamaSaving = true;
    try {
      const provider = aiManager.getProvider('ollama');
      if (provider) {
        await provider.configure({
          apiKey: ollamaBaseUrl, // apiKey field stores base URL
          model: ollamaModel,
        });
        // Save chat preference
        const storage = aiManager.getStorage();
        const prefs = await storage.getPreferences();
        await storage.savePreferences({ ...prefs, useOllamaForChat: ollamaForChat });
        aiProviderStatuses = await aiManager.checkStatus();
        setStatus(`Ollama configured: ${ollamaModel}${ollamaForChat ? ' (chat enabled)' : ''}`, 'success');
      }
    } catch (err) {
      setStatus(`Failed to save: ${err instanceof Error ? err.message : 'unknown'}`, 'error');
    }
    ollamaSaving = false;
  }

  async function testOllama() {
    ollamaTesting = true;
    try {
      // Save config first so the provider picks it up
      const provider = aiManager.getProvider('ollama');
      if (provider) {
        await provider.configure({ apiKey: ollamaBaseUrl, model: ollamaModel });
      }
      const result = await aiManager.complete('Say "hello" in one word.', 'You are a test assistant.');
      // Check if Ollama actually handled it
      if (result.provider === 'ollama' && result.success) {
        setStatus(`Ollama test passed: "${result.text?.slice(0, 50)}"`, 'success');
      } else if (result.success) {
        // A different provider handled it — Ollama may not be ready
        setStatus(`Test used ${result.provider} instead of Ollama — check model name`, 'error');
      } else {
        setStatus(`Ollama test failed: ${result.error}`, 'error');
      }
    } catch (err) {
      setStatus(`Ollama test error: ${err instanceof Error ? err.message : 'unknown'}`, 'error');
    }
    ollamaTesting = false;
  }

  // Personal Hub functions
  async function loadPersonalHub() {
    hubLoading = true;
    hubConnected = await personalMCP.isAvailable();
    if (hubConnected) {
      try {
        hubProfile = await personalMCP.getProfile();
        hubName = hubProfile.name || '';
        hubNeighborhood = hubProfile.neighborhood || '';
        hubInterestsList = hubProfile.interests || [];
      } catch {
        hubProfile = null;
      }
    }
    hubLoading = false;
  }

  async function savePersonalProfile() {
    hubSaving = true;
    try {
      hubProfile = await personalMCP.setProfile({
        name: hubName || undefined,
        neighborhood: hubNeighborhood || undefined,
        interests: hubInterestsList,
      });
      setStatus('Profile saved to Personal Hub', 'success');
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to save profile', 'error');
    }
    hubSaving = false;
  }

  async function refreshPersonalHub() {
    personalMCP.invalidateCache();
    await loadPersonalHub();
  }

  function addInterest(value: string) {
    const trimmed = value.trim().toLowerCase();
    if (trimmed && !hubInterestsList.includes(trimmed)) {
      hubInterestsList = [...hubInterestsList, trimmed];
    }
    hubInterestInput = '';
  }

  function removeInterest(interest: string) {
    hubInterestsList = hubInterestsList.filter(i => i !== interest);
  }

  function handleInterestKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addInterest(hubInterestInput);
    } else if (e.key === 'Backspace' && hubInterestInput === '' && hubInterestsList.length > 0) {
      hubInterestsList = hubInterestsList.slice(0, -1);
    }
  }

  // Attestation state
  let attestationCode = $state('');
  let attestationVerifying = $state(false);
  let attestationEvent: Record<string, unknown> | null = $state(null);
  let attestationDate: string | null = $state(null);
  let attestationJurisdiction: string | null = $state(null);

  function extractAttestationJurisdiction(event: Record<string, unknown>): string | null {
    const tags = event?.tags;
    if (!Array.isArray(tags)) return null;
    const jTag = tags.find((t: unknown) => Array.isArray(t) && t[0] === 'j');
    return Array.isArray(jTag) && typeof jTag[1] === 'string' ? jTag[1] : null;
  }

  async function loadAttestationStatus() {
    // Check local storage first
    const stored = await chrome.storage.local.get('civicos_attestation');
    if (stored.civicos_attestation) {
      attestationEvent = stored.civicos_attestation;
      attestationJurisdiction = extractAttestationJurisdiction(stored.civicos_attestation);
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
            attestationJurisdiction = extractAttestationJurisdiction(status.attestation_event);
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
        attestationJurisdiction = extractAttestationJurisdiction(response.data);
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
      setStatus(`City set to ${availableServers.find(s => s.jurisdiction_id === selectedJurisdiction)?.display_name || selectedJurisdiction}`, 'success');
    } catch (err) {
      setStatus('Failed to save jurisdiction', 'error');
    }
    jurisdictionSaving = false;
  }

  // Auto-save jurisdiction on change
  let prevJurisdiction = '';
  $effect(() => {
    if (selectedJurisdiction && prevJurisdiction && selectedJurisdiction !== prevJurisdiction) {
      saveJurisdiction();
    }
    prevJurisdiction = selectedJurisdiction;
  });

  // AI section expand/collapse
  let showAISettings = $state(false);
  function getAIStatusSummary(): string {
    const active = aiProviderStatuses.find(p => p.active);
    if (active) return active.name;
    return 'Not configured';
  }

  loadIdentity();
  loadAIStatus();
  loadOllamaStatus();
  loadJurisdiction();
  loadPersonalHub();

  // Load attestation after identity loads
  $effect(() => {
    if (identity) {
      loadAttestationStatus();
    }
  });
</script>

<div class="options">
  <h1>Settings</h1>

  <div class="toast" class:visible={!!statusMessage} class:success={statusType === 'success'} class:error={statusType === 'error'}>
    {statusMessage}
  </div>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if identity}

    <!-- === ESSENTIALS: What every user needs === -->
    <section class="card">
      <!-- City selector -->
      {#if availableServers.length > 0}
        <div class="form-group">
          <label for="jurisdiction-select">Your city</label>
          <span class="field-desc">Determines what meetings, decisions, and issues you see</span>
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
            Also includes {selectedServer.parent_jurisdictions
              .map(pid => availableServers.find(s => s.jurisdiction_id === pid)?.display_name || pid)
              .join(', ')}
          </div>
        {/if}
      {/if}

      <!-- Sign in / Sign out -->
      <div class="form-group" style="margin-top: 16px;">
        <label>Account</label>
        {#if identity.isUnlocked}
          <div class="signed-in-bar">
            <span class="signed-in-dot"></span>
            <span class="signed-in-label">Signed in</span>
            {#if attestationEvent}
              <span class="verified-inline">Verified resident</span>
            {/if}
            <button class="btn-link" onclick={lock}>Sign out</button>
          </div>
        {:else}
          <span class="field-desc">Sign in to draft comments and participate</span>
          <form class="sign-in-form" autocomplete="off" onsubmit={(e: Event) => { e.preventDefault(); unlock(); }}>
            <input
              id="unlock-password"
              name="unlock-password"
              type="password"
              autocomplete="off"
              placeholder="Password"
              bind:value={unlockPassword}
            />
            <button type="submit" class="btn-primary btn-compact" disabled={unlocking}>
              {unlocking ? '...' : 'Sign in'}
            </button>
          </form>
        {/if}
      </div>

      {#if showMnemonic}
        <div class="mnemonic-warning">
          <h3>Recovery Phrase — Save This Now</h3>
          <p>Write down these 12 words in order. You'll need them to recover your account.</p>
          <div class="mnemonic-words">{showMnemonic}</div>
          <button class="btn-secondary" onclick={() => { showMnemonic = ''; }}>
            I've saved my recovery phrase
          </button>
        </div>
      {/if}

      <!-- Residency verification (only if signed in + not yet verified) -->
      {#if !attestationEvent && identity.isUnlocked}
        <div class="verify-row">
          <label>Verify residency</label>
          <span class="field-desc">Got a code at a civic event? Enter it to verify you're a local resident</span>
          <form class="attestation-form" onsubmit={(e: Event) => { e.preventDefault(); redeemAttestation(); }}>
            <input
              type="text"
              placeholder="e.g. SR-2026-02-XXXX"
              bind:value={attestationCode}
              autocomplete="off"
            />
            <button type="submit" class="btn-primary btn-compact" disabled={attestationVerifying || !attestationCode.trim()}>
              {attestationVerifying ? '...' : 'Verify'}
            </button>
          </form>
        </div>
      {/if}
    </section>

    <!-- === PROFILE: Personalization === -->
    {#if hubConnected}
      <section class="card section-gap">
        <h2>Personalize</h2>
        <p class="card-desc">Help CivicOS highlight what matters to you</p>

        <div class="form-group">
          <label for="hub-name">Name</label>
          <span class="field-desc">Shown when you comment on agenda items</span>
          <input id="hub-name" type="text" placeholder="Display name" bind:value={hubName} />
        </div>
        <div class="form-group">
          <label for="hub-neighborhood">Neighborhood</label>
          <span class="field-desc">We'll prioritize issues near you</span>
          <input id="hub-neighborhood" type="text" placeholder="e.g. Terra Linda" bind:value={hubNeighborhood} />
        </div>
        <div class="form-group">
          <label>Interests</label>
          <span class="field-desc">Topics you care about — matching items get highlighted in your feed</span>
          <div class="interest-pills-input">
            {#each hubInterestsList as interest}
              <span class="interest-pill">
                {interest}
                <button class="pill-remove" onclick={() => removeInterest(interest)} aria-label="Remove {interest}">&times;</button>
              </span>
            {/each}
            <input
              class="pill-text-input"
              type="text"
              placeholder={hubInterestsList.length === 0 ? 'Type a topic and press Enter' : 'Add more...'}
              bind:value={hubInterestInput}
              onkeydown={handleInterestKeydown}
              onblur={() => { if (hubInterestInput.trim()) addInterest(hubInterestInput); }}
            />
          </div>
        </div>
        <button class="btn-primary" onclick={savePersonalProfile} disabled={hubSaving}>
          {hubSaving ? 'Saving...' : 'Save'}
        </button>
      </section>
    {/if}

    <!-- === ADVANCED: Power user settings === -->
    <section class="card section-gap">
      <button class="section-toggle" onclick={() => { showAdvanced = !showAdvanced; }}>
        <div class="section-toggle-left">
          <h2 class="section-toggle-title">Advanced</h2>
          <span class="section-toggle-summary">
            AI: {getAIStatusSummary()}{ollamaConnected ? ' · Ollama' : ''}
          </span>
        </div>
        <span class="chevron-small" class:open={showAdvanced}></span>
      </button>

      {#if showAdvanced}
        <div class="section-expand-body">

          <!-- AI Provider -->
          <div class="advanced-group">
            <h3 class="advanced-group-title">Comment drafting AI</h3>
            <p class="advanced-group-desc">Choose which AI helps draft your public comments on agenda items</p>

            <div class="form-group">
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
                No setup needed — works with your CivicOS account.
                {#if !identity?.isUnlocked}
                  <span class="civicos-unlock-hint">Sign in above to enable.</span>
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
              <div class="key-warning">Keys stored locally in your browser (unencrypted).</div>
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
          </div>

          <hr class="subsection-divider" />

          <!-- Ollama -->
          <div class="advanced-group">
            <h3 class="advanced-group-title">On-device AI</h3>
            <p class="advanced-group-desc">Run AI privately on your computer using Ollama — no data leaves your machine</p>

            <div class="ollama-status" class:connected={ollamaConnected}>
              <span class="ollama-dot"></span>
              {ollamaConnected ? `Connected — ${ollamaModels.length} model${ollamaModels.length === 1 ? '' : 's'}` : 'Not connected'}
              <button class="ollama-refresh" onclick={loadOllamaStatus} title="Refresh">&#8635;</button>
            </div>

            {#if ollamaConnected}
              <div class="form-group">
                <label for="ollama-model">Model</label>
                {#if ollamaModels.length > 0}
                  <select id="ollama-model" bind:value={ollamaModel}>
                    {#each ollamaModels as model}
                      <option value={model}>{model}</option>
                    {/each}
                  </select>
                {:else}
                  <input id="ollama-model" type="text" placeholder="llama3.1:8b" bind:value={ollamaModel} />
                {/if}
              </div>

              <div class="form-group">
                <label for="ollama-url">Server URL</label>
                <input id="ollama-url" type="text" placeholder="http://localhost:11434" bind:value={ollamaBaseUrl} />
              </div>

              <label class="toggle-label">
                <input type="checkbox" bind:checked={ollamaForChat} />
                <span class="toggle-text">Use for chat search</span>
                <span class="toggle-hint">
                  {ollamaForChat
                    ? 'Chat queries stay on your device'
                    : 'Chat uses CivicOS cloud for better quality'}
                </span>
              </label>

              <div class="ai-action-buttons">
                <button class="btn-primary" onclick={saveOllama} disabled={ollamaSaving}>
                  {ollamaSaving ? 'Saving...' : 'Save'}
                </button>
                <button class="btn-secondary" onclick={testOllama} disabled={ollamaTesting}>
                  {ollamaTesting ? 'Testing...' : 'Test'}
                </button>
              </div>
            {:else}
              <div class="ollama-setup-hint">
                <ol>
                  <li>Install from <a href="https://ollama.com" target="_blank" rel="noopener">ollama.com</a></li>
                  <li>Run: <code>ollama pull llama3.1:8b</code></li>
                  <li>Click refresh above</li>
                </ol>
              </div>
            {/if}
          </div>

          <hr class="subsection-divider" />

          <!-- Identity -->
          <div class="advanced-group">
            <h3 class="advanced-group-title">Identity</h3>
            <div class="info-grid">
              <div class="info-row">
                <span class="info-label">Public key</span>
                <span class="npub" title={identity.npub}>{truncateNpub(identity.npub)}</span>
              </div>
              <div class="info-row">
                <span class="info-label">Created</span>
                <span>{formatDate(identity.createdAt)}</span>
              </div>
            </div>
          </div>

          <hr class="subsection-divider" />

          <!-- Recovery -->
          <div class="advanced-group">
            <h3 class="advanced-group-title">Recovery</h3>
            <p class="advanced-group-desc">Import an existing account using your 12-word recovery phrase</p>
            <button class="btn-secondary" onclick={() => { showImport = !showImport; }}>
              {showImport ? 'Cancel' : 'Recover Existing Account'}
            </button>

            {#if showImport}
              <div class="import-form">
                <div class="form-group">
                  <label for="importPassword">New Password</label>
                  <input id="importPassword" type="password" placeholder="Password to encrypt" bind:value={importPassword} />
                </div>
                <div class="form-group">
                  <label for="importMnemonic">Recovery Phrase (12 words)</label>
                  <textarea id="importMnemonic" rows="3" placeholder="word1 word2 word3 ..." bind:value={importMnemonic}></textarea>
                </div>
                <button class="btn-primary" onclick={handleImport} disabled={importing}>
                  {importing ? 'Recovering...' : 'Recover Account'}
                </button>
              </div>
            {/if}
          </div>

          <hr class="subsection-divider" />

          <!-- Danger zone -->
          <div class="advanced-group">
            <button class="btn-danger" onclick={deleteIdentity}>Delete Account</button>
            <span class="form-hint">This cannot be undone. Make sure you have your recovery phrase backed up.</span>
          </div>
        </div>
      {/if}
    </section>

  {:else}
    <!-- Create Account -->
    <section class="card">
      <h2>Get Started</h2>
      <p class="card-desc">Create an account to draft comments, verify your residency, and participate in local governance. Your data stays on your device.</p>

      <div class="form-group">
        <label for="password">Password</label>
        <input id="password" type="password" placeholder="Choose a password" bind:value={password} />
      </div>
      <div class="form-group">
        <label for="confirmPassword">Confirm password</label>
        <input id="confirmPassword" type="password" placeholder="Confirm password" bind:value={confirmPassword} />
      </div>

      <button class="btn-primary" onclick={createIdentity} disabled={creating}>
        {creating ? 'Creating...' : 'Create Account'}
      </button>

      <div class="divider">
        <span>or</span>
      </div>

      <button class="btn-secondary" onclick={() => { showImport = !showImport; }}>
        {showImport ? 'Cancel' : 'Recover Existing Account'}
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

</div>

<style>
  .options {
    max-width: 440px;
    margin: 0 auto;
    padding: 32px 20px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  }

  h1 {
    font-size: 20px;
    font-weight: 600;
    color: #e2e8f0;
    margin-bottom: 20px;
  }

  h2 {
    font-size: 14px;
    font-weight: 600;
    color: #cbd5e1;
    margin-bottom: 14px;
  }

  .card-desc {
    font-size: 12px;
    color: #64748b;
    margin: -8px 0 16px;
    line-height: 1.5;
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
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.4);
    border-radius: 10px;
    padding: 18px;
  }

  .field-desc {
    display: block;
    font-size: 11px;
    color: #64748b;
    margin-bottom: 6px;
    line-height: 1.4;
  }

  .verified-inline {
    font-size: 11px;
    color: #4ade80;
    margin-left: 4px;
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

  /* Sign in / Sign out bar */
  .signed-in-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: rgba(34, 197, 94, 0.06);
    border-radius: 6px;
    font-size: 13px;
    color: #22c55e;
  }
  .signed-in-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;
    flex-shrink: 0;
  }
  .signed-in-label {
    font-weight: 500;
  }
  .sign-in-form {
    display: flex;
    gap: 8px;
  }
  .sign-in-form input {
    flex: 1;
    min-width: 0;
  }
  .btn-link {
    background: none;
    border: none;
    color: #818cf8;
    font-size: 12px;
    cursor: pointer;
    padding: 0;
    margin-left: auto;
  }
  .btn-link:hover { text-decoration: underline; }
  .btn-compact {
    width: auto;
    flex-shrink: 0;
  }

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
    padding: 9px 11px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-radius: 8px;
    color: #e2e8f0;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
  }
  input:focus, textarea:focus { border-color: rgba(99, 102, 241, 0.6); }
  textarea { resize: vertical; font-family: 'SF Mono', 'Fira Code', monospace; }

  .btn-primary {
    background: rgba(99, 102, 241, 0.85);
    color: white;
    border: none;
    padding: 9px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    width: 100%;
    transition: background 0.15s;
  }
  .btn-primary:hover { background: rgba(79, 70, 229, 0.9); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

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
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
    margin: 0 0 10px 0;
  }

  .advanced-group {
    margin-bottom: 4px;
  }
  .advanced-group-title {
    font-size: 13px;
    font-weight: 600;
    color: #cbd5e1;
    margin: 0 0 4px 0;
  }
  .advanced-group-desc {
    font-size: 11px;
    color: #64748b;
    margin: 0 0 12px 0;
    line-height: 1.4;
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

  .section-gap {
    margin-top: 16px;
  }

  .verify-row {
    margin-top: 12px;
  }

  /* Collapsible section toggle */
  .section-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0;
    text-align: left;
  }
  .section-toggle:hover .section-toggle-title { color: #e2e8f0; }
  .section-toggle-left {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .section-toggle-title {
    font-size: 14px;
    font-weight: 600;
    color: #cbd5e1;
    margin: 0;
    transition: color 0.15s;
  }
  .section-toggle-summary {
    font-size: 12px;
    color: #64748b;
  }
  .section-expand-body {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #334155;
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

  /* Ollama section */
  .ollama-status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #ef4444;
    padding: 8px 12px;
    background: rgba(239, 68, 68, 0.06);
    border-radius: 6px;
    margin-bottom: 12px;
  }
  .ollama-status.connected {
    color: #22c55e;
    background: rgba(34, 197, 94, 0.06);
  }
  .ollama-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ef4444;
    flex-shrink: 0;
  }
  .ollama-status.connected .ollama-dot {
    background: #22c55e;
  }
  .ollama-refresh {
    margin-left: auto;
    background: none;
    border: none;
    color: inherit;
    font-size: 16px;
    cursor: pointer;
    padding: 0 4px;
    opacity: 0.7;
  }
  .ollama-refresh:hover { opacity: 1; }

  .toggle-label {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    margin-bottom: 12px;
    cursor: pointer;
  }
  .toggle-label input[type="checkbox"] {
    width: auto;
    accent-color: #6366f1;
  }
  .toggle-text {
    font-size: 13px;
    color: #e2e8f0;
    font-weight: 500;
  }
  .toggle-hint {
    width: 100%;
    font-size: 11px;
    color: #64748b;
    padding-left: 24px;
  }

  .ollama-privacy-note {
    font-size: 11px;
    color: #22c55e;
    background: rgba(34, 197, 94, 0.06);
    padding: 8px 12px;
    border-radius: 6px;
    margin-top: 12px;
    line-height: 1.5;
  }

  .ollama-setup-hint {
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.6;
  }
  .ollama-setup-hint ol {
    margin: 6px 0 0;
    padding-left: 18px;
  }
  .ollama-setup-hint li {
    margin-bottom: 4px;
  }
  .ollama-setup-hint code {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    background: #0f172a;
    padding: 2px 6px;
    border-radius: 3px;
    color: #e2e8f0;
  }
  .ollama-setup-hint a {
    color: #818cf8;
    text-decoration: none;
  }
  .ollama-setup-hint a:hover {
    text-decoration: underline;
  }

  select {
    width: 100%;
    padding: 9px 11px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-radius: 8px;
    color: #e2e8f0;
    font-size: 13px;
    outline: none;
    appearance: auto;
    transition: border-color 0.15s;
  }
  select:focus { border-color: rgba(99, 102, 241, 0.6); }

  /* Personal Hub (inline in Profile) */
  .hub-loading {
    font-size: 12px;
    color: #64748b;
    text-align: center;
    padding: 12px;
  }
  .hub-offline-hint {
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.6;
  }
  .hub-offline-hint p { margin: 0 0 8px; }
  .hub-command {
    display: block;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    background: #0f172a;
    padding: 8px 12px;
    border-radius: 6px;
    color: #e2e8f0;
    margin-bottom: 8px;
  }

  /* Interest pills */
  .interest-pills-input {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 10px;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.6);
    border-radius: 8px;
    min-height: 40px;
    align-items: center;
    cursor: text;
    transition: border-color 0.15s;
  }
  .interest-pills-input:focus-within {
    border-color: rgba(99, 102, 241, 0.6);
  }
  .interest-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px 3px 10px;
    background: rgba(99, 102, 241, 0.15);
    color: #a5b4fc;
    border-radius: 12px;
    font-size: 12px;
    white-space: nowrap;
    animation: pill-in 0.15s ease-out;
  }
  @keyframes pill-in {
    from { transform: scale(0.8); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
  }
  .pill-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    background: none;
    border: none;
    color: #818cf8;
    font-size: 14px;
    cursor: pointer;
    padding: 0;
    border-radius: 50%;
    line-height: 1;
  }
  .pill-remove:hover {
    background: rgba(99, 102, 241, 0.3);
    color: #e0e7ff;
  }
  .pill-text-input {
    flex: 1;
    min-width: 80px;
    background: none;
    border: none;
    color: #e2e8f0;
    font-size: 13px;
    outline: none;
    padding: 2px 0;
  }
  .pill-text-input::placeholder {
    color: #475569;
  }

  /* Chevron for collapsible sections */
  .chevron-small {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid #64748b;
    transition: transform 0.15s;
  }
  .chevron-small.open {
    transform: rotate(180deg);
  }
</style>

<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import { createExtensionAIManager } from '../lib/ai.js';
  import { registry } from '../lib/client.js';
  import type { RegistryServer } from '@civicos/client';
  import { marked } from 'marked';

  marked.setOptions({ breaks: true, gfm: true });

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
  let aiCloudProProvider: 'civicos' | 'claude' | 'openai' | 'ollama' = $state('civicos');
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

  // Profile state (chrome.storage.local — never leaves device)
  const PROFILE_KEY = 'civicos_profile';
  let profileName = $state('');
  let profileSaving = $state(false);

  // Civic Journal state (chrome.storage.local)
  const JOURNAL_KEY = 'civicos_journal';
  let journalText = $state('');
  let journalSaving = $state(false);
  let journalMode: 'edit' | 'preview' = $state('edit');

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
  let showAIPrivacy = $state(false);

  // Endpoints state
  let showEndpoints = $state(false);
  let resolvedMcpUrl = $state('');
  let resolvedRelayUrl = $state('');
  let mcpOverride = $state('');
  let relayOverride = $state('');
  let personalMcpUrl = $state('http://localhost:8081');
  let mcpHealth: 'unknown' | 'ok' | 'error' = $state('unknown');
  let relayHealth: 'unknown' | 'ok' | 'error' = $state('unknown');
  let personalMcpHealth: 'unknown' | 'ok' | 'error' = $state('unknown');
  let endpointsSaving = $state(false);
  let endpointsChecking = $state(false);

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

    // Ensure Ollama connection state is known before deciding provider
    await loadOllamaStatus();

    // Check if Ollama was the chosen provider (ollamaForChat + connected)
    const storage = aiManager.getStorage();
    const prefs = await storage.getPreferences();
    if (prefs.useOllamaForChat && ollamaConnected) {
      aiCloudProProvider = 'ollama';
    } else {
      const active = aiProviderStatuses.find(p => p.active);
      if (active && active.id !== 'ollama') {
        aiCloudProProvider = active.id as 'civicos' | 'claude' | 'openai';
      }
    }

    await loadCurrentApiKey();
  }

  async function loadCurrentApiKey() {
    if (aiCloudProProvider === 'civicos' || aiCloudProProvider === 'ollama') {
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
      if (aiCloudProProvider === 'ollama') {
        // Ollama — configure and enable for chat
        const provider = aiManager.getProvider('ollama');
        if (provider) {
          await provider.configure({
            apiKey: ollamaBaseUrl,
            model: ollamaModel,
          });
          const storage = aiManager.getStorage();
          const prefs = await storage.getPreferences();
          await storage.savePreferences({ ...prefs, useOllamaForChat: true });
          ollamaForChat = true;
          setStatus(`AI provider set to Ollama (${ollamaModel})`, 'success');
        }
      } else if (aiCloudProProvider === 'civicos') {
        // CivicOS proxy — no API key needed, just activate
        await aiManager.setActiveProvider('civicos');
        // Disable Ollama for chat when switching to cloud
        const storage = aiManager.getStorage();
        const prefs = await storage.getPreferences();
        await storage.savePreferences({ ...prefs, useOllamaForChat: false });
        ollamaForChat = false;
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
          // Disable Ollama for chat when switching to cloud
          const storage = aiManager.getStorage();
          const prefs = await storage.getPreferences();
          await storage.savePreferences({ ...prefs, useOllamaForChat: false });
          ollamaForChat = false;
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

  // Profile functions (chrome.storage.local)
  async function loadProfile() {
    try {
      const stored = await chrome.storage.local.get(PROFILE_KEY);
      const profile = stored[PROFILE_KEY] || {};
      profileName = profile.name || '';
    } catch {
      // Ignore — defaults are fine
    }
  }

  async function saveProfile() {
    profileSaving = true;
    try {
      await chrome.storage.local.set({
        [PROFILE_KEY]: {
          name: profileName || undefined,
        },
      });
      setStatus('Profile saved', 'success');
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to save profile', 'error');
    }
    profileSaving = false;
  }

  async function loadJournal() {
    try {
      const stored = await chrome.storage.local.get(JOURNAL_KEY);
      const text = stored[JOURNAL_KEY]?.text;
      if (text) {
        journalText = text;
      } else {
        journalText = JOURNAL_TEMPLATE;
        await chrome.storage.local.set({ [JOURNAL_KEY]: { text: JOURNAL_TEMPLATE } });
      }
    } catch {
      journalText = JOURNAL_TEMPLATE;
    }
  }

  async function saveJournal() {
    journalSaving = true;
    try {
      await chrome.storage.local.set({ [JOURNAL_KEY]: { text: journalText } });
      setStatus('Journal saved', 'success');
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to save journal', 'error');
    }
    journalSaving = false;
  }

  const JOURNAL_TEMPLATE = `# What I care about
- Housing affordability and preventing displacement
- Safe streets and bike infrastructure
- Public school funding and quality

# What I support
- Love the new parklet program on C Street — want to see more
- The library expansion has strong community backing, I'm in favor
- Marin Clean Energy's community solar initiative

# What frustrates me
- Encampment near Pickleweed Park — kids can't use the playground after school
- Construction on 4th Street stalled for weeks with no signage or timeline
- Water bill up 18% with no clear explanation of the rate structure

# What I'm following
- 2nd St bike lane proposal — support the concept but worried about small business parking
- Downtown precise plan update — concerned about 5-story buildings changing neighborhood character
- AB 1234 on ADU permitting — could affect my neighborhood directly
- Proposed FEMA flood map changes for Marin County

# My vision for the city
- San Rafael should be the most bikeable city in Marin
- Climate resilience should drive all infrastructure decisions
- We need more community spaces, not more luxury development

# My civic history
- Spoke at the 2024 housing element hearing
- Served on the bicycle/pedestrian advisory committee 2023-2024
- Regular at council meetings when housing or transit is on the agenda

# People and organizations I trust
- Councilmember Llorens on transit issues
- Marin Conservation League on environmental policy
- San Rafael Coalition for Better Housing

# How I want to engage
- I prefer written comments over speaking at meetings
- Notify me about relevant items — I'll decide when to act
- Draft comments in my voice: direct, specific, solution-oriented

# My perspective
- Parent and homeowner in Terra Linda
- Lived in San Rafael for 8 years
- Background in civil engineering — I understand infrastructure tradeoffs
- Active in school PTA
`;

  function applyJournalTemplate() {
    if (journalText.trim() && !confirm('Replace your current journal with the starter template?')) return;
    journalText = JOURNAL_TEMPLATE;
  }

  function exportJournal() {
    const blob = new Blob([journalText], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'civic-journal.md';
    a.click();
    URL.revokeObjectURL(url);
  }

  function importJournal() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.md,.txt';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const text = await file.text();
      journalText = text;
      setStatus(`Imported ${file.name}`, 'success');
    };
    input.click();
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

  async function loadEndpoints() {
    resolvedMcpUrl = await registry.getMcpUrl();
    resolvedRelayUrl = await registry.getRelayUrl();
    // Load overrides from chrome.storage.local (same backing store as ChromeStorageAdapter)
    const stored = await chrome.storage.local.get(['civicos_api_url', 'civicos_relay_url', 'civicos_personal_mcp_url']);
    mcpOverride = stored.civicos_api_url || '';
    relayOverride = stored.civicos_relay_url || '';
    if (stored.civicos_personal_mcp_url) personalMcpUrl = stored.civicos_personal_mcp_url;
  }

  async function checkEndpointHealth() {
    endpointsChecking = true;

    // Check MCP
    try {
      const resp = await fetch(`${resolvedMcpUrl}/health`, { signal: AbortSignal.timeout(3000) });
      mcpHealth = resp.ok ? 'ok' : 'error';
    } catch { mcpHealth = 'error'; }

    // Check Relay
    try {
      const resp = await fetch(`${resolvedRelayUrl.replace(/\/relay\/?$/, '')}/health`, { signal: AbortSignal.timeout(3000) });
      relayHealth = resp.ok ? 'ok' : 'error';
    } catch { relayHealth = 'error'; }

    // Check Personal MCP
    try {
      const resp = await fetch(`${personalMcpUrl}/health`, { signal: AbortSignal.timeout(1000) });
      personalMcpHealth = resp.ok ? 'ok' : 'error';
    } catch { personalMcpHealth = 'error'; }

    endpointsChecking = false;
  }

  async function saveEndpoints() {
    endpointsSaving = true;
    try {
      if (mcpOverride.trim()) {
        await registry.setMcpUrl(mcpOverride.trim());
      } else {
        await registry.setMcpUrl('');
      }
      if (relayOverride.trim()) {
        await registry.setRelayUrl(relayOverride.trim());
      } else {
        await registry.clearRelayUrlOverride();
      }
      await chrome.storage.local.set({ civicos_personal_mcp_url: personalMcpUrl });
      // Reload resolved URLs
      resolvedMcpUrl = await registry.getMcpUrl();
      resolvedRelayUrl = await registry.getRelayUrl();
      // Re-check health
      await checkEndpointHealth();
      setStatus('Endpoints saved', 'success');
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to save endpoints', 'error');
    }
    endpointsSaving = false;
  }

  async function resetEndpoints() {
    mcpOverride = '';
    relayOverride = '';
    personalMcpUrl = 'http://localhost:8081';
    await saveEndpoints();
  }

  // Auto-save jurisdiction on change + refresh endpoints
  let prevJurisdiction = '';
  $effect(() => {
    if (selectedJurisdiction && prevJurisdiction && selectedJurisdiction !== prevJurisdiction) {
      saveJurisdiction();
      // Re-resolve endpoints for the new jurisdiction
      loadEndpoints().then(() => {
        if (showEndpoints) {
          mcpHealth = 'unknown';
          relayHealth = 'unknown';
          checkEndpointHealth();
        }
      });
    }
    prevJurisdiction = selectedJurisdiction;
  });

  // AI section expand/collapse
  let showAISettings = $state(false);
  function getAIStatusSummary(): string {
    switch (aiCloudProProvider) {
      case 'ollama': return ollamaConnected ? `Ollama (${ollamaModel})` : 'Ollama';
      case 'civicos': return 'CivicOS';
      case 'claude': return 'Claude';
      case 'openai': return 'OpenAI';
      default: return 'Not configured';
    }
  }

  loadIdentity();
  loadAIStatus();  // also loads Ollama status internally
  loadJurisdiction();
  loadProfile();
  loadJournal();
  loadEndpoints();

  // Sync sign-in state and journal when changed from side panel or other pages
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === 'session' && changes['civicos_session_key']) {
      loadIdentity();
    }
    if (areaName === 'local' && changes[JOURNAL_KEY]) {
      journalText = changes[JOURNAL_KEY].newValue?.text || '';
    }
  });

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

    <!-- Sign in (top-level when locked) -->
    {#if !identity.isUnlocked}
      <div class="sign-in-row">
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
      </div>
    {/if}

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

    <!-- ═══ YOUR PROFILE ═══ -->
    <div class="group-header">Your profile</div>
    <section class="flat-section">
      {#if availableServers.length > 0}
        {@const cityServers = availableServers.filter(s => s.level === 'city')}
        <div class="form-group">
          <label for="jurisdiction-select">City</label>
          <span class="field-desc">Determines what meetings, decisions, and issues you see</span>
          <select id="jurisdiction-select" bind:value={selectedJurisdiction}>
            {#each cityServers as server (server.jurisdiction_id)}
              <option value={server.jurisdiction_id}>
                {server.display_name}
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

      {#if identity.isUnlocked && attestationEvent}
        <div class="verified-badge">
          <span class="verified-badge-check">&#10003;</span>
          <div class="verified-badge-text">
            <span class="verified-badge-label">Verified resident</span>
            {#if attestationDate || attestationJurisdiction}
              <span class="verified-badge-meta">
                {#if attestationJurisdiction}{attestationJurisdiction}{/if}{#if attestationDate} · {attestationDate}{/if}
              </span>
            {/if}
          </div>
        </div>
        {#if attestationJurisdiction && attestationJurisdiction !== selectedJurisdiction}
          <div class="attestation-mismatch">
            You're verified for {attestationJurisdiction} but viewing {availableServers.find(s => s.jurisdiction_id === selectedJurisdiction)?.display_name || selectedJurisdiction}. CivicOS AI features require verification for the selected city.
          </div>
        {/if}
      {/if}

      {#if identity?.isUnlocked}
        <div class="form-group">
          <label for="profile-name">Name</label>
          <span class="field-desc">Shown when you comment on agenda items</span>
          <input id="profile-name" type="text" placeholder="Display name" bind:value={profileName} />
        </div>
        <button class="btn-primary" onclick={saveProfile} disabled={profileSaving}>
          {profileSaving ? 'Saving...' : 'Save'}
        </button>

        <hr class="subsection-divider" />

        <!-- Civic Journal -->
        <div class="form-group">
          <label>Civic Journal</label>
          <span class="field-desc">A living document about what you care about, are frustrated by, or following. The AI reads this to personalize every interaction.</span>
          <div class="journal-mode-tabs">
            <button class="journal-tab" class:active={journalMode === 'edit'} onclick={() => journalMode = 'edit'}>Edit</button>
            <button class="journal-tab" class:active={journalMode === 'preview'} onclick={() => journalMode = 'preview'}>Preview</button>
          </div>
          {#if journalMode === 'edit'}
            <textarea
              class="journal-textarea"
              bind:value={journalText}
              rows="14"
            ></textarea>
          {:else}
            <div class="journal-preview">
              {@html marked.parse(journalText || '*Empty journal*', { async: false })}
            </div>
          {/if}
          <div class="journal-actions">
            <button class="btn-primary" onclick={saveJournal} disabled={journalSaving}>
              {journalSaving ? 'Saving...' : 'Save journal'}
            </button>
            <div class="journal-secondary-actions">
              <button class="btn-subtle" onclick={applyJournalTemplate}>Reset to template</button>
              <button class="btn-subtle" onclick={importJournal}>Import .md</button>
              {#if journalText.trim()}
                <button class="btn-subtle" onclick={exportJournal}>Export .md</button>
              {/if}
            </div>
          </div>
        </div>
      {/if}

      <!-- Account management (within profile section) -->
      {#if identity.isUnlocked}
        <hr class="subsection-divider" />

        {#if !attestationEvent}
          <div class="form-group">
            <label>Verify residency</label>
            <span class="field-desc">Enter a code from a civic event to unlock CivicOS AI</span>
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

        <div class="info-grid">
          <div class="info-row">
            <span class="info-label">Public key</span>
            <span class="npub" title={identity.npub}>{truncateNpub(identity.npub)}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Account</span>
            <span>
              Created {formatDate(identity.createdAt)}
              · <button class="btn-link" onclick={lock}>Sign out</button>
            </span>
          </div>
        </div>

        <div class="account-actions">
          <button class="btn-secondary" onclick={() => { showImport = !showImport; }}>
            {showImport ? 'Cancel' : 'Recover Existing Account'}
          </button>
          <button class="btn-danger" onclick={deleteIdentity}>Delete Account</button>
        </div>

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
      {/if}
    </section>

    <!-- ═══ EXPANDABLE ROWS ═══ -->
    <hr class="section-divider" />

    <!-- AI & Privacy -->
    <button class="expand-row" onclick={() => { showAIPrivacy = !showAIPrivacy; }}>
      <span class="expand-row-label">AI & Privacy</span>
      <span class="expand-row-meta">{getAIStatusSummary()}</span>
      <span class="chevron-right" class:open={showAIPrivacy}></span>
    </button>

    {#if showAIPrivacy}
      <section class="expand-body">
        <div class="form-group">
          <label for="ai-provider-select">Provider</label>
          <span class="field-desc">Powers comment drafting and search</span>
          <select id="ai-provider-select" bind:value={aiCloudProProvider} onchange={() => loadCurrentApiKey()}>
            <option value="civicos">CivicOS</option>
            <option value="claude">Claude (Anthropic)</option>
            <option value="openai">OpenAI</option>
            {#if ollamaConnected}
              <option value="ollama">Ollama — private, on-device</option>
            {/if}
          </select>
        </div>

        <!-- CivicOS: no setup needed -->
        {#if aiCloudProProvider === 'civicos'}
          <div class="civicos-provider-note">
            {#if !identity?.isUnlocked}
              Sign in above to enable.
            {:else if !attestationEvent}
              Verify your residency above to enable.
            {:else}
              Ready — no API key needed.
            {/if}
          </div>

        <!-- Claude / OpenAI: API key -->
        {:else if aiCloudProProvider === 'claude' || aiCloudProProvider === 'openai'}
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

        <!-- Ollama: model picker -->
        {:else if aiCloudProProvider === 'ollama'}
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
          <div class="civicos-provider-note">
            All data stays on your machine. Requires <a href="https://ollama.com" target="_blank" rel="noopener">Ollama</a> running locally.
          </div>
        {/if}

        <div class="ai-action-buttons">
          <button class="btn-primary" onclick={saveAIProvider} disabled={aiSaving}>
            {aiSaving ? 'Saving...' : 'Save'}
          </button>
          <button class="btn-secondary" onclick={aiCloudProProvider === 'ollama' ? testOllama : testAIProvider} disabled={aiTesting || ollamaTesting || (aiCloudProProvider !== 'civicos' && aiCloudProProvider !== 'ollama' && !aiApiKey.trim())}>
            {aiTesting || ollamaTesting ? 'Testing...' : 'Test'}
          </button>
          {#if aiCloudProProvider === 'claude' || aiCloudProProvider === 'openai'}
            <button class="btn-secondary" onclick={clearAIProvider}>
              Clear
            </button>
          {/if}
        </div>

        <!-- Ollama not detected hint -->
        {#if !ollamaConnected && aiCloudProProvider !== 'ollama'}
          <div class="ollama-hint-row">
            <span class="field-desc">Want full privacy? Install <a href="https://ollama.com" target="_blank" rel="noopener">Ollama</a> for on-device AI.</span>
            <button class="ollama-refresh" onclick={loadOllamaStatus} title="Check for Ollama">&#8635;</button>
          </div>
        {/if}
      </section>
    {/if}

    <!-- Endpoints -->
    <button class="expand-row" onclick={() => { showEndpoints = !showEndpoints; if (showEndpoints && mcpHealth === 'unknown') checkEndpointHealth(); }}>
      <span class="expand-row-label">Endpoints</span>
      <span class="expand-row-meta">
        {#if mcpHealth === 'ok'}Connected{:else if mcpHealth === 'error'}Unreachable{:else}...{/if}
      </span>
      <span class="chevron-right" class:open={showEndpoints}></span>
    </button>

    {#if showEndpoints}
      <section class="expand-body">
        <div class="endpoint-group">
          <div class="endpoint-row">
            <span class="endpoint-label">MCP Server</span>
            <span class="health-dot" class:ok={mcpHealth === 'ok'} class:err={mcpHealth === 'error'}></span>
          </div>
          <span class="endpoint-url">{resolvedMcpUrl}</span>
          <div class="form-group endpoint-override">
            <input type="text" placeholder="Override URL (leave empty for auto)" bind:value={mcpOverride} />
          </div>
        </div>

        <div class="endpoint-group">
          <div class="endpoint-row">
            <span class="endpoint-label">Relay</span>
            <span class="health-dot" class:ok={relayHealth === 'ok'} class:err={relayHealth === 'error'}></span>
          </div>
          <span class="endpoint-url">{resolvedRelayUrl}</span>
          <div class="form-group endpoint-override">
            <input type="text" placeholder="Override URL (leave empty for auto)" bind:value={relayOverride} />
          </div>
        </div>

        <div class="endpoint-group">
          <div class="endpoint-row">
            <span class="endpoint-label">Personal MCP</span>
            <span class="health-dot" class:ok={personalMcpHealth === 'ok'} class:err={personalMcpHealth === 'error'}></span>
          </div>
          <span class="endpoint-url">{personalMcpUrl}</span>
          <div class="form-group endpoint-override">
            <input type="text" placeholder="http://localhost:8081" bind:value={personalMcpUrl} />
          </div>
        </div>

        <div class="ai-action-buttons">
          <button class="btn-primary" onclick={saveEndpoints} disabled={endpointsSaving}>
            {endpointsSaving ? 'Saving...' : 'Save'}
          </button>
          <button class="btn-secondary" onclick={checkEndpointHealth} disabled={endpointsChecking}>
            {endpointsChecking ? 'Checking...' : 'Check'}
          </button>
          <button class="btn-secondary" onclick={resetEndpoints}>Reset</button>
        </div>

        <span class="field-desc" style="margin-top: 8px;">
          Endpoints are auto-discovered from the registry. Override only for local development.
        </span>
      </section>
    {/if}

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

  /* Kept for create-account view */
  .card {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(51, 65, 85, 0.4);
    border-radius: 10px;
    padding: 18px;
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

  /* Flat grouped layout (iOS-style) */
  .group-header {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 20px 0 8px;
    padding: 0 2px;
  }
  .group-header:first-of-type {
    margin-top: 0;
  }

  .flat-section {
    padding: 0;
    margin-bottom: 4px;
  }

  .section-divider {
    border: none;
    border-top: 1px solid rgba(51, 65, 85, 0.4);
    margin: 20px 0 4px;
  }

  .expand-row {
    display: flex;
    align-items: center;
    width: 100%;
    padding: 14px 2px;
    background: none;
    border: none;
    border-bottom: 1px solid rgba(51, 65, 85, 0.2);
    color: inherit;
    cursor: pointer;
    text-align: left;
    gap: 8px;
  }
  .expand-row:hover {
    background: rgba(30, 41, 59, 0.3);
  }
  .expand-row-label {
    font-size: 14px;
    font-weight: 500;
    color: #e2e8f0;
  }
  .expand-row-meta {
    font-size: 12px;
    color: #64748b;
    margin-left: auto;
  }

  .chevron-right {
    display: inline-block;
    width: 0;
    height: 0;
    border-top: 4px solid transparent;
    border-bottom: 4px solid transparent;
    border-left: 5px solid #64748b;
    transition: transform 0.15s;
    flex-shrink: 0;
  }
  .chevron-right.open {
    transform: rotate(90deg);
  }

  .expand-body {
    padding: 16px 2px;
  }

  .verified-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: rgba(34, 197, 94, 0.06);
    border-radius: 6px;
    margin-top: 8px;
  }
  .verified-badge-check {
    color: #4ade80;
    font-size: 14px;
    font-weight: 600;
    flex-shrink: 0;
  }
  .verified-badge-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .verified-badge-label {
    font-size: 13px;
    color: #4ade80;
    font-weight: 500;
  }
  .verified-badge-meta {
    font-size: 11px;
    color: #64748b;
  }

  .sign-in-row {
    margin-top: 12px;
  }

  .field-desc {
    display: block;
    font-size: 11px;
    color: #64748b;
    margin-bottom: 6px;
    line-height: 1.4;
  }
  .privacy-note {
    display: block;
    font-size: 10px;
    color: #4b5563;
    margin-top: 8px;
  }

  /* Civic Journal */
  .journal-mode-tabs {
    display: flex;
    gap: 0;
    margin-bottom: 0;
  }
  .journal-tab {
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    background: rgba(0, 0, 0, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-bottom: none;
    cursor: pointer;
  }
  .journal-tab:first-child { border-radius: 6px 0 0 0; }
  .journal-tab:last-child { border-radius: 0 6px 0 0; }
  .journal-tab.active {
    color: #d1d5db;
    background: rgba(0, 0, 0, 0.2);
    border-color: rgba(255, 255, 255, 0.1);
  }
  .journal-textarea {
    width: 100%;
    padding: 10px;
    font-size: 12px;
    line-height: 1.6;
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0 6px 6px 6px;
    color: #e5e7eb;
    resize: vertical;
    font-family: monospace;
    outline: none;
    margin-bottom: 8px;
  }
  .journal-textarea:focus {
    border-color: rgba(16, 185, 129, 0.4);
  }
  .journal-preview {
    padding: 10px;
    font-size: 12px;
    line-height: 1.6;
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0 6px 6px 6px;
    color: #d1d5db;
    margin-bottom: 8px;
    min-height: 200px;
    max-height: 400px;
    overflow-y: auto;
  }
  .journal-preview :global(h1) {
    font-size: 15px;
    font-weight: 700;
    color: #f3f4f6;
    margin: 0 0 6px 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 4px;
  }
  .journal-preview :global(h2) {
    font-size: 13px;
    font-weight: 600;
    color: #e5e7eb;
    margin: 12px 0 4px 0;
  }
  .journal-preview :global(ul), .journal-preview :global(ol) {
    margin: 4px 0;
    padding-left: 20px;
  }
  .journal-preview :global(li) {
    margin: 2px 0;
  }
  .journal-preview :global(p) {
    margin: 6px 0;
  }
  .journal-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .journal-secondary-actions {
    display: flex;
    gap: 8px;
  }
  .btn-subtle {
    padding: 4px 10px;
    font-size: 11px;
    color: #9ca3af;
    background: none;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    cursor: pointer;
  }
  .btn-subtle:hover {
    color: #d1d5db;
    border-color: rgba(255, 255, 255, 0.15);
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
    width: auto;
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
  .btn-primary.btn-compact {
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

  .verify-row {
    margin-top: 12px;
  }

  .account-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }
  .account-actions .btn-secondary,
  .account-actions .btn-danger {
    flex: 1;
    font-size: 11px;
    padding: 6px 10px;
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

  .parent-info {
    font-size: 12px;
    color: #94a3b8;
    margin: 8px 0;
    padding: 6px 10px;
    background: #1e293b;
    border-radius: 4px;
    border-left: 2px solid #6366f1;
  }

  /* Ollama hint */
  .ollama-hint-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 12px;
  }
  .ollama-hint-row a {
    color: #818cf8;
    text-decoration: none;
  }
  .ollama-hint-row a:hover { text-decoration: underline; }
  .ollama-refresh {
    background: none;
    border: none;
    color: #64748b;
    font-size: 16px;
    cursor: pointer;
    padding: 0 4px;
    opacity: 0.7;
    flex-shrink: 0;
  }
  .ollama-refresh:hover { opacity: 1; }


  .attestation-mismatch {
    font-size: 11px;
    color: #fbbf24;
    background: rgba(251, 191, 36, 0.08);
    padding: 8px 10px;
    border-radius: 6px;
    margin-top: 6px;
    line-height: 1.4;
  }

  /* Endpoints */
  .endpoint-group {
    margin-bottom: 14px;
  }
  .endpoint-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 2px;
  }
  .endpoint-label {
    font-size: 12px;
    font-weight: 500;
    color: #94a3b8;
  }
  .endpoint-url {
    display: block;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #64748b;
    margin-bottom: 6px;
    word-break: break-all;
  }
  .endpoint-override {
    margin-bottom: 0;
  }
  .endpoint-override input {
    font-size: 12px;
    padding: 6px 9px;
  }
  .health-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #475569;
    flex-shrink: 0;
  }
  .health-dot.ok { background: #22c55e; }
  .health-dot.err { background: #ef4444; }

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


</style>

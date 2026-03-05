<script lang="ts">
  import { tick } from 'svelte';
  import { sendMessage } from '../lib/messaging.js';
  import { api, registry } from '../lib/client.js';
  import { CivicSession } from '@civicos/client';
  import type { CityPulseData, DataProvenance, VoiceCounts, CommentCounts, CommentSynthesis, RegistryServer } from '@civicos/client';
  import { isAIAvailable, getAIManager, onAIConfigChanged } from '../lib/ai.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import { personalMCP } from '../lib/personal-mcp-client.js';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  // Reusable components and utilities from @civicos/components
  import CivicAgendaView from '@civicos/components/src/components/CivicAgendaView.svelte';
  import CivicDecisionView from '@civicos/components/src/components/CivicDecisionView.svelte';
  import CivicInitiativeView from '@civicos/components/src/components/CivicInitiativeView.svelte';
  import CivicIssueMap from '@civicos/components/src/components/CivicIssueMap.svelte';
  import CivicBudgetBreakdown from '@civicos/components/src/components/CivicBudgetBreakdown.svelte';
  import CivicMeetingCard from '@civicos/components/src/components/CivicMeetingCard.svelte';
  import CivicProvenancePanel from '@civicos/components/src/components/CivicProvenancePanel.svelte';
  import CivicIdentityChip from '@civicos/components/src/components/CivicIdentityChip.svelte';
  import CivicReadOnlyPulse from '@civicos/components/src/components/CivicReadOnlyPulse.svelte';
  import CivicChatBar from '@civicos/components/src/components/CivicChatBar.svelte';


  // High-level orchestration session (stateless — recreated when AI config changes)
  let session = new CivicSession(api, registry, getAIManager());

  // Configure marked for compact output (no extra <p> wrappers for simple text)
  marked.setOptions({ breaks: true, gfm: true });

  function renderMarkdown(text: string): string {
    const raw = marked.parse(text, { async: false }) as string;
    return DOMPurify.sanitize(raw);
  }

  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);
  let pulseData: CityPulseData | null = $state(null);
  let pulseError: string | null = $state(null);
  let pulseLoading = $state(true);

  // Collapsible section state
  let expanded: Record<string, boolean> = $state({
    meetings: false,
    items: true,
    outcomes: false,
    issueMap: false,
    budget: false,
  });

  // Data provenance
  let showProvenance = $state(false);
  let provenanceData: DataProvenance | null = $state(null);
  let provenanceLoading = $state(false);

  // Jurisdiction tab state (which jurisdiction's content is shown)
  let activeTab: string = $state('city-san-rafael');

  // Voice counts
  let voiceCounts = $state(new Map<string, VoiceCounts>());

  // Voice submission state
  type Stance = 'support' | 'oppose' | 'watching';
  let userStances = $state(new Map<string, Stance>());
  let votingInProgress = $state(new Set<string>());
  const STANCES_STORAGE_KEY = 'civicos_user_stances';

  // Attestation state
  let attestationLabels: string[] = $state([]);

  // US state abbreviations for compact badge display
  const STATE_ABBREVS: Record<string, string> = {
    'state-california': 'CA', 'state-texas': 'TX', 'state-new-york': 'NY',
    'state-florida': 'FL', 'state-illinois': 'IL', 'state-pennsylvania': 'PA',
    'state-ohio': 'OH', 'state-georgia': 'GA', 'state-michigan': 'MI',
    'state-washington': 'WA', 'state-oregon': 'OR', 'state-colorado': 'CO',
    'state-virginia': 'VA', 'state-massachusetts': 'MA', 'state-arizona': 'AZ',
    'state-nevada': 'NV', 'state-minnesota': 'MN', 'state-maryland': 'MD',
  };

  function buildAttestationLabels(event: Record<string, unknown> | null | undefined): string[] {
    if (!event) return [];
    const tags = event?.tags;
    if (!Array.isArray(tags)) return ['verified'];
    const jTag = tags.find((t: unknown) => Array.isArray(t) && t[0] === 'j');
    const jurisdictionId = Array.isArray(jTag) && typeof jTag[1] === 'string' ? jTag[1] : null;
    if (!jurisdictionId) return [];

    const labels: string[] = [];
    const server = availableServers.find(s => s.jurisdiction_id === jurisdictionId);
    labels.push(server?.display_name?.toLowerCase() || jurisdictionId.replace(/^city-/, '').replace(/-/g, ' '));

    // Add parent jurisdictions (skip federal)
    const parents = server?.parent_jurisdictions ?? [];
    for (const pid of parents) {
      if (pid.startsWith('federal-')) continue;
      const abbrev = STATE_ABBREVS[pid];
      if (abbrev) {
        labels.push(abbrev);
      } else {
        const parentServer = availableServers.find(s => s.jurisdiction_id === pid);
        if (parentServer) labels.push(parentServer.display_name.toLowerCase());
      }
    }
    return labels;
  }

  // Comment counts & synthesis (loaded in bulk, shared with CivicAgendaView)
  let commentCounts = $state(new Map<string, CommentCounts>());
  let synthData = $state(new Map<string, CommentSynthesis>());

  // AI state (shared across sections — decisions, initiatives)
  let aiAvailable = $state(false);
  let activeProviderName = $state('');

  // Initiatives loaded from CivicInitiativeView (for attention bar)
  let loadedInitiatives: Array<{ id: string; title: string; topic: string; voice_count: number; creator_attested?: boolean; timestamp?: string }> = $state([]);
  let initiativeViewRef: { expandAndScrollTo: (id: string) => void } | undefined = $state();

  // Jurisdiction state
  let activeJurisdiction = $state('city-san-rafael');
  let availableServers: RegistryServer[] = $state([]);

  // Parent jurisdiction state (multi-level)
  let parentServers: RegistryServer[] = $state([]);
  let parentPulseData = $state(new Map<string, CityPulseData>());
  let parentPulseLoading = $state(new Set<string>());
  let parentPulseErrors = $state(new Map<string, string>());

  // Server health state (Connected Services)
  interface ServerHealthStatus {
    status: 'healthy' | 'degraded' | 'offline';
    latency_ms?: number;
    version?: string;
    checked_at: number;
  }
  let serverHealth = $state(new Map<string, ServerHealthStatus>());
  let relayHealth: ServerHealthStatus | null = $state(null);

  // Personal Hub state
  let personalInterests: string[] = $state([]);
  let personalNeighborhood: string = $state('');
  let hubConnected = $state(false);

  // Connector setup state
  let connectorSetupDismissed = $state(false);
  let connectorSetupLoaded = $state(false);
  const CONNECTOR_SETUP_KEY = 'civicos_connector_setup_dismissed';

  // Component refs (for lazy-load triggering)
  let issueMapRef: CivicIssueMap | undefined = $state(undefined);
  let budgetRef: CivicBudgetBreakdown | undefined = $state(undefined);

  // Toast notification
  let toastMessage: string | null = $state(null);
  let toastTimeout: ReturnType<typeof setTimeout> | null = null;

  function showToast(message: string, durationMs = 4000) {
    toastMessage = message;
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => { toastMessage = null; }, durationMs);
  }

  // Scroll-to-card highlight state
  let highlightedCardId: string | null = $state(null);
  let highlightTimeout: ReturnType<typeof setTimeout> | null = null;

  function scrollToCard(itemId: string) {
    // Expand the items section if collapsed
    expanded.items = true;
    // Wait a tick for the section to render, then scroll
    requestAnimationFrame(() => {
      const card = document.getElementById('card-' + itemId);
      if (!card) return;
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      highlightedCardId = itemId;
      if (highlightTimeout) clearTimeout(highlightTimeout);
      highlightTimeout = setTimeout(() => { highlightedCardId = null; }, 2000);
    });
  }


  function toggle(section: string) {
    expanded = { ...expanded, [section]: !expanded[section] };
  }

  async function handleChatNavigate(tool: string) {
    const NAV_MAP: Record<string, { section?: string; tab?: string }> = {
      search_meeting_history: { section: 'outcomes' },
      get_upcoming_meetings: { section: 'meetings' },
      search_budget: { section: 'budget' },
      get_public_testimony: { section: 'meetings' },
      search_legislation: { tab: parentServers.find(s => s.jurisdiction_id.startsWith('state-'))?.jurisdiction_id },
      find_similar_issues: { section: 'issueMap' },
    };
    const nav = NAV_MAP[tool];
    if (!nav) return;
    if (nav.tab) switchTab(nav.tab);
    if (nav.section) {
      expanded = { ...expanded, [nav.section]: true };
      await tick();
      // Trigger lazy-load for components that need it
      if (nav.section === 'issueMap') issueMapRef?.load();
      if (nav.section === 'budget') budgetRef?.load();
      const el = document.querySelector(`[data-section="${nav.section}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  async function loadIdentity() {
    loading = true;
    const response = await sendMessage<(IdentityInfo & { isUnlocked?: boolean }) | null>({
      type: 'GET_IDENTITY',
    });
    if (response.success) {
      identity = response.data;
    }
    loading = false;
    // Check attestation status from local storage
    try {
      const stored = await chrome.storage.local.get('civicos_attestation');
      attestationLabels = buildAttestationLabels(stored.civicos_attestation);
    } catch {
      attestationLabels = [];
    }
  }

  async function initJurisdiction() {
    activeJurisdiction = await registry.getActiveJurisdiction();
    // Pre-fetch registry for getMCPUrl() lookups
    try {
      availableServers = await registry.getRegistryServers();
    } catch {
      availableServers = [];
    }
  }

  /** Load profile + jurisdiction ordering from Personal Hub (best-effort). */
  async function loadPersonalHub() {
    hubConnected = await personalMCP.isAvailable();
    if (!hubConnected) return;

    // Load profile (interests + neighborhood for personalized filtering & drafting)
    try {
      const profile = await personalMCP.getProfile();
      personalInterests = profile.interests || [];
      personalNeighborhood = profile.neighborhood || '';
    } catch {
      personalInterests = [];
      personalNeighborhood = '';
    }

    // Load jurisdiction ordering (overrides registry default if set)
    try {
      const ordered = await personalMCP.getJurisdictions();
      if (ordered.length > 0) {
        // Use the first jurisdiction as active if it's in the registry
        const firstMatch = ordered.find(j =>
          availableServers.some(s => s.jurisdiction_id === j)
        );
        if (firstMatch && firstMatch !== activeJurisdiction) {
          activeJurisdiction = firstMatch;
          activeTab = firstMatch;
          await registry.setActiveJurisdiction(firstMatch);
        }
      }
    } catch {
      // Fall back to registry-based jurisdiction
    }
  }

  async function loadCityPulse() {
    pulseLoading = true;
    pulseError = null;
    try {
      pulseData = await session.loadPulse();
      // Update available servers for UI (registry was already refreshed by session)
      try { availableServers = await registry.getRegistryServers(); } catch {}
      // Load voice counts and comment counts in background (initiatives loaded by CivicInitiativeView)
      loadVoiceCounts();
      loadCommentCounts();
      // Load parent jurisdiction data and health checks in background
      loadParentPulse();
      checkAllHealth();
    } catch (err) {
      pulseError = err instanceof Error ? err.message : 'Failed to load civic data';
    }
    pulseLoading = false;
  }

  async function loadParentPulse() {
    try {
      parentServers = await registry.getParentServers(activeJurisdiction);
    } catch {
      parentServers = [];
      return;
    }
    if (parentServers.length === 0) return;

    // Fetch pulse data from each parent server concurrently
    for (const server of parentServers) {
      const id = server.jurisdiction_id;
      parentPulseLoading.add(id);
      parentPulseLoading = new Set(parentPulseLoading);

      api.getCityPulseFromServer(registry.getServerBaseUrl(server))
        .then(data => {
          parentPulseData.set(id, data);
          parentPulseData = new Map(parentPulseData);
          // Load voice counts and comment counts for this parent's legislation
          loadParentVoiceCounts(id, data);
          loadParentCommentCounts(id, data);
        })
        .catch(() => {
          parentPulseErrors.set(id, 'Server unavailable');
          parentPulseErrors = new Map(parentPulseErrors);
        })
        .finally(() => {
          parentPulseLoading.delete(id);
          parentPulseLoading = new Set(parentPulseLoading);
        });
    }
  }

  function extractBillEntityIds(pulse: CityPulseData): string[] {
    const ids: string[] = [];
    if (pulse.upcoming_items) {
      for (const item of pulse.upcoming_items) {
        if (item.id) ids.push(`bill:${item.id}`);
      }
    }
    if (pulse.recent_outcomes) {
      for (const outcome of pulse.recent_outcomes) {
        if (outcome.id) ids.push(`bill:${outcome.id}`);
      }
    }
    return ids;
  }

  async function loadParentVoiceCounts(jurisdictionId: string, pulse: CityPulseData) {
    const ids = extractBillEntityIds(pulse);
    if (ids.length === 0) return;
    try {
      const counts = await api.getVoiceCountsBatch(ids, jurisdictionId);
      for (const [id, c] of counts) {
        voiceCounts.set(id, c);
      }
      voiceCounts = new Map(voiceCounts);
    } catch {
      // Voice counts are non-critical — silently ignore
    }
  }

  function extractFocalPointEntityIds(pulse: CityPulseData): string[] {
    const ids: string[] = [];
    const p = pulse as any;
    if (p.comment_periods) {
      for (const period of p.comment_periods) {
        if (period.document_number) ids.push(`rule:${period.document_number}`);
      }
    }
    if (p.upcoming_hearings) {
      for (const hearing of p.upcoming_hearings) {
        if (hearing.bill_id) ids.push(`bill:${hearing.bill_id}`);
      }
    }
    if (p.governors_desk) {
      for (const bill of p.governors_desk) {
        if (bill.bill_id) ids.push(`bill:${bill.bill_id}`);
      }
    }
    return ids;
  }

  async function loadParentCommentCounts(jurisdictionId: string, pulse: CityPulseData) {
    const ids = extractFocalPointEntityIds(pulse);
    if (ids.length === 0) return;
    try {
      const counts = await api.getCommentCountsBatch(ids, jurisdictionId);
      for (const [id, c] of counts) {
        commentCounts.set(id, c);
      }
      commentCounts = new Map(commentCounts);
      // Pre-fetch syntheses in background
      const withComments = [...counts].filter(([, cc]) => cc.count > 0);
      for (const [entityId] of withComments) {
        api.getCommentSynthesis(entityId).then((synth: CommentSynthesis | null) => {
          if (synth) {
            synthData.set(entityId, synth);
            synthData = new Map(synthData);
          }
        }).catch(() => {});
      }
    } catch {
      // Comment counts are non-critical
    }
  }

  async function loadVoiceCounts() {
    if (!pulseData) return;
    voiceCounts = await session.loadVoiceCounts(pulseData);
  }

  async function loadCommentCounts() {
    if (!pulseData) return;
    commentCounts = await session.loadCommentCounts(pulseData);
    // Pre-fetch syntheses in background (enriches AI context)
    session.loadCommentSyntheses(commentCounts).then(newSynths => {
      for (const [id, s] of newSynths) synthData.set(id, s);
      synthData = new Map(synthData);
    });
  }

  async function toggleProvenance() {
    showProvenance = !showProvenance;
    if (showProvenance && !provenanceData && !provenanceLoading) {
      provenanceLoading = true;
      try {
        provenanceData = await session.loadProvenance();
      } catch (e) {
        console.error('Failed to load provenance:', e);
      } finally {
        provenanceLoading = false;
      }
    }
  }

  function switchTab(jurisdictionId: string) {
    activeTab = jurisdictionId;
    if (showProvenance) showProvenance = false;
  }

  function healthTitle(jurisdictionId: string): string {
    const health = serverHealth.get(jurisdictionId);
    if (!health) return '';
    const parts = [health.status];
    if (health.latency_ms !== undefined) parts.push(`${health.latency_ms}ms`);
    if (health.version) parts.push(`v${health.version}`);
    const server = jurisdictionId === activeJurisdiction
      ? availableServers.find(s => s.jurisdiction_id === activeJurisdiction)
      : parentServers.find(s => s.jurisdiction_id === jurisdictionId);
    if (server) parts.push(new URL(server.mcp_endpoint).host);
    return parts.join(' · ');
  }

  async function checkServerHealth(server: RegistryServer): Promise<ServerHealthStatus> {
    const start = performance.now();
    // Serverless containers may need 15s+ to cold-start
    const timeout = server.level === 'city' ? 5000 : 20000;
    try {
      const response = await fetch(server.health_endpoint, { signal: AbortSignal.timeout(timeout) });
      const latency_ms = Math.round(performance.now() - start);
      if (!response.ok) return { status: 'degraded', latency_ms, checked_at: Date.now() };
      const data = await response.json();
      return { status: 'healthy', latency_ms, version: data.version, checked_at: Date.now() };
    } catch {
      return { status: 'offline', latency_ms: Math.round(performance.now() - start), checked_at: Date.now() };
    }
  }

  async function checkRelayHealth(relayEndpoint: string): Promise<ServerHealthStatus> {
    const start = performance.now();
    try {
      const response = await fetch(`${relayEndpoint}/health`, { signal: AbortSignal.timeout(5000) });
      const latency_ms = Math.round(performance.now() - start);
      if (!response.ok) return { status: 'degraded', latency_ms, checked_at: Date.now() };
      return { status: 'healthy', latency_ms, checked_at: Date.now() };
    } catch {
      return { status: 'offline', latency_ms: Math.round(performance.now() - start), checked_at: Date.now() };
    }
  }

  async function checkAllHealth() {
    const servers = availableServers;
    // Check MCP servers in parallel
    const checks = servers.map(async (server) => {
      const health = await checkServerHealth(server);
      serverHealth.set(server.jurisdiction_id, health);
      serverHealth = new Map(serverHealth);
    });
    // Check relay health
    const activeServer = servers.find(s => s.jurisdiction_id === activeJurisdiction);
    if (activeServer?.relay_endpoint) {
      checkRelayHealth(activeServer.relay_endpoint).then(health => {
        relayHealth = health;
      });
    }
    await Promise.all(checks);
  }

  // === External AI Platform Routing ===

  type AIPlatform = 'claude';

  const AI_PLATFORMS: Record<AIPlatform, { name: string; url: string }> = {
    claude: { name: 'Claude', url: 'https://claude.ai/new' },
  };

  function getMCPUrl(): string {
    const server = availableServers.find(s => s.jurisdiction_id === activeJurisdiction);
    return server?.mcp_endpoint || `https://san-rafael.civicosproject.org/mcp`;
  }

  function formatExternalContext(context: string): string {
    const jurisdiction = pulseData?.jurisdiction || 'my city';
    return `${context}\n\n---\nSource: CivicOS — ${jurisdiction} civic data (civicosproject.org)\nTip: For richer integration, add CivicOS as an MCP connector in your AI settings:\n${getMCPUrl()}`;
  }

  // Positioned clipboard toast (appears near the clicked button)
  let clipboardToast: { y: number; platform: string } | null = $state(null);
  let clipboardToastTimeout: ReturnType<typeof setTimeout> | null = null;

  function showClipboardToast(y: number, platform: string) {
    clipboardToast = { y, platform };
    if (clipboardToastTimeout) clearTimeout(clipboardToastTimeout);
    clipboardToastTimeout = setTimeout(() => { clipboardToast = null; }, 6000);
  }

  async function openExternalAI(platform: AIPlatform, context: string, event?: MouseEvent) {
    const config = AI_PLATFORMS[platform];
    const formatted = formatExternalContext(context);
    try {
      await navigator.clipboard.writeText(formatted);
      if (platform === 'claude') {
        // Store context for the claude-bridge content script to auto-inject
        try { await chrome.storage.session.set({ civicos_claude_pending_context: formatted }); } catch { /* ignore */ }
      }
      chrome.tabs.create({ url: config.url });
      const y = event ? (event.target as HTMLElement).getBoundingClientRect().top : 0;
      showClipboardToast(y, config.name);
    } catch {
      showToast('Failed to copy context to clipboard');
    }
  }

  // === Connector Setup Banner ===

  async function loadConnectorSetupState() {
    try {
      const result = await chrome.storage.local.get(CONNECTOR_SETUP_KEY);
      connectorSetupDismissed = result[CONNECTOR_SETUP_KEY] ?? false;
    } catch { /* ignore */ }
    connectorSetupLoaded = true;
  }

  async function dismissConnectorSetup() {
    connectorSetupDismissed = true;
    try {
      await chrome.storage.local.set({ [CONNECTOR_SETUP_KEY]: true });
    } catch { /* ignore */ }
  }

  let connectorInlineHint: { message: string; url: string; name: string } | null = $state(null);

  let connectorHintTimeout: ReturnType<typeof setTimeout> | null = null;

  async function setupConnector() {
    const mcpUrl = getMCPUrl();
    const connectorName = 'CivicOS San Rafael';
    try {
      await navigator.clipboard.writeText(mcpUrl);
    } catch {
      showToast('Could not copy URL — you can copy it from the hint below');
    }
    chrome.tabs.create({ url: 'https://claude.ai/settings/connectors?modal=add-custom-connector' });
    connectorInlineHint = { message: 'Paste this URL into the connector dialog:', url: mcpUrl, name: connectorName };
    if (connectorHintTimeout) clearTimeout(connectorHintTimeout);
    connectorHintTimeout = setTimeout(() => { connectorInlineHint = null; }, 15000);
  }

  async function loadStances() {
    try {
      const result = await chrome.storage.local.get(STANCES_STORAGE_KEY);
      if (result[STANCES_STORAGE_KEY]) {
        userStances = new Map(Object.entries(result[STANCES_STORAGE_KEY]) as [string, Stance][]);
      }
    } catch {
      // Ignore load errors
    }
  }

  async function persistStances() {
    try {
      const obj: Record<string, string> = {};
      userStances.forEach((v, k) => { obj[k] = v; });
      await chrome.storage.local.set({ [STANCES_STORAGE_KEY]: obj });
    } catch {
      // Ignore persist errors
    }
  }

  function lookupItemTitle(entityId: string): string | null {
    if (!pulseData) return null;
    const rawId = entityId.replace(/^agenda:/, '').replace(/^bill:/, '');
    const item = pulseData.upcoming_items?.find(i => i.id === rawId);
    if (item) return item.title;
    const outcome = pulseData.recent_outcomes?.find(o => o.id === rawId);
    if (outcome) return outcome.title;
    // Check parent pulse data
    for (const [, pd] of parentPulseData) {
      const pi = pd.upcoming_items?.find(i => i.id === rawId);
      if (pi) return pi.title;
      const po = pd.recent_outcomes?.find(o => o.id === rawId);
      if (po) return po.title;
    }
    return null;
  }

  async function handleVoice(entityId: string, stance: Stance, overrideJurisdiction?: string) {
    if (votingInProgress.has(entityId)) return;
    if (!identity?.isUnlocked) return;

    // Read stored attestation proof
    const stored = await chrome.storage.local.get('civicos_attestation');
    const attestationProof = stored.civicos_attestation;
    if (!attestationProof) {
      showToast('Verification required to voice — visit Settings to redeem your code.');
      return;
    }

    votingInProgress.add(entityId);
    votingInProgress = new Set(votingInProgress);

    const prevStance = userStances.get(entityId);
    const prevCounts = voiceCounts.get(entityId) || { support: 0, oppose: 0, watching: 0, total: 0 };

    // Re-click same stance = revoke (toggle off)
    if (prevStance === stance) {
      const newCounts = { ...prevCounts };
      newCounts[stance] = Math.max(0, newCounts[stance] - 1);
      newCounts.total = newCounts.support + newCounts.oppose + newCounts.watching;

      voiceCounts.set(entityId, newCounts);
      voiceCounts = new Map(voiceCounts);
      userStances.delete(entityId);
      userStances = new Map(userStances);
      persistStances();

      // Sign and submit revoke (fire-and-forget)
      try {
        await api.castRevokeVoice(entityId);
      } catch {
        // Fire-and-forget
      }

      votingInProgress.delete(entityId);
      votingInProgress = new Set(votingInProgress);
      return;
    }

    // Different stance — optimistic update
    const newCounts = { ...prevCounts };
    if (prevStance) {
      newCounts[prevStance] = Math.max(0, newCounts[prevStance] - 1);
    }
    newCounts[stance] += 1;
    newCounts.total = newCounts.support + newCounts.oppose + newCounts.watching;

    voiceCounts.set(entityId, newCounts);
    voiceCounts = new Map(voiceCounts);
    userStances.set(entityId, stance);
    userStances = new Map(userStances);
    persistStances();

    // Contextual confirmation toast
    const itemTitle = lookupItemTitle(entityId);
    const othersCount = newCounts.total - 1;
    if (itemTitle) {
      const truncTitle = itemTitle.length > 50 ? itemTitle.slice(0, 47) + '...' : itemTitle;
      const others = othersCount > 0 ? ` ${othersCount} other${othersCount !== 1 ? 's' : ''} have also weighed in.` : '';
      showToast(`You voiced ${stance} on ${truncTitle}.${others}`);
    }

    // Sign and submit (fire-and-forget — stance is persisted locally regardless)
    const jurisdiction = overrideJurisdiction || pulseData?.jurisdiction || activeJurisdiction;
    api.castVoice(entityId, stance, jurisdiction, attestationProof).catch(() => {
      // Relay submission failed — local stance persists, will sync on next load
    });

    votingInProgress.delete(entityId);
    votingInProgress = new Set(votingInProgress);
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }


  // Load on mount
  initJurisdiction().then(() => loadPersonalHub());
  loadIdentity();
  loadCityPulse();
  loadStances();
  loadConnectorSetupState();
  async function refreshAIState() {
    const available = await isAIAvailable();
    aiAvailable = available;
    const mgr = getAIManager();
    const provider = mgr.getActiveProvider();
    activeProviderName = provider ? provider.name : '';
    // Recreate session with current AI manager
    session = new CivicSession(api, registry, mgr);
  }

  refreshAIState();
  onAIConfigChanged(() => refreshAIState());

  // Refresh identity and connector state when chrome.storage changes
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== 'local') return;
    if (changes['civicos-passkey-identity'] || changes['civicos-wallet-identity']) {
      loadIdentity();
    }
    if (changes['civicos_attestation']) {
      attestationLabels = buildAttestationLabels(changes['civicos_attestation'].newValue);
    }
    if (changes[CONNECTOR_SETUP_KEY]) {
      connectorSetupDismissed = changes[CONNECTOR_SETUP_KEY].newValue ?? false;
    }
  });
</script>

<div class="panel">
  <header>
    <nav class="breadcrumb">
      <!-- Primary jurisdiction -->
      <button class="breadcrumb-segment" class:active={activeTab === activeJurisdiction}
              onclick={() => switchTab(activeJurisdiction)}
              title={healthTitle(activeJurisdiction)}>
        <span class="health-dot {serverHealth.get(activeJurisdiction)?.status || 'unknown'}"></span>
        <span class="segment-name">{availableServers.find(s => s.jurisdiction_id === activeJurisdiction)?.display_name || activeJurisdiction}</span>
      </button>
      <!-- Parent jurisdictions -->
      {#each parentServers as server}
        <span class="breadcrumb-sep">/</span>
        <button class="breadcrumb-segment" class:active={activeTab === server.jurisdiction_id}
                onclick={() => switchTab(server.jurisdiction_id)}
                title={healthTitle(server.jurisdiction_id)}>
          <span class="health-dot {serverHealth.get(server.jurisdiction_id)?.status || 'unknown'}"></span>
          <span class="segment-name">{server.display_name}</span>
        </button>
      {/each}
    </nav>
    <div class="header-actions">
      <button class="icon-btn" onclick={toggleProvenance} title="Data Sources" class:active={showProvenance}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
      </button>
      <button class="icon-btn" onclick={loadCityPulse} title="Refresh" disabled={pulseLoading}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             class:spinning={pulseLoading}>
          <path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16" />
        </svg>
      </button>
      <button class="icon-btn" onclick={openOptions} title="Settings">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
        </svg>
      </button>
    </div>
  </header>

  <!-- Active tab endpoint bar -->
  {#if activeTab === activeJurisdiction}
    {@const server = availableServers.find(s => s.jurisdiction_id === activeJurisdiction)}
    {#if server}
      <div class="endpoint-bar">
        <span class="endpoint-label">MCP</span>
        <span class="endpoint-url">{new URL(server.mcp_endpoint).host}{new URL(server.mcp_endpoint).pathname}</span>
        {#if server.relay_endpoint}
          <span class="endpoint-sep">&middot;</span>
          <span class="endpoint-label">Relay</span>
          <span class="endpoint-url">{new URL(server.relay_endpoint).host}{new URL(server.relay_endpoint).pathname}</span>
        {/if}
      </div>
    {/if}
  {:else}
    {@const server = parentServers.find(s => s.jurisdiction_id === activeTab)}
    {#if server}
      <div class="endpoint-bar">
        <span class="endpoint-label">MCP</span>
        <span class="endpoint-url">{new URL(server.mcp_endpoint).host}{new URL(server.mcp_endpoint).pathname}</span>
        {#if server.relay_endpoint}
          <span class="endpoint-sep">&middot;</span>
          <span class="endpoint-label">Relay</span>
          <span class="endpoint-url">{new URL(server.relay_endpoint).host}{new URL(server.relay_endpoint).pathname}</span>
        {/if}
      </div>
    {/if}
  {/if}

  <!-- Data Provenance Panel -->
  {#if showProvenance}
    <CivicProvenancePanel data={provenanceData} loading={provenanceLoading} />
  {/if}


  <!-- Connector setup banner (guard on loaded to prevent flash) -->
  {#if connectorSetupLoaded && !connectorSetupDismissed}
    <div class="connector-banner">
      <div class="connector-banner-content">
        <div class="connector-banner-title">Get live civic data in your AI</div>
        <div class="connector-banner-desc">Connect CivicOS for dynamic meeting, budget, and legislation lookups — not just static text.</div>
        <div class="connector-banner-actions">
          <button class="connector-setup-btn" onclick={setupConnector}>
            Set up in Claude
          </button>
        </div>
      </div>
      <button class="connector-banner-close" onclick={dismissConnectorSetup} title="Dismiss">&times;</button>
    </div>
    {#if connectorInlineHint}
      <div class="connector-hint">
        <div class="connector-hint-label">{connectorInlineHint.message}</div>
        <div class="connector-hint-row">
          <span class="connector-hint-key">URL</span>
          <span class="connector-hint-value">{connectorInlineHint.url}</span>
        </div>
        <div class="connector-hint-row">
          <span class="connector-hint-key">Name</span>
          <span class="connector-hint-value">{connectorInlineHint.name}</span>
        </div>
      </div>
    {/if}
  {/if}

  <!-- Identity chip -->
  <CivicIdentityChip
    {identity}
    {loading}
    {attestationLabels}
    onunlock={async (password) => {
      const response = await sendMessage<boolean>({ type: 'UNLOCK', password });
      if (response.success && response.data) {
        identity = identity ? { ...identity, isUnlocked: true } : identity;
        return true;
      }
      return false;
    }}
    onopenoptions={openOptions}
  />

  <!-- Personal interests bar -->
  {#if hubConnected && personalInterests.length > 0}
    <div class="interests-bar">
      <span class="interests-label">Your interests</span>
      <div class="interests-chips">
        {#each personalInterests as interest}
          <span class="interest-chip">{interest}</span>
        {/each}
      </div>
    </div>
  {/if}

  <!-- AI Chat Bar (tool-backed search) -->
  <CivicChatBar
    {session}
    jurisdiction={activeJurisdiction}
    {aiAvailable}
    {renderMarkdown}
    ontoast={(message) => showToast(message)}
    onnavigate={handleChatNavigate}
  />

  <!-- City Pulse content -->
  {#if activeTab === activeJurisdiction}
  {#if pulseLoading && !pulseData}
    <div class="loading-state">
      <div class="pulse-anim"></div>
      <span>Loading civic data...</span>
    </div>
  {:else if pulseError && !pulseData}
    <div class="error-state">
      <span class="error-icon">!</span>
      <p>{pulseError}</p>
      <button class="btn-retry" onclick={loadCityPulse}>Retry</button>
    </div>
  {:else if pulseData}
    <!-- Actionable items for city tab (official + public initiatives) -->
    {@const officialActionable = (pulseData.upcoming_items || []).filter(i => i.stance_eligible || i.comment_eligible).map(i => ({
      id: i.id, title: i.title, tag: 'agenda' as const, when: i.meeting_date || '',
      action: () => scrollToCard(i.id),
    }))}
    {@const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000}
    {@const initiativeActionable = loadedInitiatives
      .filter(i => i.voice_count > 0 || (i.timestamp && new Date(i.timestamp).getTime() > sevenDaysAgo))
      .slice(0, 5)
      .map(i => {
        const isRecent = i.timestamp && new Date(i.timestamp).getTime() > sevenDaysAgo;
        const label = i.voice_count > 0
          ? `${i.voice_count} voice${i.voice_count !== 1 ? 's' : ''}${isRecent ? ' · new' : ''}`
          : 'new';
        return {
          id: i.id, title: i.title, tag: 'initiative' as const, when: label,
          action: () => initiativeViewRef?.expandAndScrollTo(i.id),
        };
      })}
    {@const allActionable = [...officialActionable, ...initiativeActionable]}
    {@const interestLower = personalInterests.map(i => i.toLowerCase())}
    {@const matchesInterest = (title: string) => interestLower.length > 0 && interestLower.some(i => title.toLowerCase().includes(i))}
    {@const sortedActionable = allActionable.toSorted((a, b) => {
      const aMatch = matchesInterest(a.title) ? 0 : 1;
      const bMatch = matchesInterest(b.title) ? 0 : 1;
      return aMatch - bMatch;
    })}
    {#if sortedActionable.length > 0}
      <div class="attention-bar">
        <div class="attention-title">
          Upcoming actionable items
          {#if hubConnected && interestLower.length > 0}
            <span class="attention-personalized" title="Sorted by your interests">personalized</span>
          {/if}
        </div>
        <div class="attention-items">
          {#each sortedActionable as item}
            <button class="attention-item" onclick={item.action}>
              <span class="attention-pip" class:attention-pip-initiative={item.tag === 'initiative'} class:attention-pip-relevant={matchesInterest(item.title)}></span>
              <span class="attention-item-title">{item.title}</span>
              <span class="attention-when">{item.when}</span>
            </button>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Official Section -->
    <div class="group-header">Official</div>

    <!-- Upcoming Meetings (today or future only) -->
    {@const todayStr = new Date().toISOString().slice(0, 10)}
    {@const upcomingMeetings = (pulseData.decisions_this_week || []).filter(m => m.meeting_datetime.slice(0, 10) >= todayStr)}
    <section class="feed-section" data-section="meetings">
      <button class="section-header" onclick={() => toggle('meetings')}>
        <span class="section-title">
          Meetings
          {#if upcomingMeetings.length > 0}
            <span class="count-badge">{upcomingMeetings.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.meetings}></span>
      </button>
      {#if expanded.meetings}
        <div class="section-body">
          {#if upcomingMeetings.length === 0}
            <div class="empty-section">No upcoming meetings</div>
          {:else}
            {#each upcomingMeetings as meeting}
              <CivicMeetingCard {meeting} />
            {/each}
          {/if}
        </div>
      {/if}
    </section>

    <!-- Upcoming Agenda Items -->
    {#if pulseData.upcoming_items && pulseData.upcoming_items.length > 0}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('items')}>
          <span class="section-title">
            Agenda Items
            <span class="count-badge">{pulseData.upcoming_items.length}</span>
            {#if pulseData.upcoming_items.some(i => i.stance_eligible || i.comment_eligible)}
              <span class="section-pip" title="Has actionable items"></span>
            {/if}
          </span>
          <span class="chevron" class:open={expanded.items}></span>
        </button>
        {#if expanded.items}
          <div class="section-body">
            <div class="section-hint">Review agenda items and share your perspective before the meeting</div>
            <CivicAgendaView
              items={pulseData.upcoming_items}
              meetings={pulseData.decisions_this_week}
              generatedAt={pulseData.generated_at}
              {voiceCounts}
              {userStances}
              {votingInProgress}
              {commentCounts}
              {synthData}
              {identity}
              {aiAvailable}
              {activeProviderName}
              jurisdiction={activeJurisdiction}
              clerkEmail={pulseData?.clerk_email || ''}
              {session}
              {api}
              {renderMarkdown}
              {highlightedCardId}
              userContext={personalInterests.length > 0 || personalNeighborhood ? { neighborhood: personalNeighborhood || undefined, interests: personalInterests.length > 0 ? personalInterests : undefined } : undefined}
              onvoice={({ entityId, stance }) => handleVoice(entityId, stance)}
              onopenexternalai={({ context, event }) => openExternalAI('claude', context, event)}
              ontoast={(message) => showToast(message)}
              oncommentcountchange={(entityId, counts) => { commentCounts.set(entityId, counts); commentCounts = new Map(commentCounts); }}
            />
          </div>
        {/if}
      </section>
    {/if}

    <!-- Recent Decisions -->
    <section class="feed-section" data-section="outcomes">
      <button class="section-header" onclick={() => toggle('outcomes')}>
        <span class="section-title">
          Recent Decisions
          {#if pulseData.recent_outcomes.length > 0}
            <span class="count-badge">{pulseData.recent_outcomes.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.outcomes}></span>
      </button>
      {#if expanded.outcomes}
        <div class="section-body">
          <CivicDecisionView
            decisions={pulseData.recent_outcomes}
            {voiceCounts}
            {userStances}
            {votingInProgress}
            {synthData}
            {identity}
            {aiAvailable}
            {activeProviderName}
            jurisdiction={activeJurisdiction}
            {session}
            {renderMarkdown}
            onvoice={({ entityId, stance }) => handleVoice(entityId, stance)}
            onopenexternalai={({ context, event }) => openExternalAI('claude', context, event)}
            ontoast={(message) => showToast(message)}
          />
        </div>
      {/if}
    </section>

    <!-- Issue Map -->
    <section class="feed-section" data-section="issueMap">
      <button class="section-header" onclick={async () => { toggle('issueMap'); await tick(); issueMapRef?.load(); }}>
        <span class="section-title">Issue Map</span>
        <span class="chevron" class:open={expanded.issueMap}></span>
      </button>
      {#if expanded.issueMap}
        <div class="section-body">
          <CivicIssueMap bind:this={issueMapRef} {api} />
        </div>
      {/if}
    </section>

    <!-- Budget -->
    <section class="feed-section" data-section="budget">
      <button class="section-header" onclick={async () => { toggle('budget'); await tick(); budgetRef?.load(); }}>
        <span class="section-title">Budget</span>
        <span class="chevron" class:open={expanded.budget}></span>
      </button>
      {#if expanded.budget}
        <div class="section-body">
          <CivicBudgetBreakdown bind:this={budgetRef} {api} />
        </div>
      {/if}
    </section>

    <!-- Public Section -->
    <div class="group-header">Public</div>

    <!-- Community Initiatives (CivicInitiativeView) -->
    <CivicInitiativeView
      bind:this={initiativeViewRef}
      {api}
      {session}
      {identity}
      jurisdiction={pulseData?.jurisdiction || activeJurisdiction}
      ontoast={(message) => showToast(message)}
      oninitiativesloaded={(items) => { loadedInitiatives = items; }}
      onunlock={async (password) => {
        const response = await sendMessage({ type: 'UNLOCK', password });
        if (response.success && response.data) {
          identity = identity ? { ...identity, isUnlocked: true } : identity;
          return true;
        }
        return false;
      }}
    />

    <!-- Footer -->
    <footer class="pulse-footer">
      <span class="footer-ts">Updated {new Date(pulseData.generated_at).toLocaleTimeString()}</span>
    </footer>
  {/if}
  {:else}
    <!-- Parent jurisdiction tab content -->
    {@const tabData = parentPulseData.get(activeTab)}
    {@const tabLoading = parentPulseLoading.has(activeTab)}
    {@const tabError = parentPulseErrors.get(activeTab)}
    {@const tabServer = parentServers.find(s => s.jurisdiction_id === activeTab)}
    {#if tabLoading}
      <div class="loading-state">
        <div class="pulse-anim"></div>
        <span>Loading {tabServer?.display_name || activeTab} data...</span>
      </div>
    {:else if tabError}
      <div class="error-state">
        <span class="error-icon">!</span>
        <p>Server warming up — try again shortly</p>
        <button class="btn-retry" onclick={() => {
          if (!tabServer) return;
          const id = tabServer.jurisdiction_id;
          parentPulseErrors.delete(id);
          parentPulseErrors = new Map(parentPulseErrors);
          parentPulseLoading.add(id);
          parentPulseLoading = new Set(parentPulseLoading);
          api.getCityPulseFromServer(registry.getServerBaseUrl(tabServer))
            .then(data => { parentPulseData.set(id, data); parentPulseData = new Map(parentPulseData); })
            .catch(() => { parentPulseErrors.set(id, 'Server unavailable'); parentPulseErrors = new Map(parentPulseErrors); })
            .finally(() => { parentPulseLoading.delete(id); parentPulseLoading = new Set(parentPulseLoading); });
        }}>Retry</button>
      </div>
    {:else if tabData}
      <CivicReadOnlyPulse
        data={tabData}
        level={tabServer?.level || 'city'}
        jurisdiction={tabData?.jurisdiction || activeTab}
        {voiceCounts}
        {userStances}
        {votingInProgress}
        {identity}
        {commentCounts}
        {synthData}
        {session}
        {api}
        {aiAvailable}
        {activeProviderName}
        {renderMarkdown}
        onvoice={({ entityId, stance }) => handleVoice(entityId, stance, activeTab)}
        onopenexternalai={({ context, event }) => openExternalAI('claude', context, event)}
        ontoast={(message) => showToast(message)}
        oncommentcountchange={(entityId, counts) => { commentCounts.set(entityId, counts); commentCounts = new Map(commentCounts); }}
      >
        <CivicInitiativeView
          {api}
          {session}
          {identity}
          jurisdiction={tabData?.jurisdiction || activeTab}
          level={tabServer?.level === 'federal' ? 'federal' : tabServer?.level === 'state' ? 'state' : 'city'}
          ontoast={(message) => showToast(message)}
          onunlock={async (password) => {
            const response = await sendMessage({ type: 'UNLOCK', password });
            if (response.success && response.data) {
              identity = identity ? { ...identity, isUnlocked: true } : identity;
              return true;
            }
            return false;
          }}
        />
      </CivicReadOnlyPulse>
    {:else}
      <div class="empty-section" style="padding: 24px 12px; text-align: center;">
        No data available for {tabServer?.display_name || activeTab}
      </div>
    {/if}
  {/if}
</div>

{#if clipboardToast}
  <div class="clipboard-toast" style="top: {clipboardToast.y}px">
    <div class="clipboard-toast-title">Context copied to clipboard</div>
    <div class="clipboard-toast-hint">Press <kbd>⌘V</kbd> to paste into {clipboardToast.platform}</div>
  </div>
{/if}

{#if toastMessage}
  <div class="toast">{toastMessage}</div>
{/if}

<style>
  /* === Base === */
  .panel {
    padding: 12px;
    min-height: 100vh;
    font-size: 13px;
    line-height: 1.4;
    background: #171717;
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
  }

  /* === Header === */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #262626;
  }

  .breadcrumb {
    display: flex;
    align-items: center;
    gap: 0;
    min-width: 0;
    overflow: hidden;
  }

  .breadcrumb-segment {
    display: flex;
    align-items: center;
    gap: 5px;
    background: none;
    border: none;
    color: #9ca3af;
    font-size: 12px;
    padding: 3px 6px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    transition: color 0.15s, background 0.15s;
  }
  .breadcrumb-segment:first-child {
    font-weight: 600;
    color: #9ca3af;
  }
  .breadcrumb-segment:hover {
    color: #eee;
    background: #333;
  }
  .breadcrumb-segment.active {
    color: #d1d5db;
    background: rgba(255, 255, 255, 0.04);
  }

  .breadcrumb-sep {
    color: #4b5563;
    font-size: 12px;
    margin: 0 2px;
    flex-shrink: 0;
  }

  .segment-name {
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .endpoint-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 0 6px;
    margin-top: -8px;
    margin-bottom: 8px;
    font-family: monospace;
    font-size: 9px;
    color: #4b5563;
    overflow: hidden;
    white-space: nowrap;
  }
  .endpoint-label {
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: #6b7280;
    flex-shrink: 0;
  }
  .endpoint-url {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .endpoint-sep {
    color: #374151;
    flex-shrink: 0;
  }

  .header-actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    background: none;
    border: none;
    color: #4b5563;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .icon-btn:hover { color: #9ca3af; }
  .icon-btn:disabled { opacity: 0.5; cursor: default; }

  .spinning {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* === Loading / Error states === */
  .loading-state {
    text-align: center;
    padding: 40px 16px;
    color: #9ca3af;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .pulse-anim {
    width: 32px;
    height: 32px;
    border: 2px solid #374151;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .error-state {
    text-align: center;
    padding: 32px 16px;
    color: #9ca3af;
  }
  .error-state .error-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #7f1d1d;
    color: #fca5a5;
    font-weight: 700;
    font-size: 16px;
    margin-bottom: 8px;
  }
  .error-state p {
    font-size: 12px;
    margin-bottom: 12px;
    color: #ef4444;
  }

  .btn-retry {
    background: #262626;
    color: #eee;
    border: 1px solid #374151;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-retry:hover { background: #374151; }

  /* === Feed Sections === */
  .feed-section {
    margin-bottom: 4px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    background: none;
    border: none;
    color: #9ca3af;
    padding: 8px 4px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #262626;
  }
  .section-header:hover { color: #d1d5db; }

  .group-header {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #4b5563;
    padding: 14px 4px 4px;
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .section-pip {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #e5e7eb;
    flex-shrink: 0;
  }

  .count-badge {
    background: rgba(255, 255, 255, 0.04);
    color: #6b7280;
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 6px;
    text-transform: none;
    letter-spacing: 0;
  }

  .chevron {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #4b5563;
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }

  .section-body {
    padding: 4px 0 8px;
  }

  .section-hint {
    font-size: 11px;
    color: #9ca3af;
    padding: 2px 8px 6px;
    font-style: italic;
  }

  .empty-section {
    padding: 12px 8px;
    color: #4b5563;
    font-size: 12px;
    font-style: italic;
  }

  /* === Cards === */

  /* === Browse Pills === */
  .browse-row {
    display: flex;
    gap: 6px;
    padding: 10px 0 4px;
  }
  .browse-pill {
    font-size: 11px;
    padding: 6px 12px;
    border-radius: 8px;
    background: #1e1e1e;
    border: 1px solid #262626;
    color: #6b7280;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .browse-pill:hover { border-color: #4b5563; color: #9ca3af; }
  .browse-expanded {
    padding: 4px 0 8px;
  }

  /* === Attention Bar === */
  .attention-bar {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #2a2a4a;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 14px;
    transition: border-color 0.15s;
  }
  .attention-bar:hover { border-color: #4b5563; }
  .attention-title {
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .attention-items {
    display: flex;
    flex-direction: column;
    gap: 3px;
    max-height: 200px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #374151 transparent;
  }
  .attention-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #9ca3af;
    cursor: pointer;
    padding: 3px 0;
    background: none;
    border: none;
    text-align: left;
    width: 100%;
  }
  .attention-item:hover { color: #e5e7eb; }
  .attention-pip {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: #e5e7eb;
    flex-shrink: 0;
  }
  .attention-pip-initiative {
    background: #6b7280;
    border-radius: 1px;
  }
  .attention-pip-relevant {
    background: #6366f1;
    box-shadow: 0 0 4px rgba(99, 102, 241, 0.5);
  }
  .attention-personalized {
    font-size: 9px;
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
    color: #6366f1;
    margin-left: 6px;
  }
  .attention-item-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .attention-when {
    margin-left: auto;
    color: #6b7280;
    font-size: 10px;
    flex-shrink: 0;
  }

  /* === Interests Bar === */
  .interests-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    margin-bottom: 8px;
    background: rgba(99, 102, 241, 0.06);
    border: 1px solid rgba(99, 102, 241, 0.12);
    border-radius: 8px;
  }
  .interests-label {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #6366f1;
    flex-shrink: 0;
  }
  .interests-chips {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    min-width: 0;
  }
  .interest-chip {
    font-size: 10px;
    color: #a5b4fc;
    background: rgba(99, 102, 241, 0.1);
    padding: 2px 8px;
    border-radius: 10px;
    white-space: nowrap;
  }

  /* === Caught-up state === */
  .caught-up {
    text-align: center;
    padding: 16px 12px 8px;
    font-size: 12px;
    color: #6b7280;
  }

  /* === Footer === */
  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid #262626;
    font-size: 10px;
    color: #374151;
  }

  .icon-btn.active { color: #d1d5db; }

  /* === Breadcrumb Detail Popover === */
  .health-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot.healthy { background: #4ade80; }
  .health-dot.degraded { background: #f59e0b; }
  .health-dot.offline { background: #ef4444; }
  .health-dot.unknown { background: #4b5563; }

  /* === Connector Setup Banner === */
  .connector-banner {
    display: flex;
    gap: 8px;
    background: #1a1a2e;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .connector-banner-content { flex: 1; }
  .connector-banner-title {
    font-size: 12px;
    font-weight: 600;
    color: #e5e7eb;
    margin-bottom: 2px;
  }
  .connector-banner-desc {
    font-size: 10px;
    color: #9ca3af;
    line-height: 1.4;
    margin-bottom: 8px;
  }
  .connector-banner-actions {
    display: flex;
    gap: 6px;
  }
  .connector-setup-btn {
    font-size: 10px;
    font-weight: 500;
    color: #60a5fa;
    background: rgba(59,130,246,0.08);
    border: 1px solid #3b82f640;
    border-radius: 4px;
    padding: 3px 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .connector-setup-btn:hover {
    background: rgba(59,130,246,0.16);
    border-color: #3b82f6;
    color: #93c5fd;
  }
  .connector-banner-close {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    font-size: 16px;
    padding: 0 2px;
    line-height: 1;
    align-self: flex-start;
  }
  .connector-banner-close:hover { color: #d1d5db; }

  /* === Clipboard Toast (positioned near click) === */
  .clipboard-toast {
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    padding: 10px 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    z-index: 200;
    text-align: center;
    max-width: 90%;
    animation: toast-in 0.2s ease;
  }
  .clipboard-toast-title {
    font-size: 12px;
    font-weight: 600;
    color: #93c5fd;
    margin-bottom: 3px;
  }
  .clipboard-toast-hint {
    font-size: 11px;
    color: #cbd5e1;
  }
  .clipboard-toast-hint kbd {
    background: #334155;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 10px;
    border: 1px solid #475569;
    font-family: inherit;
  }

  /* === Toast === */
  .toast {
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: #262626;
    color: #eee;
    font-size: 12px;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid #374151;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    z-index: 100;
    animation: toast-in 0.2s ease;
  }
  /* === Connector Inline Hint === */
  .connector-hint {
    background: #0f172a;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 8px;
    animation: toast-in 0.2s ease;
  }
  .connector-hint-label {
    font-size: 10px;
    color: #93c5fd;
    margin-bottom: 6px;
  }
  .connector-hint-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 3px;
  }
  .connector-hint-row:last-child { margin-bottom: 0; }
  .connector-hint-key {
    font-size: 9px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    flex-shrink: 0;
    min-width: 32px;
  }
  .connector-hint-value {
    font-size: 11px;
    font-weight: 600;
    color: #fff;
    font-family: monospace;
    word-break: break-all;
    user-select: all;
  }
  @keyframes toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>

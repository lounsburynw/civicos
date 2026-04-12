<script lang="ts">
  import { tick } from 'svelte';
  import { sendMessage } from '../lib/messaging.js';
  import { api, registry } from '../lib/client.js';
  import { CivicSession } from '@civicos/client';
  import type { CityPulseData, DataProvenance, VoiceCounts, CommentCounts, CommentSynthesis, RegistryServer, ChatUserContext } from '@civicos/client';
  import { isAIAvailable, getAIManager, onAIConfigChanged } from '../lib/ai.js';
  import { trackInteraction, generateSuggestions, dismissTopic } from '../lib/journal-suggestions.js';
  import type { JournalSuggestion } from '../lib/journal-suggestions.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
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
  import CivicFeedbackForm from '@civicos/components/src/components/CivicFeedbackForm.svelte';
  import TokenBalance from './TokenBalance.svelte';


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

  // Profile state (from chrome.storage.local)
  const PROFILE_KEY = 'civicos_profile';
  let personalProfile: Record<string, unknown> = $state({});

  // Civic Journal state (from chrome.storage.local)
  const JOURNAL_KEY = 'civicos_journal';
  let journalText: string = $state('');

  /** Build ChatUserContext from journal — used by CivicChatBar and CivicAgendaView. */
  function buildUserContext(): ChatUserContext | undefined {
    const notes = journalText.trim();
    if (!notes) return undefined;
    return { journalNotes: notes.length > 2000 ? notes.slice(0, 2000) : notes };
  }

  // Feedback form state
  let showFeedback = $state(false);

  async function handleFeedback({ type, content }: { type: 'bug' | 'feature' | 'general'; content: string }) {
    const jurisdiction = activeJurisdiction || 'city-san-rafael';
    api.castFeedback(type, content, jurisdiction).catch(() => {});
    showToast('Feedback sent — thank you!');
  }

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

  // Journal suggestions state
  let journalSuggestions: JournalSuggestion[] = $state([]);
  let suggestionsLoading = $state(false);

  async function handleChatInteraction(question: string, toolUsed?: string) {
    const thresholdReached = await trackInteraction(question, toolUsed);
    if (thresholdReached && !suggestionsLoading && journalSuggestions.length === 0) {
      suggestionsLoading = true;
      try {
        const askAI = async (prompt: string) => session.askQuestion(prompt);
        journalSuggestions = await generateSuggestions(askAI, journalText);
      } catch {
        // Silently fail — suggestions are non-critical
      } finally {
        suggestionsLoading = false;
      }
    }
  }

  async function acceptSuggestion(suggestion: JournalSuggestion) {
    // Find the section header in the journal (# format from template)
    const lines = journalText.split('\n');
    const sectionIdx = lines.findIndex(l => {
      const trimmed = l.trim().replace(/^#+\s*/, '');
      return trimmed.toLowerCase() === suggestion.section.toLowerCase();
    });

    if (sectionIdx >= 0) {
      // Find next section or end of file
      const nextIdx = lines.findIndex((l, i) => i > sectionIdx && /^#+\s/.test(l));
      const insertIdx = nextIdx >= 0 ? nextIdx : lines.length;
      lines.splice(insertIdx, 0, `- ${suggestion.text}`);
    } else {
      // Section not found — append at end
      lines.push('', `# ${suggestion.section}`, `- ${suggestion.text}`);
    }

    journalText = lines.join('\n');
    // Save to chrome.storage.local
    await chrome.storage.local.set({ [JOURNAL_KEY]: { text: journalText } });
    // Remove from suggestions
    journalSuggestions = journalSuggestions.filter(s => s !== suggestion);
    showToast(`Added to "${suggestion.section}"`);
  }

  async function dismissSuggestion(suggestion: JournalSuggestion) {
    await dismissTopic(suggestion.text);
    journalSuggestions = journalSuggestions.filter(s => s !== suggestion);
  }

  function dismissAllSuggestions() {
    journalSuggestions = [];
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
    // Pre-warm parent servers (fire-and-forget health pings to wake cold containers)
    // By the time loadParentPulse() runs after primary pulse loads, containers are warm.
    prewarmParentServers();
  }

  function prewarmParentServers() {
    const parents = availableServers.filter(s =>
      s.jurisdiction_id !== activeJurisdiction && s.level !== 'city'
    );
    for (const server of parents) {
      fetch(server.health_endpoint, { signal: AbortSignal.timeout(25000) }).catch(() => {});
    }
  }

  /** Load profile from chrome.storage.local (always available, no server needed). */
  async function loadProfile() {
    try {
      const stored = await chrome.storage.local.get(PROFILE_KEY);
      personalProfile = stored[PROFILE_KEY] || {};
    } catch {
      personalProfile = {};
    }
  }

  /** Load civic journal from chrome.storage.local. */
  async function loadJournal() {
    try {
      const stored = await chrome.storage.local.get(JOURNAL_KEY);
      journalText = stored[JOURNAL_KEY]?.text || '';
    } catch {
      journalText = '';
    }
  }


  const PULSE_CACHE_KEY = 'civicos_pulse_cache';

  function applyPulseData(pulse: CityPulseData) {
    pulseData = pulse;
    // Primary data loaded successfully — mark healthy regardless of health ping
    serverHealth.set(activeJurisdiction, { status: 'healthy', checked_at: Date.now() });
    serverHealth = new Map(serverHealth);
    loadVoiceCounts();
    loadCommentCounts();
    loadParentPulse();
    checkAllHealth();
  }

  async function loadCityPulse() {
    pulseLoading = true;
    pulseError = null;

    // Show cached pulse immediately (stale-while-revalidate)
    try {
      const cached = await chrome.storage.local.get(PULSE_CACHE_KEY);
      const entry = cached[PULSE_CACHE_KEY];
      if (entry?.data && !pulseData) {
        pulseData = entry.data;
        pulseLoading = false; // stop spinner early
        // Kick off enrichment with stale data (but NOT parent loads —
        // those need warm containers, so defer to fresh data path)
        loadVoiceCounts();
        loadCommentCounts();
      }
    } catch { /* no cache, continue */ }

    // Always fetch fresh data in background
    try {
      const fresh = await session.loadPulse();
      // Update available servers for UI (registry was already refreshed by session)
      try { availableServers = await registry.getRegistryServers(); } catch {}
      applyPulseData(fresh);
      // Persist for next open
      chrome.storage.local.set({ [PULSE_CACHE_KEY]: { data: fresh, cached_at: Date.now() } }).catch(() => {});
    } catch (err) {
      if (!pulseData) {
        pulseError = err instanceof Error ? err.message : 'Failed to load civic data';
      }
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

    // Clear stale errors from previous load attempts
    parentPulseErrors = new Map();

    // Route parent requests through city server (parent servers may not be deployed)
    const cityBaseUrl = await registry.getMcpUrl();

    // Fetch pulse data from each parent via city server proxy
    for (const server of parentServers) {
      const id = server.jurisdiction_id;
      parentPulseLoading.add(id);
      parentPulseLoading = new Set(parentPulseLoading);

      api.getCityPulseFromServer(cityBaseUrl, 14, 30, id)
        .then(data => {
          parentPulseData.set(id, data);
          parentPulseData = new Map(parentPulseData);
          // Data loaded successfully — ensure health dot reflects reality
          // (health check may have timed out during cold start)
          const current = serverHealth.get(id);
          if (!current || current.status !== 'healthy') {
            serverHealth.set(id, { status: 'healthy', checked_at: Date.now() });
            serverHealth = new Map(serverHealth);
          }
          // Load voice counts and comment counts for this parent's legislation
          loadParentVoiceCounts(id, data);
          loadParentCommentCounts(id, data);
        })
        .catch(() => {
          parentPulseErrors.set(id, 'Server unavailable');
          parentPulseErrors = new Map(parentPulseErrors);
          // Data failed — mark degraded even if health ping succeeded
          serverHealth.set(id, { status: 'degraded', checked_at: Date.now() });
          serverHealth = new Map(serverHealth);
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
    if (p.congressional_hearings) {
      for (const hearing of p.congressional_hearings) {
        if (hearing.event_id) ids.push(`congressional_hearing:${hearing.event_id}`);
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
    // Reconcile: if data already loaded successfully, override failed health pings.
    // Health pings can fail during cold start even though data fetches (with retry) succeed.
    if (pulseData) {
      serverHealth.set(activeJurisdiction, { status: 'healthy', checked_at: Date.now() });
    }
    for (const [id, _data] of parentPulseData) {
      const health = serverHealth.get(id);
      if (health && health.status !== 'healthy') {
        serverHealth.set(id, { status: 'healthy', checked_at: Date.now() });
      }
    }
    serverHealth = new Map(serverHealth);
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

    // Auto-attach a blinded token as payment proof if available
    let paymentProof: Record<string, unknown> | undefined;
    try {
      const tokenRes = await chrome.runtime.sendMessage({ type: 'SPEND_TOKEN' });
      if (tokenRes?.success && tokenRes.data) {
        paymentProof = tokenRes.data as Record<string, unknown>;
      }
    } catch {
      // No tokens available — proceed without payment proof
    }

    api.castVoice(entityId, stance, jurisdiction, attestationProof, paymentProof).then((result) => {
      if (!result.ok && result.rejection) {
        const reason = result.rejection.reason;
        if (reason.includes('rate limit')) {
          showToast('Daily voice limit reached. Try again tomorrow.', 6000);
        } else {
          showToast('Voice not synced — verification may be required.', 6000);
        }
      }
    }).catch(() => {
      // Network error — local stance persists, will sync on next load
    });

    votingInProgress.delete(entityId);
    votingInProgress = new Set(votingInProgress);
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }


  // Load on mount — parallelize independent init paths
  initJurisdiction();
  loadProfile();
  loadJournal();
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
    if (areaName === 'session' && changes['civicos_session_key']) {
      loadIdentity();
      return;
    }
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
    if (changes[PROFILE_KEY]) {
      personalProfile = changes[PROFILE_KEY].newValue || {};
    }
    if (changes[JOURNAL_KEY]) {
      journalText = changes[JOURNAL_KEY].newValue?.text || '';
    }
    // Re-load when user changes jurisdiction in Options
    if (changes['civicos_jurisdiction']) {
      initJurisdiction();
      loadCityPulse();
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
      <button class="icon-btn" onclick={() => showFeedback = !showFeedback} title="Send Feedback" class:active={showFeedback}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
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

  <!-- Feedback form (slide-down panel) -->
  {#if showFeedback}
    <div class="feedback-panel">
      <CivicFeedbackForm
        jurisdiction={activeJurisdiction}
        disabled={!identity?.isUnlocked}
        onsubmit={handleFeedback}
      />
      {#if !identity?.isUnlocked}
        <p class="feedback-hint">Unlock your identity in Settings to send feedback.</p>
      {/if}
    </div>
  {/if}

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
    displayName={(personalProfile.name as string) || ''}
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

  <!-- Token balance + purchase -->
  <TokenBalance {identity} />

  <!-- AI Chat Bar (tool-backed search) -->
  <CivicChatBar
    {session}
    jurisdiction={activeJurisdiction}
    {aiAvailable}
    userContext={buildUserContext()}
    {renderMarkdown}
    ontoast={(message) => showToast(message)}
    onnavigate={handleChatNavigate}
    oninteraction={handleChatInteraction}
  />

  <!-- Journal suggestions banner -->
  {#if journalSuggestions.length > 0}
    <div class="suggestions-banner">
      <div class="suggestions-header">
        <span class="suggestions-title">Journal suggestions</span>
        <button class="suggestions-dismiss-all" onclick={dismissAllSuggestions} title="Dismiss all">&times;</button>
      </div>
      <div class="suggestions-list">
        {#each journalSuggestions as suggestion}
          <div class="suggestion-item">
            <div class="suggestion-content">
              <span class="suggestion-section">{suggestion.section}</span>
              <span class="suggestion-text">{suggestion.text}</span>
            </div>
            <div class="suggestion-actions">
              <button class="suggestion-accept" onclick={() => acceptSuggestion(suggestion)} title="Add to journal">+</button>
              <button class="suggestion-dismiss" onclick={() => dismissSuggestion(suggestion)} title="Dismiss">&times;</button>
            </div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

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
    {#if allActionable.length > 0}
      <div class="attention-bar">
        <div class="attention-title">Upcoming actionable items</div>
        <div class="attention-items">
          {#each allActionable as item}
            <button class="attention-item" onclick={item.action}>
              <span class="attention-pip" class:attention-pip-initiative={item.tag === 'initiative'}></span>
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
              userContext={buildUserContext()}
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
          registry.getMcpUrl().then(cityUrl =>
            api.getCityPulseFromServer(cityUrl, 14, 30, id)
              .then(data => {
                parentPulseData.set(id, data); parentPulseData = new Map(parentPulseData);
                serverHealth.set(id, { status: 'healthy', checked_at: Date.now() });
                serverHealth = new Map(serverHealth);
              })
              .catch(() => { parentPulseErrors.set(id, 'Server unavailable'); parentPulseErrors = new Map(parentPulseErrors); })
              .finally(() => { parentPulseLoading.delete(id); parentPulseLoading = new Set(parentPulseLoading); })
          );
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
    background: var(--civic-surface-panel);
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
  }

  /* === Header === */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--civic-surface-elevated);
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
    color: var(--civic-text-muted);
    font-size: 12px;
    padding: 3px 6px;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    transition: color 0.15s, background 0.15s;
  }
  .breadcrumb-segment:first-child {
    font-weight: 600;
    color: var(--civic-text-muted);
  }
  .breadcrumb-segment:hover {
    color: var(--civic-text-primary);
    background: var(--civic-border-input);
  }
  .breadcrumb-segment.active {
    color: var(--civic-text-body);
    background: var(--civic-overlay-subtle);
  }

  .breadcrumb-sep {
    color: var(--civic-text-disabled);
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
    color: var(--civic-text-disabled);
    overflow: hidden;
    white-space: nowrap;
  }
  .endpoint-label {
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: var(--civic-text-dim);
    flex-shrink: 0;
  }
  .endpoint-url {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .endpoint-sep {
    color: var(--civic-border-default);
    flex-shrink: 0;
  }

  .header-actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    background: none;
    border: none;
    color: var(--civic-text-disabled);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .icon-btn:hover { color: var(--civic-text-muted); }
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
    color: var(--civic-text-muted);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .pulse-anim {
    width: 32px;
    height: 32px;
    border: 2px solid var(--civic-border-default);
    border-top-color: var(--civic-accent-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .error-state {
    text-align: center;
    padding: 32px 16px;
    color: var(--civic-text-muted);
  }
  .error-state .error-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--civic-status-error-bg);
    color: var(--civic-status-error-light);
    font-weight: 700;
    font-size: 16px;
    margin-bottom: 8px;
  }
  .error-state p {
    font-size: 12px;
    margin-bottom: 12px;
    color: var(--civic-status-error);
  }

  .btn-retry {
    background: var(--civic-surface-elevated);
    color: var(--civic-text-primary);
    border: 1px solid var(--civic-border-default);
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-retry:hover { background: var(--civic-border-default); }

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
    color: var(--civic-text-muted);
    padding: 8px 4px;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid var(--civic-surface-elevated);
  }
  .section-header:hover { color: var(--civic-text-body); }

  .group-header {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--civic-text-disabled);
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
    background: var(--civic-text-secondary);
    flex-shrink: 0;
  }

  .count-badge {
    background: var(--civic-overlay-subtle);
    color: var(--civic-text-dim);
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
    border-top: 5px solid var(--civic-text-disabled);
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }

  .section-body {
    padding: 4px 0 8px;
  }

  .section-hint {
    font-size: 11px;
    color: var(--civic-text-muted);
    padding: 2px 8px 6px;
    font-style: italic;
  }

  .empty-section {
    padding: 12px 8px;
    color: var(--civic-text-disabled);
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
    background: var(--civic-surface-card);
    border: 1px solid var(--civic-surface-elevated);
    color: var(--civic-text-dim);
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .browse-pill:hover { border-color: var(--civic-text-disabled); color: var(--civic-text-muted); }
  .browse-expanded {
    padding: 4px 0 8px;
  }

  /* === Attention Bar === */
  .attention-bar {
    background: var(--civic-surface-attention-gradient);
    border: 1px solid var(--civic-surface-elevated);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 14px;
    transition: border-color 0.15s;
  }
  .attention-bar:hover { border-color: var(--civic-text-disabled); }
  .attention-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--civic-text-muted);
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
    scrollbar-color: var(--civic-border-default) transparent;
  }
  .attention-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--civic-text-muted);
    cursor: pointer;
    padding: 3px 0;
    background: none;
    border: none;
    text-align: left;
    width: 100%;
  }
  .attention-item:hover { color: var(--civic-text-secondary); }
  .attention-pip {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--civic-text-secondary);
    flex-shrink: 0;
  }
  .attention-pip-initiative {
    background: var(--civic-text-dim);
    border-radius: 1px;
  }
  .attention-item-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .attention-when {
    margin-left: auto;
    color: var(--civic-text-dim);
    font-size: 10px;
    flex-shrink: 0;
  }

  /* === Caught-up state === */
  .caught-up {
    text-align: center;
    padding: 16px 12px 8px;
    font-size: 12px;
    color: var(--civic-text-dim);
  }

  /* === Feedback Panel === */
  .feedback-panel {
    padding: 8px 4px;
    border-bottom: 1px solid var(--civic-border-default);
  }
  .feedback-hint {
    font-size: 10px;
    color: var(--civic-text-dim);
    text-align: center;
    margin: 6px 0 0;
  }

  /* === Footer === */
  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid var(--civic-surface-elevated);
    font-size: 10px;
    color: var(--civic-border-default);
  }

  .icon-btn.active { color: var(--civic-text-body); }

  /* === Breadcrumb Detail Popover === */
  .health-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .health-dot.healthy { background: var(--civic-status-success-light); }
  .health-dot.degraded { background: var(--civic-status-warning); }
  .health-dot.offline { background: var(--civic-status-error); }
  .health-dot.unknown { background: var(--civic-text-disabled); }

  /* === Connector Setup Banner === */
  .connector-banner {
    display: flex;
    gap: 8px;
    background: var(--civic-surface-card-alt);
    border: 1px solid var(--civic-border-default);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .connector-banner-content { flex: 1; }
  .connector-banner-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--civic-text-secondary);
    margin-bottom: 2px;
  }
  .connector-banner-desc {
    font-size: 10px;
    color: var(--civic-text-muted);
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
    color: var(--civic-accent-primary-light);
    background: var(--civic-accent-primary-bg-summary);
    border: 1px solid var(--civic-accent-primary-border-subtle);
    border-radius: 4px;
    padding: 3px 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .connector-setup-btn:hover {
    background: var(--civic-accent-primary-bg-hover);
    border-color: var(--civic-accent-primary);
    color: var(--civic-accent-primary-bright);
  }
  .connector-banner-close {
    background: none;
    border: none;
    color: var(--civic-text-dim);
    cursor: pointer;
    font-size: 16px;
    padding: 0 2px;
    line-height: 1;
    align-self: flex-start;
  }
  .connector-banner-close:hover { color: var(--civic-text-body); }

  /* === Journal Suggestions Banner === */
  .suggestions-banner {
    background: var(--civic-surface-card-alt);
    border: 1px solid var(--civic-surface-elevated);
    border-radius: 8px;
    padding: 8px 10px;
    margin-bottom: 12px;
    animation: fadeInUp 0.3s ease-out;
  }
  .suggestions-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .suggestions-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--civic-ai-accent);
  }
  .suggestions-dismiss-all {
    background: none;
    border: none;
    color: var(--civic-text-dim);
    cursor: pointer;
    font-size: 14px;
    padding: 0 2px;
    line-height: 1;
  }
  .suggestions-dismiss-all:hover { color: var(--civic-text-body); }
  .suggestions-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .suggestion-item {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border-radius: 6px;
    background: var(--civic-ai-bg-suggestion);
    border: 1px solid transparent;
    transition: border-color 0.15s;
  }
  .suggestion-item:hover {
    border-color: var(--civic-ai-border-suggestion);
  }
  .suggestion-content {
    flex: 1;
    min-width: 0;
  }
  .suggestion-section {
    display: block;
    font-size: 9px;
    color: var(--civic-text-dim);
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .suggestion-text {
    display: block;
    font-size: 11px;
    color: var(--civic-text-body);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .suggestion-actions {
    display: flex;
    gap: 2px;
    flex-shrink: 0;
  }
  .suggestion-accept {
    background: var(--civic-ai-bg-accept);
    border: 1px solid var(--civic-ai-border-accept);
    border-radius: 4px;
    color: var(--civic-ai-accent);
    font-size: 12px;
    font-weight: 600;
    width: 22px;
    height: 22px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  .suggestion-accept:hover {
    background: var(--civic-ai-bg-accept-hover);
    border-color: var(--civic-ai-accent);
  }
  .suggestion-dismiss {
    background: none;
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--civic-text-disabled);
    font-size: 12px;
    width: 22px;
    height: 22px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  .suggestion-dismiss:hover {
    color: var(--civic-text-muted);
    border-color: var(--civic-border-default);
  }

  /* === Clipboard Toast (positioned near click) === */
  .clipboard-toast {
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    background: var(--civic-border-divider);
    border: 1px solid var(--civic-accent-primary);
    border-radius: 8px;
    padding: 10px 16px;
    box-shadow: var(--civic-shadow-toast);
    z-index: 200;
    text-align: center;
    max-width: 90%;
    animation: toast-in 0.2s ease;
  }
  .clipboard-toast-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--civic-accent-primary-bright);
    margin-bottom: 3px;
  }
  .clipboard-toast-hint {
    font-size: 11px;
    color: var(--civic-text-body);
  }
  .clipboard-toast-hint kbd {
    background: var(--civic-border-default);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 10px;
    border: 1px solid var(--civic-border-strong);
    font-family: inherit;
  }

  /* === Toast === */
  .toast {
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--civic-surface-elevated);
    color: var(--civic-text-primary);
    font-size: 12px;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid var(--civic-border-default);
    box-shadow: var(--civic-shadow-elevated);
    z-index: 100;
    animation: toast-in 0.2s ease;
  }
  /* === Connector Inline Hint === */
  .connector-hint {
    background: var(--civic-surface-base);
    border: 1px solid var(--civic-accent-primary);
    border-radius: 6px;
    padding: 8px 10px;
    margin-top: 8px;
    animation: toast-in 0.2s ease;
  }
  .connector-hint-label {
    font-size: 10px;
    color: var(--civic-accent-primary-bright);
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
    color: var(--civic-text-dim);
    text-transform: uppercase;
    flex-shrink: 0;
    min-width: 32px;
  }
  .connector-hint-value {
    font-size: 11px;
    font-weight: 600;
    color: var(--civic-text-bright);
    font-family: monospace;
    word-break: break-all;
    user-select: all;
  }
  @keyframes toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>

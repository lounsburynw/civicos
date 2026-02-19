<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import { api, registry } from '../lib/client.js';
  import { CivicSession } from '@civicos/client';
  import type { CityPulseData, DataProvenance, VoiceCounts, IssuePoint, BudgetCategory, CommentCounts, CommentSynthesis, RegistryServer } from '@civicos/client';
  import { isAIAvailable, getAIManager, onAIConfigChanged } from '../lib/ai.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import 'leaflet/dist/leaflet.css';
  import L from 'leaflet';
  import { Chart, DoughnutController, ArcElement, Tooltip, Legend } from 'chart.js';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';
  // Reusable components from @civicos/components
  import CivicAgendaView from '@civicos/components/src/components/CivicAgendaView.svelte';
  import CivicDecisionView from '@civicos/components/src/components/CivicDecisionView.svelte';
  import CivicInitiativeView from '@civicos/components/src/components/CivicInitiativeView.svelte';

  Chart.register(DoughnutController, ArcElement, Tooltip, Legend);

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
    meetings: true,
    items: true,
    outcomes: true,
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
  let hasAttestation = $state(false);

  // Comment counts & synthesis (loaded in bulk, shared with CivicAgendaView)
  let commentCounts = $state(new Map<string, CommentCounts>());
  let synthData = $state(new Map<string, CommentSynthesis>());

  // AI state (shared across sections — decisions, initiatives)
  let aiAvailable = $state(false);
  let activeProviderName = $state('');

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

  // Calendar dropdown
  let calendarOpen: string | null = $state(null);

  // Connector setup state
  let connectorSetupDismissed = $state(false);
  let connectorSetupLoaded = $state(false);
  const CONNECTOR_SETUP_KEY = 'civicos_connector_setup_dismissed';

  // Inline unlock
  let unlockPassword = $state('');
  let unlocking = $state(false);
  let unlockError: string | null = $state(null);

  // Issue map state
  let issuePoints: IssuePoint[] = $state([]);
  let issueMapLoading = $state(false);
  let issueMapLoaded = $state(false);
  let leafletMap: L.Map | null = null;
  let mapContainer: HTMLDivElement | undefined = $state(undefined);

  // Budget chart state
  let budgetCategories: BudgetCategory[] = $state([]);
  let budgetTotal = $state(0);
  let budgetYear = $state('');
  let budgetLoading = $state(false);
  let budgetLoaded = $state(false);
  let chartCanvas: HTMLCanvasElement | undefined = $state(undefined);
  let budgetChart: Chart | null = null;

  // Toast notification
  let toastMessage: string | null = $state(null);
  let toastTimeout: ReturnType<typeof setTimeout> | null = null;

  function showToast(message: string, durationMs = 4000) {
    toastMessage = message;
    if (toastTimeout) clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => { toastMessage = null; }, durationMs);
  }


  function toggle(section: string) {
    expanded[section] = !expanded[section];
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
      hasAttestation = !!stored.civicos_attestation;
    } catch {
      hasAttestation = false;
    }
  }

  async function handleUnlock() {
    if (!unlockPassword) return;
    unlocking = true;
    unlockError = null;

    const response = await sendMessage<boolean>({
      type: 'UNLOCK',
      password: unlockPassword,
    });

    if (response.success && response.data) {
      identity = identity ? { ...identity, isUnlocked: true } : identity;
    } else {
      unlockError = 'Wrong password';
    }
    unlockPassword = '';
    unlocking = false;
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
    try {
      const response = await fetch(server.health_endpoint, { signal: AbortSignal.timeout(5000) });
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

  function isPastMeeting(meeting: { meeting_datetime: string }): boolean {
    return new Date(meeting.meeting_datetime) < new Date();
  }

  function googleCalendarUrl(meeting: { title: string; date: string; time: string; location: string; meeting_datetime: string }): string {
    const start = new Date(meeting.meeting_datetime);
    const end = new Date(start.getTime() + 2 * 60 * 60 * 1000); // assume 2hr
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    return `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(meeting.title)}&dates=${fmt(start)}/${fmt(end)}&location=${encodeURIComponent(meeting.location || '')}`;
  }

  function downloadIcs(meeting: { title: string; location: string; meeting_datetime: string }) {
    const start = new Date(meeting.meeting_datetime);
    const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const ics = `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nDTSTART:${fmt(start)}\nDTEND:${fmt(end)}\nSUMMARY:${meeting.title}\nLOCATION:${meeting.location || ''}\nEND:VEVENT\nEND:VCALENDAR`;
    const blob = new Blob([ics], { type: 'text/calendar' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${meeting.title.replace(/[^a-zA-Z0-9]/g, '_')}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleCalendar(meetingTitle: string) {
    calendarOpen = calendarOpen === meetingTitle ? null : meetingTitle;
  }

  // === Issue Map ===

  const ISSUE_COLORS: Record<string, string> = {
    'Pothole': '#ef4444',
    'Graffiti': '#f59e0b',
    'Illegal Dumping': '#8b5cf6',
    'Sidewalk': '#3b82f6',
    'Street Light': '#eab308',
    'Tree': '#22c55e',
    'Traffic': '#f97316',
    'Other': '#6b7280',
  };

  function getIssueColor(type: string): string {
    for (const [key, color] of Object.entries(ISSUE_COLORS)) {
      if (type.toLowerCase().includes(key.toLowerCase())) return color;
    }
    return ISSUE_COLORS['Other'];
  }

  function getIssueCategory(type: string): string {
    for (const key of Object.keys(ISSUE_COLORS)) {
      if (type.toLowerCase().includes(key.toLowerCase())) return key;
    }
    return 'Other';
  }

  let activeIssueFilters = $state(new Set(Object.keys(ISSUE_COLORS)));
  let issueLayerGroups = new Map<string, L.LayerGroup>();
  let mapExpanded = $state(false);
  let mapDaysFilter: number | null = $state(null); // null = all time

  const MAP_DAYS_OPTIONS: { label: string; value: number | null }[] = [
    { label: '7d', value: 7 },
    { label: '30d', value: 30 },
    { label: '90d', value: 90 },
    { label: 'All', value: null },
  ];

  function toggleMapExpanded() {
    mapExpanded = !mapExpanded;
    // Wait for CSS transition (200ms) to finish before recalculating tile coverage
    setTimeout(() => leafletMap?.invalidateSize(), 250);
  }

  function issuesInWindow(points: IssuePoint[], days: number | null): IssuePoint[] {
    if (days === null) return points;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    return points.filter(pt => new Date(pt.created_at) >= cutoff);
  }

  function timeFilteredPoints(): IssuePoint[] {
    return issuesInWindow(issuePoints, mapDaysFilter);
  }

  function categoryCounts(): Map<string, number> {
    const counts = new Map<string, number>();
    for (const cat of Object.keys(ISSUE_COLORS)) counts.set(cat, 0);
    for (const pt of timeFilteredPoints()) {
      const cat = getIssueCategory(pt.type);
      counts.set(cat, (counts.get(cat) || 0) + 1);
    }
    return counts;
  }

  function issueTrend(): { pct: number; direction: 'up' | 'down' | 'flat' } | null {
    // Compare current 30d vs previous 30d
    const now = new Date();
    const d30ago = new Date(); d30ago.setDate(now.getDate() - 30);
    const d60ago = new Date(); d60ago.setDate(now.getDate() - 60);
    const current = issuePoints.filter(pt => new Date(pt.created_at) >= d30ago).length;
    const previous = issuePoints.filter(pt => {
      const d = new Date(pt.created_at);
      return d >= d60ago && d < d30ago;
    }).length;
    if (previous === 0 && current === 0) return null;
    if (previous === 0) return { pct: 100, direction: 'up' };
    const pct = Math.round(((current - previous) / previous) * 100);
    if (pct === 0) return { pct: 0, direction: 'flat' };
    return { pct: Math.abs(pct), direction: pct > 0 ? 'up' : 'down' };
  }

  function toggleIssueFilter(category: string) {
    if (activeIssueFilters.has(category)) {
      activeIssueFilters.delete(category);
      const lg = issueLayerGroups.get(category);
      if (lg && leafletMap) leafletMap.removeLayer(lg);
    } else {
      activeIssueFilters.add(category);
      const lg = issueLayerGroups.get(category);
      if (lg && leafletMap) leafletMap.addLayer(lg);
    }
    activeIssueFilters = new Set(activeIssueFilters);
  }

  function setDaysFilter(days: number | null) {
    mapDaysFilter = days;
    rebuildMapMarkers();
  }

  function rebuildMapMarkers() {
    if (!leafletMap) return;
    // Remove existing layer groups
    for (const lg of issueLayerGroups.values()) {
      leafletMap.removeLayer(lg);
    }
    issueLayerGroups.clear();
    // Rebuild from time-filtered points
    const points = timeFilteredPoints();
    const grouped = new Map<string, L.CircleMarker[]>();
    for (const pt of points) {
      const cat = getIssueCategory(pt.type);
      const marker = L.circleMarker([pt.lat, pt.lng], {
        radius: 5,
        color: getIssueColor(pt.type),
        fillColor: getIssueColor(pt.type),
        fillOpacity: 0.7,
        weight: 1,
      }).bindPopup(`<b>${pt.type}</b><br>${pt.address}<br><small>${pt.status}</small>`);
      if (!grouped.has(cat)) grouped.set(cat, []);
      grouped.get(cat)!.push(marker);
    }
    for (const [cat, markers] of grouped) {
      const lg = L.layerGroup(markers);
      issueLayerGroups.set(cat, lg);
      if (activeIssueFilters.has(cat)) lg.addTo(leafletMap);
    }
  }

  function filteredIssueCount(): number {
    return timeFilteredPoints().filter(pt => activeIssueFilters.has(getIssueCategory(pt.type))).length;
  }

  async function loadIssueMap() {
    if (issueMapLoaded || issueMapLoading) return;
    issueMapLoading = true;
    try {
      const data = await api.getIssueGeography(500);
      issuePoints = data.points;
      issueMapLoaded = true;
    } catch (e) {
      console.error('Failed to load issue map:', e);
    } finally {
      issueMapLoading = false;
    }
  }

  // Render map when container becomes available (after Svelte re-renders)
  $effect(() => {
    if (mapContainer && issuePoints.length > 0) {
      // Use tick to ensure DOM is fully ready
      requestAnimationFrame(() => renderMap());
    }
  });

  function renderMap() {
    if (!mapContainer || issuePoints.length === 0) return;

    // If map already exists, just invalidate size (handles re-expand)
    if (leafletMap) {
      leafletMap.invalidateSize();
      return;
    }

    leafletMap = L.map(mapContainer, {
      zoomControl: false,
      attributionControl: false,
    }).setView([37.9735, -122.5311], 13);

    L.control.zoom({ position: 'topright' }).addTo(leafletMap);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
    }).addTo(leafletMap);

    // Build markers from time-filtered points
    rebuildMapMarkers();

    // Fit bounds to all points (not filtered, so initial view is stable)
    if (issuePoints.length > 1) {
      const bounds = L.latLngBounds(issuePoints.map(p => [p.lat, p.lng] as [number, number]));
      leafletMap.fitBounds(bounds, { padding: [20, 20] });
    }

    // Invalidate size after a brief delay to ensure container has final dimensions
    setTimeout(() => leafletMap?.invalidateSize(), 200);
  }

  // === Budget Chart ===

  const BUDGET_COLORS = [
    '#3b82f6', '#ec4899', '#14b8a6', '#f59e0b', '#ef4444',
    '#8b5cf6', '#22c55e', '#3b82f6', '#f97316', '#6b7280',
    '#a855f7', '#06b6d4', '#84cc16', '#e11d48',
  ];

  async function loadBudget() {
    if (budgetLoaded || budgetLoading) return;
    budgetLoading = true;
    try {
      const data = await api.getBudgetSummary('department');
      budgetCategories = data.categories;
      budgetTotal = data.total_budgeted_dollars;
      budgetYear = data.fiscal_year;
      budgetLoaded = true;
    } catch (e) {
      console.error('Failed to load budget:', e);
    } finally {
      budgetLoading = false;
    }
  }

  // Render chart when canvas becomes available (after Svelte re-renders)
  $effect(() => {
    if (chartCanvas && budgetCategories.length > 0) {
      requestAnimationFrame(() => renderBudgetChart());
    }
  });

  function renderBudgetChart() {
    if (!chartCanvas || budgetCategories.length === 0) return;
    if (budgetChart) { budgetChart.destroy(); budgetChart = null; }

    budgetChart = new Chart(chartCanvas, {
      type: 'doughnut',
      data: {
        labels: budgetCategories.map(c => c.category),
        datasets: [{
          data: budgetCategories.map(c => c.budgeted_dollars),
          backgroundColor: budgetCategories.map((_, i) => BUDGET_COLORS[i % BUDGET_COLORS.length]),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const val = ctx.raw as number;
                return ` $${(val / 1_000_000).toFixed(1)}M (${budgetCategories[ctx.dataIndex].percentage}%)`;
              },
            },
          },
        },
      },
    });
  }

  function formatDollars(amount: number): string {
    if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
    if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`;
    return `$${amount.toFixed(0)}`;
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

  async function handleVoice(entityId: string, stance: Stance) {
    if (votingInProgress.has(entityId)) return;
    if (!identity?.isUnlocked) return;

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

    // Sign and submit
    try {
      const jurisdiction = pulseData?.jurisdiction || activeJurisdiction;
      const ok = await api.castVoice(entityId, stance, jurisdiction);
      if (!ok) {
        throw new Error('Relay submission failed');
      }
    } catch {
      // Revert on failure
      voiceCounts.set(entityId, prevCounts);
      voiceCounts = new Map(voiceCounts);
      if (prevStance) {
        userStances.set(entityId, prevStance);
      } else {
        userStances.delete(entityId);
      }
      userStances = new Map(userStances);
      persistStances();
    }

    votingInProgress.delete(entityId);
    votingInProgress = new Set(votingInProgress);
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }

  function truncateNpub(npub: string): string {
    if (npub.length <= 16) return npub;
    return npub.slice(0, 10) + '...' + npub.slice(-6);
  }

  function formatMeetingTime(meeting: { date: string; time: string }): string {
    return meeting.time ? `${meeting.date} @ ${meeting.time}` : meeting.date;
  }

  function outcomeIcon(outcome: string): string {
    const lower = outcome.toLowerCase();
    if (lower === 'on_agenda') return '\u25B6';
    if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted')) return '\u2713';
    if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected')) return '\u2717';
    if (lower.includes('continued') || lower.includes('tabled')) return '\u21BB';
    return '\u2022';
  }

  function outcomeClass(outcome: string): string {
    const lower = outcome.toLowerCase();
    if (lower === 'on_agenda') return 'upcoming';
    if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted')) return 'passed';
    if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected')) return 'failed';
    return 'other';
  }

  function formatRelativeDate(dateStr: string | null): string {
    if (!dateStr) return 'unknown';
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 30) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  }

  // Load on mount
  initJurisdiction();
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
      hasAttestation = !!changes['civicos_attestation'].newValue;
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
    <div class="provenance-panel">
      {#if provenanceLoading}
        <div class="prov-loading">Loading data sources...</div>
      {:else if provenanceData}
        <div class="prov-header">
          <span class="prov-title">Data Sources</span>
          <span class="prov-jurisdiction">{provenanceData.jurisdiction}</span>
        </div>
        <div class="prov-stats">
          <span>{provenanceData.total_storage_docs.toLocaleString()} records</span>
          <span class="meta-sep">&middot;</span>
          <span>{provenanceData.total_vector_docs.toLocaleString()} embeddings</span>
        </div>
        <div class="prov-corpora">
          {#each provenanceData.corpora as corpus}
            <div class="corpus-row">
              <span class="corpus-name">{corpus.display_name}</span>
              <span class="corpus-stats">
                <span class="corpus-count">{corpus.storage_count.toLocaleString()}</span>
                {#if corpus.vector_count > 0}
                  {#if corpus.vector_count > corpus.storage_count}
                    <!-- Chunked corpus (e.g. transcripts → many embeddings) -->
                    <span class="corpus-indexed">indexed</span>
                  {:else if corpus.coverage_percent !== null && corpus.coverage_percent >= 99}
                    <span class="corpus-indexed">indexed</span>
                  {:else if corpus.coverage_percent !== null}
                    <span class="corpus-coverage" class:low={corpus.coverage_percent < 50}>
                      {Math.round(corpus.coverage_percent)}%
                    </span>
                  {/if}
                {:else if corpus.coverage_percent !== null}
                  <span class="corpus-coverage low">0%</span>
                {/if}
              </span>
            </div>
          {/each}
        </div>
        <div class="prov-footer-row">
          {#if provenanceData.freshness.last_updated}
            <span class="prov-freshness">
              Updated {formatRelativeDate(provenanceData.freshness.last_updated)}
            </span>
          {/if}
          <span class="prov-backend">{provenanceData.storage_backend}</span>
        </div>
      {:else}
        <div class="prov-loading">Unable to load data sources</div>
      {/if}
    </div>
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
  {#if loading}
    <div class="identity-chip skeleton">&nbsp;</div>
  {:else if identity}
    <div class="identity-chip">
      <div class="chip-row">
        <span class="tier-badge private">private</span>
        {#if identity.isUnlocked}
          <span class="lock-status unlocked">unlocked</span>
        {:else}
          <span class="lock-status">locked</span>
        {/if}
        {#if hasAttestation}
          <span class="attested-chip">Attested</span>
        {/if}
      </div>
      {#if !identity.isUnlocked}
        <form class="chip-unlock-form" onsubmit={(e: Event) => { e.preventDefault(); handleUnlock(); }}>
          <input type="password" class="chip-unlock-input" placeholder="Password" bind:value={unlockPassword} autocomplete="off" />
          <button type="submit" class="chip-unlock-btn" disabled={unlocking || !unlockPassword}>{unlocking ? '...' : 'Unlock'}</button>
        </form>
        {#if unlockError}
          <div class="chip-unlock-error">{unlockError}</div>
        {/if}
      {:else}
        <div class="npub">{truncateNpub(identity.npub)}</div>
      {/if}
    </div>
  {:else}
    <div class="identity-chip empty">
      <span>No identity</span>
      <button class="link-btn" onclick={openOptions}>Set up</button>
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
    <!-- Upcoming Meetings -->
    <section class="feed-section">
      <button class="section-header" onclick={() => toggle('meetings')}>
        <span class="section-title">
          Meetings
          {#if pulseData.decisions_this_week.length > 0}
            <span class="count-badge">{pulseData.decisions_this_week.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.meetings}></span>
      </button>
      {#if expanded.meetings}
        <div class="section-body">
          {#if pulseData.decisions_this_week.length === 0}
            <div class="empty-section">No upcoming meetings</div>
          {:else}
            {#each pulseData.decisions_this_week as meeting}
              <div class="card meeting-card" class:past-meeting={isPastMeeting(meeting)}>
                <div class="meeting-top-row">
                  <div class="card-title">
                    {#if isPastMeeting(meeting)}<span class="past-icon" title="Past meeting">&#128337;</span>{/if}
                    {meeting.title}
                  </div>
                  <button class="cal-btn" onclick={() => toggleCalendar(meeting.title)} title="Add to calendar" disabled={isPastMeeting(meeting)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </button>
                </div>
                <div class="card-meta">
                  <span class="meta-date">{formatMeetingTime(meeting)}</span>
                  {#if meeting.location}
                    <span class="meta-sep">&middot;</span>
                    <span class="meta-location">{meeting.location}</span>
                  {/if}
                </div>
                {#if calendarOpen === meeting.title}
                  <div class="cal-dropdown">
                    <a href={googleCalendarUrl(meeting)} target="_blank" rel="noopener" class="cal-option">Google Calendar</a>
                    <button class="cal-option" onclick={() => downloadIcs(meeting)}>Download .ics</button>
                  </div>
                {/if}
              </div>
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
          </span>
          <span class="chevron" class:open={expanded.items}></span>
        </button>
        {#if expanded.items}
          <div class="section-body">
            <CivicAgendaView
              items={pulseData.upcoming_items}
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
    <section class="feed-section">
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

    <!-- Community Initiatives + My Commitments (CivicInitiativeView) -->
    <CivicInitiativeView
      {api}
      {session}
      {identity}
      jurisdiction={pulseData?.jurisdiction || activeJurisdiction}
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

    <!-- Issue Map -->
    <section class="feed-section">
      <button class="section-header" onclick={() => { toggle('issueMap'); if (!issueMapLoaded) loadIssueMap(); }}>
        <span class="section-title">Issue Map</span>
        <span class="chevron" class:open={expanded.issueMap}></span>
      </button>
      {#if expanded.issueMap}
        <div class="section-body">
          {#if issueMapLoading}
            <div class="viz-loading">Loading issue locations...</div>
          {:else if issuePoints.length === 0}
            <div class="empty-section">No issue location data available</div>
          {:else}
            {@const counts = categoryCounts()}
            {@const trend = issueTrend()}
            <div class="map-time-bar">
              {#each MAP_DAYS_OPTIONS as opt}
                <button
                  class="time-chip"
                  class:active={mapDaysFilter === opt.value}
                  onclick={() => setDaysFilter(opt.value)}
                >{opt.label}</button>
              {/each}
              {#if trend}
                <span class="trend-stat" class:trend-up={trend.direction === 'up'} class:trend-down={trend.direction === 'down'}>
                  {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '—'} {trend.pct}% past 30d
                </span>
              {/if}
            </div>
            <div class="map-filters">
              {#each Object.entries(ISSUE_COLORS) as [label, color]}
                <button
                  class="filter-chip"
                  class:inactive={!activeIssueFilters.has(label)}
                  onclick={() => toggleIssueFilter(label)}
                >
                  <span class="legend-dot" style="background:{activeIssueFilters.has(label) ? color : '#4b5563'}"></span>
                  {label}
                  <span class="chip-count">{counts.get(label) || 0}</span>
                </button>
              {/each}
            </div>
            <div class="map-container" class:map-expanded={mapExpanded}>
              <div class="map-wrapper" bind:this={mapContainer}></div>
              <button class="map-expand-btn" onclick={toggleMapExpanded} title={mapExpanded ? 'Collapse map' : 'Expand map'}>
                {mapExpanded ? '↙' : '↗'}
              </button>
            </div>
            <div class="viz-stat">{filteredIssueCount()} of {timeFilteredPoints().length} issues shown</div>
          {/if}
        </div>
      {/if}
    </section>

    <!-- Budget Breakdown -->
    <section class="feed-section">
      <button class="section-header" onclick={() => { toggle('budget'); if (!budgetLoaded) loadBudget(); }}>
        <span class="section-title">Budget</span>
        <span class="chevron" class:open={expanded.budget}></span>
      </button>
      {#if expanded.budget}
        <div class="section-body">
          {#if budgetLoading}
            <div class="viz-loading">Loading budget data...</div>
          {:else if budgetCategories.length === 0}
            <div class="empty-section">No budget data available</div>
          {:else}
            <div class="budget-header">
              <span class="budget-total">{formatDollars(budgetTotal)}</span>
              <span class="budget-year">{budgetYear}</span>
            </div>
            <div class="chart-wrapper">
              <canvas bind:this={chartCanvas} width="200" height="200"></canvas>
            </div>
            <div class="budget-legend">
              {#each budgetCategories.slice(0, 8) as cat, i}
                <div class="budget-legend-item">
                  <span class="legend-dot" style="background:{BUDGET_COLORS[i % BUDGET_COLORS.length]}"></span>
                  <span class="budget-cat-name">{cat.category}</span>
                  <span class="budget-cat-amount">{formatDollars(cat.budgeted_dollars)} ({cat.percentage}%)</span>
                </div>
              {/each}
              {#if budgetCategories.length > 8}
                <div class="budget-legend-more">+{budgetCategories.length - 8} more departments</div>
              {/if}
            </div>
          {/if}
        </div>
      {/if}
    </section>

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
      </div>
    {:else if tabData}
      <!-- Meetings -->
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('meetings')}>
          <span class="section-title">
            Meetings
            {#if tabData.decisions_this_week.length > 0}
              <span class="count-badge">{tabData.decisions_this_week.length}</span>
            {/if}
          </span>
          <span class="chevron" class:open={expanded.meetings}></span>
        </button>
        {#if expanded.meetings}
          <div class="section-body">
            {#if tabData.decisions_this_week.length === 0}
              <div class="empty-section">No upcoming meetings</div>
            {:else}
              {#each tabData.decisions_this_week as meeting}
                <div class="card meeting-card" class:past-meeting={isPastMeeting(meeting)}>
                  <div class="meeting-top-row">
                    <div class="card-title">
                      {#if isPastMeeting(meeting)}<span class="past-icon" title="Past meeting">&#128337;</span>{/if}
                      {meeting.title}
                    </div>
                  </div>
                  <div class="card-meta">
                    <span class="meta-date">{formatMeetingTime(meeting)}</span>
                    {#if meeting.location}
                      <span class="meta-sep">&middot;</span>
                      <span class="meta-location">{meeting.location}</span>
                    {/if}
                  </div>
                </div>
              {/each}
            {/if}
          </div>
        {/if}
      </section>

      <!-- Agenda Items -->
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('items')}>
          <span class="section-title">
            Agenda Items
            {#if tabData.upcoming_items && tabData.upcoming_items.length > 0}
              <span class="count-badge">{tabData.upcoming_items.length}</span>
            {/if}
          </span>
          <span class="chevron" class:open={expanded.items}></span>
        </button>
        {#if expanded.items}
          <div class="section-body">
            {#if !tabData.upcoming_items || tabData.upcoming_items.length === 0}
              <div class="empty-section">No upcoming agenda items</div>
            {:else}
              {#each tabData.upcoming_items as item}
                <div class="card item-card">
                  <div class="card-title">{item.title}</div>
                  <div class="card-meta">
                    {#if item.meeting_title}
                      <span class="meta-body">{item.meeting_title}</span>
                    {/if}
                    {#if item.project_type}
                      <span class="item-type">{item.project_type}</span>
                    {/if}
                  </div>
                </div>
              {/each}
            {/if}
          </div>
        {/if}
      </section>

      <!-- Recent Outcomes -->
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('outcomes')}>
          <span class="section-title">
            Recent Outcomes
            {#if tabData.recent_outcomes.length > 0}
              <span class="count-badge">{tabData.recent_outcomes.length}</span>
            {/if}
          </span>
          <span class="chevron" class:open={expanded.outcomes}></span>
        </button>
        {#if expanded.outcomes}
          <div class="section-body">
            {#if tabData.recent_outcomes.length === 0}
              <div class="empty-section">No recent outcomes</div>
            {:else}
              {#each tabData.recent_outcomes as outcome}
                <div class="card">
                  <div class="card-title">
                    <span class="outcome-icon {outcomeClass(outcome.outcome)}">{outcomeIcon(outcome.outcome)}</span>
                    {outcome.title}
                  </div>
                  <div class="card-meta">
                    <span class="meta-date">{formatRelativeDate(outcome.date)}</span>
                    {#if outcome.outcome}
                      <span class="meta-sep">&middot;</span>
                      <span class="outcome-label">{outcome.outcome.replace(/_/g, ' ')}</span>
                    {/if}
                  </div>
                </div>
              {/each}
            {/if}
          </div>
        {/if}
      </section>

      <!-- Footer -->
      <footer class="pulse-footer">
        <span class="footer-ts">Updated {new Date(tabData.generated_at).toLocaleTimeString()}</span>
      </footer>
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
    border-bottom: 1px solid #374151;
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
    color: #d1d5db;
  }
  .breadcrumb-segment:hover {
    color: #eee;
    background: #333;
  }
  .breadcrumb-segment.active {
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    border-bottom: 2px solid #60a5fa;
    padding-bottom: 2px;
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
    color: #9ca3af;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .icon-btn:hover { color: #eee; background: #333; }
  .icon-btn:disabled { opacity: 0.5; cursor: default; }

  .spinning {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* === Identity Chip === */
  .identity-chip {
    background: #262626;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .identity-chip.skeleton {
    height: 48px;
    animation: pulse 1.5s infinite;
  }
  .identity-chip.empty {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #6b7280;
    font-size: 12px;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 0.3; }
  }

  .chip-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 4px;
  }

  .tier-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 3px;
    background: #374151;
    color: #9ca3af;
  }
  .tier-badge.private { background: #3b1f4b; color: #c084fc; }

  .lock-status {
    font-size: 10px;
    color: #ef4444;
  }
  .lock-status.unlocked { color: #22c55e; }
  .attested-chip {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #22c55e;
    background: rgba(34, 197, 94, 0.12);
    padding: 1px 6px;
    border-radius: 3px;
    margin-left: auto;
  }
  .lock-btn {
    background: none;
    border: 1px solid #ef4444;
    border-radius: 4px;
    cursor: pointer;
    padding: 1px 6px;
    font-size: 10px;
    color: #ef4444;
  }
  .lock-btn:hover { background: rgba(239, 68, 68, 0.1); }
  .lock-btn:disabled { opacity: 0.5; cursor: default; }

  .chip-unlock-form {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .chip-unlock-input {
    flex: 1;
    min-width: 0;
    padding: 4px 8px;
    background: #1a1a1a;
    border: 1px solid #404040;
    border-radius: 4px;
    color: #e5e7eb;
    font-size: 12px;
    outline: none;
  }
  .chip-unlock-input:focus { border-color: #6366f1; }
  .chip-unlock-btn {
    background: #6366f1;
    color: white;
    border: none;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
  }
  .chip-unlock-btn:hover { background: #4f46e5; }
  .chip-unlock-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .chip-unlock-error {
    font-size: 10px;
    color: #ef4444;
    margin-top: 2px;
  }

  .unlock-inline {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 6px;
  }
  .unlock-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #6b7280;
  }

  .link-btn {
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 12px;
    text-decoration: underline;
  }
  .link-btn:hover { color: #60a5fa; }

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
    color: #eee;
    padding: 8px 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #374151;
  }
  .section-header:hover { color: #eee; }

  .section-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .count-badge {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 8px;
    text-transform: none;
    letter-spacing: 0;
  }

  .chevron {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6b7280;
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }

  .section-body {
    padding: 4px 0 8px;
  }

  .empty-section {
    padding: 12px 8px;
    color: #4b5563;
    font-size: 12px;
    font-style: italic;
  }

  /* === Cards === */
  .card {
    background: #262626;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 6px;
    border: 1px solid #374151;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .card:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59,130,246,0.1);
  }

  .card-title {
    color: #eee;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.3;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #6b7280;
    margin-top: 4px;
    flex-wrap: wrap;
  }

  .meta-sep { color: #4b5563; }

  .card-desc {
    color: #9ca3af;
    font-size: 12px;
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .card-why {
    color: #9ca3af;
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.45;
  }
  .card-top-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 11px;
    color: #6b7280;
  }

  .item-number {
    color: #60a5fa;
    font-weight: 600;
  }

  .card-tags {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    flex-wrap: wrap;
  }

  .tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: #374151;
    color: #9ca3af;
  }
  .tag-voice { background: #1e3a5f; color: #60a5fa; }
  .tag-comment { background: #1a332e; color: #34d399; }

  /* === Decision cards === */
  .decision-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }

  .outcome-icon {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    margin-top: 1px;
  }
  .outcome-icon.passed { background: #14532d; color: #4ade80; }
  .outcome-icon.failed { background: #7f1d1d; color: #f87171; }
  .outcome-icon.upcoming { background: #1e3a5f; color: #60a5fa; }
  .outcome-icon.other { background: #374151; color: #9ca3af; }

  .decision-info { flex: 1; min-width: 0; }

  .outcome-label {
    font-weight: 500;
    text-transform: capitalize;
  }
  .outcome-label.passed { color: #4ade80; }
  .outcome-label.failed { color: #f87171; }
  .outcome-label.upcoming { color: #60a5fa; }
  .outcome-label.other { color: #9ca3af; }

  /* === Issue Map Filters === */
  .map-time-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-bottom: 6px;
  }
  .time-chip {
    padding: 2px 10px;
    border-radius: 10px;
    border: 1px solid #374151;
    background: transparent;
    color: #9ca3af;
    font-size: 10px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .time-chip:hover { border-color: #6b7280; }
  .time-chip.active {
    background: #374151;
    color: #f3f4f6;
    border-color: #6b7280;
  }
  .trend-stat {
    margin-left: auto;
    font-size: 10px;
    color: #9ca3af;
  }
  .trend-stat.trend-up { color: #f87171; }
  .trend-stat.trend-down { color: #4ade80; }
  .map-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 8px;
  }
  .filter-chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 12px;
    border: 1px solid #374151;
    background: #1f2937;
    color: #d1d5db;
    font-size: 10px;
    cursor: pointer;
    transition: opacity 0.15s, border-color 0.15s;
  }
  .filter-chip:hover { border-color: #6b7280; }
  .filter-chip.inactive {
    opacity: 0.4;
    border-color: #1f2937;
  }
  .chip-count {
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }

  /* === Footer === */
  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid #374151;
    font-size: 10px;
    color: #4b5563;
  }

  /* === Parent Jurisdiction Sections === */
  .level-badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #9ca3af;
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 3px;
    padding: 1px 5px;
    margin-right: 4px;
    vertical-align: middle;
  }

  /* === Provenance Panel === */
  .provenance-panel {
    background: #262626;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
    border: 1px solid #374151;
  }
  .prov-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .prov-title {
    font-size: 12px;
    font-weight: 600;
    color: #eee;
  }
  .prov-jurisdiction {
    font-size: 10px;
    color: #6b7280;
  }
  .prov-stats {
    display: flex;
    gap: 4px;
    font-size: 11px;
    color: #9ca3af;
    margin-bottom: 8px;
  }
  .prov-corpora {
    border-top: 1px solid #374151;
    padding-top: 6px;
  }
  .corpus-row {
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 11px;
  }
  .corpus-name { color: #d1d5db; }
  .corpus-stats {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .corpus-count { color: #6b7280; font-variant-numeric: tabular-nums; }
  .corpus-indexed {
    font-size: 9px;
    color: #4ade80;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .corpus-coverage {
    font-size: 10px;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }
  .corpus-coverage.low { color: #f59e0b; }
  .prov-footer-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid #374151;
    padding-top: 6px;
    margin-top: 6px;
  }
  .prov-freshness {
    font-size: 10px;
    color: #4b5563;
  }
  .prov-backend {
    font-size: 9px;
    color: #4b5563;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .prov-loading {
    font-size: 11px;
    color: #6b7280;
    padding: 8px 0;
  }

  .icon-btn.active { color: #60a5fa; background: #333; }

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
  .service-badge {
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 1px 5px;
    border-radius: 3px;
  }
  .service-badge.primary {
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.15);
  }

  /* === Past Meeting === */
  .past-meeting {
    opacity: 0.65;
  }
  .past-icon {
    font-size: 12px;
    margin-right: 4px;
  }
  .meeting-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 6px;
  }

  /* === Calendar === */
  .cal-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover:not(:disabled) { color: #60a5fa; background: #374151; }
  .cal-btn:disabled { opacity: 0.3; cursor: default; }

  .cal-dropdown {
    display: flex;
    gap: 8px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #374151;
  }
  .cal-option {
    font-size: 11px;
    color: #3b82f6;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-decoration: none;
  }
  .cal-option:hover { color: #60a5fa; text-decoration: underline; }

  /* === Voice Counts === */
  .voice-counts {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    font-size: 10px;
  }
  .vc {
    padding: 1px 5px;
    border-radius: 3px;
  }
  .vc-support { background: #14532d; color: #4ade80; }
  .vc-oppose { background: #7f1d1d; color: #f87171; }
  .vc-watch { background: #374151; color: #9ca3af; }
  .vc-attested { background: rgba(34, 197, 94, 0.12); color: #22c55e; }

  .voice-inline {
    color: #60a5fa;
    font-size: 10px;
  }

  /* === Decision Expansion === */
  .decision-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
  }
  .expand-chevron {
    display: inline-block;
    flex-shrink: 0;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #4b5563;
    transition: transform 0.15s ease;
    margin-left: 6px;
    margin-top: 6px;
  }
  .expand-chevron.open { transform: rotate(180deg); }



  .decision-detail {
    border-top: 1px solid #374151;
    padding-top: 8px;
    margin-top: 8px;
  }
  .detail-loading {
    font-size: 11px;
    color: #6b7280;
    padding: 4px 0;
  }
  .outcome-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  .outcome-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(107, 114, 128, 0.15);
    color: #9ca3af;
  }
  .outcome-badge.approved {
    background: rgba(34, 197, 94, 0.15);
    color: #4ade80;
  }
  .outcome-badge.denied {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
  }
  .outcome-badge.upcoming {
    background: rgba(96, 165, 250, 0.15);
    color: #60a5fa;
  }
  .outcome-desc {
    font-size: 11px;
    color: #9ca3af;
    font-style: italic;
  }
  .vote-detail {
    font-size: 11px;
    color: #6b7280;
  }
  .decision-summary {
    font-size: 13px;
    color: #d1d5db;
    line-height: 1.5;
    margin-bottom: 10px;
    padding: 8px 10px;
    background: rgba(59, 130, 246, 0.08);
    border-left: 3px solid rgba(59, 130, 246, 0.4);
    border-radius: 0 4px 4px 0;
  }
  .detail-body {
    font-size: 12px;
    color: #9ca3af;
    line-height: 1.45;
    margin-bottom: 8px;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .detail-section {
    margin-bottom: 10px;
    padding-top: 8px;
    border-top: 1px solid #262626;
  }
  .detail-label {
    font-size: 10px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
  }
  .testimony-card {
    font-size: 11px;
    padding: 6px 8px;
    margin-top: 4px;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 4px;
    border-left: 2px solid rgba(96, 165, 250, 0.3);
  }
  .testimony-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 2px;
  }
  .testimony-speaker {
    color: #d1d5db;
    font-weight: 600;
    font-size: 11px;
  }
  .testimony-timestamp {
    font-size: 10px;
    color: #6b7280;
    font-family: 'SF Mono', 'Menlo', monospace;
    background: rgba(255, 255, 255, 0.05);
    padding: 0 4px;
    border-radius: 3px;
  }
  .testimony-text {
    color: #9ca3af;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .testimony-video-link {
    display: inline-block;
    font-size: 10px;
    color: #60a5fa;
    text-decoration: none;
    margin-top: 2px;
  }
  .testimony-video-link:hover { text-decoration: underline; }
  .detail-expand-btn {
    font-size: 10px;
    color: #3b82f6;
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px 0;
    margin-top: 2px;
  }
  .detail-expand-btn:hover { color: #60a5fa; }
  .related-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    padding: 3px 0;
  }
  .outcome-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .outcome-dot.passed { background: #4ade80; }
  .outcome-dot.failed { background: #f87171; }
  .outcome-dot.other { background: #9ca3af; }
  .related-title { color: #d1d5db; flex: 1; }
  .related-date { color: #4b5563; }
  .detail-empty {
    font-size: 11px;
    color: #4b5563;
    font-style: italic;
  }

  /* === Voice Action Buttons === */
  .voice-actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
  }
  .detail-voice {
    border-top: 1px solid #374151;
    padding-top: 8px;
    margin-top: 8px;
  }
  .voice-btn {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #374151;
    background: transparent;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .voice-btn:hover:not(:disabled) {
    border-color: #4b5563;
    color: #eee;
  }
  .voice-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .vb-support.active {
    background: #14532d;
    border-color: #22c55e;
    color: #4ade80;
  }
  .vb-oppose.active {
    background: #7f1d1d;
    border-color: #ef4444;
    color: #f87171;
  }
  .vb-watch.active {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #60a5fa;
  }
  .voice-locked {
    font-size: 10px;
    color: #6b7280;
    font-style: italic;
  }

  /* === Visualization Shared === */
  .viz-loading {
    font-size: 11px;
    color: #6b7280;
    padding: 12px 0;
    text-align: center;
  }
  .viz-stat {
    font-size: 10px;
    color: #4b5563;
    text-align: center;
    margin-top: 4px;
  }
  .legend-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* === Issue Map === */
  .map-container {
    position: relative;
  }
  .map-wrapper {
    height: 220px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid #374151;
    transition: height 0.2s ease;
  }
  .map-expanded .map-wrapper {
    height: 70vh;
  }
  .map-expand-btn {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 26px;
    height: 26px;
    border-radius: 4px;
    border: none;
    background: rgba(31, 41, 55, 0.85);
    color: #d1d5db;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .map-expand-btn:hover {
    background: rgba(55, 65, 81, 0.9);
  }

  /* === Budget Chart === */
  .budget-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
  }
  .budget-total {
    font-size: 18px;
    font-weight: 700;
    color: #eee;
  }
  .budget-year {
    font-size: 11px;
    color: #6b7280;
  }
  .chart-wrapper {
    display: flex;
    justify-content: center;
    padding: 4px 0;
  }
  .chart-wrapper canvas {
    max-width: 200px;
    max-height: 200px;
  }
  .budget-legend {
    margin-top: 8px;
  }
  .budget-legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    padding: 3px 0;
  }
  .budget-cat-name {
    flex: 1;
    color: #d1d5db;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .budget-cat-amount {
    color: #6b7280;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .budget-legend-more {
    font-size: 10px;
    color: #4b5563;
    margin-top: 4px;
  }

  /* === Detail Label Row (with action button) === */
  .detail-label-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
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


  /* === AI Draft Toolbar === */
  .draft-toolbar {
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
  }
  .enrich-btn {
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    background: rgba(34, 197, 94, 0.08);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.2);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .enrich-btn:hover:not(:disabled) {
    background: rgba(34, 197, 94, 0.15);
    border-color: #4ade80;
  }
  .enrich-btn:disabled { opacity: 0.5; cursor: default; }
  .ai-provider-tag {
    font-size: 10px;
    color: #64748b;
    align-self: center;
    white-space: nowrap;
  }
</style>

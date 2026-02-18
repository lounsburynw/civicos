<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import { api, registry } from '../lib/client.js';
  import type { CityPulseData, DecisionDetailData, DataProvenance, VoiceCounts, Initiative, CivicAction, CivicActionProgress, IssuePoint, BudgetCategory, Comment, CommentCounts, CommentSynthesis, RegistryServer } from '@civicos/client';
  import { isAIAvailable, getAIManager, onAIConfigChanged, composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from '../lib/ai.js';
  import type { IdentityInfo, NostrEvent, SignedNostrEvent } from '../lib/providers/types.js';
  import { CivicEventKinds, createVoiceContent, createVoiceTags, createCommitmentContent, createCommitmentTags, createCompletionContent, createCompletionTags, generateCommitmentId, generateCompletionId, generateActionRef } from '../lib/providers/types.js';
  import 'leaflet/dist/leaflet.css';
  import L from 'leaflet';
  import { Chart, DoughnutController, ArcElement, Tooltip, Legend } from 'chart.js';
  import { marked } from 'marked';
  import DOMPurify from 'dompurify';

  Chart.register(DoughnutController, ArcElement, Tooltip, Legend);

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
    initiatives: true,
    commitments: true,
    issueMap: false,
    budget: false,
  });

  // Decision detail expansion
  let expandedDecisions = $state(new Set<string>());
  let decisionDetails = $state(new Map<string, DecisionDetailData>());
  let decisionLoading = $state(new Set<string>());
  let expandedTestimony = $state(new Set<string>());
  let expandedCouncil = $state(new Set<string>());

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

  // Comment thread state
  let commentCounts = $state(new Map<string, CommentCounts>());
  let openThreads = $state(new Set<string>());
  let threadComments = $state(new Map<string, Comment[]>());
  let threadDrafts = $state(new Map<string, string>());
  let threadSubmitting = $state(new Set<string>());
  let threadLoading = $state(new Set<string>());
  let threadErrors = $state(new Map<string, string>());
  let synthData = $state(new Map<string, CommentSynthesis>());

  // AI drafting state
  let aiAvailable = $state(false);
  let activeProviderName = $state('');
  let draftingInProgress = $state(new Set<string>());
  let enrichingInProgress = $state(new Set<string>());

  // Ask AI inline response state
  let aiResponses = $state(new Map<string, string>());
  let aiResponseLoading = $state(new Set<string>());

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

  // Initiatives state
  let initiatives: Initiative[] = $state([]);
  let initiativesLoading = $state(false);
  let expandedInitiatives = $state(new Set<string>());
  let initiativeActions = $state(new Map<string, CivicAction[]>());
  let actionProgress = $state(new Map<string, CivicActionProgress>());
  let actionsLoading = $state(new Set<string>());

  // AI action drafts (create form)
  let formDraftLoading = $state(false);

  // Commitment tracking (persisted)
  let committedActions = $state(new Set<string>());
  let completedActions = $state(new Set<string>());
  let actionInProgress = $state(new Set<string>());
  // Store action metadata for My Commitments (renders without expanding initiative)
  let committedActionMeta = $state(new Map<string, { action_type: string; description: string; deadline?: string }>());
  const COMMITMENTS_STORAGE_KEY = 'civicos_user_commitments';
  const COMPLETIONS_STORAGE_KEY = 'civicos_user_completions';
  const COMMITMENT_META_STORAGE_KEY = 'civicos_commitment_meta';

  // Connector setup state
  let connectorSetupDismissed = $state(false);
  let connectorSetupLoaded = $state(false);
  const CONNECTOR_SETUP_KEY = 'civicos_connector_setup_dismissed';

  // Inline unlock
  let unlockPassword = $state('');
  let unlocking = $state(false);
  let unlockError: string | null = $state(null);

  // Create initiative form
  let showCreateInitiative = $state(false);
  let newInitiative = $state({ topic: '', title: '', description: '', coordination_url: '' });
  let creatingInitiative = $state(false);
  let customTopic = $state('');
  const INITIATIVE_TOPICS = ['Traffic Safety', 'Housing', 'Parks', 'Budget', 'Environment', 'Public Safety', 'Infrastructure', 'Education'];

  function selectTopic(t: string) {
    if (newInitiative.topic === t) {
      newInitiative.topic = '';
    } else {
      newInitiative.topic = t;
      customTopic = '';
    }
  }
  function selectCustomTopic() {
    newInitiative.topic = '__custom__';
  }
  function effectiveTopic(): string {
    return newInitiative.topic === '__custom__' ? customTopic.trim().toLowerCase() : newInitiative.topic.toLowerCase();
  }

  // Create action form (per initiative)
  let showCreateAction: string | null = $state(null); // initiative ID
  let newAction = $state({ action_type: 'written_comment', description: '', target: '', deadline: '', template: '', deadlineContext: '', targetCount: null as number | null });
  let creatingAction = $state(false);

  // Dynamic config per action type — matches Open WebUI's CreateActionModal
  const ACTION_TYPE_CONFIG: Record<string, {
    descPlaceholder: string;
    targetLabel: string;
    targetPlaceholder: string;
    showTemplate: boolean;
    templateLabel: string;
    templatePlaceholder: string;
    deadlineLabel: string;
    deadlineContextPlaceholder: string;
  }> = {
    written_comment: {
      descPlaceholder: 'e.g., Submit a written comment opposing the median removal',
      targetLabel: 'Submission link',
      targetPlaceholder: 'https://city.gov/comment-form',
      showTemplate: true,
      templateLabel: 'Draft text',
      templatePlaceholder: 'Dear Planning Commission, I urge you to...',
      deadlineLabel: 'Deadline',
      deadlineContextPlaceholder: 'e.g., Comment period closes March 1',
    },
    attend_meeting: {
      descPlaceholder: 'e.g., Show up to the City Council meeting to oppose the redesign',
      targetLabel: 'Meeting location or link',
      targetPlaceholder: 'City Hall, Council Chambers',
      showTemplate: true,
      templateLabel: 'Logistics',
      templatePlaceholder: 'Meeting at 7pm. Public comment is item 6 (~8pm). Free parking on 5th Ave after 6pm.',
      deadlineLabel: 'Meeting date',
      deadlineContextPlaceholder: 'e.g., Council votes at this meeting',
    },
    public_comment: {
      descPlaceholder: 'e.g., Speak during public comment about pedestrian safety',
      targetLabel: 'Meeting link',
      targetPlaceholder: 'https://cityofsanrafael.org/city-council-meeting',
      showTemplate: true,
      templateLabel: 'Talking points',
      templatePlaceholder: 'Key points: 1) Safety audit flagged this, 2) Schools nearby, 3) Request traffic calming',
      deadlineLabel: 'Meeting date',
      deadlineContextPlaceholder: 'e.g., Public comment heard before the vote',
    },
    contact_official: {
      descPlaceholder: 'e.g., Email Councilmember about the median removal',
      targetLabel: 'Email or phone',
      targetPlaceholder: 'council@cityofsanrafael.org',
      showTemplate: true,
      templateLabel: 'Draft message',
      templatePlaceholder: 'Dear Councilmember, I am writing to express my concern about...',
      deadlineLabel: 'Deadline',
      deadlineContextPlaceholder: 'e.g., Council votes March 3 — contact them before then',
    },
    signature: {
      descPlaceholder: 'e.g., Sign the petition to preserve pedestrian islands',
      targetLabel: 'Petition link',
      targetPlaceholder: 'https://change.org/...',
      showTemplate: false,
      templateLabel: '',
      templatePlaceholder: '',
      deadlineLabel: 'Deadline',
      deadlineContextPlaceholder: 'e.g., Petition submitted to Council on March 1',
    },
    share: {
      descPlaceholder: 'e.g., Share the community letter on Nextdoor',
      targetLabel: 'Link to share',
      targetPlaceholder: 'https://...',
      showTemplate: true,
      templateLabel: 'Suggested post',
      templatePlaceholder: 'The City wants to remove safety islands. Here\'s what you can do...',
      deadlineLabel: 'Deadline',
      deadlineContextPlaceholder: 'e.g., Share before the Council meeting for maximum impact',
    },
    custom: {
      descPlaceholder: 'Describe what people should do',
      targetLabel: 'Link',
      targetPlaceholder: 'https://...',
      showTemplate: true,
      templateLabel: 'Instructions',
      templatePlaceholder: 'Step-by-step instructions for this action...',
      deadlineLabel: 'Deadline',
      deadlineContextPlaceholder: 'Why does this need to happen by this date?',
    },
  };
  const DEFAULT_ACTION_CONFIG = ACTION_TYPE_CONFIG.custom;

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
      // Force-refresh registry to pick up new servers/relay fields
      try {
        availableServers = await registry.getRegistryServers(true);
      } catch { /* keep existing servers */ }
      pulseData = await api.getCityPulse();
      // Auto-configure relay URL from server response
      if (pulseData.relay_url) {
        registry.setRelayUrl(pulseData.relay_url);
      }
      // Load voice counts, comment counts, and initiatives in background
      loadVoiceCounts();
      loadCommentCounts();
      loadInitiatives();
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
    const ids: string[] = [];
    if (pulseData.recent_outcomes) {
      ids.push(...pulseData.recent_outcomes.map(d => d.id).filter(Boolean));
    }
    if (pulseData.upcoming_items) {
      ids.push(...pulseData.upcoming_items.filter(i => i.stance_eligible).map(i => `agenda-item:${i.id}`));
    }
    if (ids.length > 0) {
      voiceCounts = await api.getVoiceCountsBatch(ids, pulseData.jurisdiction || activeJurisdiction);
    }
  }

  async function loadCommentCounts() {
    if (!pulseData) return;
    const ids: string[] = [];
    if (pulseData.upcoming_items) {
      ids.push(...pulseData.upcoming_items.filter(i => i.comment_eligible).map(i => `agenda-item:${i.id}`));
    }
    if (ids.length > 0) {
      commentCounts = await api.getCommentCountsBatch(ids, pulseData.jurisdiction || activeJurisdiction);
      // Pre-fetch synthesis for items with comments (enriches AI context)
      for (const [entityId, cc] of commentCounts) {
        if (cc.count > 0) {
          api.getCommentSynthesis(entityId).then(synth => {
            if (synth) {
              synthData.set(entityId, synth);
              synthData = new Map(synthData);
            }
          });
        }
      }
    }
  }

  function getUserComment(entityId: string): Comment | undefined {
    if (!identity?.publicKey) return undefined;
    return (threadComments.get(entityId) || []).find(c => c.public_key === identity!.publicKey);
  }

  async function toggleCommentThread(entityId: string) {
    if (openThreads.has(entityId)) {
      openThreads.delete(entityId);
      openThreads = new Set(openThreads);
      return;
    }
    openThreads.add(entityId);
    openThreads = new Set(openThreads);

    // Fetch comments and synthesis if not already loaded
    if (!threadComments.has(entityId)) {
      threadLoading.add(entityId);
      threadLoading = new Set(threadLoading);
      try {
        const [comments, synth] = await Promise.all([
          api.getComments(entityId),
          api.getCommentSynthesis(entityId),
        ]);
        threadComments.set(entityId, comments);
        threadComments = new Map(threadComments);
        if (synth) {
          synthData.set(entityId, synth);
          synthData = new Map(synthData);
        }
        // Pre-fill draft with user's existing comment for editing
        if (identity?.publicKey) {
          const mine = comments.find(c => c.public_key === identity!.publicKey);
          if (mine && !threadDrafts.has(entityId)) {
            threadDrafts.set(entityId, mine.comment_text);
            threadDrafts = new Map(threadDrafts);
          }
        }
      } catch {
        threadErrors.set(entityId, 'Failed to load comments');
        threadErrors = new Map(threadErrors);
      }
      threadLoading.delete(entityId);
      threadLoading = new Set(threadLoading);
    }
  }

  async function handleSubmitComment(entityId: string) {
    const draft = (threadDrafts.get(entityId) || '').trim();
    if (!draft || !identity?.isUnlocked) return;

    threadSubmitting.add(entityId);
    threadSubmitting = new Set(threadSubmitting);
    threadErrors.delete(entityId);
    threadErrors = new Map(threadErrors);

    try {
      const createdAt = Math.floor(Date.now() / 1000);
      // Determine stance from user's current voice on this entity
      const userStance = userStances.get(entityId);

      // Build tags to match server's verify_comment(): d (entity), j (jurisdiction), optionally stance
      const tags: string[][] = [['d', entityId], ['j', activeJurisdiction]];
      if (userStance) tags.push(['stance', userStance]);

      // Content is the actual comment text — server verifies signature over this
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: 30803,
        tags,
        content: draft,
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        threadErrors.set(entityId, 'Signing failed');
        threadErrors = new Map(threadErrors);
        threadSubmitting.delete(entityId);
        threadSubmitting = new Set(threadSubmitting);
        return;
      }

      const ok = await api.submitComment(
        entityId,
        draft,
        signResult.data.pubkey,
        signResult.data.sig,
        createdAt,
        activeJurisdiction,
        userStance
      );

      if (ok) {
        // Optimistic update: replace existing or prepend new
        const newComment: Comment = {
          entity: entityId,
          comment_text: draft,
          public_key: signResult.data.pubkey,
          signature: signResult.data.sig,
          timestamp: new Date().toISOString(),
          jurisdiction: activeJurisdiction,
          stance: userStance,
          deleted: false,
        };
        const existing = threadComments.get(entityId) || [];
        const existingIdx = existing.findIndex(c => c.public_key === signResult.data.pubkey);
        if (existingIdx >= 0) {
          // Update in place (server upserts — 1 comment per user per entity)
          existing[existingIdx] = newComment;
          threadComments.set(entityId, [...existing]);
        } else {
          threadComments.set(entityId, [newComment, ...existing]);
          // Only increment count for genuinely new comments
          const prev = commentCounts.get(entityId) || { entity: entityId, count: 0 };
          commentCounts.set(entityId, { ...prev, count: prev.count + 1 });
          commentCounts = new Map(commentCounts);
        }
        threadComments = new Map(threadComments);

        // Clear draft
        threadDrafts.delete(entityId);
        threadDrafts = new Map(threadDrafts);
      } else {
        threadErrors.set(entityId, 'Failed to submit comment');
        threadErrors = new Map(threadErrors);
      }
    } catch {
      threadErrors.set(entityId, 'Error submitting comment');
      threadErrors = new Map(threadErrors);
    }

    threadSubmitting.delete(entityId);
    threadSubmitting = new Set(threadSubmitting);
  }

  async function toggleDecisionDetail(title: string) {
    if (expandedDecisions.has(title)) {
      expandedDecisions.delete(title);
      expandedDecisions = new Set(expandedDecisions);
      return;
    }

    expandedDecisions.add(title);
    expandedDecisions = new Set(expandedDecisions);

    if (!decisionDetails.has(title)) {
      decisionLoading.add(title);
      decisionLoading = new Set(decisionLoading);
      try {
        const detail = await api.getDecisionDetail(title);
        decisionDetails.set(title, detail);
        decisionDetails = new Map(decisionDetails);
      } catch (e) {
        console.error('Failed to load decision detail:', e);
      } finally {
        decisionLoading.delete(title);
        decisionLoading = new Set(decisionLoading);
      }
    }
  }

  async function toggleProvenance() {
    showProvenance = !showProvenance;
    if (showProvenance && !provenanceData && !provenanceLoading) {
      provenanceLoading = true;
      try {
        provenanceData = await api.getDataProvenance();
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

  // Calendar helpers for committed actions with deadlines
  function actionGoogleCalendarUrl(meta: { action_type: string; description: string; deadline?: string }): string {
    if (!meta.deadline) return '#';
    const start = new Date(meta.deadline);
    const end = new Date(start.getTime() + 1 * 60 * 60 * 1000);
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const label = actionTypeLabel(meta.action_type);
    return `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(`${label}: ${meta.description}`)}&dates=${fmt(start)}/${fmt(end)}`;
  }

  function downloadActionIcs(meta: { action_type: string; description: string; deadline?: string }) {
    if (!meta.deadline) return;
    const start = new Date(meta.deadline);
    const end = new Date(start.getTime() + 1 * 60 * 60 * 1000);
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const label = actionTypeLabel(meta.action_type);
    const summary = `${label}: ${meta.description}`.slice(0, 100);
    const ics = `BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//CivicOS//Action Calendar//EN\nBEGIN:VEVENT\nDTSTAMP:${fmt(new Date())}\nDTSTART:${fmt(start)}\nDTEND:${fmt(end)}\nSUMMARY:${summary}\nDESCRIPTION:${meta.description}\nEND:VEVENT\nEND:VCALENDAR`;
    const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `civicos-action-${meta.action_type}.ics`;
    a.click();
    URL.revokeObjectURL(url);
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

  // === Ask AI (context injection) ===

  function composeSentimentBlock(entityId: string): string[] {
    const lines: string[] = [];
    const counts = voiceCounts.get(entityId);
    const synth = synthData.get(entityId);
    const comments = threadComments.get(entityId);

    if (counts && counts.total > 0) {
      lines.push('', '--- Community Sentiment ---');
      lines.push(`Stances: ${counts.support} support, ${counts.oppose} oppose, ${counts.watching} watching`);
      if (counts.attested != null && counts.attested > 0) {
        lines.push(`Verified: ${counts.attested} attested (in-person verified), ${counts.unattested ?? 0} unattested`);
      }
    }
    if (synth && synth.total > 0) {
      lines.push(`Public comments: ${synth.total} total (${synth.support} supportive, ${synth.oppose} opposed, ${synth.neutral} neutral)`);
    }
    if (comments && comments.length > 0) {
      const visible = comments.filter(c => !c.deleted);
      if (visible.length > 0) {
        lines.push('', 'Resident comments:');
        for (const c of visible.slice(0, 8)) {
          const stanceTag = c.stance ? ` [${c.stance}]` : '';
          lines.push(`- "${c.comment_text}"${stanceTag}`);
        }
        if (visible.length > 8) lines.push(`... and ${visible.length - 8} more comments`);
      }
    }
    return lines;
  }

  function composeAgendaContext(item: import('../lib/types.js').PulseAgendaItem): string {
    const lines = [
      `I'd like to understand this civic agenda item from ${pulseData?.jurisdiction || 'my city'}:`,
      '',
      `**${item.title}**`,
      `Meeting: ${item.meeting_title} (${item.meeting_date})`,
    ];
    if (item.item_number) lines.push(`Item #${item.item_number}`);
    if (item.project_type) lines.push(`Type: ${item.project_type}`);
    if (item.description) lines.push('', item.description);
    if (item.why_it_matters) lines.push('', `Why it matters: ${item.why_it_matters}`);
    lines.push(...composeSentimentBlock(`agenda-item:${item.id}`));
    lines.push('', 'What are the key implications for residents? If community sentiment data is available, summarize what residents are saying and the key themes. What questions should I ask at the public hearing?');
    return lines.join('\n');
  }

  function getMailtoLink(item: import('../lib/types.js').PulseAgendaItem): string {
    if (!pulseData?.clerk_email) return '';
    const subject = `Public Comment - Item ${item.item_number}: ${item.title} - ${item.meeting_title} ${item.meeting_date}`;
    const body = `[Paste your drafted comment here]\n\nRegarding: ${item.title}\nMeeting: ${item.meeting_title}, ${item.meeting_date}\nItem: ${item.item_number}`;
    return `mailto:${encodeURIComponent(pulseData.clerk_email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  function composeDecisionContext(decision: import('../lib/types.js').PulseOutcome): string {
    const detail = decisionDetails.get(decision.title);
    const lines = [
      `I'd like to understand this civic decision from ${pulseData?.jurisdiction || 'my city'}:`,
      '',
      `**${decision.title}**`,
      `Outcome: ${decision.outcome}`,
      `Date: ${decision.date}`,
    ];
    if (decision.vote_tally) lines.push(`Vote: ${decision.vote_tally}`);
    if (detail?.decision?.body) lines.push('', detail.decision.body);
    if (detail?.testimony?.public_comments && detail.testimony.public_comments.length > 0) {
      lines.push('', `--- Public Testimony (${detail.testimony.public_comments.length} speakers) ---`);
      for (const c of detail.testimony.public_comments.slice(0, 8)) {
        lines.push(`- **${c.speaker}:** ${c.text}`);
      }
      if (detail.testimony.public_comments.length > 8) {
        lines.push(`... and ${detail.testimony.public_comments.length - 8} more speakers`);
      }
    }
    if (detail?.testimony?.council_discussion && detail.testimony.council_discussion.length > 0) {
      lines.push('', `--- Council Discussion (${detail.testimony.council_discussion.length} excerpts) ---`);
      for (const c of detail.testimony.council_discussion.slice(0, 6)) {
        lines.push(`- **${c.speaker}:** ${c.text}`);
      }
      if (detail.testimony.council_discussion.length > 6) {
        lines.push(`... and ${detail.testimony.council_discussion.length - 6} more excerpts`);
      }
    }
    lines.push(...composeSentimentBlock(decision.id));
    lines.push('', 'What are the implications of this decision for residents? If testimony or community sentiment data is available, summarize the key themes and concerns raised. What should I know about this issue going forward?');
    return lines.join('\n');
  }

  function composeTestimonySummary(decision: import('../lib/types.js').PulseOutcome, comments: import('../lib/types.js').TestimonyComment[]): string {
    const lines = [
      `Summarize the public testimony from this civic decision in ${pulseData?.jurisdiction || 'my city'}:`,
      '',
      `**${decision.title}**`,
      `Outcome: ${decision.outcome} (${decision.date})`,
      '',
      `${comments.length} speakers testified:`,
      '',
    ];
    for (const c of comments) {
      lines.push(`**${c.speaker}:** ${c.text}`);
      lines.push('');
    }
    lines.push('Please provide:');
    lines.push('1. A concise summary of the key themes and concerns raised');
    lines.push('2. Points of agreement and disagreement among speakers');
    lines.push('3. Any action items or follow-ups mentioned');
    return lines.join('\n');
  }

  function composeThreadSummary(item: import('../lib/types.js').PulseAgendaItem, entityId: string): string {
    const comments = threadComments.get(entityId) || [];
    const lines = [
      `Summarize the public comment thread for **${item.meeting_title}** (${item.meeting_date}), Agenda Item ${item.item_number}: ${item.title}.`,
      '',
    ];
    const vc = voiceCounts.get(entityId);
    if (vc) {
      const total = (vc.support || 0) + (vc.oppose || 0) + (vc.watching || 0);
      let sentimentLine = `**Community sentiment:** ${total} voices — ${vc.support || 0} support, ${vc.oppose || 0} oppose, ${vc.watching || 0} watching`;
      if (vc.attested != null && vc.attested > 0) {
        sentimentLine += ` (${vc.attested} attested)`;
      }
      lines.push(sentimentLine, '');
    }
    lines.push(`**${comments.length} public comment${comments.length !== 1 ? 's' : ''}:**`);
    for (const c of comments) {
      const stance = c.stance ? ` [${c.stance}]` : '';
      lines.push(`- "${c.comment_text}"${stance}`);
    }
    lines.push('', 'Analyze these comments:', '1. What are the 2-3 key themes or concerns raised?', '2. Are there notable points of agreement or disagreement?', '3. What are the strongest arguments on each side?', '', 'Be concise. Use bullet points.');
    return lines.join('\n');
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

  async function askAI(key: string, context: string) {
    // Toggle off if already showing a response for this key
    if (aiResponses.has(key)) {
      aiResponses.delete(key);
      aiResponses = new Map(aiResponses);
      return;
    }

    if (!aiAvailable) {
      return;
    }

    aiResponseLoading.add(key);
    aiResponseLoading = new Set(aiResponseLoading);

    try {
      const result = await getAIManager().complete(context, QA_SYSTEM_PROMPT);
      if (result.success && result.text) {
        aiResponses.set(key, result.text);
        aiResponses = new Map(aiResponses);
      } else {
        showToast(`AI failed: ${result.error}`);
      }
    } catch (err) {
      showToast(`AI request failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    }

    aiResponseLoading.delete(key);
    aiResponseLoading = new Set(aiResponseLoading);
  }

  // === AI Drafting ===

  async function handleDraftWithAI(entityId: string, item: import('../lib/types.js').PulseAgendaItem) {
    draftingInProgress.add(entityId);
    draftingInProgress = new Set(draftingInProgress);

    try {
      const stance = userStances.get(entityId);
      const counts = voiceCounts.get(entityId);
      const promptText = composeDraftPrompt(item, stance, counts);

      const aiResult = await getAIManager().complete(promptText, SYSTEM_PROMPT);
      if (!aiResult.success) {
        showToast(`AI drafting failed: ${aiResult.error}`);
        draftingInProgress.delete(entityId);
        draftingInProgress = new Set(draftingInProgress);
        return;
      }

      threadDrafts.set(entityId, aiResult.text!);
      threadDrafts = new Map(threadDrafts);

      // Open the thread if not already open
      if (!openThreads.has(entityId)) {
        openThreads.add(entityId);
        openThreads = new Set(openThreads);
        // Load comments if not already loaded
        if (!threadComments.has(entityId)) {
          threadLoading.add(entityId);
          threadLoading = new Set(threadLoading);
          try {
            const [comments, synth] = await Promise.all([
              api.getComments(entityId),
              api.getCommentSynthesis(entityId),
            ]);
            threadComments.set(entityId, comments);
            threadComments = new Map(threadComments);
            if (synth) {
              synthData.set(entityId, synth);
              synthData = new Map(synthData);
            }
          } catch {
            // Non-critical — draft is already in textarea
          }
          threadLoading.delete(entityId);
          threadLoading = new Set(threadLoading);
        }
      }
    } catch {
      showToast('AI drafting failed — try again');
    }

    draftingInProgress.delete(entityId);
    draftingInProgress = new Set(draftingInProgress);
  }

  async function handleEnrichDraft(entityId: string, item: import('../lib/types.js').PulseAgendaItem) {
    const draft = (threadDrafts.get(entityId) || '').trim();
    if (!draft) return;

    enrichingInProgress.add(entityId);
    enrichingInProgress = new Set(enrichingInProgress);

    try {
      const context = await api.getItemContext(item.id, ['history', 'regulatory', 'testimony']);
      const enrichPrompt = composeEnrichPrompt(draft, context);

      const aiResult = await getAIManager().complete(enrichPrompt, SYSTEM_PROMPT);
      if (!aiResult.success) {
        showToast(`Enrichment failed: ${aiResult.error}`);
        enrichingInProgress.delete(entityId);
        enrichingInProgress = new Set(enrichingInProgress);
        return;
      }

      threadDrafts.set(entityId, aiResult.text!);
      threadDrafts = new Map(threadDrafts);
    } catch {
      showToast('Enrichment failed — server may be unavailable');
    }

    enrichingInProgress.delete(entityId);
    enrichingInProgress = new Set(enrichingInProgress);
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

  // === Initiative loading ===

  async function loadInitiatives() {
    initiativesLoading = true;
    try {
      const jurisdiction = pulseData?.jurisdiction || activeJurisdiction;
      initiatives = await api.getInitiatives(jurisdiction);
      // Load all actions + progress upfront for card-level stats
      loadAllActionStats();
    } catch {
      initiatives = [];
    }
    initiativesLoading = false;
  }

  async function loadAllActionStats() {
    await Promise.all(initiatives.map(async (ini) => {
      if (initiativeActions.has(ini.id)) return;
      try {
        const actions = await api.getCivicActions(ini.id);
        initiativeActions.set(ini.id, actions);
        await Promise.all(actions.map(async (action) => {
          const progress = await api.getCivicActionProgress(action.id);
          if (progress) actionProgress.set(action.id, progress);
        }));
        actionProgress = new Map(actionProgress);
      } catch {
        initiativeActions.set(ini.id, []);
      }
    }));
    initiativeActions = new Map(initiativeActions);
  }

  async function toggleInitiativeDetail(initiativeId: string) {
    if (expandedInitiatives.has(initiativeId)) {
      expandedInitiatives.delete(initiativeId);
      expandedInitiatives = new Set(expandedInitiatives);
      return;
    }

    expandedInitiatives.add(initiativeId);
    expandedInitiatives = new Set(expandedInitiatives);

    if (!initiativeActions.has(initiativeId)) {
      actionsLoading.add(initiativeId);
      actionsLoading = new Set(actionsLoading);
      try {
        const actions = await api.getCivicActions(initiativeId);
        initiativeActions.set(initiativeId, actions);
        initiativeActions = new Map(initiativeActions);

        // Load progress for each action
        const progressPromises = actions.map(async (action) => {
          const progress = await api.getCivicActionProgress(action.id);
          if (progress) {
            actionProgress.set(action.id, progress);
          }
        });
        await Promise.all(progressPromises);
        actionProgress = new Map(actionProgress);
      } catch {
        initiativeActions.set(initiativeId, []);
        initiativeActions = new Map(initiativeActions);
      } finally {
        actionsLoading.delete(initiativeId);
        actionsLoading = new Set(actionsLoading);
      }
    }
  }

  // === Commitment stats ===

  function initiativeStats(initiativeId: string): { committed: number; completed: number } {
    const actions = initiativeActions.get(initiativeId);
    if (!actions) return { committed: 0, completed: 0 };
    let committed = 0, completed = 0;
    for (const a of actions) {
      const p = actionProgress.get(a.id);
      if (p) {
        committed += p.commitment_count;
        completed += p.completion_count;
      }
    }
    return { committed, completed };
  }

  function aggregateStats(): { committed: number; completed: number } {
    let committed = 0, completed = 0;
    for (const p of actionProgress.values()) {
      committed += p.commitment_count;
      completed += p.completion_count;
    }
    return { committed, completed };
  }

  // === Commitment persistence ===

  async function loadCommitments() {
    try {
      const result = await chrome.storage.local.get([COMMITMENTS_STORAGE_KEY, COMPLETIONS_STORAGE_KEY, COMMITMENT_META_STORAGE_KEY]);
      if (result[COMMITMENTS_STORAGE_KEY]) {
        committedActions = new Set(result[COMMITMENTS_STORAGE_KEY] as string[]);
      }
      if (result[COMPLETIONS_STORAGE_KEY]) {
        completedActions = new Set(result[COMPLETIONS_STORAGE_KEY] as string[]);
      }
      if (result[COMMITMENT_META_STORAGE_KEY]) {
        committedActionMeta = new Map(Object.entries(result[COMMITMENT_META_STORAGE_KEY]) as [string, { action_type: string; description: string; deadline?: string }][]);
      }
    } catch {
      // Ignore load errors
    }
  }

  async function persistCommitments() {
    try {
      const metaObj: Record<string, { action_type: string; description: string; deadline?: string }> = {};
      committedActionMeta.forEach((v, k) => { metaObj[k] = v; });
      await chrome.storage.local.set({
        [COMMITMENTS_STORAGE_KEY]: [...committedActions],
        [COMPLETIONS_STORAGE_KEY]: [...completedActions],
        [COMMITMENT_META_STORAGE_KEY]: metaObj,
      });
    } catch {
      // Ignore persist errors
    }
  }

  // === Action handlers ===

  async function handleCommit(action: CivicAction) {
    if (actionInProgress.has(action.id)) return;
    if (!identity?.isUnlocked) return;

    actionInProgress.add(action.id);
    actionInProgress = new Set(actionInProgress);

    try {
      const jurisdiction = pulseData?.jurisdiction || activeJurisdiction;
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_COMMITMENT,
        tags: createCommitmentTags(action.id, jurisdiction),
        content: createCommitmentContent(action.id, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        showToast(`Signing failed: ${(signResult as { error?: string }).error || 'unknown error'}`);
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      const ok = await api.commitToCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt, jurisdiction);
      if (!ok) {
        showToast('Failed to commit. Relay may be unreachable.');
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      // Optimistic update
      committedActions.add(action.id);
      committedActions = new Set(committedActions);
      committedActionMeta.set(action.id, { action_type: action.action_type, description: action.description, deadline: action.deadline });
      committedActionMeta = new Map(committedActionMeta);
      persistCommitments();

      // Update progress
      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, commitment_count: prev.commitment_count + 1 });
        actionProgress = new Map(actionProgress);
      }
      showToast('Committed!');
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }

    actionInProgress.delete(action.id);
    actionInProgress = new Set(actionInProgress);
  }

  async function handleComplete(action: CivicAction) {
    if (actionInProgress.has(action.id)) return;
    if (!identity?.isUnlocked) return;

    actionInProgress.add(action.id);
    actionInProgress = new Set(actionInProgress);

    try {
      const jurisdiction = pulseData?.jurisdiction || activeJurisdiction;
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_COMPLETION,
        tags: createCompletionTags(action.id, jurisdiction),
        content: createCompletionContent(action.id, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        showToast(`Signing failed: ${(signResult as { error?: string }).error || 'unknown error'}`);
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      const ok = await api.completeCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt, jurisdiction);
      if (!ok) {
        showToast('Failed to mark action complete. Relay may be unreachable.');
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      completedActions.add(action.id);
      completedActions = new Set(completedActions);
      persistCommitments();

      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, completion_count: prev.completion_count + 1 });
        actionProgress = new Map(actionProgress);
      }
      showToast('Marked complete!');
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }

    actionInProgress.delete(action.id);
    actionInProgress = new Set(actionInProgress);
  }

  async function handleWithdraw(action: CivicAction) {
    if (actionInProgress.has(action.id)) return;
    if (!identity?.isUnlocked) return;

    actionInProgress.add(action.id);
    actionInProgress = new Set(actionInProgress);

    try {
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_COMMITMENT,
        tags: [['d', action.id], ['action', 'withdraw']],
        content: `civicos:withdraw:v1:${action.id}:${createdAt}`,
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        showToast(`Signing failed: ${(signResult as { error?: string }).error || 'unknown error'}`);
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      const ok = await api.withdrawCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt);
      if (!ok) {
        showToast('Failed to withdraw. Relay may be unreachable.');
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      committedActions.delete(action.id);
      committedActions = new Set(committedActions);
      committedActionMeta.delete(action.id);
      committedActionMeta = new Map(committedActionMeta);
      persistCommitments();

      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, commitment_count: Math.max(0, prev.commitment_count - 1) });
        actionProgress = new Map(actionProgress);
      }
      showToast('Withdrawn');
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }

    actionInProgress.delete(action.id);
    actionInProgress = new Set(actionInProgress);
  }

  // === AI Draft Generation ===

  const DRAFTABLE_TYPES = new Set(['written_comment', 'public_comment', 'contact_official']);

  async function handleFormDraft(initiative: Initiative) {
    if (formDraftLoading) return;
    formDraftLoading = true;
    try {
      const description = newAction.description.trim()
        || `${initiative.title}: ${initiative.description}`;
      const result = await api.generateActionDraft(
        newAction.action_type,
        initiative.topic,
        description,
        newAction.target || undefined,
        newAction.template || undefined,
      );
      if (result) {
        newAction.template = result.draft;
        if (result.description && !newAction.description.trim()) {
          newAction.description = result.description;
        }
      } else {
        showToast('Failed to generate draft');
      }
    } catch {
      showToast('Draft generation error');
    }
    formDraftLoading = false;
  }

  // === Deadline helpers ===

  function deadlineDaysLeft(deadline: string): number {
    const d = new Date(deadline);
    const now = new Date();
    return Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  }

  function deadlineLabel(deadline: string): string {
    const days = deadlineDaysLeft(deadline);
    if (days < 0) return 'overdue';
    if (days === 0) return 'due today';
    if (days === 1) return 'due tomorrow';
    return `${days}d left`;
  }

  function deadlineClass(deadline: string): string {
    const days = deadlineDaysLeft(deadline);
    if (days < 0) return 'overdue';
    if (days <= 3) return 'urgent';
    return 'normal';
  }

  function actionTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      written_comment: 'Write Comment',
      attend_meeting: 'Attend Meeting',
      public_comment: 'Public Comment',
      contact_official: 'Contact Official',
      signature: 'Sign Petition',
      share: 'Share',
      custom: 'Action',
    };
    return labels[type] || type;
  }

  async function handleCreateInitiative() {
    if (creatingInitiative || !identity?.isUnlocked) return;
    const topic = effectiveTopic();
    if (!topic || !newInitiative.title.trim() || !newInitiative.description.trim()) return;

    creatingInitiative = true;
    try {
      const jurisdiction = pulseData?.jurisdiction || activeJurisdiction;
      const createdAt = Math.floor(Date.now() / 1000);
      const content = `civicos:initiative:v1:${jurisdiction}:${topic}:${createdAt}`;
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: 30800,
        tags: [['d', `initiative:${jurisdiction}:${topic}`], ['j', jurisdiction]],
        content,
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        showToast(`Signing failed: ${(signResult as { error?: string }).error || 'unknown error'}`);
        creatingInitiative = false;
        return;
      }

      const created = await api.createInitiative(
        jurisdiction,
        topic,
        newInitiative.title.trim(),
        newInitiative.description.trim(),
        signResult.data.pubkey,
        signResult.data.sig,
        createdAt,
        undefined,
        newInitiative.coordination_url.trim() || undefined
      );
      if (created) {
        initiatives = [created, ...initiatives];
        showCreateInitiative = false;
        newInitiative = { topic: '', title: '', description: '', coordination_url: '' };
        customTopic = '';
        showToast('Initiative created!');
      } else {
        showToast('Failed to create initiative. Relay may be unreachable.');
      }
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }
    creatingInitiative = false;
  }

  async function handleCreateAction(initiativeId: string) {
    if (creatingAction || !identity?.isUnlocked) return;
    if (!newAction.description.trim()) return;

    creatingAction = true;
    try {
      const createdAt = Math.floor(Date.now() / 1000);
      const content = `civicos:action:v1:${initiativeId}:${newAction.action_type}:${createdAt}`;
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_EVENT,
        tags: [['d', `action:${initiativeId}:${newAction.action_type}`], ['initiative', initiativeId]],
        content,
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        showToast(`Signing failed: ${(signResult as { error?: string }).error || 'unknown error'}`);
        creatingAction = false;
        return;
      }

      const created = await api.createCivicAction(
        initiativeId,
        newAction.action_type,
        newAction.description.trim(),
        signResult.data.pubkey,
        signResult.data.sig,
        createdAt,
        newAction.target.trim() || undefined,
        newAction.deadline || undefined,
        newAction.targetCount ?? undefined,
        newAction.template.trim() || undefined,
        newAction.deadlineContext.trim() || undefined
      );
      if (created) {
        const existing = initiativeActions.get(initiativeId) || [];
        initiativeActions.set(initiativeId, [...existing, created]);
        initiativeActions = new Map(initiativeActions);
        showCreateAction = null;
        newAction = { action_type: 'written_comment', description: '', target: '', deadline: '', template: '', deadlineContext: '', targetCount: null };
        showToast('Action created!');
      } else {
        showToast('Failed to create action. Relay may be unreachable.');
      }
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }
    creatingAction = false;
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
        const createdAt = Math.floor(Date.now() / 1000);
        const unsigned: NostrEvent = {
          created_at: createdAt,
          kind: CivicEventKinds.VOICE,
          tags: [['d', entityId]],
          content: `civicos:voice:v1:${entityId}:revoke:${createdAt}`,
        };
        const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
        if (signResult.success) {
          api.revokeVoice(entityId, signResult.data.pubkey, signResult.data.sig, createdAt);
        }
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
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.VOICE,
        tags: createVoiceTags(entityId, jurisdiction, stance),
        content: createVoiceContent(entityId, stance, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        throw new Error('Signing failed');
      }

      const ok = await api.submitVoice(entityId, stance, jurisdiction, signResult.data.pubkey, signResult.data.sig, createdAt);
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
  loadCommitments();
  loadConnectorSetupState();
  async function refreshAIState() {
    const available = await isAIAvailable();
    aiAvailable = available;
    const mgr = getAIManager();
    const provider = mgr.getActiveProvider();
    activeProviderName = provider ? provider.name : '';
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
            {#each pulseData.upcoming_items as item}
              <div class="card item-card">
                <div class="card-top-row">
                  {#if item.item_number}
                    <span class="item-number">#{item.item_number}</span>
                  {/if}
                  <span class="item-meeting">{item.meeting_title} &middot; {item.meeting_date}</span>
                </div>
                <div class="card-title">{item.title}</div>
                {#if item.description}
                  <div class="card-desc">{item.description}</div>
                {/if}
                {#if item.why_it_matters}
                  <div class="card-why"><strong>Why it matters:</strong> <em>{item.why_it_matters}</em></div>
                {/if}
                <div class="card-tags">
                  {#if item.stance_eligible}
                    <span class="tag tag-voice">Voice eligible</span>
                  {/if}
                  {#if item.comment_eligible}
                    <span class="tag tag-comment">Comment eligible</span>
                  {/if}
                  {#if item.project_type}
                    <span class="tag">{item.project_type}</span>
                  {/if}
                </div>
                {#if voiceCounts.has(`agenda-item:${item.id}`)}
                  {@const counts = voiceCounts.get(`agenda-item:${item.id}`)!}
                  <div class="voice-counts">
                    {#if counts.support > 0}<span class="vc vc-support">{counts.support} support</span>{/if}
                    {#if counts.oppose > 0}<span class="vc vc-oppose">{counts.oppose} oppose</span>{/if}
                    {#if counts.watching > 0}<span class="vc vc-watch">{counts.watching} watching</span>{/if}
                    {#if counts.attested != null && counts.attested > 0}<span class="vc vc-attested" title="{counts.attested} attested, {counts.unattested ?? 0} unattested">{counts.attested} attested</span>{/if}
                  </div>
                {/if}
                {#if item.stance_eligible}
                  <div class="voice-actions">
                    {#if identity?.isUnlocked}
                      {@const eid = `agenda-item:${item.id}`}
                      <button
                        class="voice-btn vb-support"
                        class:active={userStances.get(eid) === 'support'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'support')}
                      >Support</button>
                      <button
                        class="voice-btn vb-oppose"
                        class:active={userStances.get(eid) === 'oppose'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'oppose')}
                      >Oppose</button>
                      <button
                        class="voice-btn vb-watch"
                        class:active={userStances.get(eid) === 'watching'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'watching')}
                      >Watch</button>
                    {:else if identity}
                      <span class="voice-locked">Unlock to vote</span>
                    {/if}
                  </div>
                {/if}
                <!-- Comment Thread -->
                {#if item.comment_eligible}
                  {@const commentEntityId = `agenda-item:${item.id}`}
                  <div class="comment-section">
                    <div class="comment-actions-row">
                      <button class="comment-toggle" onclick={() => toggleCommentThread(commentEntityId)}>
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
                        {commentCounts.get(commentEntityId)?.count || 0} {(commentCounts.get(commentEntityId)?.count || 0) === 1 ? 'comment' : 'comments'}{#if (commentCounts.get(commentEntityId)?.attested ?? 0) > 0}&nbsp;({commentCounts.get(commentEntityId)?.attested} attested){/if}
                        <span class="chevron-sm" class:open={openThreads.has(commentEntityId)}></span>
                      </button>
                      {#if pulseData?.clerk_email && item.comment_eligible}
                        <a class="email-clerk-btn" href={getMailtoLink(item)} title="Email your comment to the City Clerk">
                          <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 4l6 4 6-4M2 4v8h12V4H2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
                          Email Clerk
                        </a>
                      {/if}
                    </div>
                    {#if openThreads.has(commentEntityId)}
                      <div class="comment-thread">
                        {#if threadLoading.has(commentEntityId)}
                          <div class="thread-loading">Loading comments...</div>
                        {:else}
                          <!-- Synthesis bar -->
                          {#if synthData.has(commentEntityId)}
                            {@const synth = synthData.get(commentEntityId)!}
                            {#if synth.total > 0}
                              <div class="synthesis-bar-wrapper">
                                <div class="synthesis-bar">
                                  {#if synth.support > 0}
                                    <div class="bar-seg bar-support" style="width: {(synth.support / synth.total) * 100}%" title="{synth.support} support"></div>
                                  {/if}
                                  {#if synth.oppose > 0}
                                    <div class="bar-seg bar-oppose" style="width: {(synth.oppose / synth.total) * 100}%" title="{synth.oppose} oppose"></div>
                                  {/if}
                                  {#if synth.neutral > 0}
                                    <div class="bar-seg bar-neutral" style="width: {(synth.neutral / synth.total) * 100}%" title="{synth.neutral} neutral"></div>
                                  {/if}
                                </div>
                                <div class="synthesis-labels">
                                  {#if synth.support > 0}<span class="synth-label synth-support">{synth.support} support</span>{/if}
                                  {#if synth.oppose > 0}<span class="synth-label synth-oppose">{synth.oppose} oppose</span>{/if}
                                  {#if synth.neutral > 0}<span class="synth-label synth-neutral">{synth.neutral} neutral</span>{/if}
                                </div>
                              </div>
                            {/if}
                          {/if}

                          <!-- Summarize thread button -->
                          {#if aiAvailable && (threadComments.get(commentEntityId) || []).length >= 2}
                            <div class="thread-summarize-row">
                              <button
                                class="summarize-btn"
                                disabled={aiResponseLoading.has(`summarize-thread:${commentEntityId}`)}
                                onclick={() => askAI(`summarize-thread:${commentEntityId}`, composeThreadSummary(item, commentEntityId))}
                              >
                                <span class="sparkle">✦</span>
                                {aiResponseLoading.has(`summarize-thread:${commentEntityId}`) ? 'Summarizing...' : aiResponses.has(`summarize-thread:${commentEntityId}`) ? 'Hide summary' : 'Summarize'}
                              </button>
                            </div>
                            {#if aiResponses.has(`summarize-thread:${commentEntityId}`)}
                              <div class="ai-response thread-summary-response">
                                <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`summarize-thread:${commentEntityId}`) ?? '')}</div>
                              </div>
                            {/if}
                          {/if}

                          <!-- Comment list -->
                          {#if (threadComments.get(commentEntityId) || []).length > 0}
                            <div class="thread-list">
                              {#each (threadComments.get(commentEntityId) || []) as comment}
                                <div class="thread-comment" class:stance-support={comment.stance === 'support'} class:stance-oppose={comment.stance === 'oppose'}>
                                  <div class="thread-comment-meta">
                                    <span class="thread-author">{identity?.publicKey && comment.public_key === identity.publicKey ? 'You' : comment.public_key.slice(0, 8) + '...'}</span>
                                    {#if comment.attested}<span class="thread-attested">Attested</span>{/if}
                                    {#if comment.stance}
                                      <span class="thread-stance" class:support={comment.stance === 'support'} class:oppose={comment.stance === 'oppose'}>{comment.stance}</span>
                                    {/if}
                                    <span class="thread-time">{new Date(comment.timestamp).toLocaleDateString()}</span>
                                  </div>
                                  <div class="thread-text">{comment.comment_text}</div>
                                </div>
                              {/each}
                            </div>
                          {:else}
                            <div class="thread-empty">No comments yet. Be the first!</div>
                          {/if}

                          <!-- Compose area -->
                          {#if identity?.isUnlocked}
                            {@const userExisting = getUserComment(commentEntityId)}
                            <div class="thread-compose">
                              {#if aiAvailable}
                                <div class="draft-toolbar">
                                  <button
                                    class="draft-btn"
                                    disabled={draftingInProgress.has(commentEntityId)}
                                    onclick={() => handleDraftWithAI(commentEntityId, item)}
                                    title={activeProviderName ? `via ${activeProviderName}` : ''}
                                  >
                                    {draftingInProgress.has(commentEntityId) ? 'Drafting...' : 'Draft with AI'}
                                  </button>
                                  {#if (threadDrafts.get(commentEntityId) || '').trim()}
                                    <button
                                      class="enrich-btn"
                                      disabled={enrichingInProgress.has(commentEntityId)}
                                      onclick={() => handleEnrichDraft(commentEntityId, item)}
                                    >
                                      {enrichingInProgress.has(commentEntityId) ? 'Enriching...' : 'Enrich with context'}
                                    </button>
                                  {/if}
                                  {#if activeProviderName}
                                    <span class="ai-provider-tag">via {activeProviderName}</span>
                                  {/if}
                                </div>
                              {/if}
                              <textarea
                                class="thread-textarea"
                                class:ai-loading={draftingInProgress.has(commentEntityId) || enrichingInProgress.has(commentEntityId)}
                                placeholder={userExisting ? 'Edit your comment...' : 'Add a comment...'}
                                rows={2}
                                maxlength={500}
                                value={threadDrafts.get(commentEntityId) || ''}
                                oninput={(e: Event) => { threadDrafts.set(commentEntityId, (e.target as HTMLTextAreaElement).value); threadDrafts = new Map(threadDrafts); }}
                              ></textarea>
                              <div class="thread-compose-footer">
                                <span class="ini-char-count" class:near-limit={(threadDrafts.get(commentEntityId) || '').length > 400}>
                                  {(threadDrafts.get(commentEntityId) || '').length}/500
                                </span>
                                <button
                                  class="thread-submit"
                                  disabled={!(threadDrafts.get(commentEntityId) || '').trim() || threadSubmitting.has(commentEntityId)}
                                  onclick={() => handleSubmitComment(commentEntityId)}
                                >
                                  {#if threadSubmitting.has(commentEntityId)}
                                    {userExisting ? 'Updating...' : 'Posting...'}
                                  {:else}
                                    {userExisting ? 'Update' : 'Post'}
                                  {/if}
                                </button>
                              </div>
                            </div>
                          {:else if identity}
                            <div class="thread-locked">Unlock to comment</div>
                          {/if}

                          {#if threadErrors.has(commentEntityId)}
                            <div class="thread-error">{threadErrors.get(commentEntityId)}</div>
                          {/if}
                        {/if}
                      </div>
                    {/if}
                  </div>
                {/if}

                {#if aiAvailable && identity?.isUnlocked && item.comment_eligible && !openThreads.has(`agenda-item:${item.id}`)}
                  <button class="draft-btn draft-btn-standalone" onclick={() => handleDraftWithAI(`agenda-item:${item.id}`, item)} disabled={draftingInProgress.has(`agenda-item:${item.id}`)} title={activeProviderName ? `via ${activeProviderName}` : ''}>
                    {draftingInProgress.has(`agenda-item:${item.id}`) ? 'Drafting...' : 'Draft with AI'}
                  </button>
                {/if}

                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-agenda:${item.id}`)}
                      disabled={aiResponseLoading.has(`ask-agenda:${item.id}`)}
                      onclick={() => askAI(`ask-agenda:${item.id}`, composeAgendaContext(item))}
                    >
                      <span class="sparkle">✦</span> {aiResponseLoading.has(`ask-agenda:${item.id}`) ? 'Thinking...' : aiResponses.has(`ask-agenda:${item.id}`) ? 'Hide' : activeProviderName}                    </button>
                  {/if}
                  <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => openExternalAI('claude', composeAgendaContext(item), e)}>
                    Claude <span class="ext-icon">↗</span>
                  </button>
                </div>
                {#if aiResponses.has(`ask-agenda:${item.id}`)}
                  <div class="ai-response">
                    <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-agenda:${item.id}`) ?? '')}</div>
                    {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                  </div>
                {/if}
              </div>
            {/each}
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
          {#if pulseData.recent_outcomes.length === 0}
            <div class="empty-section">No recent decisions</div>
          {:else}
            {#each pulseData.recent_outcomes as decision}
              <div class="card decision-card" class:expanded-card={expandedDecisions.has(decision.title)}>
                <button class="decision-row decision-toggle" onclick={() => toggleDecisionDetail(decision.title)}>
                  <span class="outcome-icon {outcomeClass(decision.outcome)}">
                    {outcomeIcon(decision.outcome)}
                  </span>
                  <div class="decision-info">
                    <div class="card-title">{decision.title}</div>
                    <div class="card-meta">
                      <span class="outcome-label {outcomeClass(decision.outcome)}">{decision.is_upcoming ? 'upcoming' : decision.outcome}</span>
                      {#if decision.vote_tally}
                        <span class="meta-sep">&middot;</span>
                        <span>{decision.vote_tally}</span>
                      {/if}
                      <span class="meta-sep">&middot;</span>
                      <span>{decision.date}</span>
                      {#if voiceCounts.has(decision.id)}
                        {@const counts = voiceCounts.get(decision.id)!}
                        {#if counts.total > 0}
                          <span class="meta-sep">&middot;</span>
                          <span class="voice-inline">{counts.total} voices{#if counts.attested != null && counts.attested > 0} ({counts.attested} attested){/if}</span>
                        {/if}
                      {/if}
                    </div>
                  </div>
                  <span class="expand-chevron" class:open={expandedDecisions.has(decision.title)}></span>
                </button>

                {#if expandedDecisions.has(decision.title)}
                  <div class="decision-detail">
                    {#if decisionLoading.has(decision.title)}
                      <div class="detail-loading">Loading details...</div>
                    {:else if decisionDetails.has(decision.title)}
                      {@const detail = decisionDetails.get(decision.title)!}
                      {#if detail.found && detail.decision}
                        <!-- Outcome badge row -->
                        <div class="outcome-row">
                          <span class="outcome-badge" class:approved={detail.decision.outcome?.toLowerCase().includes('approved')} class:denied={detail.decision.outcome?.toLowerCase().includes('denied')} class:upcoming={detail.is_upcoming}>
                            {detail.is_upcoming ? 'upcoming' : detail.decision.outcome}
                          </span>
                          {#if detail.decision.outcome_description}
                            <span class="outcome-desc">{detail.decision.outcome_description}</span>
                          {/if}
                          {#if detail.decision.votes}
                            <span class="vote-detail">
                              {Object.entries(detail.decision.votes).map(([k, v]) => `${k}: ${v}`).join(', ')}
                            </span>
                          {/if}
                        </div>

                        {#if detail.summary}
                          <div class="decision-summary">{detail.summary}</div>
                        {/if}

                        {#if detail.decision.body}
                          <div class="detail-body">{detail.decision.body}</div>
                        {/if}

                        <!-- Public Testimony -->
                        {#if detail.testimony?.public_comments && detail.testimony.public_comments.length > 0}
                          {@const testimonies = detail.testimony.public_comments}
                          {@const showAll = expandedTestimony.has(decision.title)}
                          {@const displayTestimonies = showAll ? testimonies : testimonies.slice(0, 3)}
                          <div class="detail-section">
                            <div class="detail-label-row">
                              <div class="detail-label">Public Testimony ({testimonies.length})</div>
                              {#if aiAvailable}
                                <button
                                  class="summarize-btn"
                                  disabled={aiResponseLoading.has(`ask-testimony:${decision.id}`)}
                                  onclick={() => askAI(`ask-testimony:${decision.id}`, composeTestimonySummary(decision, testimonies))}
                                >
                                  {aiResponseLoading.has(`ask-testimony:${decision.id}`) ? 'Summarizing...' : aiResponses.has(`ask-testimony:${decision.id}`) ? 'Hide summary' : 'Summarize'}
                                </button>
                              {/if}
                            </div>
                            {#each displayTestimonies as comment}
                              <div class="testimony-card">
                                <div class="testimony-meta">
                                  <span class="testimony-speaker">{comment.speaker}</span>
                                  {#if comment.start_timestamp}
                                    <span class="testimony-timestamp">{comment.start_timestamp}</span>
                                  {/if}
                                </div>
                                <div class="testimony-text">{comment.text}</div>
                                {#if comment.video_url}
                                  <a class="testimony-video-link" href={comment.video_url} target="_blank" rel="noopener">Watch clip</a>
                                {/if}
                              </div>
                            {/each}
                            {#if testimonies.length > 3}
                              <button class="detail-expand-btn" onclick={() => { if (showAll) { expandedTestimony.delete(decision.title); } else { expandedTestimony.add(decision.title); } expandedTestimony = new Set(expandedTestimony); }}>
                                {showAll ? 'Show less' : `+${testimonies.length - 3} more`}
                              </button>
                            {/if}
                            {#if aiResponses.has(`ask-testimony:${decision.id}`)}
                              <div class="ai-response">
                                <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-testimony:${decision.id}`) ?? '')}</div>
                                {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                              </div>
                            {/if}
                            <div class="ai-action-row">
                              <button class="ai-action-btn ai-action-claude solo" onclick={(e: MouseEvent) => openExternalAI('claude', composeTestimonySummary(decision, testimonies), e)}>
                                Discuss testimony in Claude <span class="ext-icon">↗</span>
                              </button>
                            </div>
                          </div>
                        {/if}

                        <!-- Council Discussion -->
                        {#if detail.testimony?.council_discussion && detail.testimony.council_discussion.length > 0}
                          {@const excerpts = detail.testimony.council_discussion}
                          {@const showAllCouncil = expandedCouncil.has(decision.title)}
                          {@const displayExcerpts = showAllCouncil ? excerpts : excerpts.slice(0, 3)}
                          <div class="detail-section">
                            <div class="detail-label">Council Discussion ({excerpts.length})</div>
                            {#each displayExcerpts as excerpt}
                              <div class="testimony-card">
                                <div class="testimony-meta">
                                  <span class="testimony-speaker">{excerpt.speaker}</span>
                                  {#if excerpt.start_timestamp}
                                    <span class="testimony-timestamp">{excerpt.start_timestamp}</span>
                                  {/if}
                                </div>
                                <div class="testimony-text">{excerpt.text}</div>
                                {#if excerpt.video_url}
                                  <a class="testimony-video-link" href={excerpt.video_url} target="_blank" rel="noopener">Watch clip</a>
                                {/if}
                              </div>
                            {/each}
                            {#if excerpts.length > 3}
                              <button class="detail-expand-btn" onclick={() => { if (showAllCouncil) { expandedCouncil.delete(decision.title); } else { expandedCouncil.add(decision.title); } expandedCouncil = new Set(expandedCouncil); }}>
                                {showAllCouncil ? 'Show less' : `+${excerpts.length - 3} more`}
                              </button>
                            {/if}
                          </div>
                        {/if}

                        <!-- Related Decisions -->
                        {#if detail.related_decisions && detail.related_decisions.length > 0}
                          <div class="detail-section">
                            <div class="detail-label">Related Decisions</div>
                            {#each detail.related_decisions as related}
                              <div class="related-item">
                                <span class="outcome-dot {outcomeClass(related.outcome)}"></span>
                                <span class="related-title">{related.title}</span>
                                <span class="related-date">{related.date}</span>
                              </div>
                            {/each}
                          </div>
                        {/if}
                        <!-- Voice buttons for decisions -->
                        <div class="voice-actions detail-voice">
                          {#if identity?.isUnlocked}
                            <button
                              class="voice-btn vb-support"
                              class:active={userStances.get(decision.id) === 'support'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'support')}
                            >Support</button>
                            <button
                              class="voice-btn vb-oppose"
                              class:active={userStances.get(decision.id) === 'oppose'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'oppose')}
                            >Oppose</button>
                            <button
                              class="voice-btn vb-watch"
                              class:active={userStances.get(decision.id) === 'watching'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'watching')}
                            >Watch</button>
                          {:else if identity}
                            <span class="voice-locked">Unlock to vote</span>
                          {/if}
                        </div>
                        <div class="ai-action-row">
                          {#if aiAvailable}
                            <button
                              class="ai-action-btn ai-action-ask"
                              class:active={aiResponses.has(`ask-decision:${decision.id}`)}
                              disabled={aiResponseLoading.has(`ask-decision:${decision.id}`)}
                              onclick={() => askAI(`ask-decision:${decision.id}`, composeDecisionContext(decision))}
                            >
                              <span class="sparkle">✦</span> {aiResponseLoading.has(`ask-decision:${decision.id}`) ? 'Thinking...' : aiResponses.has(`ask-decision:${decision.id}`) ? 'Hide' : activeProviderName}                            </button>
                          {/if}
                          <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => openExternalAI('claude', composeDecisionContext(decision), e)}>
                            Claude <span class="ext-icon">↗</span>
                          </button>
                        </div>
                        {#if aiResponses.has(`ask-decision:${decision.id}`)}
                          <div class="ai-response">
                            <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-decision:${decision.id}`) ?? '')}</div>
                            {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                          </div>
                        {/if}
                      {:else}
                        <div class="detail-empty">No details available</div>
                      {/if}
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </section>

    <!-- Community Initiatives -->
    <section class="feed-section ini">
      <button class="section-header" onclick={() => toggle('initiatives')}>
        <span class="section-title">
          Community Initiatives
          {#if initiatives.length > 0}
            <span class="ini-count">{initiatives.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.initiatives}></span>
      </button>
      {#if expanded.initiatives}
        <div class="ini-toolbar">
          <button class="ini-new-btn" onclick={() => { showCreateInitiative = !showCreateInitiative; }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            Start Initiative
          </button>
          {#if aggregateStats().committed > 0 || aggregateStats().completed > 0}
            <div class="ini-aggregate-stats">
              {#if aggregateStats().committed > 0}<span class="agg-stat">{aggregateStats().committed} committed</span>{/if}
              {#if aggregateStats().completed > 0}<span class="agg-stat agg-completed">{aggregateStats().completed} completed</span>{/if}
            </div>
          {/if}
        </div>
        <!-- Create initiative form -->
        {#if showCreateInitiative}
          <div class="ini-form">
            <div class="ini-form-header">
              <div class="ini-form-title">Start a Community Initiative</div>
              <button class="ini-form-close" aria-label="Close form" onclick={() => { showCreateInitiative = false; }}>
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
              </button>
            </div>

            {#if !identity}
              <div class="ini-hint">Set up identity in <button class="link-btn" onclick={openOptions}>Options</button> to sign initiatives.</div>
            {:else if !identity.isUnlocked}
              <div class="unlock-inline">
                <form class="unlock-row" onsubmit={(e: Event) => { e.preventDefault(); handleUnlock(); }}>
                  <input type="password" class="ini-input" placeholder="Password to unlock" bind:value={unlockPassword} autocomplete="off" />
                  <button type="submit" class="ini-btn-primary" disabled={unlocking || !unlockPassword}>{unlocking ? 'Unlocking...' : 'Unlock'}</button>
                </form>
                {#if unlockError}
                  <div class="ini-error">{unlockError}</div>
                {/if}
              </div>
            {/if}

            <label class="ini-field-label">
              Topic
              <div class="ini-topic-chips">
                {#each INITIATIVE_TOPICS as t}
                  <button class="ini-chip" class:active={newInitiative.topic === t} onclick={() => selectTopic(t)}>{t}</button>
                {/each}
                <button class="ini-chip" class:active={newInitiative.topic === '__custom__'} onclick={selectCustomTopic}>Other...</button>
              </div>
              {#if newInitiative.topic === '__custom__'}
                <input type="text" class="ini-input" placeholder="Enter topic" maxlength={50} bind:value={customTopic} />
              {/if}
            </label>

            <label class="ini-field-label">
              Title
              <input type="text" class="ini-input" placeholder="e.g., Safer crosswalks on 4th Street" maxlength={100} bind:value={newInitiative.title} />
              <span class="ini-char-hint">{newInitiative.title.length}/100</span>
            </label>

            <label class="ini-field-label">
              Description
              <textarea class="ini-textarea" placeholder="What's the issue? What outcome do you want?" maxlength={1000} rows={3} bind:value={newInitiative.description}></textarea>
              <span class="ini-char-hint">{newInitiative.description.length}/1000</span>
            </label>

            <label class="ini-field-label">
              Coordination Channel <span class="ini-optional">(optional)</span>
              <input type="url" class="ini-input" placeholder="Signal, SimpleX, Matrix, or Discord link" bind:value={newInitiative.coordination_url} />
            </label>

            <div class="ini-form-actions">
              <button class="ini-btn-cancel" onclick={() => { showCreateInitiative = false; }}>Cancel</button>
              <button class="ini-btn-primary" disabled={!identity?.isUnlocked || creatingInitiative || !effectiveTopic() || !newInitiative.title.trim() || !newInitiative.description.trim()} onclick={handleCreateInitiative}>
                {creatingInitiative ? 'Creating...' : 'Create Initiative'}
              </button>
            </div>
          </div>
        {/if}

        <div class="section-body">
          {#if initiativesLoading && initiatives.length === 0}
            <div class="ini-empty">Loading initiatives...</div>
          {:else if initiatives.length === 0 && !showCreateInitiative}
            <div class="ini-empty">
              No active initiatives yet.
              <button class="ini-start-link" onclick={() => { showCreateInitiative = true; }}>Start one</button>
            </div>
          {:else}
            {#each initiatives as initiative}
              <div class="ini-card" class:ini-card-expanded={expandedInitiatives.has(initiative.id)}>
                <button class="ini-card-toggle" onclick={() => toggleInitiativeDetail(initiative.id)}>
                  <div class="ini-card-top">
                    <span class="ini-topic-pill">{initiative.topic}</span>
                    <div class="ini-card-badges">
                      {#if initiative.voice_count > 0}
                        <span class="ini-voice-inline" title="{initiative.attested_voice_count != null && initiative.attested_voice_count > 0 ? `${initiative.attested_voice_count} attested` : ''}">
                          <svg class="ini-voice-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M6.956 1.745C7.021.81 7.908.087 8.864.325l.261.066c.463.116.874.456 1.012.965.22.816.533 2.511.062 4.51a10 10 0 0 1 .443-.051c.713-.065 1.669-.072 2.516.21.518.173.994.681 1.2 1.273.184.532.16 1.162-.234 1.733q.086.18.138.363c.077.27.113.567.113.856s-.036.586-.113.856c-.039.135-.09.273-.16.404.169.387.107.82-.003 1.149a3.2 3.2 0 0 1-.488.901c.054.152.076.312.076.465 0 .305-.089.625-.253.912C13.1 15.522 12.437 16 11.5 16H8c-.605 0-1.07-.081-1.466-.218a4.8 4.8 0 0 1-.97-.484l-.048-.03c-.504-.307-.999-.609-2.068-.722C2.682 14.464 2 13.846 2 13V9c0-.85.685-1.432 1.357-1.615.849-.232 1.574-.787 2.132-1.41.56-.627.914-1.28 1.039-1.639.199-.575.356-1.539.428-2.59z"/></svg>
                          <span class="ini-voice-num">{initiative.voice_count}{#if initiative.attested_voice_count != null && initiative.attested_voice_count > 0} <span class="ini-voice-attested">({initiative.attested_voice_count} attested)</span>{/if}</span>
                        </span>
                      {/if}
                      {#if initiative.coordination_url}
                        <svg class="ini-coord-icon" viewBox="0 0 16 16" fill="none"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2L7 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                      {/if}
                      <svg class="ini-expand-chevron" class:expanded={expandedInitiatives.has(initiative.id)} viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/></svg>
                    </div>
                  </div>
                  <div class="ini-card-title">{initiative.title}</div>
                  <div class="ini-card-desc">{initiative.description}</div>
                  {#if initiative.creator_attested || initiativeStats(initiative.id).committed > 0 || initiativeStats(initiative.id).completed > 0}
                    {@const stats = initiativeStats(initiative.id)}
                    <div class="ini-card-stats">
                      {#if initiative.creator_attested}<span class="ini-stat ini-stat-attested" title="Initiative creator is in-person verified">Attested</span>{/if}
                      {#if stats.committed > 0}<span class="ini-stat">{stats.committed} committed</span>{/if}
                      {#if stats.completed > 0}<span class="ini-stat ini-stat-done">{stats.completed} done</span>{/if}
                    </div>
                  {/if}
                </button>

                {#if expandedInitiatives.has(initiative.id)}
                  <div class="ini-detail">
                    {#if initiative.coordination_url}
                      <a href={initiative.coordination_url} target="_blank" rel="noopener" class="ini-coord-link">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2L7 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        Join coordination channel
                      </a>
                    {/if}

                    {#if actionsLoading.has(initiative.id)}
                      <div class="ini-detail-msg">Loading actions...</div>
                    {:else if initiativeActions.has(initiative.id)}
                      {@const actions = initiativeActions.get(initiative.id)!}
                      {#if actions.length === 0 && showCreateAction !== initiative.id}
                        <div class="ini-detail-msg">No civic actions defined yet</div>
                      {/if}
                      {#if actions.length > 0}
                        <div class="ini-detail-label">Civic Actions</div>
                        {#each actions as action}
                          <div class="ini-action">
                            <div class="ini-action-top">
                              <span class="ini-action-type">{actionTypeLabel(action.action_type)}</span>
                              {#if action.deadline}
                                <span class="ini-deadline {deadlineClass(action.deadline)}">
                                  {deadlineLabel(action.deadline)}
                                </span>
                              {/if}
                            </div>
                            <div class="ini-action-desc">{action.description}</div>
                            {#if action.target}
                              <div class="ini-action-target">Target: {action.target}</div>
                            {/if}

                            {#if actionProgress.has(action.id)}
                              {@const progress = actionProgress.get(action.id)!}
                              <div class="ini-progress">
                                <div class="ini-progress-bar">
                                  <div class="ini-progress-fill" style="width: {progress.progress_percent ?? 0}%"></div>
                                </div>
                                <span class="ini-progress-text">
                                  {progress.completion_count}/{progress.target_count ?? '?'}
                                  {#if progress.commitment_count > 0}
                                    ({progress.commitment_count} committed)
                                  {/if}
                                </span>
                              </div>
                            {/if}

                            <div class="ini-action-btns">
                              {#if identity?.isUnlocked}
                                {#if completedActions.has(action.id)}
                                  <span class="ini-completed-label">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                    Done
                                  </span>
                                {:else if committedActions.has(action.id)}
                                  <button class="ini-btn-primary ini-btn-sm" disabled={actionInProgress.has(action.id)} onclick={() => handleComplete(action)}>Mark Done</button>
                                  <button class="ini-btn-cancel ini-btn-sm" disabled={actionInProgress.has(action.id)} onclick={() => handleWithdraw(action)}>Withdraw</button>
                                {:else}
                                  <button class="ini-btn-primary ini-btn-sm" disabled={actionInProgress.has(action.id)} onclick={() => handleCommit(action)}>Commit</button>
                                {/if}
                              {:else if identity}
                                <span class="ini-locked-hint">Unlock to participate</span>
                              {/if}
                            </div>

                            {#if action.template}
                              <div class="ini-draft">
                                <textarea class="ini-draft-text" readonly>{action.template}</textarea>
                                <div class="ini-draft-actions">
                                  <button class="ini-btn-sm ini-btn-copy" onclick={async () => {
                                    await navigator.clipboard.writeText(action.template!);
                                    showToast('Copied to clipboard');
                                  }}>Copy</button>
                                </div>
                              </div>
                            {/if}
                          </div>
                        {/each}
                      {/if}
                      <!-- Add Action -->
                      {#if showCreateAction === initiative.id}
                        {@const actionConfig = ACTION_TYPE_CONFIG[newAction.action_type] || DEFAULT_ACTION_CONFIG}
                        <div class="ini-form ini-action-form" class:ini-drafting={formDraftLoading}>
                          {#if identity && !identity.isUnlocked}
                            <div class="unlock-inline">
                              <form class="unlock-row" onsubmit={(e: Event) => { e.preventDefault(); handleUnlock(); }}>
                                <input type="password" class="ini-input" placeholder="Password to unlock" bind:value={unlockPassword} autocomplete="off" />
                                <button type="submit" class="ini-btn-primary ini-btn-sm" disabled={unlocking || !unlockPassword}>{unlocking ? 'Unlocking...' : 'Unlock'}</button>
                              </form>
                              {#if unlockError}
                                <div class="ini-error">{unlockError}</div>
                              {/if}
                            </div>
                          {/if}
                          <select class="ini-input" bind:value={newAction.action_type}>
                            <option value="written_comment">Write Comment</option>
                            <option value="attend_meeting">Attend Meeting</option>
                            <option value="public_comment">Public Comment</option>
                            <option value="contact_official">Contact Official</option>
                            <option value="signature">Sign Petition</option>
                            <option value="share">Share</option>
                            <option value="custom">Custom</option>
                          </select>
                          <label class="ini-field-label">Description
                            <div class="ini-field">
                              <textarea class="ini-input ini-textarea" placeholder={actionConfig.descPlaceholder} maxlength={500} rows={2} bind:value={newAction.description}></textarea>
                              <span class="ini-char-count" class:near-limit={newAction.description.length > 400}>{newAction.description.length}/500</span>
                            </div>
                          </label>
                          <label class="ini-field-label">{actionConfig.targetLabel}
                            <div class="ini-field">
                              <input class="ini-input" type="text" placeholder={actionConfig.targetPlaceholder} bind:value={newAction.target} />
                            </div>
                          </label>
                          {#if actionConfig.showTemplate}
                            <label class="ini-field-label">{actionConfig.templateLabel}
                              <div class="ini-field">
                                <textarea class="ini-input ini-textarea" placeholder={actionConfig.templatePlaceholder} maxlength={2000} rows={3} bind:value={newAction.template}></textarea>
                                <span class="ini-char-count" class:near-limit={newAction.template.length > 1600}>{newAction.template.length}/2000</span>
                              </div>
                            </label>
                            {#if DRAFTABLE_TYPES.has(newAction.action_type)}
                              <button class="ini-btn-sm ini-btn-draft"
                                      disabled={formDraftLoading}
                                      onclick={() => handleFormDraft(initiative)}>
                                {formDraftLoading ? 'Drafting...' : 'Draft with AI'}
                              </button>
                            {/if}
                          {/if}
                          <label class="ini-field-label">{actionConfig.deadlineLabel}
                            <div class="ini-field">
                              <input class="ini-input" type="date" bind:value={newAction.deadline} />
                            </div>
                          </label>
                          {#if newAction.deadline}
                            <label class="ini-field-label">Context
                              <div class="ini-field">
                                <input class="ini-input" type="text" placeholder={actionConfig.deadlineContextPlaceholder} maxlength={200} bind:value={newAction.deadlineContext} />
                                <span class="ini-char-count" class:near-limit={newAction.deadlineContext.length > 160}>{newAction.deadlineContext.length}/200</span>
                              </div>
                            </label>
                          {/if}
                          {#if newAction.action_type === 'signature'}
                            <div class="ini-field">
                              <label class="ini-field-label">Signature goal
                                <input class="ini-input" type="number" placeholder="e.g., 500" min={1} bind:value={newAction.targetCount} />
                              </label>
                            </div>
                          {/if}
                          <div class="ini-form-actions">
                            <button class="ini-btn-cancel ini-btn-sm" onclick={() => { showCreateAction = null; }}>Cancel</button>
                            <button class="ini-btn-primary ini-btn-sm" disabled={!identity?.isUnlocked || creatingAction || !newAction.description.trim()} onclick={() => handleCreateAction(initiative.id)}>
                              {creatingAction ? 'Adding...' : 'Add Action'}
                            </button>
                          </div>
                        </div>
                      {:else}
                        <button class="ini-add-action" onclick={() => { showCreateAction = initiative.id; }}>
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
                          Add Action
                        </button>
                      {/if}
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </section>

    <!-- My Commitments (personal tracker) -->
    {#if committedActionMeta.size > 0}
      <section class="feed-section my-commitments-section">
        <button class="section-header" onclick={() => toggle('commitments')}>
          <span class="section-title">
            My Commitments
            <span class="count-badge">{committedActionMeta.size}</span>
          </span>
          <span class="chevron" class:open={expanded.commitments}></span>
        </button>
        {#if expanded.commitments}
          <div class="section-body">
            {#each [...committedActionMeta.entries()] as [actionId, meta]}
              <div class="card commitment-card" class:completed-commitment={completedActions.has(actionId)}>
                <div class="action-header">
                  <span class="action-type-badge">{actionTypeLabel(meta.action_type)}</span>
                  {#if completedActions.has(actionId)}
                    <span class="commitment-status done">Done</span>
                  {:else if meta.deadline}
                    <span class="deadline-badge {deadlineClass(meta.deadline)}">
                      {deadlineLabel(meta.deadline)}
                    </span>
                  {:else}
                    <span class="commitment-status active">Active</span>
                  {/if}
                </div>
                <div class="action-desc">{meta.description}</div>
                {#if meta.deadline && !completedActions.has(actionId)}
                  <div class="commitment-cal-row">
                    <a href={actionGoogleCalendarUrl(meta)} target="_blank" rel="noopener" class="commitment-cal-btn">Google Calendar</a>
                    <button class="commitment-cal-btn" onclick={() => downloadActionIcs(meta)}>Download .ics</button>
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

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
  .card-why strong { color: #d1d5db; }

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
  .decision-toggle:hover .card-title { color: #60a5fa; }

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

  .expanded-card {
    border: 1px solid #374151;
  }

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

  /* === Initiative Cards === */
  .initiative-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
  }

  .initiative-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }

  .initiative-topic {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    color: #60a5fa;
    letter-spacing: 0.03em;
  }

  .initiative-status {
    font-size: 10px;
    color: #6b7280;
    text-transform: capitalize;
  }

  .coord-link-label {
    font-size: 10px;
    color: #3b82f6;
  }

  .coord-link {
    display: block;
    font-size: 11px;
    color: #3b82f6;
    text-decoration: none;
    margin-bottom: 8px;
  }
  .coord-link:hover { text-decoration: underline; }

  .initiative-detail {
    border-top: 1px solid #374151;
    padding-top: 8px;
    margin-top: 8px;
  }

  /* === Action Cards (inside initiatives) === */
  .action-card {
    background: #171717;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 6px;
    border: 1px solid #374151;
  }

  .action-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }

  .action-type-badge {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
    background: #1e3a5f;
    color: #60a5fa;
  }

  .action-desc {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.3;
    margin-bottom: 4px;
  }

  .action-target {
    font-size: 10px;
    color: #6b7280;
    margin-bottom: 4px;
  }

  /* === Deadline Badges === */
  .deadline-badge {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .deadline-badge.normal { background: #374151; color: #9ca3af; }
  .deadline-badge.urgent { background: #78350f; color: #fbbf24; }
  .deadline-badge.overdue { background: #7f1d1d; color: #f87171; }

  /* === Progress Bar === */
  .progress-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 6px 0;
  }

  .progress-bar {
    flex: 1;
    height: 4px;
    background: #374151;
    border-radius: 2px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: #22c55e;
    border-radius: 2px;
    transition: width 0.3s ease;
  }

  .progress-text {
    font-size: 10px;
    color: #6b7280;
    white-space: nowrap;
  }

  /* === Action Buttons === */
  .action-buttons {
    display: flex;
    gap: 6px;
    margin-top: 6px;
    align-items: center;
  }

  .action-btn {
    font-size: 12px;
    padding: 5px 12px;
    border-radius: 8px;
    border: 1px solid #374151;
    background: transparent;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .action-btn:disabled { opacity: 0.5; cursor: default; }

  .btn-commit {
    color: #4ade80;
    border-color: #22c55e40;
  }
  .btn-commit:hover:not(:disabled) {
    background: #14532d;
    border-color: #22c55e;
  }

  .btn-complete {
    color: #60a5fa;
    border-color: #3b82f640;
  }
  .btn-complete:hover:not(:disabled) {
    background: #1e3a5f;
    border-color: #3b82f6;
  }

  .btn-withdraw {
    color: #9ca3af;
    border-color: #4b556340;
  }
  .btn-withdraw:hover:not(:disabled) {
    color: #f87171;
    border-color: #ef4444;
    background: #7f1d1d40;
  }

  .action-done {
    font-size: 10px;
    color: #4ade80;
    font-weight: 500;
  }

  /* === My Commitments Section === */
  .my-commitments-section {
    border-top: 2px solid #374151;
    margin-top: 4px;
    padding-top: 4px;
  }

  .static-header {
    padding: 8px 4px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #eee;
    border-bottom: 1px solid #374151;
  }

  .commitment-card {
    border-left: 2px solid #3b82f6;
  }
  .completed-commitment {
    border-left-color: #22c55e;
    opacity: 0.7;
  }

  .commitment-status {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .commitment-status.active { background: rgba(59,130,246,0.12); color: #60a5fa; }
  .commitment-status.done { background: #14532d; color: #4ade80; }
  .commitment-cal-row {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .commitment-cal-btn {
    font-size: 10px;
    color: #9ca3af;
    background: none;
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 2px 8px;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s;
  }
  .commitment-cal-btn:hover { color: #60a5fa; border-color: #60a5fa; }



  .add-btn {
    background: none;
    border: 1px solid #374151;
    color: #3b82f6;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 4px;
    flex-shrink: 0;
  }
  .add-btn:hover { background: #333; border-color: #3b82f6; }

  .add-action-btn {
    display: block;
    width: 100%;
    background: none;
    border: 1px dashed #374151;
    color: #6b7280;
    font-size: 11px;
    padding: 6px;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 4px;
  }
  .add-action-btn:hover { color: #3b82f6; border-color: #3b82f6; }

  /* === Create forms === */
  .create-form {
    background: #262626;
    border: 1px solid #374151;
    border-radius: 10px;
    padding: 10px;
    margin-bottom: 8px;
  }
  .form-hint {
    font-size: 11px;
    color: #f59e0b;
    margin-bottom: 6px;
    padding: 4px 8px;
    background: #78350f20;
    border-radius: 4px;
    border: 1px solid #78350f40;
  }
  .action-create-form {
    margin-top: 8px;
  }

  .form-input, .form-textarea {
    display: block;
    width: 100%;
    background: transparent;
    border: 1px solid #374151;
    color: #eee;
    font-size: 13px;
    padding: 5px 8px;
    border-radius: 4px;
    margin-bottom: 6px;
    font-family: inherit;
    box-sizing: border-box;
  }
  .form-input:focus, .form-textarea:focus {
    outline: none;
    border-color: #60a5fa;
  }
  .form-textarea {
    resize: vertical;
    min-height: 40px;
  }

  .form-actions {
    display: flex;
    gap: 6px;
    margin-top: 4px;
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
  .summarize-btn {
    font-size: 10px;
    color: #60a5fa;
    background: none;
    border: 1px solid #3b82f640;
    border-radius: 4px;
    padding: 1px 8px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .summarize-btn:hover {
    background: rgba(59,130,246,0.12);
    border-color: #3b82f6;
    color: #93c5fd;
  }
  .thread-summarize-row {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 6px;
  }
  .thread-summary-response {
    margin-bottom: 8px;
    border-left: 2px solid #3b82f640;
    padding-left: 8px;
  }

  /* === Comment Thread === */
  .comment-section { margin-top: 8px; }
  .comment-actions-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .email-clerk-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #9ca3af;
    text-decoration: none;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid transparent;
    transition: all 0.15s ease;
  }
  .email-clerk-btn:hover {
    color: #d1d5db;
    background: rgba(59,130,246,0.08);
    border-color: rgba(59,130,246,0.2);
  }
  .email-clerk-btn svg { opacity: 0.6; }
  .comment-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #9ca3af;
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px 0;
    transition: color 0.15s;
  }
  .comment-toggle:hover { color: #d1d5db; }
  .comment-toggle svg { opacity: 0.6; }
  .chevron-sm {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-right: 1.5px solid currentColor;
    border-bottom: 1.5px solid currentColor;
    transform: rotate(-45deg);
    transition: transform 0.15s;
    margin-left: 2px;
  }
  .chevron-sm.open { transform: rotate(45deg); }
  .comment-thread {
    margin-top: 6px;
    padding: 8px;
    background: #1e1e1e;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
  }
  .thread-loading, .thread-empty, .thread-locked {
    font-size: 11px;
    color: #6b7280;
    text-align: center;
    padding: 8px 0;
  }

  /* Synthesis bar */
  .synthesis-bar-wrapper { margin-bottom: 8px; }
  .synthesis-bar {
    display: flex;
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    background: #262626;
  }
  .bar-seg { min-width: 4px; }
  .bar-support { background: #22c55e; }
  .bar-oppose { background: #ef4444; }
  .bar-neutral { background: #9ca3af; }
  .synthesis-labels {
    display: flex;
    gap: 8px;
    margin-top: 4px;
  }
  .synth-label {
    font-size: 10px;
    color: #6b7280;
  }
  .synth-support { color: #22c55e; }
  .synth-oppose { color: #ef4444; }

  /* Thread list */
  .thread-list {
    max-height: 200px;
    overflow-y: auto;
    margin-bottom: 8px;
  }
  .thread-comment {
    padding: 6px 8px;
    border-radius: 6px;
    margin-bottom: 4px;
    background: #262626;
  }
  .thread-comment.stance-support { border-left: 2px solid rgba(34, 197, 94, 0.3); }
  .thread-comment.stance-oppose { border-left: 2px solid rgba(239, 68, 68, 0.3); }
  .thread-comment-meta {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 2px;
  }
  .thread-author {
    font-size: 10px;
    font-weight: 600;
    color: #d1d5db;
  }
  .thread-attested {
    font-size: 8px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    padding: 1px 5px;
    border-radius: 8px;
    background: rgba(34, 197, 94, 0.12);
    color: #22c55e;
  }
  .thread-stance {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 8px;
    background: #374151;
    color: #9ca3af;
  }
  .thread-stance.support { background: rgba(34,197,94,0.15); color: #22c55e; }
  .thread-stance.oppose { background: rgba(239,68,68,0.15); color: #ef4444; }
  .thread-time {
    font-size: 10px;
    color: #6b7280;
  }
  .thread-text {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.4;
    white-space: pre-wrap;
  }

  /* Compose area */
  .thread-compose { margin-top: 8px; }
  .thread-textarea {
    display: block;
    width: 100%;
    padding: 6px 8px;
    background: transparent;
    border: 1px solid #374151;
    border-radius: 6px;
    color: #eee;
    font-size: 12px;
    font-family: inherit;
    outline: none;
    resize: vertical;
    min-height: 40px;
    box-sizing: border-box;
  }
  .thread-textarea:focus { border-color: #60a5fa; }
  .thread-compose-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 4px;
  }
  .thread-submit {
    font-size: 11px;
    font-weight: 500;
    padding: 4px 12px;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .thread-submit:hover:not(:disabled) { background: #2563eb; }
  .thread-submit:disabled { opacity: 0.4; cursor: default; }
  .thread-error {
    font-size: 10px;
    color: #ef4444;
    margin-top: 4px;
  }

  /* === AI Action Row (Ask AI + Claude peer buttons) === */
  .ai-action-row {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .ai-action-btn {
    flex: 1;
    padding: 5px 0;
    font-size: 11px;
    font-weight: 500;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: center;
  }
  .ai-action-ask {
    color: #60a5fa;
    background: rgba(59,130,246,0.06);
    border: 1px solid #3b82f630;
  }
  .ai-action-ask:hover:not(:disabled) {
    background: rgba(59,130,246,0.14);
    border-color: #3b82f6;
    color: #93c5fd;
  }
  .ai-action-ask:disabled { opacity: 0.6; cursor: default; }
  .ai-action-ask.active {
    background: rgba(59,130,246,0.12);
    border-color: #3b82f6;
  }
  .ai-action-claude {
    color: #d4a574;
    background: rgba(212,165,116,0.06);
    border: 1px solid #d4a57430;
  }
  .ai-action-claude:hover {
    background: rgba(212,165,116,0.14);
    border-color: #d4a574;
    color: #e8c9a0;
  }
  .ai-action-claude.solo {
    flex: 1;
  }
  .sparkle { font-size: 10px; opacity: 0.7; }
  .ext-icon { font-size: 9px; }

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

  /* === AI Inline Response === */
  .ai-response {
    margin-top: 8px;
    padding: 10px 12px;
    background: rgba(139, 92, 246, 0.06);
    border: 1px solid rgba(139, 92, 246, 0.15);
    border-radius: 8px;
  }
  .ai-response-text {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.5;
  }
  .ai-response-text.prose :global(p) { margin: 0 0 8px; }
  .ai-response-text.prose :global(p:last-child) { margin-bottom: 0; }
  .ai-response-text.prose :global(strong) { color: #e5e7eb; font-weight: 600; }
  .ai-response-text.prose :global(em) { color: #c4b5fd; }
  .ai-response-text.prose :global(ul), .ai-response-text.prose :global(ol) {
    margin: 4px 0 8px;
    padding-left: 18px;
  }
  .ai-response-text.prose :global(li) { margin-bottom: 2px; }
  .ai-response-text.prose :global(code) {
    font-size: 11px;
    background: rgba(255,255,255,0.06);
    padding: 1px 4px;
    border-radius: 3px;
    color: #e2e8f0;
  }
  .ai-response-text.prose :global(h1), .ai-response-text.prose :global(h2),
  .ai-response-text.prose :global(h3), .ai-response-text.prose :global(h4) {
    font-size: 12px;
    font-weight: 600;
    color: #e5e7eb;
    margin: 8px 0 4px;
  }
  .ai-response-text.prose :global(h1:first-child), .ai-response-text.prose :global(h2:first-child),
  .ai-response-text.prose :global(h3:first-child), .ai-response-text.prose :global(h4:first-child) {
    margin-top: 0;
  }
  .ai-response-text.prose :global(blockquote) {
    margin: 4px 0;
    padding: 4px 10px;
    border-left: 2px solid rgba(139, 92, 246, 0.3);
    color: #a1a1aa;
  }
  .ai-response-text.prose :global(a) {
    color: #60a5fa;
    text-decoration: none;
  }
  .ai-response-text.prose :global(a:hover) { text-decoration: underline; }
  .ai-response-provider {
    display: block;
    margin-top: 6px;
    font-size: 10px;
    color: #64748b;
  }

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

  /* ======================================== */
  /* Community Initiatives — Open WebUI style */
  /* ======================================== */

  .ini .ini-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    font-size: 11px;
    font-weight: 600;
    border-radius: 9px;
    text-transform: none;
    letter-spacing: 0;
  }

  /* Toolbar inside expanded section: stats + New button */
  .ini-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0 2px;
  }
  .ini-new-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 14px;
    border: 1px solid #374151;
    border-radius: 8px;
    background: rgba(59, 130, 246, 0.08);
    color: #60a5fa;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-aggregate-stats {
    display: flex;
    gap: 12px;
    font-size: 11px;
    margin-left: auto;
  }
  .agg-stat { color: #9ca3af; }
  .agg-stat.agg-completed { color: #4ade80; }
  .ini-new-btn:hover {
    background: rgba(59, 130, 246, 0.12);
    border-color: #60a5fa;
  }

  .ini-card-stats {
    display: flex;
    gap: 8px;
    margin-top: 4px;
    font-size: 10px;
  }
  .ini-stat { color: #9ca3af; }
  .ini-stat.ini-stat-done { color: #4ade80; }
  .ini-stat.ini-stat-attested {
    color: #22c55e;
    background: rgba(34, 197, 94, 0.12);
    padding: 0 5px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  /* === Create Initiative Form === */
  .ini-form {
    background: #262626;
    border: 1px solid #374151;
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 8px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .ini-form-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .ini-form-title {
    font-size: 14px;
    font-weight: 600;
    color: #eee;
  }
  .ini-form-close {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-form-close:hover { color: #d1d5db; background: rgba(255, 255, 255, 0.06); }
  .ini-field-label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    font-weight: 600;
    color: #9ca3af;
  }
  .ini-optional { font-weight: 400; color: #6b7280; }
  .ini-char-hint { font-size: 10px; font-weight: 400; color: #6b7280; text-align: right; }
  .ini-hint {
    font-size: 12px;
    color: #fbbf24;
    padding: 8px 10px;
    background: rgba(251, 191, 36, 0.08);
    border: 1px solid rgba(251, 191, 36, 0.2);
    border-radius: 8px;
  }
  .ini-error {
    font-size: 12px;
    color: #ef4444;
    padding: 6px 10px;
    background: rgba(239, 68, 68, 0.08);
    border-radius: 6px;
  }
  .ini-input, .ini-textarea {
    display: block;
    width: 100%;
    padding: 8px 10px;
    background: transparent;
    border: 1px solid #374151;
    border-radius: 8px;
    color: #eee;
    font-size: 13px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s;
    box-sizing: border-box;
  }
  .ini-input:focus, .ini-textarea:focus { border-color: #60a5fa; }
  .ini-textarea { resize: vertical; min-height: 48px; }
  select.ini-input { appearance: auto; }

  /* Field wrapper with char counter */
  .ini-field {
    position: relative;
  }
  .ini-char-count {
    display: block;
    text-align: right;
    font-size: 10px;
    color: #6b7280;
    margin-top: 2px;
  }
  .ini-char-count.near-limit { color: #dc2626; }

  /* Topic chips */
  .ini-topic-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 2px;
  }
  .ini-chip {
    padding: 4px 10px;
    border: 1px solid #374151;
    border-radius: 12px;
    background: transparent;
    font-size: 12px;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-chip:hover { border-color: #4b5563; color: #d1d5db; }
  .ini-chip.active { background: #2563eb; border-color: #2563eb; color: white; }

  /* Form buttons */
  .ini-form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 2px;
  }
  .ini-btn-primary {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    background: #3b82f6;
    color: white;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-btn-primary:hover:not(:disabled) { background: #2563eb; }
  .ini-btn-primary:disabled { opacity: 0.4; cursor: default; }
  .ini-btn-cancel {
    padding: 8px 14px;
    border: 1px solid #374151;
    border-radius: 8px;
    background: transparent;
    color: #9ca3af;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-btn-cancel:hover { border-color: #4b5563; color: #d1d5db; }
  .ini-btn-sm { padding: 5px 12px; font-size: 12px; }

  /* Empty state */
  .ini-empty {
    padding: 16px 8px;
    color: #6b7280;
    font-size: 13px;
    text-align: center;
  }
  .ini-start-link {
    background: none;
    border: none;
    color: #3b82f6;
    cursor: pointer;
    font-size: 13px;
    text-decoration: underline;
  }
  .ini-start-link:hover { color: #60a5fa; }

  /* === Initiative Cards === */
  .ini-card {
    background: #262626;
    border: 1px solid #374151;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .ini-card:hover { border-color: #3b82f6; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1); }
  .ini-card-expanded { border-color: #3b82f6; }

  .ini-card-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
  }
  .ini-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    gap: 8px;
  }
  .ini-topic-pill {
    display: inline-block;
    padding: 2px 8px;
    background: rgba(59, 130, 246, 0.12);
    color: #60a5fa;
    font-size: 11px;
    font-weight: 600;
    border-radius: 10px;
    text-transform: capitalize;
  }
  .ini-card-badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .ini-voice-inline {
    display: flex;
    align-items: center;
    gap: 3px;
    color: #9ca3af;
  }
  .ini-voice-icon {
    width: 13px;
    height: 13px;
    color: #60a5fa;
  }
  .ini-voice-num {
    font-size: 11px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: #9ca3af;
  }
  .ini-voice-attested {
    font-size: 9px;
    font-weight: 500;
    color: #22c55e;
  }
  .ini-coord-icon {
    width: 13px;
    height: 13px;
    color: #6b7280;
    flex-shrink: 0;
  }
  .ini-expand-chevron {
    width: 12px;
    height: 12px;
    color: #6b7280;
    flex-shrink: 0;
    transition: transform 150ms ease;
  }
  .ini-expand-chevron.expanded {
    transform: rotate(180deg);
  }
  .ini-card-title {
    color: #eee;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.3;
  }
  .ini-card-toggle:hover .ini-card-title { color: #60a5fa; }
  .ini-card-desc {
    color: #9ca3af;
    font-size: 13px;
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    line-height: 1.4;
  }
  .ini-card-toggle:hover .ini-expand-chevron { color: #60a5fa; }
  .ini-card-toggle:hover .ini-coord-icon { color: #60a5fa; }

  /* === Initiative Detail (expanded) === */
  .ini-detail {
    border-top: 1px solid #374151;
    padding-top: 10px;
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ini-coord-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: #3b82f6;
    text-decoration: none;
    transition: color 0.15s;
  }
  .ini-coord-link:hover { color: #60a5fa; text-decoration: underline; }
  .ini-detail-msg { font-size: 12px; color: #6b7280; font-style: italic; }
  .ini-detail-label {
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* === Action Cards (inside initiatives) === */
  .ini-action {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 12px;
    position: relative;
  }

  /* AI drafting border animation */
  .ini-drafting {
    position: relative;
    border-color: transparent;
  }
  .ini-drafting::before {
    content: '';
    position: absolute;
    inset: -1px;
    border-radius: inherit;
    padding: 1px;
    background: conic-gradient(
      from var(--draft-angle, 0deg),
      transparent 40%,
      #a78bfa 50%,
      #7c3aed 55%,
      #a78bfa 60%,
      transparent 70%
    );
    -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    animation: draft-rotate 2s linear infinite;
    pointer-events: none;
  }
  @keyframes draft-rotate {
    to { --draft-angle: 360deg; }
  }
  @property --draft-angle {
    syntax: '<angle>';
    initial-value: 0deg;
    inherits: false;
  }
  .ini-action-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .ini-action-type {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    background: rgba(59, 130, 246, 0.12);
    color: #60a5fa;
  }
  .ini-deadline {
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 6px;
  }
  .ini-deadline.normal { background: rgba(107, 114, 128, 0.12); color: #9ca3af; }
  .ini-deadline.urgent { background: rgba(251, 191, 36, 0.12); color: #fbbf24; }
  .ini-deadline.overdue { background: rgba(239, 68, 68, 0.12); color: #f87171; }
  .ini-action-desc { font-size: 13px; color: #d1d5db; line-height: 1.4; }
  .ini-action-target { font-size: 12px; color: #6b7280; margin-top: 2px; }

  .ini-progress {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
  }
  .ini-progress-bar {
    flex: 1;
    height: 6px;
    background: #333;
    border-radius: 3px;
    overflow: hidden;
  }
  .ini-progress-fill {
    height: 100%;
    background: #3b82f6;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .ini-progress-text { font-size: 11px; color: #6b7280; white-space: nowrap; }

  .ini-action-btns {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
  }
  .ini-completed-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 600;
    color: #4ade80;
    padding: 3px 10px;
    background: rgba(34, 197, 94, 0.1);
    border-radius: 6px;
  }
  .ini-locked-hint {
    font-size: 11px;
    color: #6b7280;
    font-style: italic;
  }

  /* AI Draft */
  .ini-btn-draft {
    margin-top: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
    color: #a78bfa;
    background: rgba(139, 92, 246, 0.1);
    border: 1px solid rgba(139, 92, 246, 0.25);
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }
  .ini-btn-draft:hover:not(:disabled) { background: rgba(139, 92, 246, 0.2); border-color: rgba(139, 92, 246, 0.4); }
  .ini-btn-draft:disabled { opacity: 0.5; cursor: default; }
  .ini-draft {
    margin-top: 8px;
    border: 1px solid rgba(139, 92, 246, 0.2);
    border-radius: 8px;
    padding: 8px;
    background: rgba(139, 92, 246, 0.05);
  }
  .ini-draft-text {
    width: 100%;
    min-height: 120px;
    background: transparent;
    border: none;
    color: #d1d5db;
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
    font-family: inherit;
    outline: none;
  }
  .ini-draft-actions {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .ini-btn-copy {
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
    color: #a78bfa;
    background: rgba(139, 92, 246, 0.15);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 6px;
    cursor: pointer;
  }
  .ini-btn-copy:hover { background: rgba(139, 92, 246, 0.25); }

  /* Add Action button */
  .ini-add-action {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    background: transparent;
    border: 1px dashed #374151;
    border-radius: 8px;
    color: #6b7280;
    font-size: 12px;
    padding: 8px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ini-add-action:hover { color: #3b82f6; border-color: #3b82f6; }

  .ini-action-form { margin-top: 4px; padding: 12px; }

  /* === AI Draft Toolbar === */
  .draft-toolbar {
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
  }
  .draft-btn {
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    background: rgba(139, 92, 246, 0.1);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.25);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .draft-btn:hover:not(:disabled) {
    background: rgba(139, 92, 246, 0.2);
    border-color: #a78bfa;
  }
  .draft-btn:disabled { opacity: 0.5; cursor: default; }
  .draft-btn-standalone {
    display: block;
    width: 100%;
    margin-top: 6px;
    padding: 5px 0;
    text-align: center;
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
  .thread-textarea.ai-loading {
    animation: ai-pulse 1.5s ease-in-out infinite;
  }
  @keyframes ai-pulse {
    0%, 100% { border-color: #374151; }
    50% { border-color: #a78bfa; }
  }
</style>

<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import { getCityPulse, getDecisionDetail, getDataProvenance, getVoiceCountsBatch, submitVoice, revokeVoice, getInitiatives, getCivicActions, getCivicActionProgress, commitToCivicAction, completeCivicAction, withdrawCivicAction, createInitiative, createCivicAction, getIssueGeography, getBudgetSummary } from '../lib/api.js';
  import type { IdentityInfo, NostrEvent, SignedNostrEvent } from '../lib/providers/types.js';
  import { CivicEventKinds, createVoiceContent, createVoiceTags, createCommitmentContent, createCommitmentTags, createCompletionContent, createCompletionTags, generateCommitmentId, generateCompletionId, generateActionRef } from '../lib/providers/types.js';
  import type { CityPulseData, DecisionDetailData, DataProvenance, VoiceCounts, Initiative, CivicAction, CivicActionProgress, IssuePoint, BudgetCategory } from '../lib/types.js';
  import 'leaflet/dist/leaflet.css';
  import L from 'leaflet';
  import { Chart, DoughnutController, ArcElement, Tooltip, Legend } from 'chart.js';

  Chart.register(DoughnutController, ArcElement, Tooltip, Legend);

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
    community: false,
    issueMap: false,
    budget: false,
  });

  // Decision detail expansion
  let expandedDecisions = $state(new Set<string>());
  let decisionDetails = $state(new Map<string, DecisionDetailData>());
  let decisionLoading = $state(new Set<string>());

  // Data provenance
  let showProvenance = $state(false);
  let provenanceData: DataProvenance | null = $state(null);
  let provenanceLoading = $state(false);

  // Voice counts
  let voiceCounts = $state(new Map<string, VoiceCounts>());

  // Voice submission state
  type Stance = 'support' | 'oppose' | 'watching';
  let userStances = $state(new Map<string, Stance>());
  let votingInProgress = $state(new Set<string>());
  const STANCES_STORAGE_KEY = 'civicos_user_stances';

  // Calendar dropdown
  let calendarOpen: string | null = $state(null);

  // Initiatives state
  let initiatives: Initiative[] = $state([]);
  let initiativesLoading = $state(false);
  let expandedInitiatives = $state(new Set<string>());
  let initiativeActions = $state(new Map<string, CivicAction[]>());
  let actionProgress = $state(new Map<string, CivicActionProgress>());
  let actionsLoading = $state(new Set<string>());

  // Commitment tracking (persisted)
  let committedActions = $state(new Set<string>());
  let completedActions = $state(new Set<string>());
  let actionInProgress = $state(new Set<string>());
  // Store action metadata for My Commitments (renders without expanding initiative)
  let committedActionMeta = $state(new Map<string, { action_type: string; description: string; deadline?: string }>());
  const COMMITMENTS_STORAGE_KEY = 'civicos_user_commitments';
  const COMPLETIONS_STORAGE_KEY = 'civicos_user_completions';
  const COMMITMENT_META_STORAGE_KEY = 'civicos_commitment_meta';

  // Create initiative form
  let showCreateInitiative = $state(false);
  let newInitiative = $state({ topic: '', title: '', description: '', coordination_url: '' });
  let creatingInitiative = $state(false);

  // Create action form (per initiative)
  let showCreateAction: string | null = $state(null); // initiative ID
  let newAction = $state({ action_type: 'written_comment', description: '', target: '', deadline: '' });
  let creatingAction = $state(false);

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
  }

  async function loadCityPulse() {
    pulseLoading = true;
    pulseError = null;
    try {
      pulseData = await getCityPulse();
      // Load voice counts and initiatives in background after pulse data arrives
      loadVoiceCounts();
      loadInitiatives();
    } catch (err) {
      pulseError = err instanceof Error ? err.message : 'Failed to load civic data';
    }
    pulseLoading = false;
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
      voiceCounts = await getVoiceCountsBatch(ids);
    }
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
        const detail = await getDecisionDetail(title);
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
        provenanceData = await getDataProvenance();
      } catch (e) {
        console.error('Failed to load provenance:', e);
      } finally {
        provenanceLoading = false;
      }
    }
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
    'Other': '#64748b',
  };

  function getIssueColor(type: string): string {
    for (const [key, color] of Object.entries(ISSUE_COLORS)) {
      if (type.toLowerCase().includes(key.toLowerCase())) return color;
    }
    return ISSUE_COLORS['Other'];
  }

  async function loadIssueMap() {
    if (issueMapLoaded || issueMapLoading) return;
    issueMapLoading = true;
    try {
      const data = await getIssueGeography(500);
      issuePoints = data.points;
      issueMapLoaded = true;
      // Render map after DOM updates
      await new Promise(r => setTimeout(r, 50));
      renderMap();
    } catch (e) {
      console.error('Failed to load issue map:', e);
    } finally {
      issueMapLoading = false;
    }
  }

  function renderMap() {
    if (!mapContainer || issuePoints.length === 0) return;
    if (leafletMap) { leafletMap.remove(); leafletMap = null; }

    leafletMap = L.map(mapContainer, { zoomControl: false }).setView([37.9735, -122.5311], 13);
    L.control.zoom({ position: 'topright' }).addTo(leafletMap);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      maxZoom: 19,
    }).addTo(leafletMap);

    for (const pt of issuePoints) {
      L.circleMarker([pt.lat, pt.lng], {
        radius: 5,
        color: getIssueColor(pt.type),
        fillColor: getIssueColor(pt.type),
        fillOpacity: 0.7,
        weight: 1,
      }).bindPopup(`<b>${pt.type}</b><br>${pt.address}<br><small>${pt.status}</small>`)
        .addTo(leafletMap);
    }

    // Fit bounds to points
    if (issuePoints.length > 1) {
      const bounds = L.latLngBounds(issuePoints.map(p => [p.lat, p.lng] as [number, number]));
      leafletMap.fitBounds(bounds, { padding: [20, 20] });
    }
  }

  // === Budget Chart ===

  const BUDGET_COLORS = [
    '#6366f1', '#ec4899', '#14b8a6', '#f59e0b', '#ef4444',
    '#8b5cf6', '#22c55e', '#3b82f6', '#f97316', '#64748b',
    '#a855f7', '#06b6d4', '#84cc16', '#e11d48',
  ];

  async function loadBudget() {
    if (budgetLoaded || budgetLoading) return;
    budgetLoading = true;
    try {
      const data = await getBudgetSummary('department');
      budgetCategories = data.categories;
      budgetTotal = data.total_budgeted_dollars;
      budgetYear = data.fiscal_year;
      budgetLoaded = true;
      await new Promise(r => setTimeout(r, 50));
      renderBudgetChart();
    } catch (e) {
      console.error('Failed to load budget:', e);
    } finally {
      budgetLoading = false;
    }
  }

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
    const eid = `agenda-item:${item.id}`;
    const counts = voiceCounts.get(eid);
    if (counts && counts.total > 0) {
      lines.push('', `Community sentiment: ${counts.support} support, ${counts.oppose} oppose, ${counts.watching} watching`);
    }
    lines.push('', 'What are the key implications for residents? What questions should I ask at the public hearing?');
    return lines.join('\n');
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
      lines.push('', `Public testimony (${detail.testimony.public_comments.length} speakers):`);
      for (const c of detail.testimony.public_comments.slice(0, 5)) {
        lines.push(`- ${c.speaker}: ${c.text}`);
      }
      if (detail.testimony.public_comments.length > 5) {
        lines.push(`... and ${detail.testimony.public_comments.length - 5} more speakers`);
      }
    }
    const counts = voiceCounts.get(decision.id);
    if (counts && counts.total > 0) {
      lines.push('', `Community sentiment: ${counts.support} support, ${counts.oppose} oppose, ${counts.watching} watching`);
    }
    lines.push('', 'What are the implications of this decision for residents? What should I know about this issue going forward?');
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

  async function askAI(context: string) {
    try {
      await navigator.clipboard.writeText(context);
      chrome.tabs.create({ url: 'https://claude.ai/new' });
      showToast('Context copied — paste into chat (Ctrl+V)');
    } catch {
      showToast('Could not copy to clipboard');
    }
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
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
      initiatives = await getInitiatives(jurisdiction);
    } catch {
      initiatives = [];
    }
    initiativesLoading = false;
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
        const actions = await getCivicActions(initiativeId);
        initiativeActions.set(initiativeId, actions);
        initiativeActions = new Map(initiativeActions);

        // Load progress for each action
        const progressPromises = actions.map(async (action) => {
          const progress = await getCivicActionProgress(action.id);
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
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_COMMITMENT,
        tags: createCommitmentTags(action.id, jurisdiction),
        content: createCommitmentContent(action.id, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) throw new Error('Signing failed');

      const ok = await commitToCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt, jurisdiction);
      if (!ok) throw new Error('Relay submission failed');

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
    } catch {
      // No rollback needed — commitment wasn't added on failure
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
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.ACTION_COMPLETION,
        tags: createCompletionTags(action.id, jurisdiction),
        content: createCompletionContent(action.id, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) throw new Error('Signing failed');

      const ok = await completeCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt, jurisdiction);
      if (!ok) throw new Error('Relay submission failed');

      completedActions.add(action.id);
      completedActions = new Set(completedActions);
      persistCommitments();

      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, completion_count: prev.completion_count + 1 });
        actionProgress = new Map(actionProgress);
      }
    } catch {
      // No rollback needed
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
      if (!signResult.success) throw new Error('Signing failed');

      const ok = await withdrawCivicAction(action.id, signResult.data.pubkey, signResult.data.sig, createdAt);
      if (!ok) throw new Error('Relay submission failed');

      committedActions.delete(action.id);
      committedActions = new Set(committedActions);
      persistCommitments();

      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, commitment_count: Math.max(0, prev.commitment_count - 1) });
        actionProgress = new Map(actionProgress);
      }
    } catch {
      // No rollback needed
    }

    actionInProgress.delete(action.id);
    actionInProgress = new Set(actionInProgress);
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
    if (!newInitiative.topic.trim() || !newInitiative.title.trim() || !newInitiative.description.trim()) return;

    creatingInitiative = true;
    try {
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
      const createdAt = Math.floor(Date.now() / 1000);
      const content = `civicos:initiative:v1:${jurisdiction}:${newInitiative.topic}:${createdAt}`;
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: 30800, // Use voice kind for initiative signing
        tags: [['d', `initiative:${jurisdiction}:${newInitiative.topic}`], ['j', jurisdiction]],
        content,
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) throw new Error('Signing failed');

      const created = await createInitiative(
        jurisdiction,
        newInitiative.topic.trim(),
        newInitiative.title.trim(),
        newInitiative.description.trim(),
        signResult.data.pubkey,
        signResult.data.sig,
        undefined,
        newInitiative.coordination_url.trim() || undefined
      );
      if (created) {
        initiatives = [created, ...initiatives];
        showCreateInitiative = false;
        newInitiative = { topic: '', title: '', description: '', coordination_url: '' };
      }
    } catch {
      // Show nothing — form stays open for retry
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
      if (!signResult.success) throw new Error('Signing failed');

      const created = await createCivicAction(
        initiativeId,
        newAction.action_type,
        newAction.description.trim(),
        signResult.data.pubkey,
        signResult.data.sig,
        newAction.target.trim() || undefined,
        newAction.deadline || undefined,
        undefined
      );
      if (created) {
        const existing = initiativeActions.get(initiativeId) || [];
        initiativeActions.set(initiativeId, [...existing, created]);
        initiativeActions = new Map(initiativeActions);
        showCreateAction = null;
        newAction = { action_type: 'written_comment', description: '', target: '', deadline: '' };
      }
    } catch {
      // Form stays open for retry
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
          revokeVoice(entityId, signResult.data.pubkey, signResult.data.sig, createdAt);
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
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
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

      const ok = await submitVoice(entityId, stance, jurisdiction, signResult.data.pubkey, signResult.data.sig, createdAt);
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
    if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted')) return '\u2713';
    if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected')) return '\u2717';
    if (lower.includes('continued') || lower.includes('tabled')) return '\u21BB';
    return '\u2022';
  }

  function outcomeClass(outcome: string): string {
    const lower = outcome.toLowerCase();
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
  loadIdentity();
  loadCityPulse();
  loadStances();
  loadCommitments();
</script>

<div class="panel">
  <header>
    <div class="header-left">
      <h1>City Pulse</h1>
      {#if pulseData}
        <span class="jurisdiction">{pulseData.jurisdiction}</span>
      {/if}
    </div>
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
          <span>{provenanceData.corpora.length} data types</span>
          <span class="meta-sep">&middot;</span>
          <span>{provenanceData.total_vector_docs.toLocaleString()} indexed docs</span>
          {#if provenanceData.overall_coverage_percent != null}
            <span class="meta-sep">&middot;</span>
            <span>{provenanceData.overall_coverage_percent}% coverage</span>
          {/if}
        </div>
        <div class="prov-corpora">
          {#each provenanceData.corpora as corpus}
            <div class="corpus-row">
              <span class="corpus-name">{corpus.display_name}</span>
              <span class="corpus-count">{corpus.storage_count.toLocaleString()}</span>
            </div>
          {/each}
        </div>
        {#if provenanceData.freshness.last_updated}
          <div class="prov-freshness">
            Updated {formatRelativeDate(provenanceData.freshness.last_updated)}
          </div>
        {/if}
      {:else}
        <div class="prov-loading">Unable to load data sources</div>
      {/if}
    </div>
  {/if}

  <!-- Identity chip -->
  {#if loading}
    <div class="identity-chip skeleton">&nbsp;</div>
  {:else if identity}
    <div class="identity-chip">
      <div class="chip-row">
        <span class="tier-badge" class:easy={identity.tier === 'easy'} class:private={identity.tier === 'private'}>
          {identity.tier}
        </span>
        <span class="lock-status" class:unlocked={identity.isUnlocked}>
          {identity.isUnlocked ? 'unlocked' : 'locked'}
        </span>
      </div>
      <div class="npub">{truncateNpub(identity.npub)}</div>
    </div>
  {:else}
    <div class="identity-chip empty">
      <span>No identity</span>
      <button class="link-btn" onclick={openOptions}>Set up</button>
    </div>
  {/if}

  <!-- City Pulse content -->
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
                <button class="ask-ai-btn" onclick={() => askAI(composeAgendaContext(item))}>
                  Ask AI about this
                </button>
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
                      <span class="outcome-label {outcomeClass(decision.outcome)}">{decision.outcome}</span>
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
                          <span class="voice-inline">{counts.total} voices</span>
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
                        {#if detail.decision.body}
                          <div class="detail-body">{detail.decision.body}</div>
                        {/if}
                        {#if detail.testimony?.public_comments && detail.testimony.public_comments.length > 0}
                          <div class="detail-section">
                            <div class="detail-label-row">
                              <div class="detail-label">Public Testimony ({detail.testimony.public_comments.length})</div>
                              <button class="summarize-btn" onclick={() => askAI(composeTestimonySummary(decision, detail.testimony!.public_comments!))}>
                                Summarize
                              </button>
                            </div>
                            {#each detail.testimony.public_comments.slice(0, 3) as comment}
                              <div class="testimony-item">
                                <span class="testimony-speaker">{comment.speaker}</span>
                                <span class="testimony-text">{comment.text}</span>
                              </div>
                            {/each}
                            {#if detail.testimony.public_comments.length > 3}
                              <div class="detail-more">+{detail.testimony.public_comments.length - 3} more</div>
                            {/if}
                          </div>
                        {/if}
                        {#if detail.related_decisions && detail.related_decisions.length > 0}
                          <div class="detail-section">
                            <div class="detail-label">Related Decisions</div>
                            {#each detail.related_decisions.slice(0, 3) as related}
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
                        <button class="ask-ai-btn" onclick={() => askAI(composeDecisionContext(decision))}>
                          Ask AI about this
                        </button>
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
    <section class="feed-section">
      <div class="section-header-row">
        <button class="section-header" onclick={() => toggle('initiatives')}>
          <span class="section-title">
            Community Initiatives
            {#if initiatives.length > 0}
              <span class="count-badge">{initiatives.length}</span>
            {/if}
          </span>
          <span class="chevron" class:open={expanded.initiatives}></span>
        </button>
        {#if identity?.isUnlocked && expanded.initiatives}
          <button
            class="add-btn"
            title="Start initiative"
            onclick={() => { showCreateInitiative = !showCreateInitiative; }}
          >+</button>
        {/if}
      </div>
      {#if expanded.initiatives}
        <!-- Create initiative form -->
        {#if showCreateInitiative}
          <div class="create-form">
            <input class="form-input" type="text" placeholder="Topic (e.g. traffic safety)" bind:value={newInitiative.topic} />
            <input class="form-input" type="text" placeholder="Title" bind:value={newInitiative.title} />
            <textarea class="form-textarea" placeholder="Description" bind:value={newInitiative.description} rows="2"></textarea>
            <input class="form-input" type="url" placeholder="Coordination URL (optional)" bind:value={newInitiative.coordination_url} />
            <div class="form-actions">
              <button class="action-btn btn-commit" disabled={creatingInitiative || !newInitiative.topic.trim() || !newInitiative.title.trim() || !newInitiative.description.trim()} onclick={handleCreateInitiative}>
                {creatingInitiative ? 'Creating...' : 'Create Initiative'}
              </button>
              <button class="action-btn btn-withdraw" onclick={() => { showCreateInitiative = false; }}>Cancel</button>
            </div>
          </div>
        {/if}

        <div class="section-body">
          {#if initiativesLoading && initiatives.length === 0}
            <div class="empty-section">Loading initiatives...</div>
          {:else if initiatives.length === 0 && !showCreateInitiative}
            <div class="empty-section">
              No active initiatives
              {#if identity?.isUnlocked}
                <button class="link-btn" onclick={() => { showCreateInitiative = true; }}>Start one</button>
              {/if}
            </div>
          {:else}
            {#each initiatives as initiative}
              <div class="card initiative-card" class:expanded-card={expandedInitiatives.has(initiative.id)}>
                <button class="initiative-toggle" onclick={() => toggleInitiativeDetail(initiative.id)}>
                  <div class="initiative-header">
                    <span class="initiative-topic">{initiative.topic}</span>
                    {#if initiative.voice_count > 0}
                      <span class="voice-inline">{initiative.voice_count} voices</span>
                    {/if}
                  </div>
                  <div class="card-title">{initiative.title}</div>
                  <div class="card-desc">{initiative.description}</div>
                  <div class="card-meta">
                    <span class="initiative-status">{initiative.status}</span>
                    {#if initiative.coordination_url}
                      <span class="meta-sep">&middot;</span>
                      <span class="coord-link-label">coordination channel</span>
                    {/if}
                    <span class="expand-chevron" class:open={expandedInitiatives.has(initiative.id)}></span>
                  </div>
                </button>

                {#if expandedInitiatives.has(initiative.id)}
                  <div class="initiative-detail">
                    {#if initiative.coordination_url}
                      <a href={initiative.coordination_url} target="_blank" rel="noopener" class="coord-link">
                        Join coordination channel
                      </a>
                    {/if}

                    {#if actionsLoading.has(initiative.id)}
                      <div class="detail-loading">Loading actions...</div>
                    {:else if initiativeActions.has(initiative.id)}
                      {@const actions = initiativeActions.get(initiative.id)!}
                      {#if actions.length === 0 && showCreateAction !== initiative.id}
                        <div class="detail-empty">No civic actions defined yet</div>
                      {/if}
                      {#if actions.length > 0}
                        <div class="detail-label">Civic Actions</div>
                        {#each actions as action}
                          <div class="action-card">
                            <div class="action-header">
                              <span class="action-type-badge">{actionTypeLabel(action.action_type)}</span>
                              {#if action.deadline}
                                <span class="deadline-badge {deadlineClass(action.deadline)}">
                                  {deadlineLabel(action.deadline)}
                                </span>
                              {/if}
                            </div>
                            <div class="action-desc">{action.description}</div>
                            {#if action.target}
                              <div class="action-target">Target: {action.target}</div>
                            {/if}

                            <!-- Progress bar -->
                            {#if actionProgress.has(action.id)}
                              {@const progress = actionProgress.get(action.id)!}
                              <div class="progress-row">
                                <div class="progress-bar">
                                  <div
                                    class="progress-fill"
                                    style="width: {progress.progress_percent ?? 0}%"
                                  ></div>
                                </div>
                                <span class="progress-text">
                                  {progress.completion_count}/{progress.target_count ?? '?'}
                                  {#if progress.commitment_count > 0}
                                    ({progress.commitment_count} committed)
                                  {/if}
                                </span>
                              </div>
                            {/if}

                            <!-- Action buttons -->
                            <div class="action-buttons">
                              {#if identity?.isUnlocked}
                                {#if completedActions.has(action.id)}
                                  <span class="action-done">Completed</span>
                                {:else if committedActions.has(action.id)}
                                  <button
                                    class="action-btn btn-complete"
                                    disabled={actionInProgress.has(action.id)}
                                    onclick={() => handleComplete(action)}
                                  >Mark Done</button>
                                  <button
                                    class="action-btn btn-withdraw"
                                    disabled={actionInProgress.has(action.id)}
                                    onclick={() => handleWithdraw(action)}
                                  >Withdraw</button>
                                {:else}
                                  <button
                                    class="action-btn btn-commit"
                                    disabled={actionInProgress.has(action.id)}
                                    onclick={() => handleCommit(action)}
                                  >Commit</button>
                                {/if}
                              {:else if identity}
                                <span class="voice-locked">Unlock to participate</span>
                              {/if}
                            </div>
                          </div>
                        {/each}
                      {/if}
                      <!-- Add Action button -->
                      {#if identity?.isUnlocked}
                        {#if showCreateAction === initiative.id}
                          <div class="create-form action-create-form">
                            <select class="form-input" bind:value={newAction.action_type}>
                              <option value="written_comment">Write Comment</option>
                              <option value="attend_meeting">Attend Meeting</option>
                              <option value="public_comment">Public Comment</option>
                              <option value="contact_official">Contact Official</option>
                              <option value="signature">Sign Petition</option>
                              <option value="share">Share</option>
                              <option value="custom">Custom</option>
                            </select>
                            <input class="form-input" type="text" placeholder="What needs to be done?" bind:value={newAction.description} />
                            <input class="form-input" type="text" placeholder="Target (optional, e.g. City Council)" bind:value={newAction.target} />
                            <input class="form-input" type="date" placeholder="Deadline" bind:value={newAction.deadline} />
                            <div class="form-actions">
                              <button class="action-btn btn-commit" disabled={creatingAction || !newAction.description.trim()} onclick={() => handleCreateAction(initiative.id)}>
                                {creatingAction ? 'Adding...' : 'Add Action'}
                              </button>
                              <button class="action-btn btn-withdraw" onclick={() => { showCreateAction = null; }}>Cancel</button>
                            </div>
                          </div>
                        {:else}
                          <button class="add-action-btn" onclick={() => { showCreateAction = initiative.id; }}>
                            + Add Action
                          </button>
                        {/if}
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
        <div class="section-header static-header">
          <span class="section-title">My Commitments</span>
        </div>
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
            </div>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Community Pulse -->
    {#if pulseData.community_pulse && pulseData.community_pulse.total_issues}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('community')}>
          <span class="section-title">
            Community Issues
            <span class="count-badge">{pulseData.community_pulse.total_issues}</span>
          </span>
          <span class="chevron" class:open={expanded.community}></span>
        </button>
        {#if expanded.community}
          <div class="section-body">
            <div class="issue-stats">
              {#if pulseData.community_pulse.top_types}
                {#each Object.entries(pulseData.community_pulse.top_types) as [type, count]}
                  <div class="issue-type-row">
                    <span class="issue-type-name">{type}</span>
                    <span class="issue-type-count">{count}</span>
                  </div>
                {/each}
              {/if}
            </div>
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
            <div class="map-wrapper" bind:this={mapContainer}></div>
            <div class="map-legend">
              {#each Object.entries(ISSUE_COLORS).slice(0, -1) as [label, color]}
                <span class="legend-item">
                  <span class="legend-dot" style="background:{color}"></span>
                  {label}
                </span>
              {/each}
            </div>
            <div class="viz-stat">{issuePoints.length} issues mapped</div>
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
      {#if pulseData.clerk_email}
        <a href="mailto:{pulseData.clerk_email}" class="footer-link">Contact City Clerk</a>
      {/if}
      <span class="footer-ts">Updated {new Date(pulseData.generated_at).toLocaleTimeString()}</span>
    </footer>
  {/if}
</div>

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
  }

  /* === Header === */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #1e293b;
  }

  .header-left {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  h1 {
    font-size: 16px;
    font-weight: 700;
    color: #f8fafc;
    margin: 0;
  }

  .jurisdiction {
    font-size: 11px;
    color: #64748b;
  }

  .header-actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .icon-btn:hover { color: #e2e8f0; background: #1e293b; }
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
    background: #1e293b;
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
    color: #64748b;
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
  .tier-badge.easy { background: #1e3a5f; color: #60a5fa; }
  .tier-badge.private { background: #3b1f4b; color: #c084fc; }

  .lock-status {
    font-size: 10px;
    color: #ef4444;
  }
  .lock-status.unlocked { color: #22c55e; }

  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #64748b;
  }

  .link-btn {
    background: none;
    border: none;
    color: #6366f1;
    cursor: pointer;
    font-size: 12px;
    text-decoration: underline;
  }
  .link-btn:hover { color: #818cf8; }

  /* === Loading / Error states === */
  .loading-state {
    text-align: center;
    padding: 40px 16px;
    color: #94a3b8;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .pulse-anim {
    width: 32px;
    height: 32px;
    border: 2px solid #334155;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .error-state {
    text-align: center;
    padding: 32px 16px;
    color: #94a3b8;
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
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-retry:hover { background: #334155; }

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
    color: #e2e8f0;
    padding: 8px 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #1e293b;
  }
  .section-header:hover { color: #f8fafc; }

  .section-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .count-badge {
    background: #334155;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 500;
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
    border-top: 5px solid #64748b;
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }

  .section-body {
    padding: 4px 0 8px;
  }

  .empty-section {
    padding: 12px 8px;
    color: #475569;
    font-size: 12px;
    font-style: italic;
  }

  /* === Cards === */
  .card {
    background: #1e293b;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 6px;
  }

  .card-title {
    color: #f1f5f9;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #64748b;
    margin-top: 4px;
    flex-wrap: wrap;
  }

  .meta-sep { color: #475569; }

  .card-desc {
    color: #94a3b8;
    font-size: 12px;
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .card-top-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 11px;
    color: #64748b;
  }

  .item-number {
    color: #818cf8;
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
    background: #334155;
    color: #94a3b8;
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
  .outcome-icon.other { background: #334155; color: #94a3b8; }

  .decision-info { flex: 1; min-width: 0; }

  .outcome-label {
    font-weight: 500;
    text-transform: capitalize;
  }
  .outcome-label.passed { color: #4ade80; }
  .outcome-label.failed { color: #f87171; }
  .outcome-label.other { color: #94a3b8; }

  /* === Community Issues === */
  .issue-stats {
    padding: 4px 0;
  }

  .issue-type-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    font-size: 12px;
  }
  .issue-type-row:nth-child(odd) { background: #1e293b; border-radius: 4px; }

  .issue-type-name { color: #cbd5e1; }
  .issue-type-count { color: #64748b; font-variant-numeric: tabular-nums; }

  /* === Footer === */
  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid #1e293b;
    font-size: 10px;
    color: #475569;
  }

  .footer-link {
    color: #6366f1;
    text-decoration: none;
  }
  .footer-link:hover { text-decoration: underline; }

  /* === Provenance Panel === */
  .provenance-panel {
    background: #1e293b;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
    border: 1px solid #334155;
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
    color: #e2e8f0;
  }
  .prov-jurisdiction {
    font-size: 10px;
    color: #64748b;
  }
  .prov-stats {
    display: flex;
    gap: 4px;
    font-size: 11px;
    color: #94a3b8;
    margin-bottom: 8px;
  }
  .prov-corpora {
    border-top: 1px solid #334155;
    padding-top: 6px;
  }
  .corpus-row {
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 11px;
  }
  .corpus-name { color: #cbd5e1; }
  .corpus-count { color: #64748b; font-variant-numeric: tabular-nums; }
  .prov-freshness {
    border-top: 1px solid #334155;
    padding-top: 6px;
    margin-top: 6px;
    font-size: 10px;
    color: #475569;
  }
  .prov-loading {
    font-size: 11px;
    color: #64748b;
    padding: 8px 0;
  }

  .icon-btn.active { color: #818cf8; background: #1e293b; }

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
    color: #64748b;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover:not(:disabled) { color: #818cf8; background: #334155; }
  .cal-btn:disabled { opacity: 0.3; cursor: default; }

  .cal-dropdown {
    display: flex;
    gap: 8px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #334155;
  }
  .cal-option {
    font-size: 11px;
    color: #6366f1;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-decoration: none;
  }
  .cal-option:hover { color: #818cf8; text-decoration: underline; }

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
  .vc-watch { background: #334155; color: #94a3b8; }

  .voice-inline {
    color: #818cf8;
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
  .decision-toggle:hover .card-title { color: #818cf8; }

  .expand-chevron {
    display: inline-block;
    flex-shrink: 0;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #475569;
    transition: transform 0.15s ease;
    margin-left: 6px;
    margin-top: 6px;
  }
  .expand-chevron.open { transform: rotate(180deg); }

  .expanded-card {
    border: 1px solid #334155;
  }

  .decision-detail {
    border-top: 1px solid #334155;
    padding-top: 8px;
    margin-top: 8px;
  }
  .detail-loading {
    font-size: 11px;
    color: #64748b;
    padding: 4px 0;
  }
  .detail-body {
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.4;
    margin-bottom: 8px;
  }
  .detail-section {
    margin-bottom: 8px;
  }
  .detail-label {
    font-size: 10px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }
  .testimony-item {
    font-size: 11px;
    padding: 4px 0;
    border-bottom: 1px solid #1e293b;
  }
  .testimony-speaker {
    color: #cbd5e1;
    font-weight: 500;
    margin-right: 4px;
  }
  .testimony-speaker::after { content: ':'; }
  .testimony-text {
    color: #94a3b8;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .detail-more {
    font-size: 10px;
    color: #6366f1;
    margin-top: 4px;
  }
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
  .outcome-dot.other { background: #94a3b8; }
  .related-title { color: #cbd5e1; flex: 1; }
  .related-date { color: #475569; }
  .detail-empty {
    font-size: 11px;
    color: #475569;
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
    border-top: 1px solid #334155;
    padding-top: 8px;
    margin-top: 8px;
  }
  .voice-btn {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #334155;
    background: transparent;
    color: #94a3b8;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .voice-btn:hover:not(:disabled) {
    border-color: #475569;
    color: #e2e8f0;
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
    color: #64748b;
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
  .initiative-toggle:hover .card-title { color: #818cf8; }

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
    color: #818cf8;
    letter-spacing: 0.03em;
  }

  .initiative-status {
    font-size: 10px;
    color: #64748b;
    text-transform: capitalize;
  }

  .coord-link-label {
    font-size: 10px;
    color: #6366f1;
  }

  .coord-link {
    display: block;
    font-size: 11px;
    color: #6366f1;
    text-decoration: none;
    margin-bottom: 8px;
  }
  .coord-link:hover { text-decoration: underline; }

  .initiative-detail {
    border-top: 1px solid #334155;
    padding-top: 8px;
    margin-top: 8px;
  }

  /* === Action Cards (inside initiatives) === */
  .action-card {
    background: #0f172a;
    border-radius: 4px;
    padding: 8px 10px;
    margin-bottom: 6px;
    border: 1px solid #1e293b;
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
    color: #cbd5e1;
    line-height: 1.3;
    margin-bottom: 4px;
  }

  .action-target {
    font-size: 10px;
    color: #64748b;
    margin-bottom: 4px;
  }

  /* === Deadline Badges === */
  .deadline-badge {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .deadline-badge.normal { background: #334155; color: #94a3b8; }
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
    background: #334155;
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
    color: #64748b;
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
    font-size: 10px;
    padding: 3px 10px;
    border-radius: 10px;
    border: 1px solid #334155;
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
    color: #94a3b8;
    border-color: #47556940;
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
    border-top: 2px solid #334155;
    margin-top: 4px;
    padding-top: 4px;
  }

  .static-header {
    padding: 8px 4px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #e2e8f0;
    border-bottom: 1px solid #1e293b;
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
  .commitment-status.active { background: #1e3a5f; color: #60a5fa; }
  .commitment-status.done { background: #14532d; color: #4ade80; }

  /* === Section header with add button === */
  .section-header-row {
    display: flex;
    align-items: center;
  }
  .section-header-row .section-header {
    flex: 1;
  }

  .add-btn {
    background: none;
    border: 1px solid #334155;
    color: #818cf8;
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
  .add-btn:hover { background: #1e293b; border-color: #818cf8; }

  .add-action-btn {
    display: block;
    width: 100%;
    background: none;
    border: 1px dashed #334155;
    color: #64748b;
    font-size: 11px;
    padding: 6px;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 4px;
  }
  .add-action-btn:hover { color: #818cf8; border-color: #818cf8; }

  /* === Create forms === */
  .create-form {
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
  }
  .action-create-form {
    margin-top: 8px;
  }

  .form-input, .form-textarea {
    display: block;
    width: 100%;
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    font-size: 11px;
    padding: 5px 8px;
    border-radius: 4px;
    margin-bottom: 6px;
    font-family: inherit;
    box-sizing: border-box;
  }
  .form-input:focus, .form-textarea:focus {
    outline: none;
    border-color: #6366f1;
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
    color: #64748b;
    padding: 12px 0;
    text-align: center;
  }
  .viz-stat {
    font-size: 10px;
    color: #475569;
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
  .map-wrapper {
    height: 220px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid #334155;
  }
  .map-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 10px;
    margin-top: 6px;
    font-size: 10px;
    color: #94a3b8;
  }
  .legend-item {
    display: flex;
    align-items: center;
    gap: 3px;
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
    color: #e2e8f0;
  }
  .budget-year {
    font-size: 11px;
    color: #64748b;
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
    color: #cbd5e1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .budget-cat-amount {
    color: #64748b;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .budget-legend-more {
    font-size: 10px;
    color: #475569;
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
    color: #818cf8;
    background: none;
    border: 1px solid #4f46e540;
    border-radius: 4px;
    padding: 1px 8px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .summarize-btn:hover {
    background: #1e1b4b40;
    border-color: #6366f1;
    color: #a5b4fc;
  }

  /* === Ask AI Button === */
  .ask-ai-btn {
    display: block;
    width: 100%;
    margin-top: 8px;
    padding: 5px 0;
    font-size: 11px;
    font-weight: 500;
    color: #818cf8;
    background: #1e1b4b20;
    border: 1px dashed #4f46e540;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .ask-ai-btn:hover {
    background: #1e1b4b40;
    border-color: #6366f1;
    color: #a5b4fc;
  }

  /* === Toast === */
  .toast {
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: #1e293b;
    color: #e2e8f0;
    font-size: 12px;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid #334155;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    z-index: 100;
    animation: toast-in 0.2s ease;
  }
  @keyframes toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
</style>

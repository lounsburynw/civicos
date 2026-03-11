<script lang="ts">
  import CivicInitiativeCard from './CivicInitiativeCard.svelte';

  // Local type declarations (mirrors @civicos/client types)
  interface Initiative {
    id: string;
    topic: string;
    title: string;
    description: string;
    coordination_url?: string;
    voice_count: number;
    creator_attested?: boolean;
    attested_voice_count?: number;
    timestamp?: string;
  }

  interface CivicAction {
    id: string;
    action_type: string;
    description: string;
    target?: string;
    deadline?: string;
    template?: string;
  }

  interface CivicActionProgress {
    commitment_count: number;
    completion_count: number;
    target_count?: number;
    progress_percent?: number;
  }

  // --- Props (shared state from parent) ---

  let {
    api = null as any,
    session = null as any,
    identity = null as { publicKey: string; isUnlocked?: boolean } | null,
    jurisdiction = '',
    level = 'city' as 'city' | 'state' | 'federal',
    // Callbacks to parent
    ontoast = undefined as ((message: string) => void) | undefined,
    onunlock = undefined as ((password: string) => Promise<boolean>) | undefined,
    oninitiativesloaded = undefined as ((items: Initiative[]) => void) | undefined,
  } = $props();

  // --- Internal state ---

  // Initiative data
  let initiatives: Initiative[] = $state([]);
  let initiativesLoading = $state(false);
  let expandedInitiatives = $state(new Set<string>());
  let initiativeActions = $state(new Map<string, CivicAction[]>());
  let actionProgress = $state(new Map<string, CivicActionProgress>());
  let actionsLoading = $state(new Set<string>());

  // AI draft state (create form)
  let formDraftLoading = $state(false);

  // Commitment tracking (persisted via chrome.storage)
  let committedActions = $state(new Set<string>());
  let completedActions = $state(new Set<string>());
  let actionInProgress = $state(new Set<string>());
  let committedActionMeta = $state(new Map<string, { action_type: string; description: string; deadline?: string }>());
  const COMMITMENTS_STORAGE_KEY = 'civicos_user_commitments';
  const COMPLETIONS_STORAGE_KEY = 'civicos_user_completions';
  const COMMITMENT_META_STORAGE_KEY = 'civicos_commitment_meta';

  // --- Topic filtering ---

  let availableTopics = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const ini of initiatives) {
      if (ini.topic) {
        const t = ini.topic.charAt(0).toUpperCase() + ini.topic.slice(1);
        counts.set(t, (counts.get(t) || 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);
  });

  let selectedTopics = $state(new Set<string>());

  function toggleTopicFilter(topic: string) {
    if (selectedTopics.has(topic)) {
      selectedTopics.delete(topic);
    } else {
      selectedTopics.add(topic);
    }
    selectedTopics = new Set(selectedTopics);
  }

  let filteredInitiatives = $derived.by(() => {
    if (selectedTopics.size === 0) return initiatives;
    return initiatives.filter(i => {
      if (!i.topic) return false;
      const normalized = i.topic.charAt(0).toUpperCase() + i.topic.slice(1);
      return selectedTopics.has(normalized);
    });
  });

  // Section expand state (owned)
  let initiativesExpanded = $state(true);

  // Inline unlock (within create forms)
  let unlockPassword = $state('');
  let unlocking = $state(false);
  let unlockError: string | null = $state(null);

  // Create initiative form
  let showCreateInitiative = $state(false);
  let newInitiative = $state({ topic: '', title: '', description: '', coordination_url: '' });
  let creatingInitiative = $state(false);
  let customTopic = $state('');
  const CITY_TOPICS = ['Traffic Safety', 'Housing', 'Parks', 'Budget', 'Environment', 'Public Safety', 'Infrastructure', 'Education'];
  const PARENT_TOPICS = ['Healthcare', 'Housing', 'Education', 'Environment', 'Budget', 'Public Safety', 'Transportation', 'Labor'];
  let INITIATIVE_TOPICS = $derived(level === 'city' ? CITY_TOPICS : PARENT_TOPICS);
  let sectionTitle = $derived(level === 'city' ? 'Community Initiatives' : 'Civic Initiatives');

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
  let showCreateAction: string | null = $state(null);
  let newAction = $state({ action_type: 'written_comment', description: '', target: '', deadline: '', template: '', deadlineContext: '', targetCount: null as number | null });
  let creatingAction = $state(false);

  // Dynamic config per action type
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
  const DRAFTABLE_TYPES = new Set(['written_comment', 'public_comment', 'contact_official']);

  // --- Drag-to-AI ---

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  let draggingId = $state<string | null>(null);

  function composeInitiativeContext(initiative: Initiative): string {
    const actions = initiativeActions.get(initiative.id) ?? [];
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || 'my city';
    const lines = [
      `--- CivicOS Context: Community Initiative ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${initiative.title}**`,
      `Topic: ${initiative.topic}`,
      `Supporters: ${initiative.voice_count}`,
    ];
    if (initiative.attested_voice_count) {
      lines.push(`Verified supporters: ${initiative.attested_voice_count}`);
    }
    lines.push('', initiative.description);
    if (actions.length > 0) {
      lines.push('', `### Actions (${actions.length})`);
      for (const a of actions) {
        const progress = actionProgress.get(a.id);
        let line = `- **${actionTypeLabel(a.action_type)}**: ${a.description}`;
        if (a.deadline) line += ` (deadline: ${a.deadline})`;
        if (progress) line += ` — ${progress.commitment_count} committed, ${progress.completion_count} completed`;
        lines.push(line);
      }
    }
    if (initiative.coordination_url) {
      lines.push('', `Coordination: ${initiative.coordination_url}`);
    }
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What advice would you give to someone wanting to support this initiative? What are the most effective actions they could take?');
    return lines.join('\n');
  }

  function handleDragStart(e: DragEvent, initiative: Initiative) {
    const markdown = composeInitiativeContext(initiative);
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    draggingId = initiative.id;
  }

  function handleDragEnd() {
    draggingId = null;
  }

  // --- Initiative Loading ---

  async function loadInitiatives() {
    initiativesLoading = true;
    try {
      initiatives = await api.getInitiatives(jurisdiction);
      oninitiativesloaded?.(initiatives);
      loadAllActionStats();
    } catch {
      initiatives = [];
    }
    initiativesLoading = false;
  }

  async function loadAllActionStats() {
    const toLoad = initiatives.filter(ini => !initiativeActions.has(ini.id));
    if (toLoad.length === 0) return;
    const details = await session.loadAllInitiativeDetails(toLoad);
    for (const [iniId, detail] of details) {
      initiativeActions.set(iniId, detail.actions);
      for (const [actionId, progress] of detail.progress) {
        actionProgress.set(actionId, progress);
      }
    }
    initiativeActions = new Map(initiativeActions);
    actionProgress = new Map(actionProgress);
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
        const detail = await session.loadInitiativeDetail(initiativeId);
        initiativeActions.set(initiativeId, detail.actions);
        initiativeActions = new Map(initiativeActions);
        for (const [actionId, progress] of detail.progress) {
          actionProgress.set(actionId, progress);
        }
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

  // --- Aggregate Stats ---

  function aggregateStats(): { committed: number; completed: number } {
    let committed = 0, completed = 0;
    for (const p of actionProgress.values()) {
      committed += p.commitment_count;
      completed += p.completion_count;
    }
    return { committed, completed };
  }

  // --- Commitment Persistence ---

  async function loadCommitments() {
    try {
      const storage = (globalThis as any).chrome?.storage?.local;
      if (!storage) return;
      const result = await storage.get([COMMITMENTS_STORAGE_KEY, COMPLETIONS_STORAGE_KEY, COMMITMENT_META_STORAGE_KEY]);
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
      const storage = (globalThis as any).chrome?.storage?.local;
      if (!storage) return;
      const metaObj: Record<string, { action_type: string; description: string; deadline?: string }> = {};
      committedActionMeta.forEach((v, k) => { metaObj[k] = v; });
      await storage.set({
        [COMMITMENTS_STORAGE_KEY]: [...committedActions],
        [COMPLETIONS_STORAGE_KEY]: [...completedActions],
        [COMMITMENT_META_STORAGE_KEY]: metaObj,
      });
    } catch {
      // Ignore persist errors
    }
  }

  // --- Action Handlers ---

  async function handleCommit(action: CivicAction) {
    if (actionInProgress.has(action.id)) return;
    if (!identity?.isUnlocked) return;

    actionInProgress.add(action.id);
    actionInProgress = new Set(actionInProgress);

    try {
      const result = await api.castCommitment(action.id, jurisdiction);
      if (!result.ok) {
        const msg = result.rejection?.reason.includes('rate limit')
          ? 'Daily action limit reached. Try again tomorrow.'
          : result.rejection ? 'Action not accepted — verification may be required.' : 'Failed to commit. Relay may be unreachable.';
        ontoast?.(msg);
        actionInProgress.delete(action.id);
        actionInProgress = new Set(actionInProgress);
        return;
      }

      committedActions.add(action.id);
      committedActions = new Set(committedActions);
      committedActionMeta.set(action.id, { action_type: action.action_type, description: action.description, deadline: action.deadline });
      committedActionMeta = new Map(committedActionMeta);
      persistCommitments();

      const prev = actionProgress.get(action.id);
      if (prev) {
        actionProgress.set(action.id, { ...prev, commitment_count: prev.commitment_count + 1 });
        actionProgress = new Map(actionProgress);
      }
      ontoast?.('Committed!');
    } catch (err) {
      ontoast?.(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
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
      const result = await api.castCompletion(action.id, jurisdiction);
      if (!result.ok) {
        const msg = result.rejection?.reason.includes('rate limit')
          ? 'Daily action limit reached. Try again tomorrow.'
          : result.rejection ? 'Action not accepted — verification may be required.' : 'Failed to mark action complete. Relay may be unreachable.';
        ontoast?.(msg);
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
      ontoast?.('Marked complete!');
    } catch (err) {
      ontoast?.(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
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
      const result = await api.castWithdrawal(action.id);
      if (!result.ok) {
        const msg = result.rejection?.reason.includes('rate limit')
          ? 'Daily action limit reached. Try again tomorrow.'
          : result.rejection ? 'Withdrawal not accepted — verification may be required.' : 'Failed to withdraw. Relay may be unreachable.';
        ontoast?.(msg);
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
      ontoast?.('Withdrawn');
    } catch (err) {
      ontoast?.(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }

    actionInProgress.delete(action.id);
    actionInProgress = new Set(actionInProgress);
  }

  // --- AI Draft Generation ---

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
        ontoast?.('Failed to generate draft');
      }
    } catch {
      ontoast?.('Draft generation error');
    }
    formDraftLoading = false;
  }

  // --- Create Handlers ---

  async function handleCreateInitiative() {
    if (creatingInitiative || !identity?.isUnlocked) return;
    const topic = effectiveTopic();
    if (!topic || !newInitiative.title.trim() || !newInitiative.description.trim()) return;

    creatingInitiative = true;
    try {
      const created = await api.castInitiative(
        jurisdiction,
        topic,
        newInitiative.title.trim(),
        newInitiative.description.trim(),
        newInitiative.coordination_url.trim() || undefined,
      );
      if (created) {
        initiatives = [created, ...initiatives];
        showCreateInitiative = false;
        newInitiative = { topic: '', title: '', description: '', coordination_url: '' };
        customTopic = '';
        ontoast?.('Initiative created!');
      } else {
        ontoast?.('Failed to create initiative. Relay may be unreachable.');
      }
    } catch (err) {
      ontoast?.(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }
    creatingInitiative = false;
  }

  async function handleCreateAction(initiativeId: string) {
    if (creatingAction || !identity?.isUnlocked) return;
    if (!newAction.description.trim()) return;

    creatingAction = true;
    try {
      const created = await api.castCivicAction(
        initiativeId,
        newAction.action_type,
        newAction.description.trim(),
        {
          target: newAction.target.trim() || undefined,
          deadline: newAction.deadline || undefined,
          targetCount: newAction.targetCount ?? undefined,
          template: newAction.template.trim() || undefined,
          deadlineContext: newAction.deadlineContext.trim() || undefined,
        },
      );
      if (created) {
        const existing = initiativeActions.get(initiativeId) || [];
        initiativeActions.set(initiativeId, [...existing, created]);
        initiativeActions = new Map(initiativeActions);
        showCreateAction = null;
        newAction = { action_type: 'written_comment', description: '', target: '', deadline: '', template: '', deadlineContext: '', targetCount: null };
        ontoast?.('Action created!');
      } else {
        ontoast?.('Failed to create action. Relay may be unreachable.');
      }
    } catch (err) {
      ontoast?.(`Error: ${err instanceof Error ? err.message : 'unknown'}`);
    }
    creatingAction = false;
  }

  // --- Inline Unlock ---

  async function handleUnlock() {
    if (!unlockPassword || !onunlock) return;
    unlocking = true;
    unlockError = null;
    const success = await onunlock(unlockPassword);
    if (!success) {
      unlockError = 'Wrong password';
    }
    unlockPassword = '';
    unlocking = false;
  }

  // --- Deadline Helpers ---

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

  // --- Calendar Helpers (for My Commitments) ---

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

  // --- Public API ---

  export function expandAndScrollTo(initiativeId: string) {
    initiativesExpanded = true;
    requestAnimationFrame(() => {
      const el = document.getElementById(`ini-${initiativeId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ini-highlighted');
        setTimeout(() => el.classList.remove('ini-highlighted'), 2000);
      }
    });
  }

  // --- Load on mount ---
  loadInitiatives();
  loadCommitments();
</script>

<!-- Community Initiatives -->
<section class="feed-section ini">
  <button class="section-header" onclick={() => { initiativesExpanded = !initiativesExpanded; }}>
    <span class="section-title">
      {sectionTitle}
      {#if initiatives.length > 0}
        <span class="ini-count">{initiatives.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={initiativesExpanded}></span>
  </button>
  {#if initiativesExpanded}
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
          <div class="ini-hint">Set up identity in Options to sign initiatives.</div>
        {:else if !identity.isUnlocked && onunlock}
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
        {#if availableTopics.length > 0}
          <div class="topic-filters">
            {#each availableTopics as topic}
              <button
                class="topic-filter-pill"
                class:active={selectedTopics.has(topic)}
                onclick={() => toggleTopicFilter(topic)}
              >{topic}</button>
            {/each}
            {#if selectedTopics.size > 0}
              <button class="topic-filter-clear" onclick={() => { selectedTopics = new Set(); }}>Clear</button>
            {/if}
          </div>
        {/if}
        {#each filteredInitiatives as initiative}
          <div class="ini-card" id="ini-{initiative.id}"
               class:ini-card-expanded={expandedInitiatives.has(initiative.id)}
               class:dragging={draggingId === initiative.id}
               draggable="true"
               ondragstart={(e: DragEvent) => handleDragStart(e, initiative)}
               ondragend={handleDragEnd}>
            <CivicInitiativeCard
              {initiative}
              expanded={expandedInitiatives.has(initiative.id)}
              actions={initiativeActions.get(initiative.id) ?? []}
              actionsLoading={actionsLoading.has(initiative.id)}
              actionProgress={Object.fromEntries(actionProgress)}
              committedActionIds={[...committedActions]}
              completedActionIds={[...completedActions]}
              actionInProgressIds={[...actionInProgress]}
              isUnlocked={identity?.isUnlocked ?? false}
              hasIdentity={!!identity}
              showAddAction={showCreateAction !== initiative.id}
              ontoggle={() => toggleInitiativeDetail(initiative.id)}
              oncommit={({ actionId }: { actionId: string }) => {
                const action = (initiativeActions.get(initiative.id) ?? []).find(a => a.id === actionId);
                if (action) handleCommit(action);
              }}
              oncomplete={({ actionId }: { actionId: string }) => {
                const action = (initiativeActions.get(initiative.id) ?? []).find(a => a.id === actionId);
                if (action) handleComplete(action);
              }}
              onwithdraw={({ actionId }: { actionId: string }) => {
                const action = (initiativeActions.get(initiative.id) ?? []).find(a => a.id === actionId);
                if (action) handleWithdraw(action);
              }}
              oncopytemplate={async ({ template }: { template: string }) => {
                await navigator.clipboard.writeText(template);
                ontoast?.('Copied to clipboard');
              }}
              onaddaction={() => { showCreateAction = initiative.id; }}
            />
            {#if expandedInitiatives.has(initiative.id) && showCreateAction === initiative.id}
              {@const actionConfig = ACTION_TYPE_CONFIG[newAction.action_type] || DEFAULT_ACTION_CONFIG}
              <div class="ini-form ini-action-form" class:ini-drafting={formDraftLoading}>
                {#if identity && !identity.isUnlocked && onunlock}
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
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>


<style>
  /* --- Topic Filter Pills --- */
  .topic-filters {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    padding: 4px 0 8px;
  }
  .topic-filter-pill {
    padding: 3px 8px;
    border-radius: 10px;
    border: 1px solid var(--civic-border-input);
    background: transparent;
    color: var(--civic-text-dim);
    font-size: 10px;
    font-weight: 500;
    cursor: pointer;
    transition: all 150ms;
    font-family: inherit;
  }
  .topic-filter-pill:hover {
    color: var(--civic-text-muted);
    border-color: var(--civic-text-disabled);
  }
  .topic-filter-pill.active {
    background: var(--civic-accent-primary-bg-badge);
    border-color: var(--civic-accent-primary-border-testimony);
    color: var(--civic-accent-primary-light);
  }
  .topic-filter-clear {
    padding: 3px 8px;
    border-radius: 10px;
    border: none;
    background: none;
    color: var(--civic-text-disabled);
    font-size: 10px;
    cursor: pointer;
    font-family: inherit;
  }
  .topic-filter-clear:hover { color: var(--civic-text-dim); }

  /* === Section Layout (matches SidePanel patterns) === */
  .feed-section {
    margin-bottom: 2px;
  }
  .section-header {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 4px;
    background: none;
    border: none;
    border-bottom: 1px solid var(--civic-surface-elevated);
    color: var(--civic-text-muted);
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .section-header:hover { color: var(--civic-text-body); }
  .section-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .chevron {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid var(--civic-text-disabled);
    transition: transform 0.15s ease;
    flex-shrink: 0;
  }
  .chevron.open {
    transform: rotate(180deg);
  }
  .section-body {
    padding: 6px 0;
  }
  .ini-count {
    background: var(--civic-overlay-subtle);
    color: var(--civic-text-dim);
    font-size: 9px;
    font-weight: 600;
    padding: 1px 5px;
    border-radius: 6px;
  }

  /* === Initiative Toolbar === */
  .ini-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 4px;
  }
  .ini-new-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 500;
    color: var(--civic-text-muted);
    background: none;
    border: 1px solid var(--civic-overlay-light);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .ini-new-btn:hover {
    background: var(--civic-overlay-subtle);
    border-color: var(--civic-overlay-medium);
    color: var(--civic-text-body);
  }
  .ini-aggregate-stats {
    display: flex;
    gap: 8px;
    font-size: 10px;
    color: var(--civic-text-dim);
  }
  .agg-stat { color: var(--civic-text-muted); }
  .agg-completed { color: var(--civic-status-success-light); }

  /* === Initiative Cards (wrapper) === */
  .ini-card {
    background: var(--civic-surface-card);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 4px;
    border: 1px solid var(--civic-surface-elevated);
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: grab;
  }
  .ini-card:hover { border-color: var(--civic-border-default); }
  .ini-card:active { cursor: grabbing; }
  .ini-card.dragging { opacity: 0.4; border-color: var(--civic-text-disabled); }
  .ini-card-expanded { border-color: var(--civic-border-default); }
  :global(.ini-highlighted) {
    box-shadow: inset 0 0 0 1px var(--civic-overlay-medium);
    transition: box-shadow 0.3s ease;
  }

  .ini-empty {
    font-size: 12px;
    color: var(--civic-text-dim);
    padding: 12px 4px;
    text-align: center;
  }
  .ini-start-link {
    background: none;
    border: none;
    color: var(--civic-text-muted);
    cursor: pointer;
    font-size: 12px;
    padding: 0;
    text-decoration: underline;
  }
  .ini-start-link:hover { color: var(--civic-text-body); }

  /* === Create Forms === */
  .ini-form {
    background: var(--civic-surface-card-alt);
    border: 1px solid var(--civic-surface-elevated);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 8px;
  }
  .ini-form-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .ini-form-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--civic-text-secondary);
  }
  .ini-form-close {
    background: none;
    border: none;
    color: var(--civic-text-dim);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .ini-form-close:hover { color: var(--civic-text-body); background: var(--civic-hover-bg); }
  .ini-field-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: var(--civic-text-muted);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .ini-optional { font-weight: 400; color: var(--civic-text-dim); }
  .ini-char-hint { font-size: 10px; font-weight: 400; color: var(--civic-text-dim); text-align: right; }
  .ini-hint {
    font-size: 11px;
    color: var(--civic-status-warning);
    margin-bottom: 8px;
    padding: 6px 8px;
    background: var(--civic-status-warning-bg-subtle);
    border-radius: 4px;
    border: 1px solid var(--civic-status-warning-bg-subtle);
  }
  .ini-error {
    font-size: 11px;
    color: var(--civic-status-error-light);
    margin-top: 4px;
    padding: 4px 8px;
    background: var(--civic-status-error-bg)20;
    border-radius: 4px;
  }
  .ini-input, .ini-textarea {
    display: block;
    width: 100%;
    background: transparent;
    border: 1px solid var(--civic-border-default);
    color: var(--civic-text-primary);
    font-size: 13px;
    padding: 6px 8px;
    border-radius: 4px;
    margin-top: 4px;
    margin-bottom: 2px;
    font-family: inherit;
    box-sizing: border-box;
  }
  .ini-input:focus, .ini-textarea:focus { border-color: var(--civic-text-dim); outline: none; }
  .ini-textarea { resize: vertical; min-height: 48px; }
  select.ini-input { appearance: auto; cursor: pointer; }

  .ini-field {
    position: relative;
  }
  .ini-char-count {
    position: absolute;
    bottom: 6px;
    right: 8px;
    font-size: 10px;
    color: var(--civic-text-disabled);
  }
  .ini-char-count.near-limit { color: var(--civic-status-error-dark); }

  /* === Topic Chips === */
  .ini-topic-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
    margin-bottom: 4px;
  }
  .ini-chip {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 12px;
    border: 1px solid var(--civic-border-default);
    background: transparent;
    color: var(--civic-text-muted);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .ini-chip:hover { border-color: var(--civic-text-disabled); color: var(--civic-text-body); }
  .ini-chip.active { background: var(--civic-overlay-light); border-color: var(--civic-text-muted); color: var(--civic-text-secondary); }

  /* === Form Actions === */
  .ini-form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 10px;
  }
  .ini-btn-primary {
    font-size: 13px;
    font-weight: 500;
    padding: 6px 16px;
    border-radius: 6px;
    background: var(--civic-overlay-light);
    color: var(--civic-text-secondary);
    border: 1px solid var(--civic-overlay-medium);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .ini-btn-primary:hover:not(:disabled) { background: var(--civic-overlay-medium); border-color: var(--civic-overlay-highlight); }
  .ini-btn-primary:disabled { opacity: 0.4; cursor: default; }
  .ini-btn-cancel {
    font-size: 13px;
    padding: 6px 16px;
    border-radius: 6px;
    background: transparent;
    color: var(--civic-text-muted);
    border: 1px solid var(--civic-border-default);
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .ini-btn-cancel:hover { border-color: var(--civic-text-disabled); color: var(--civic-text-body); }
  .ini-btn-sm { padding: 5px 12px; font-size: 12px; }

  /* === AI Draft Button === */
  .ini-btn-draft {
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    background: var(--civic-ai-bg-subtle);
    color: var(--civic-ai-accent);
    border: 1px solid var(--civic-ai-border-blockquote);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    margin-bottom: 6px;
  }
  .ini-btn-draft:hover:not(:disabled) { background: var(--civic-ai-border-medium); border-color: var(--civic-ai-border-accept); }
  .ini-btn-draft:disabled { opacity: 0.5; cursor: default; }

  .ini-action-form { margin-top: 4px; padding: 12px; }
  .ini-drafting {
    position: relative;
    opacity: 0.7;
  }
  .ini-drafting::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--civic-ai-accent), transparent);
    animation: draft-pulse 1.5s ease-in-out infinite;
    border-radius: 8px 8px 0 0;
  }
  @keyframes draft-pulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 1; }
  }

  /* === Unlock Inline === */
  .unlock-inline {
    margin-bottom: 8px;
  }
  .unlock-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

</style>

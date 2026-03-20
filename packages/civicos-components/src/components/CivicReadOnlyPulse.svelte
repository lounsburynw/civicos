<script lang="ts">
  import CivicMeetingCard from './CivicMeetingCard.svelte';
  import CivicProcessBar from './CivicProcessBar.svelte';
  import CivicVoiceButtons from './CivicVoiceButtons.svelte';
  import CivicCommentThread from './CivicCommentThread.svelte';
  import { outcomeIcon, outcomeClass, formatRelativeDate, googleCalendarUrl, downloadIcs, computeCityFocalMeetings, urgencyClass as urgencyClassFn, meetingDaysUntil as meetingDaysUntilFn, classifyTopics } from '../utils/civic-helpers.js';

  type Stance = 'support' | 'oppose' | 'watching';

  type VoiceCounts = {
    support: number;
    oppose: number;
    watching: number;
    total: number;
  };

  type PulseData = {
    decisions_this_week: Array<{ title: string; date: string; time: string; location: string; meeting_datetime: string }>;
    upcoming_items?: Array<{ id?: string; title: string; meeting_title?: string; project_type?: string; description?: string; summary?: string; status?: string; official_url?: string }>;
    recent_outcomes: Array<{ id?: string; title: string; date: string; outcome: string; is_upcoming?: boolean; summary?: string; official_url?: string }>;
    generated_at: string;
    comment_periods?: Array<{ document_number: string; title: string; abstract?: string; agency_names: string[]; comments_close_on: string; comment_url?: string; html_url?: string; days_remaining: number; document_type?: string; topics?: string[]; pdf_url?: string; publication_date?: string }>;
    upcoming_hearings?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string; description?: string; summary?: string; official_url?: string; days_until: number }>;
    governors_desk?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; summary?: string; enrolled_date?: string }>;
  };

  interface Comment {
    entity: string;
    comment_text: string;
    public_key: string;
    signature: string;
    timestamp: string;
    jurisdiction?: string;
    stance?: string;
    deleted: boolean;
    attested?: boolean;
  }

  interface CommentCounts {
    entity: string;
    count: number;
    attested?: number;
    unattested?: number;
  }

  interface CommentSynthesis {
    entity_id: string;
    total: number;
    support: number;
    oppose: number;
    neutral: number;
  }

  type JurisdictionLevel = 'federal' | 'state' | 'city' | string;
  type IdentityInfo = { publicKey?: string; isUnlocked?: boolean } | null;

  import type { Snippet } from 'svelte';

  let {
    data,
    showCalendar = false,
    level = 'city',
    jurisdiction = '',
    voiceCounts = new Map<string, VoiceCounts>(),
    userStances = new Map<string, Stance>(),
    votingInProgress = new Set<string>(),
    identity = null as IdentityInfo,
    commentCounts: parentCommentCounts = new Map<string, CommentCounts>(),
    synthData: parentSynthData = new Map<string, CommentSynthesis>(),
    session = null as any,
    api = null as any,
    aiAvailable = false,
    activeProviderName = '',
    renderMarkdown = (text: string) => text,
    onvoice,
    ontoast,
    oncommentcountchange,
    onopenexternalai,
    children,
  }: {
    data: PulseData;
    showCalendar?: boolean;
    level?: JurisdictionLevel;
    jurisdiction?: string;
    voiceCounts?: Map<string, VoiceCounts>;
    userStances?: Map<string, Stance>;
    votingInProgress?: Set<string>;
    identity?: IdentityInfo;
    commentCounts?: Map<string, CommentCounts>;
    synthData?: Map<string, CommentSynthesis>;
    session?: any;
    api?: any;
    aiAvailable?: boolean;
    activeProviderName?: string;
    renderMarkdown?: (text: string) => string;
    onvoice?: (detail: { entityId: string; stance: Stance }) => void;
    ontoast?: (message: string) => void;
    oncommentcountchange?: (entityId: string, counts: CommentCounts) => void;
    onopenexternalai?: (detail: { context: string; event: MouseEvent }) => void;
    children?: Snippet;
  } = $props();

  function billEntityId(id: string): string {
    return `bill:${id}`;
  }

  const isLegislative = $derived(level === 'state' || level === 'federal');
  const meetingsLabel = $derived(isLegislative ? 'Active Topics' : 'Meetings');
  const itemsLabel = $derived(isLegislative ? 'Key Legislation' : 'Agenda Items');
  const outcomesLabel = $derived(isLegislative ? 'Bill Activity' : 'Recent Outcomes');
  const emptyMeetings = $derived(isLegislative ? 'No tracked topics' : 'No upcoming meetings');
  const emptyItems = $derived(isLegislative ? 'No actionable legislation' : 'No upcoming agenda items');
  const emptyOutcomes = $derived(isLegislative ? 'No tracked bills' : 'No recent outcomes');

  // --- Drag-to-AI ---

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  let draggingId = $state<string | null>(null);
  let shakingCardId = $state<string | null>(null);
  let expandedAbstracts = $state(new Set<string>());

  function truncate(text: string, max: number): string {
    if (text.length <= max) return text;
    return text.slice(0, max).replace(/\s+\S*$/, '') + '...';
  }

  function groupVotesByMember(votes: Array<{ member_name: string; [key: string]: unknown }>): Record<string, typeof votes> {
    const groups: Record<string, typeof votes> = {};
    for (const v of votes) {
      const name = v.member_name || 'Unknown';
      if (!groups[name]) groups[name] = [];
      groups[name].push(v);
    }
    return groups;
  }

  function composeLegislationContext(item: { id?: string; title: string; meeting_title?: string; status?: string; summary?: string; description?: string; official_url?: string }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || level || 'legislation';
    const lines = [
      `--- CivicOS Context: Legislation ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${item.title}**`,
    ];
    if (item.meeting_title) lines.push(`Committee: ${item.meeting_title}`);
    if (item.status) lines.push(`Status: ${item.status}`);
    if (item.id) {
      const eid = billEntityId(item.id);
      const counts = voiceCounts.get(eid);
      if (counts && counts.total > 0) {
        lines.push(`Community voices: ${counts.support} support, ${counts.oppose} oppose, ${counts.watching} watching`);
      }
    }
    if (item.summary) lines.push('', item.summary);
    if (item.description) lines.push('', `Why it matters: ${item.description}`);
    if (item.official_url) lines.push('', `Official text: ${item.official_url}`);
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What are the key implications? Who does this affect and how?');
    return lines.join('\n');
  }

  function composeOutcomeContext(outcome: { id?: string; title: string; date: string; outcome: string; summary?: string; official_url?: string }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || level || 'legislation';
    const lines = [
      `--- CivicOS Context: Legislative Outcome ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${outcome.title}**`,
      `Outcome: ${outcome.outcome.replace(/_/g, ' ')}`,
      `Date: ${outcome.date}`,
    ];
    if (outcome.summary) lines.push('', outcome.summary);
    if (outcome.official_url) lines.push('', `Official text: ${outcome.official_url}`);
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What does this mean going forward? What are the implications?');
    return lines.join('\n');
  }

  function composeMeetingContext(meeting: { title: string; date: string; time: string; location: string }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || 'my city';
    const lines = [
      `--- CivicOS Context: Meeting ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${meeting.title}**`,
      `Date: ${meeting.date}`,
    ];
    if (meeting.time) lines.push(`Time: ${meeting.time}`);
    if (meeting.location) lines.push(`Location: ${meeting.location}`);
    const meetingItems = (data.upcoming_items || []).filter(item => item.meeting_title === meeting.title);
    if (meetingItems.length > 0) {
      lines.push('', `Known agenda items (${meetingItems.length}):`);
      for (const item of meetingItems) {
        let line = `- ${item.title}`;
        if (item.project_type) line += ` [${item.project_type}]`;
        lines.push(line);
      }
    }
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What should I know about this meeting? What topics are likely on the agenda?');
    return lines.join('\n');
  }

  function handleDragStart(e: DragEvent, markdown: string, id: string) {
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    draggingId = id;
  }

  function handleDragEnd() {
    draggingId = null;
  }

  const hasCommentPeriods = $derived((data.comment_periods ?? []).length > 0);
  const hasHearings = $derived((data.upcoming_hearings ?? []).length > 0);
  const hasGovernorsDesk = $derived((data.governors_desk ?? []).length > 0);
  const hasCongressionalVotes = $derived((data.congressional_votes ?? []).length > 0);

  // Reference time for relative date calculations (uses data timestamp for consistency with mock data)
  const referenceTime = $derived(data.generated_at ? new Date(data.generated_at) : new Date());

  // City focal points: meetings happening within 7 days (uses shared utility)
  const cityFocalMeetings = $derived(
    !isLegislative
      ? computeCityFocalMeetings(data.decisions_this_week, data.upcoming_items || [], referenceTime)
      : []
  );
  const hasCityFocal = $derived(cityFocalMeetings.length > 0);
  const hasFocalPoints = $derived(hasCommentPeriods || hasHearings || hasGovernorsDesk || hasCongressionalVotes || hasCityFocal);

  // --- Topic Classification & Filtering ---

  // Classify topics for each item type. Comment periods use API-provided topics; all others are auto-classified.
  type TopicEntry = { id: string; topics: string[] };

  let allItemTopics = $derived.by(() => {
    const entries: TopicEntry[] = [];
    for (const p of data.comment_periods ?? []) {
      entries.push({ id: p.document_number, topics: p.topics ?? classifyTopics(p.title, p.abstract) });
    }
    for (const h of data.upcoming_hearings ?? []) {
      entries.push({ id: h.bill_id, topics: classifyTopics(h.bill_name || h.bill_number || '', h.summary || h.description) });
    }
    for (const b of data.governors_desk ?? []) {
      entries.push({ id: b.bill_id, topics: classifyTopics(b.bill_name || b.bill_number || '', b.summary) });
    }
    for (const i of data.upcoming_items ?? []) {
      entries.push({ id: i.id || i.title, topics: classifyTopics(i.title, i.summary || i.description) });
    }
    for (const o of data.recent_outcomes) {
      entries.push({ id: o.id || o.title, topics: classifyTopics(o.title, o.summary) });
    }
    return new Map(entries.map(e => [e.id, e.topics]));
  });

  let availableTopics = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const topics of allItemTopics.values()) {
      for (const t of topics) {
        counts.set(t, (counts.get(t) || 0) + 1);
      }
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);
  });

  let selectedTopics = $state(new Set<string>());

  function toggleTopic(topic: string) {
    if (selectedTopics.has(topic)) {
      selectedTopics.delete(topic);
    } else {
      selectedTopics.add(topic);
    }
    selectedTopics = new Set(selectedTopics);
  }

  function topicsMatch(id: string): boolean {
    if (selectedTopics.size === 0) return true;
    const topics = allItemTopics.get(id) || [];
    return topics.some(t => selectedTopics.has(t));
  }

  function getTopics(id: string): string[] {
    return allItemTopics.get(id) || [];
  }

  let filteredCommentPeriods = $derived((data.comment_periods ?? []).filter(p => topicsMatch(p.document_number)));
  let filteredHearings = $derived((data.upcoming_hearings ?? []).filter(h => topicsMatch(h.bill_id)));
  let filteredGovernorsDesk = $derived((data.governors_desk ?? []).filter(b => topicsMatch(b.bill_id)));
  let filteredItems = $derived((data.upcoming_items ?? []).filter(i => topicsMatch(i.id || i.title)));
  let filteredOutcomes = $derived(data.recent_outcomes.filter(o => topicsMatch(o.id || o.title)));

  // --- Focal Point Context Composers (Drag-to-AI) ---

  function composeCommentPeriodContext(period: { document_number: string; title: string; abstract?: string; agency_names: string[]; comments_close_on: string; comment_url?: string; html_url?: string; days_remaining: number }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const lines = [
      `--- CivicOS Context: Federal Comment Period ---`,
      `Source: CivicOS (federal rulemaking) | ${today}`,
      '',
      `**${period.title}**`,
      `Agency: ${period.agency_names.join(', ')}`,
      `Comment deadline: ${period.comments_close_on} (${period.days_remaining} days remaining)`,
    ];
    if (period.abstract) lines.push('', period.abstract);
    if (period.comment_url) lines.push('', `Submit comment: ${period.comment_url}`);
    if (period.html_url) lines.push('', `Read full rule: ${period.html_url}`);
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: Help me draft a public comment on this proposed rule. What are the key issues to address?');
    return lines.join('\n');
  }

  function composeHearingContext(hearing: { bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string; description?: string; summary?: string; official_url?: string; days_until: number }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const label = hearing.bill_number || hearing.bill_id;
    const lines = [
      `--- CivicOS Context: Legislative Hearing ---`,
      `Source: CivicOS (state legislature) | ${today}`,
      '',
      `**${label}**`,
    ];
    if (hearing.bill_name) lines.push(hearing.bill_name);
    lines.push(`Hearing date: ${hearing.event_date} (${hearing.days_until === 0 ? 'Today' : hearing.days_until === 1 ? 'Tomorrow' : `in ${hearing.days_until} days`})`);
    if (hearing.committee) lines.push(`Committee: ${hearing.committee}`);
    if (hearing.location) lines.push(`Location: ${hearing.location}`);
    if (hearing.summary) lines.push('', hearing.summary);
    else if (hearing.description) lines.push('', hearing.description);
    if (hearing.official_url) lines.push('', `Bill details: ${hearing.official_url}`);
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What should I know about this bill and hearing? How can I participate?');
    return lines.join('\n');
  }

  function composeGovernorsDeskContext(bill: { bill_id: string; bill_number?: string; bill_name?: string; summary?: string; enrolled_date?: string }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const label = bill.bill_number || bill.bill_id;
    const lines = [
      `--- CivicOS Context: Governor's Desk ---`,
      `Source: CivicOS (state legislature) | ${today}`,
      '',
      `**${label}** — Awaiting Governor's Signature`,
    ];
    if (bill.bill_name) lines.push(bill.bill_name);
    if (bill.enrolled_date) lines.push(`Enrolled: ${bill.enrolled_date}`);
    if (bill.summary) lines.push('', bill.summary);
    lines.push('', '--- End Context ---');
    lines.push('', "Suggested question: What does this bill do? Should the governor sign it? Help me draft a message to the governor's office.");
    return lines.join('\n');
  }

  function composeCityMeetingFocalContext(meeting: { title: string; date: string; time: string; location: string; days_until: number; agendaItems: Array<{ title: string; project_type?: string }> }): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || 'my city';
    const urgency = meeting.days_until === 0 ? 'TODAY' : meeting.days_until === 1 ? 'TOMORROW' : `in ${meeting.days_until} days`;
    const lines = [
      `--- CivicOS Context: Upcoming City Meeting (${urgency}) ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${meeting.title}**`,
      `Date: ${meeting.date} at ${meeting.time}`,
    ];
    if (meeting.location) lines.push(`Location: ${meeting.location}`);
    if (meeting.agendaItems.length > 0) {
      lines.push('', `Agenda items (${meeting.agendaItems.length}):`);
      for (const item of meeting.agendaItems) {
        let line = `- ${item.title}`;
        if (item.project_type) line += ` [${item.project_type}]`;
        lines.push(line);
      }
    }
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What should I know about this meeting? How can I participate or submit comments?');
    return lines.join('\n');
  }

  // Delegate to shared utilities
  function urgencyClass(days: number): string {
    return urgencyClassFn(days);
  }

  function meetingDaysUntil(meetingTitle: string): number | null {
    if (isLegislative) return null;
    return meetingDaysUntilFn(meetingTitle, data.decisions_this_week, referenceTime);
  }

  let expanded: Record<string, boolean> = $state({
    meetings: true,
    items: true,
    outcomes: false,
    commentPeriods: true,
    hearings: true,
    governorsDesk: true,
    congressionalVotes: true,
    cityFocal: true,
  });

  function toggle(section: string) {
    expanded[section] = !expanded[section];
  }

  // --- Comment Thread State ---

  let openThreads = $state(new Set<string>());
  let threadComments = $state(new Map<string, Comment[]>());
  let threadDrafts = $state(new Map<string, string>());
  let threadSubmitting = $state(new Set<string>());
  let threadLoading = $state(new Set<string>());
  let threadErrors = $state(new Map<string, string>());
  let localSynthData = $state(new Map<string, CommentSynthesis>());
  let aiResponseLoading = $state(new Set<string>());
  let aiResponses = $state(new Map<string, string>());
  let draftingInProgress = $state(new Set<string>());
  let enrichingInProgress = $state(new Set<string>());
  let hearingCalendarOpen = $state(new Set<string>());

  // --- Official Comment Drafting (Federal Comment Periods) ---
  let officialDrafts = $state(new Map<string, string>());
  let officialDraftLoading = $state(new Set<string>());
  let officialDraftCopied = $state(new Set<string>());

  // --- Attention bar: time-sensitive items ---
  type AttentionItem = { title: string; when: string; section: string };
  const attentionItems = $derived.by(() => {
    const items: AttentionItem[] = [];
    for (const p of data.comment_periods ?? []) {
      if (p.days_remaining >= 0) {
        items.push({ title: p.title, when: p.days_remaining === 0 ? 'Closes today' : p.days_remaining === 1 ? '1 day left' : `${p.days_remaining} days left`, section: 'commentPeriods' });
      }
    }
    for (const h of data.upcoming_hearings ?? []) {
      items.push({ title: h.bill_name || h.bill_number || h.bill_id, when: h.days_until === 0 ? 'Today' : h.days_until === 1 ? 'Tomorrow' : `In ${h.days_until} days`, section: 'hearings' });
    }
    for (const b of data.governors_desk ?? []) {
      items.push({ title: b.bill_name || b.bill_number || b.bill_id, when: 'Awaiting signature', section: 'governorsDesk' });
    }
    return items;
  });
  const hasAttention = $derived(attentionItems.length > 0);

  function scrollToSection(section: string) {
    expanded[section] = true;
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-section="${section}"]`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function getSynthesis(entityId: string): CommentSynthesis | null {
    return localSynthData.get(entityId) ?? parentSynthData.get(entityId) ?? null;
  }

  async function toggleCommentThread(entityId: string) {
    if (!session) return;
    if (openThreads.has(entityId)) {
      openThreads.delete(entityId);
      openThreads = new Set(openThreads);
      return;
    }
    openThreads.add(entityId);
    openThreads = new Set(openThreads);

    if (!threadComments.has(entityId)) {
      threadLoading.add(entityId);
      threadLoading = new Set(threadLoading);
      try {
        const thread = await session.loadCommentThread(entityId);
        threadComments.set(entityId, thread.comments);
        threadComments = new Map(threadComments);
        if (thread.synthesis) {
          localSynthData.set(entityId, thread.synthesis);
          localSynthData = new Map(localSynthData);
        }
        if (identity?.publicKey) {
          const mine = thread.comments.find((c: Comment) => c.public_key === identity!.publicKey);
          if (mine && !threadDrafts.has(entityId)) {
            threadDrafts.set(entityId, mine.comment_text);
            threadDrafts = new Map(threadDrafts);
          }
        }
      } catch (err) {
        console.error('[CivicOS] Failed to load comments for', entityId, err);
        const msg = err instanceof Error ? err.message : 'Failed to load comments';
        threadErrors.set(entityId, msg);
        threadErrors = new Map(threadErrors);
        // Still allow thread to display (empty) so user can post
        if (!threadComments.has(entityId)) {
          threadComments.set(entityId, []);
          threadComments = new Map(threadComments);
        }
      }
      threadLoading.delete(entityId);
      threadLoading = new Set(threadLoading);
    }
  }

  async function handleSubmitComment(entityId: string) {
    const draft = (threadDrafts.get(entityId) || '').trim();
    if (!draft || !identity?.isUnlocked || !api) return;

    threadSubmitting.add(entityId);
    threadSubmitting = new Set(threadSubmitting);
    threadErrors.delete(entityId);
    threadErrors = new Map(threadErrors);

    try {
      const userStance = userStances.get(entityId);
      const result = await api.castComment(entityId, draft, jurisdiction, userStance);

      if (result.ok) {
        const pubkey = identity?.publicKey || '';
        const newComment: Comment = {
          entity: entityId,
          comment_text: draft,
          public_key: pubkey,
          signature: '',
          timestamp: new Date().toISOString(),
          jurisdiction,
          stance: userStance,
          deleted: false,
        };
        const existing = threadComments.get(entityId) || [];
        const existingIdx = existing.findIndex(c => c.public_key === pubkey);
        if (existingIdx >= 0) {
          existing[existingIdx] = newComment;
          threadComments.set(entityId, [...existing]);
        } else {
          threadComments.set(entityId, [newComment, ...existing]);
          const prev = parentCommentCounts.get(entityId) || { entity: entityId, count: 0 };
          const updated = { ...prev, count: prev.count + 1 };
          oncommentcountchange?.(entityId, updated);
        }
        threadComments = new Map(threadComments);
        threadDrafts.delete(entityId);
        threadDrafts = new Map(threadDrafts);
      } else {
        const msg = result.rejection?.reason.includes('rate limit')
          ? 'Daily comment limit reached. Try again tomorrow.'
          : result.rejection ? 'Comment not accepted — verification may be required.' : 'Failed to submit comment';
        threadErrors.set(entityId, msg);
        threadErrors = new Map(threadErrors);
      }
    } catch {
      threadErrors.set(entityId, 'Error submitting comment');
      threadErrors = new Map(threadErrors);
    }

    threadSubmitting.delete(entityId);
    threadSubmitting = new Set(threadSubmitting);
  }

  async function handleSummarize(entityId: string, title: string) {
    const key = `summarize-thread:${entityId}`;
    if (aiResponses.has(key)) {
      aiResponses.delete(key);
      aiResponses = new Map(aiResponses);
      return;
    }
    if (!session?.askQuestion) return;

    aiResponseLoading.add(key);
    aiResponseLoading = new Set(aiResponseLoading);

    const comments = threadComments.get(entityId) || [];
    const lines = [
      `Summarize the public comment thread for: **${title}**`,
      '',
      `**${comments.length} public comment${comments.length !== 1 ? 's' : ''}:**`,
    ];
    for (const c of comments) {
      const stanceTag = c.stance ? ` [${c.stance}]` : '';
      lines.push(`- "${c.comment_text}"${stanceTag}`);
    }
    lines.push('', 'Analyze these comments:', '1. What are the key themes?', '2. Are there points of agreement or disagreement?', '3. What are the strongest arguments?', '', 'Be concise. Use bullet points.');

    try {
      const answer = await session.askQuestion(lines.join('\n'));
      if (answer) {
        aiResponses.set(key, answer);
        aiResponses = new Map(aiResponses);
      } else {
        ontoast?.('AI summarization failed');
      }
    } catch {
      ontoast?.('AI summarization failed');
    }

    aiResponseLoading.delete(key);
    aiResponseLoading = new Set(aiResponseLoading);
  }

  // --- Ask AI for focal point items ---

  async function askFocalAI(key: string, context: string) {
    if (aiResponses.has(key)) {
      aiResponses.delete(key);
      aiResponses = new Map(aiResponses);
      return;
    }
    if (!session?.askQuestion) return;

    aiResponseLoading.add(key);
    aiResponseLoading = new Set(aiResponseLoading);

    try {
      const answer = await session.askQuestion(context);
      if (answer) {
        aiResponses.set(key, answer);
        aiResponses = new Map(aiResponses);
      } else {
        ontoast?.('AI request failed');
      }
    } catch {
      ontoast?.('AI request failed');
    }

    aiResponseLoading.delete(key);
    aiResponseLoading = new Set(aiResponseLoading);
  }

  // --- Draft/Enrich for focal point comment threads ---

  async function handleDraftFocal(entityId: string, title: string, context: string) {
    if (!session?.askQuestion) return;

    draftingInProgress.add(entityId);
    draftingInProgress = new Set(draftingInProgress);

    try {
      const stance = userStances.get(entityId);
      const stanceText = stance ? ` My stance: ${stance}.` : '';
      const prompt = `Draft a concise, thoughtful public comment (under 500 characters) about: ${title}.${stanceText}\n\n${context}\n\nWrite as a concerned resident. Be specific and constructive. Output only the comment text.`;
      const draft = await session.askQuestion(prompt);

      if (draft) {
        threadDrafts.set(entityId, draft.slice(0, 500));
        threadDrafts = new Map(threadDrafts);

        if (!openThreads.has(entityId)) {
          openThreads.add(entityId);
          openThreads = new Set(openThreads);
          if (!threadComments.has(entityId)) {
            threadLoading.add(entityId);
            threadLoading = new Set(threadLoading);
            try {
              const thread = await session.loadCommentThread(entityId);
              threadComments.set(entityId, thread.comments);
              threadComments = new Map(threadComments);
              if (thread.synthesis) {
                localSynthData.set(entityId, thread.synthesis);
                localSynthData = new Map(localSynthData);
              }
            } catch { /* Non-critical */ }
            threadLoading.delete(entityId);
            threadLoading = new Set(threadLoading);
          }
        }
      } else {
        ontoast?.('AI drafting failed');
      }
    } catch {
      ontoast?.('AI drafting failed');
    }

    draftingInProgress.delete(entityId);
    draftingInProgress = new Set(draftingInProgress);
  }

  async function handleEnrichFocal(entityId: string, title: string) {
    const draft = (threadDrafts.get(entityId) || '').trim();
    if (!draft || !session?.askQuestion) return;

    enrichingInProgress.add(entityId);
    enrichingInProgress = new Set(enrichingInProgress);

    try {
      const prompt = `Improve this public comment about "${title}" by adding specific facts, policy references, or civic context. Keep it under 500 characters. Preserve the author's voice and stance.\n\nOriginal comment: ${draft}\n\nOutput only the enriched comment text.`;
      const enriched = await session.askQuestion(prompt);
      if (enriched) {
        threadDrafts.set(entityId, enriched.slice(0, 500));
        threadDrafts = new Map(threadDrafts);
      } else {
        ontoast?.('Enrichment failed');
      }
    } catch {
      ontoast?.('Enrichment failed');
    }

    enrichingInProgress.delete(entityId);
    enrichingInProgress = new Set(enrichingInProgress);
  }

  // --- Official Comment Drafting ---

  async function handleDraftOfficialComment(period: { document_number: string; title: string; abstract?: string; agency_names: string[]; comments_close_on: string; comment_url?: string; days_remaining: number }) {
    const key = period.document_number;
    if (officialDrafts.has(key)) return; // already drafted
    if (!session?.askQuestion) return;

    officialDraftLoading.add(key);
    officialDraftLoading = new Set(officialDraftLoading);

    const stance = userStances.get(`rule:${key}`);
    const stanceText = stance ? ` The commenter's stance: ${stance}.` : '';
    const abstractText = period.abstract ? `\n\nRule summary: ${period.abstract}` : '';

    const prompt = `Draft a formal public comment for this federal rulemaking:

Title: ${period.title}
Agency: ${period.agency_names.join(', ')}
Docket: ${period.document_number}
Comment deadline: ${period.comments_close_on}${abstractText}${stanceText}

Write as a concerned member of the public. Structure the comment:
1. Opening — state your position on the proposed rule
2. Specific concerns — address provisions in the rule, cite impacts
3. Personal/community impact — how this affects real people
4. Recommendation — what the agency should do

Keep it substantive but accessible (150-300 words). Reference the docket number. Be respectful and specific — agencies must respond to substantive comments. Output only the comment text.`;

    try {
      const draft = await session.askQuestion(prompt);
      if (draft) {
        officialDrafts.set(key, draft);
        officialDrafts = new Map(officialDrafts);
      } else {
        ontoast?.('Failed to draft comment');
      }
    } catch {
      ontoast?.('Failed to draft comment');
    }

    officialDraftLoading.delete(key);
    officialDraftLoading = new Set(officialDraftLoading);
  }

  async function handleCopyOfficialDraft(key: string) {
    const draft = officialDrafts.get(key);
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
      officialDraftCopied.add(key);
      officialDraftCopied = new Set(officialDraftCopied);
      setTimeout(() => {
        officialDraftCopied.delete(key);
        officialDraftCopied = new Set(officialDraftCopied);
      }, 2000);
    } catch {
      ontoast?.('Failed to copy — try selecting the text manually');
    }
  }

  // --- Calendar helpers for hearings ---

  function hearingToMeeting(hearing: { bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string }): { title: string; date: string; time: string; location: string; meeting_datetime: string } {
    const title = hearing.bill_name
      ? `${hearing.bill_number || hearing.bill_id}: ${hearing.bill_name}`
      : `Hearing: ${hearing.bill_number || hearing.bill_id}`;
    return {
      title,
      date: hearing.event_date,
      time: '',
      location: hearing.location || hearing.committee || '',
      meeting_datetime: new Date(hearing.event_date).toISOString(),
    };
  }

  // --- Section hints by level ---

  // Map outcome strings to process stage for the process bar
  function outcomeToStage(outcome: string): string {
    const lower = outcome.toLowerCase();
    if (lower.includes('signed') || lower.includes('enacted')) return 'governor';
    if (lower.includes('passed') || lower.includes('approved') || lower.includes('adopted') || lower.includes('enrolled')) return 'vote';
    if (lower === 'on_agenda' || lower.includes('upcoming')) return 'committee';
    return 'vote'; // default for completed items
  }

  const meetingsHint = $derived(
    isLegislative ? '' : 'Attend public meetings or submit written comments to shape local decisions'
  );
  const itemsHint = $derived(
    isLegislative ? 'Track key bills and express your stance' : 'Review agenda items and share your perspective before the meeting'
  );
  const outcomesHint = $derived(
    isLegislative ? '' : 'View recent decisions and how the community weighed in'
  );
</script>

<!-- Attention Bar: time-sensitive items (compact links) -->
{#if hasAttention}
  <div class="attention-bar">
    <div class="attention-title">Upcoming Actionable Items</div>
    <div class="attention-items">
      {#each attentionItems as item}
        <button class="attention-item" onclick={() => scrollToSection(item.section)}>
          <span class="attention-pip"></span>
          <span class="attention-item-title">{item.title}</span>
          <span class="attention-when">{item.when}</span>
        </button>
      {/each}
    </div>
  </div>
{/if}

<!-- Topic Filter -->
{#if availableTopics.length > 0}
  <div class="topic-filters">
    {#each availableTopics as topic}
      <button
        class="topic-filter-pill"
        class:active={selectedTopics.has(topic)}
        onclick={() => toggleTopic(topic)}
      >{topic}</button>
    {/each}
    {#if selectedTopics.size > 0}
      <button class="topic-filter-clear" onclick={() => { selectedTopics = new Set(); }}>Clear</button>
    {/if}
  </div>
{/if}

<!-- Official data sections -->
{#if isLegislative}
  <div class="group-header">Official</div>
{/if}

{#if hasFocalPoints}
    <!-- Comment Periods (Federal) -->
    {#if hasCommentPeriods}
      <section class="feed-section" data-section="commentPeriods">
        <button class="section-header" onclick={() => toggle('commentPeriods')}>
          <span class="section-title">
            Comment Periods
            <span class="count-badge">{filteredCommentPeriods.length}</span>
          </span>
          <span class="chevron" class:open={expanded.commentPeriods}></span>
        </button>
        {#if expanded.commentPeriods}
          <div class="section-body">
            <div class="section-hint">Your comment directly shapes federal policy — the agency must read and respond</div>
            {#each filteredCommentPeriods as period}
              {@const eid = `rule:${period.document_number}`}
              {@const counts = voiceCounts.get(eid)}
              <div class="card" class:dragging={draggingId === period.document_number}
                   class:shaking={shakingCardId === period.document_number}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeCommentPeriodContext(period), period.document_number)}
                   ondragend={handleDragEnd}>
                <CivicProcessBar level="federal" stage="comment" />
                <div class="card-title">{period.title}</div>
                <div class="card-meta">
                  <span>{period.agency_names.join(', ')}</span>
                  {#if period.document_type}
                    <span class="doc-type-tag">{period.document_type === 'proposed_rule' ? 'Proposed Rule' : period.document_type.replace(/_/g, ' ')}</span>
                  {/if}
                  <span class="deadline-tag {urgencyClass(period.days_remaining)}">
                    {#if period.days_remaining < 0}
                      Closed
                    {:else if period.days_remaining === 0}
                      Closes today
                    {:else if period.days_remaining === 1}
                      1 day left
                    {:else}
                      {period.days_remaining} days left
                    {/if}
                  </span>
                  {#if counts && counts.total > 0}
                    <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
                  {/if}
                </div>
                {#if period.topics && period.topics.length > 0}
                  <div class="card-topics">
                    {#each period.topics.slice(0, 3) as topic}
                      <span class="topic-tag">{topic}</span>
                    {/each}
                  </div>
                {/if}
                {#if period.abstract}
                  <div class="card-summary">
                    {#if period.abstract.length > 150 && !expandedAbstracts.has(period.document_number)}
                      {truncate(period.abstract, 150)}
                      <button class="expand-btn" onclick={() => { expandedAbstracts.add(period.document_number); expandedAbstracts = new Set(expandedAbstracts); }}>more</button>
                    {:else}
                      {period.abstract}
                    {/if}
                  </div>
                {/if}
                {#if onvoice && period.days_remaining >= 0}
                  <div class="card-voice">
                    <CivicVoiceButtons
                      entityId={eid}
                      userStance={userStances.get(eid) ?? null}
                      disabled={votingInProgress.has(eid)}
                      locked={!identity?.isUnlocked}
                      {onvoice}
                    />
                  </div>
                {:else if counts && counts.total > 0 && period.days_remaining < 0}
                  <div class="card-meta closed-results">
                    <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''} recorded</span>
                  </div>
                {/if}
                <!-- Action button row (matches city tab) -->
                {#if period.days_remaining >= 0}
                  <div class="action-btn-row">
                    {#if aiAvailable && !officialDrafts.has(period.document_number)}
                      <button class="action-btn action-btn-draft" disabled={officialDraftLoading.has(period.document_number)} onclick={() => handleDraftOfficialComment(period)}>
                        <span class="sparkle">&#x2726;</span> {officialDraftLoading.has(period.document_number) ? 'Drafting...' : 'Draft with AI'}
                      </button>
                    {/if}
                    {#if period.comment_url}
                      <a href={period.comment_url} target="_blank" rel="noopener" class="action-btn action-btn-official">
                        <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M14 4.5L8 9 2 4.5M2 4v8h12V4H2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
                        Submit Official Comment
                      </a>
                    {/if}
                    <button class="action-btn action-btn-unofficial" class:active={openThreads.has(eid)} onclick={() => toggleCommentThread(eid)}>
                      <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
                      Unofficial Comment
                      {#if (parentCommentCounts.get(eid)?.count || 0) > 0}<span class="action-btn-count">{parentCommentCounts.get(eid)?.count}</span>{/if}
                      <span class="action-btn-chevron" class:open={openThreads.has(eid)}></span>
                    </button>
                  </div>
                {/if}
                {#if officialDrafts.has(period.document_number)}
                  <div class="official-draft">
                    <div class="official-draft-header">
                      <span class="official-draft-label">Draft Official Comment</span>
                      <div class="official-draft-actions">
                        <button class="official-draft-copy" onclick={() => handleCopyOfficialDraft(period.document_number)}>
                          {officialDraftCopied.has(period.document_number) ? 'Copied!' : 'Copy'}
                        </button>
                        <button class="official-draft-discard" onclick={() => { officialDrafts.delete(period.document_number); officialDrafts = new Map(officialDrafts); }}>Discard</button>
                      </div>
                    </div>
                    <textarea class="official-draft-text" rows="8"
                      oninput={(e: Event) => { officialDrafts.set(period.document_number, (e.target as HTMLTextAreaElement).value); officialDrafts = new Map(officialDrafts); }}
                    >{officialDrafts.get(period.document_number)}</textarea>
                    {#if period.comment_url}
                      <div class="official-draft-submit">
                        <span class="official-draft-hint">Edit above, copy, then paste into the official form:</span>
                        <a href={period.comment_url} target="_blank" rel="noopener" class="action-btn action-btn-official" style="flex: none; padding: 5px 12px;">Submit on regulations.gov</a>
                      </div>
                    {/if}
                  </div>
                {/if}
                {#if (period.html_url || period.pdf_url)}
                  <div class="card-secondary-links">
                    {#if period.html_url}
                      <a href={period.html_url} target="_blank" rel="noopener" class="secondary-link">Read Rule</a>
                    {/if}
                    {#if period.pdf_url}
                      <a href={period.pdf_url} target="_blank" rel="noopener" class="secondary-link">PDF</a>
                    {/if}
                  </div>
                {/if}
                <!-- Comment Thread (unofficial) -->
                {#if session}
                  <CivicCommentThread
                    entityId={eid}
                    commentCount={parentCommentCounts.get(eid)?.count || 0}
                    attestedCount={parentCommentCounts.get(eid)?.attested ?? 0}
                    comments={threadComments.get(eid) || []}
                    synthesis={getSynthesis(eid)}
                    expanded={openThreads.has(eid)}
                    loading={threadLoading.has(eid)}
                    submitting={threadSubmitting.has(eid)}
                    error={threadErrors.get(eid) || ''}
                    draft={threadDrafts.get(eid) || ''}
                    userPublicKey={identity?.publicKey || ''}
                    isUnlocked={identity?.isUnlocked ?? false}
                    hasIdentity={!!identity}
                    {aiAvailable}
                    {activeProviderName}
                    draftLoading={draftingInProgress.has(eid)}
                    enrichLoading={enrichingInProgress.has(eid)}
                    summarizeLoading={aiResponseLoading.has(`summarize-thread:${eid}`)}
                    summaryHtml={renderMarkdown(aiResponses.get(`summarize-thread:${eid}`) ?? '')}
                    showSummary={aiResponses.has(`summarize-thread:${eid}`)}
                    ontoggle={() => toggleCommentThread(eid)}
                    onsubmit={() => handleSubmitComment(eid)}
                    ondraftchange={({ text }: { text: string }) => { threadDrafts.set(eid, text); threadDrafts = new Map(threadDrafts); }}
                    ondraft={() => handleDraftFocal(eid, period.title, composeCommentPeriodContext(period))}
                    onenrich={() => handleEnrichFocal(eid, period.title)}
                    onsummarize={() => handleSummarize(eid, period.title)}
                  />
                {/if}
                <!-- AI action row -->
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${period.document_number}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${period.document_number}`)}
                      onclick={() => askFocalAI(`ask-focal:${period.document_number}`, composeCommentPeriodContext(period))}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${period.document_number}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${period.document_number}`) ? 'Hide' : 'Summary'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: composeCommentPeriodContext(period), event: e }); shakingCardId = period.document_number; setTimeout(() => { shakingCardId = null; }, 2500); }}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
                {#if shakingCardId === period.document_number}
                  <div class="drag-hint">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    Drag this card into Claude's input
                  </div>
                {/if}
                {#if aiResponses.has(`ask-focal:${period.document_number}`)}
                  <div class="ai-response">
                    <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-focal:${period.document_number}`) ?? '')}</div>
                    {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- Upcoming Hearings (State) -->
    {#if hasHearings}
      <section class="feed-section" data-section="hearings">
        <button class="section-header" onclick={() => toggle('hearings')}>
          <span class="section-title">
            Upcoming Hearings
            <span class="count-badge">{filteredHearings.length}</span>
          </span>
          <span class="chevron" class:open={expanded.hearings}></span>
        </button>
        {#if expanded.hearings}
          <div class="section-body">
            <div class="section-hint">Hearings are open to public testimony — attend or submit written comments</div>
            {#each filteredHearings as hearing}
              {@const eid = billEntityId(hearing.bill_id)}
              {@const counts = voiceCounts.get(eid)}
              <div class="card" class:dragging={draggingId === hearing.bill_id}
                   class:shaking={shakingCardId === hearing.bill_id}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeHearingContext(hearing), hearing.bill_id)}
                   ondragend={handleDragEnd}>
                <CivicProcessBar level="state" stage="hearing" />
                <div class="meeting-top-row">
                  <div class="card-title">{hearing.bill_number || hearing.bill_id}</div>
                  <button class="cal-btn" onclick={() => { hearingCalendarOpen.has(hearing.bill_id) ? hearingCalendarOpen.delete(hearing.bill_id) : hearingCalendarOpen.add(hearing.bill_id); hearingCalendarOpen = new Set(hearingCalendarOpen); }} title="Add to calendar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </button>
                </div>
                {#if hearing.bill_name}
                  <div class="card-subtitle">{hearing.bill_name}</div>
                {/if}
                {#if hearingCalendarOpen.has(hearing.bill_id)}
                  {@const meetingData = hearingToMeeting(hearing)}
                  <div class="cal-dropdown">
                    <a href={googleCalendarUrl(meetingData)} target="_blank" rel="noopener" class="cal-option">Google Calendar</a>
                    <button class="cal-option" onclick={() => downloadIcs(hearingToMeeting(hearing))}>Download .ics</button>
                  </div>
                {/if}
                <div class="card-meta">
                  <span class="meta-date">{hearing.event_date}</span>
                  <span class="deadline-tag {urgencyClass(hearing.days_until)}">
                    {#if hearing.days_until === 0}
                      Today
                    {:else if hearing.days_until === 1}
                      Tomorrow
                    {:else}
                      In {hearing.days_until} days
                    {/if}
                  </span>
                  {#if hearing.committee}
                    <span>{hearing.committee}</span>
                  {/if}
                  {#if counts && counts.total > 0}
                    <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
                  {/if}
                </div>
                {#if hearing.summary}
                  <div class="card-summary">{hearing.summary}</div>
                {:else if hearing.description}
                  <div class="card-summary">{hearing.description}</div>
                {/if}
                {#if getTopics(hearing.bill_id).length > 0}
                  <div class="card-topics">
                    {#each getTopics(hearing.bill_id).slice(0, 3) as topic}
                      <span class="topic-tag">{topic}</span>
                    {/each}
                  </div>
                {/if}
                {#if onvoice}
                  <div class="card-voice">
                    <CivicVoiceButtons
                      entityId={eid}
                      userStance={userStances.get(eid) ?? null}
                      disabled={votingInProgress.has(eid)}
                      locked={!identity?.isUnlocked}
                      {onvoice}
                    />
                  </div>
                {/if}
                <div class="action-btn-row">
                  {#if aiAvailable}
                    <button class="action-btn action-btn-draft" onclick={() => handleDraftFocal(eid, hearing.bill_name || hearing.bill_number || hearing.bill_id, composeHearingContext(hearing))} disabled={draftingInProgress.has(eid)}>
                      <span class="sparkle">&#x2726;</span> {draftingInProgress.has(eid) ? 'Drafting...' : 'Draft with AI'}
                    </button>
                  {/if}
                  <button class="action-btn action-btn-unofficial" class:active={openThreads.has(eid)} onclick={() => toggleCommentThread(eid)}>
                    <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
                    Unofficial Comment
                    {#if (parentCommentCounts.get(eid)?.count || 0) > 0}<span class="action-btn-count">{parentCommentCounts.get(eid)?.count}</span>{/if}
                    <span class="action-btn-chevron" class:open={openThreads.has(eid)}></span>
                  </button>
                </div>
                {#if hearing.official_url}
                  <div class="card-secondary-links">
                    <a href={hearing.official_url} target="_blank" rel="noopener" class="secondary-link">View Bill</a>
                  </div>
                {/if}
                {#if session}
                  <CivicCommentThread
                    entityId={eid}
                    commentCount={parentCommentCounts.get(eid)?.count || 0}
                    attestedCount={parentCommentCounts.get(eid)?.attested ?? 0}
                    comments={threadComments.get(eid) || []}
                    synthesis={getSynthesis(eid)}
                    expanded={openThreads.has(eid)}
                    loading={threadLoading.has(eid)}
                    submitting={threadSubmitting.has(eid)}
                    error={threadErrors.get(eid) || ''}
                    draft={threadDrafts.get(eid) || ''}
                    userPublicKey={identity?.publicKey || ''}
                    isUnlocked={identity?.isUnlocked ?? false}
                    hasIdentity={!!identity}
                    {aiAvailable}
                    {activeProviderName}
                    draftLoading={draftingInProgress.has(eid)}
                    enrichLoading={enrichingInProgress.has(eid)}
                    summarizeLoading={aiResponseLoading.has(`summarize-thread:${eid}`)}
                    summaryHtml={renderMarkdown(aiResponses.get(`summarize-thread:${eid}`) ?? '')}
                    showSummary={aiResponses.has(`summarize-thread:${eid}`)}
                    ontoggle={() => toggleCommentThread(eid)}
                    onsubmit={() => handleSubmitComment(eid)}
                    ondraftchange={({ text }: { text: string }) => { threadDrafts.set(eid, text); threadDrafts = new Map(threadDrafts); }}
                    ondraft={() => handleDraftFocal(eid, hearing.bill_name || hearing.bill_number || hearing.bill_id, composeHearingContext(hearing))}
                    onenrich={() => handleEnrichFocal(eid, hearing.bill_name || hearing.bill_number || hearing.bill_id)}
                    onsummarize={() => handleSummarize(eid, hearing.bill_number || hearing.bill_id)}
                  />
                {/if}
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${hearing.bill_id}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${hearing.bill_id}`)}
                      onclick={() => askFocalAI(`ask-focal:${hearing.bill_id}`, composeHearingContext(hearing))}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${hearing.bill_id}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${hearing.bill_id}`) ? 'Hide' : 'Summary'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: composeHearingContext(hearing), event: e }); shakingCardId = hearing.bill_id; setTimeout(() => { shakingCardId = null; }, 2500); }}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
                {#if shakingCardId === hearing.bill_id}
                  <div class="drag-hint">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    Drag this card into Claude's input
                  </div>
                {/if}
                {#if aiResponses.has(`ask-focal:${hearing.bill_id}`)}
                  <div class="ai-response">
                    <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-focal:${hearing.bill_id}`) ?? '')}</div>
                    {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- Governor's Desk (State) -->
    {#if hasGovernorsDesk}
      <section class="feed-section" data-section="governorsDesk">
        <button class="section-header" onclick={() => toggle('governorsDesk')}>
          <span class="section-title">
            Awaiting Governor's Signature
            <span class="count-badge">{filteredGovernorsDesk.length}</span>
          </span>
          <span class="chevron" class:open={expanded.governorsDesk}></span>
        </button>
        {#if expanded.governorsDesk}
          <div class="section-body">
            <div class="section-hint">Bills awaiting governor's signature — call now to influence the outcome</div>
            {#each filteredGovernorsDesk as bill}
              {@const eid = billEntityId(bill.bill_id)}
              {@const counts = voiceCounts.get(eid)}
              <div class="card" class:dragging={draggingId === bill.bill_id}
                   class:shaking={shakingCardId === bill.bill_id}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeGovernorsDeskContext(bill), bill.bill_id)}
                   ondragend={handleDragEnd}>
                <CivicProcessBar level="state" stage="governor" />
                <div class="card-title">{bill.bill_number || bill.bill_id}</div>
                {#if bill.bill_name}
                  <div class="card-subtitle">{bill.bill_name}</div>
                {/if}
                {#if bill.summary}
                  <div class="card-summary">{bill.summary}</div>
                {/if}
                {#if getTopics(bill.bill_id).length > 0}
                  <div class="card-topics">
                    {#each getTopics(bill.bill_id).slice(0, 3) as topic}
                      <span class="topic-tag">{topic}</span>
                    {/each}
                  </div>
                {/if}
                {#if onvoice}
                  <div class="card-voice">
                    <CivicVoiceButtons
                      entityId={eid}
                      userStance={userStances.get(eid) ?? null}
                      disabled={votingInProgress.has(eid)}
                      locked={!identity?.isUnlocked}
                      {onvoice}
                    />
                  </div>
                {/if}
                <div class="action-btn-row">
                  {#if aiAvailable}
                    <button class="action-btn action-btn-draft" onclick={() => handleDraftFocal(eid, bill.bill_name || bill.bill_number || bill.bill_id, composeGovernorsDeskContext(bill))} disabled={draftingInProgress.has(eid)}>
                      <span class="sparkle">&#x2726;</span> {draftingInProgress.has(eid) ? 'Drafting...' : 'Draft with AI'}
                    </button>
                  {/if}
                  <button class="action-btn action-btn-unofficial" class:active={openThreads.has(eid)} onclick={() => toggleCommentThread(eid)}>
                    <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
                    Unofficial Comment
                    {#if (parentCommentCounts.get(eid)?.count || 0) > 0}<span class="action-btn-count">{parentCommentCounts.get(eid)?.count}</span>{/if}
                    <span class="action-btn-chevron" class:open={openThreads.has(eid)}></span>
                  </button>
                </div>
                {#if session}
                  <CivicCommentThread
                    entityId={eid}
                    commentCount={parentCommentCounts.get(eid)?.count || 0}
                    attestedCount={parentCommentCounts.get(eid)?.attested ?? 0}
                    comments={threadComments.get(eid) || []}
                    synthesis={getSynthesis(eid)}
                    expanded={openThreads.has(eid)}
                    loading={threadLoading.has(eid)}
                    submitting={threadSubmitting.has(eid)}
                    error={threadErrors.get(eid) || ''}
                    draft={threadDrafts.get(eid) || ''}
                    userPublicKey={identity?.publicKey || ''}
                    isUnlocked={identity?.isUnlocked ?? false}
                    hasIdentity={!!identity}
                    {aiAvailable}
                    {activeProviderName}
                    draftLoading={draftingInProgress.has(eid)}
                    enrichLoading={enrichingInProgress.has(eid)}
                    summarizeLoading={aiResponseLoading.has(`summarize-thread:${eid}`)}
                    summaryHtml={renderMarkdown(aiResponses.get(`summarize-thread:${eid}`) ?? '')}
                    showSummary={aiResponses.has(`summarize-thread:${eid}`)}
                    ontoggle={() => toggleCommentThread(eid)}
                    onsubmit={() => handleSubmitComment(eid)}
                    ondraftchange={({ text }: { text: string }) => { threadDrafts.set(eid, text); threadDrafts = new Map(threadDrafts); }}
                    ondraft={() => handleDraftFocal(eid, bill.bill_name || bill.bill_number || bill.bill_id, composeGovernorsDeskContext(bill))}
                    onenrich={() => handleEnrichFocal(eid, bill.bill_name || bill.bill_number || bill.bill_id)}
                    onsummarize={() => handleSummarize(eid, bill.bill_number || bill.bill_id)}
                  />
                {/if}
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${bill.bill_id}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${bill.bill_id}`)}
                      onclick={() => askFocalAI(`ask-focal:${bill.bill_id}`, composeGovernorsDeskContext(bill))}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${bill.bill_id}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${bill.bill_id}`) ? 'Hide' : 'Summary'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: composeGovernorsDeskContext(bill), event: e }); shakingCardId = bill.bill_id; setTimeout(() => { shakingCardId = null; }, 2500); }}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
                {#if shakingCardId === bill.bill_id}
                  <div class="drag-hint">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    Drag this card into Claude's input
                  </div>
                {/if}
                {#if aiResponses.has(`ask-focal:${bill.bill_id}`)}
                  <div class="ai-response">
                    <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-focal:${bill.bill_id}`) ?? '')}</div>
                    {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- How They Voted (Congressional) -->
    {#if hasCongressionalVotes}
      <section class="feed-section" data-section="congressionalVotes">
        <button class="section-header" onclick={() => toggle('congressionalVotes')}>
          <span class="section-title">
            How They Voted
            <span class="count-badge">{(data.congressional_votes ?? []).length}</span>
          </span>
          <span class="chevron" class:open={expanded.congressionalVotes}></span>
        </button>
        {#if expanded.congressionalVotes}
          <div class="section-body">
            <div class="section-hint">Recent roll call votes by your representatives in Congress</div>
            {#each Object.entries(groupVotesByMember(data.congressional_votes ?? [])) as [memberName, memberVotes]}
              <div class="votes-member-group">
                <div class="votes-member-name">
                  {memberName}
                  {#if memberVotes[0]?.member_party}
                    <span class="party-tag party-{memberVotes[0].member_party?.charAt(0)}">{memberVotes[0].member_party}</span>
                  {/if}
                  <span class="chamber-tag">{memberVotes[0]?.chamber}</span>
                </div>
                {#each memberVotes.slice(0, 5) as vote}
                  <div class="vote-row">
                    <span class="vote-position vote-{vote.vote_position.toLowerCase().replace(/\s+/g, '-')}">{vote.vote_position === 'Not Voting' ? 'NV' : vote.vote_position}</span>
                    <span class="vote-bill">{vote.bill_id || ''}</span>
                    <span class="vote-title">{(vote.bill_title || vote.vote_question || '').slice(0, 60)}{(vote.bill_title || vote.vote_question || '').length > 60 ? '...' : ''}</span>
                    {#if vote.vote_date}
                      <span class="vote-date">{vote.vote_date}</span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- Upcoming City Meetings (City) -->
    {#if hasCityFocal}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('cityFocal')}>
          <span class="section-title">
            Upcoming Meetings
            <span class="count-badge">{cityFocalMeetings.length}</span>
          </span>
          <span class="chevron" class:open={expanded.cityFocal}></span>
        </button>
        {#if expanded.cityFocal}
          <div class="section-body">
            <div class="section-hint">Your voice shapes local decisions — attend or submit written comments</div>
            {#each cityFocalMeetings as meeting}
              {@const meetingId = `meeting:${meeting.title.toLowerCase().replace(/\s+/g, '-')}`}
              {@const focalContext = composeCityMeetingFocalContext(meeting)}
              <div class="card" class:dragging={draggingId === meetingId}
                   class:shaking={shakingCardId === meetingId}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, focalContext, meetingId)}
                   ondragend={handleDragEnd}>
                <CivicProcessBar level="city" stage={meeting.days_until <= 0 ? 'vote' : 'comment'} />
                <div class="meeting-top-row">
                  <div class="card-title">{meeting.title}</div>
                  <button class="cal-btn" onclick={() => { hearingCalendarOpen.has(meetingId) ? hearingCalendarOpen.delete(meetingId) : hearingCalendarOpen.add(meetingId); hearingCalendarOpen = new Set(hearingCalendarOpen); }} title="Add to calendar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </button>
                </div>
                {#if hearingCalendarOpen.has(meetingId)}
                  <div class="cal-dropdown">
                    <a href={googleCalendarUrl(meeting)} target="_blank" rel="noopener" class="cal-option">Google Calendar</a>
                    <button class="cal-option" onclick={() => downloadIcs(meeting)}>Download .ics</button>
                  </div>
                {/if}
                <div class="card-meta">
                  <span class="meta-date">{meeting.date} · {meeting.time}</span>
                  <span class="deadline-tag {urgencyClass(meeting.days_until)}">
                    {#if meeting.days_until === 0}
                      Today
                    {:else if meeting.days_until === 1}
                      Tomorrow
                    {:else}
                      In {meeting.days_until} days
                    {/if}
                  </span>
                </div>
                {#if meeting.location}
                  <div class="card-meta"><span>{meeting.location}</span></div>
                {/if}
                {#if meeting.agendaItems.length > 0}
                  <div class="focal-agenda-preview">
                    <div class="focal-agenda-label">{meeting.agendaItems.length} agenda item{meeting.agendaItems.length !== 1 ? 's' : ''}:</div>
                    {#each meeting.agendaItems as item}
                      <div class="focal-agenda-item">
                        <span class="focal-agenda-bullet">·</span>
                        {item.title}
                        {#if item.project_type}
                          <span class="item-type">{item.project_type}</span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {/if}
                <!-- AI action row -->
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${meetingId}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${meetingId}`)}
                      onclick={() => askFocalAI(`ask-focal:${meetingId}`, focalContext)}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${meetingId}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${meetingId}`) ? 'Hide' : 'Summary'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: focalContext, event: e }); shakingCardId = meetingId; setTimeout(() => { shakingCardId = null; }, 2500); }}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
                {#if shakingCardId === meetingId}
                  <div class="drag-hint">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    Drag this card into Claude's input
                  </div>
                {/if}
                {#if aiResponses.has(`ask-focal:${meetingId}`)}
                  <div class="ai-response">
                    <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-focal:${meetingId}`) ?? '')}</div>
                    {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}
{/if}

<!-- Meetings / Hearings -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('meetings')}>
    <span class="section-title">
      {meetingsLabel}
      {#if data.decisions_this_week.length > 0}
        <span class="count-badge">{data.decisions_this_week.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.meetings}></span>
  </button>
  {#if expanded.meetings}
    <div class="section-body">
      {#if meetingsHint}
        <div class="section-hint">{meetingsHint}</div>
      {/if}
      {#if data.decisions_this_week.length === 0}
        <div class="empty-section">{emptyMeetings}</div>
      {:else if isLegislative}
        <div class="topic-grid">
          {#each data.decisions_this_week as topic}
            <div class="topic-card">
              <div class="topic-name">{topic.title}</div>
              <div class="topic-count">{topic.date}</div>
              {#if topic.time}
                <div class="topic-breakdown">{topic.time}</div>
              {/if}
            </div>
          {/each}
        </div>
      {:else}
        {#each data.decisions_this_week as meeting}
          {@const meetingAgendaItems = (data.upcoming_items || []).filter(i => i.meeting_title === meeting.title).map(i => i.title)}
        <CivicMeetingCard {meeting} {showCalendar} {jurisdiction} agendaItems={meetingAgendaItems} />
        {/each}
      {/if}
    </div>
  {/if}
</section>

<!-- Agenda Items / Legislation -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('items')}>
    <span class="section-title">
      {itemsLabel}
      {#if filteredItems.length > 0}
        <span class="count-badge">{filteredItems.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.items}></span>
  </button>
  {#if expanded.items}
    <div class="section-body">
      {#if itemsHint}
        <div class="section-hint">{itemsHint}</div>
      {/if}
      {#if filteredItems.length === 0}
        <div class="empty-section">{emptyItems}</div>
      {:else}
        {#each filteredItems as item}
          {@const eid = item.id ? billEntityId(item.id) : ''}
          {@const counts = eid ? voiceCounts.get(eid) : undefined}
          {@const itemDaysUntil = item.meeting_title ? meetingDaysUntil(item.meeting_title) : null}
          <div class="card" class:dragging={draggingId === (item.id || item.title)}
               class:shaking={shakingCardId === (item.id || item.title)}
               draggable="true"
               ondragstart={(e: DragEvent) => handleDragStart(e, composeLegislationContext(item), item.id || item.title)}
               ondragend={handleDragEnd}>
            {#if isLegislative}
              <CivicProcessBar level={level as 'state' | 'federal'} stage="committee" />
            {/if}
            <div class="card-title">
              {#if isLegislative && item.official_url}
                <a href={item.official_url} target="_blank" rel="noopener" class="card-link">{item.title}</a>
              {:else}
                {item.title}
              {/if}
            </div>
            <div class="card-meta">
              {#if item.meeting_title}
                <span>{item.meeting_title}</span>
              {/if}
              {#if isLegislative && item.status}
                <span class="status-tag">{item.status}</span>
              {/if}
              {#if item.project_type}
                <span class="item-type">{item.project_type}</span>
              {/if}
              {#if itemDaysUntil !== null}
                <span class="deadline-tag {urgencyClass(itemDaysUntil)}">
                  {#if itemDaysUntil === 0}
                    Meeting today
                  {:else if itemDaysUntil === 1}
                    Meeting tomorrow
                  {:else}
                    In {itemDaysUntil} days
                  {/if}
                </span>
              {/if}
              {#if counts && counts.total > 0}
                <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
              {/if}
            </div>
            {#if isLegislative && item.summary}
              <div class="card-summary">
                {#if item.summary.length > 150 && !expandedAbstracts.has(`leg:${item.id || item.title}`)}
                  {truncate(item.summary, 150)}
                  <button class="expand-btn" onclick={() => { expandedAbstracts.add(`leg:${item.id || item.title}`); expandedAbstracts = new Set(expandedAbstracts); }}>more</button>
                {:else}
                  {item.summary}
                {/if}
              </div>
            {/if}
            {#if isLegislative && item.description}
              <div class="card-leverage">{item.description}</div>
            {/if}
            {#if getTopics(item.id || item.title).length > 0}
              <div class="card-topics">
                {#each getTopics(item.id || item.title).slice(0, 3) as topic}
                  <span class="topic-tag">{topic}</span>
                {/each}
              </div>
            {/if}
            {#if eid && onvoice}
              <div class="card-voice">
                <CivicVoiceButtons
                  entityId={eid}
                  userStance={userStances.get(eid) ?? null}
                  disabled={votingInProgress.has(eid)}
                  locked={!identity?.isUnlocked}
                  {onvoice}
                />
              </div>
            {/if}
            {#if isLegislative && eid}
              <div class="action-btn-row">
                {#if aiAvailable}
                  <button class="action-btn action-btn-draft" onclick={() => handleDraftFocal(eid, item.title, composeLegislationContext(item))} disabled={draftingInProgress.has(eid)}>
                    <span class="sparkle">&#x2726;</span> {draftingInProgress.has(eid) ? 'Drafting...' : 'Draft with AI'}
                  </button>
                {/if}
                <button class="action-btn action-btn-unofficial" class:active={openThreads.has(eid)} onclick={() => toggleCommentThread(eid)}>
                  <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
                  Unofficial Comment
                  {#if (parentCommentCounts.get(eid)?.count || 0) > 0}<span class="action-btn-count">{parentCommentCounts.get(eid)?.count}</span>{/if}
                  <span class="action-btn-chevron" class:open={openThreads.has(eid)}></span>
                </button>
              </div>
            {/if}
            {#if isLegislative && eid && session}
              <CivicCommentThread
                entityId={eid}
                commentCount={parentCommentCounts.get(eid)?.count || 0}
                attestedCount={parentCommentCounts.get(eid)?.attested ?? 0}
                comments={threadComments.get(eid) || []}
                synthesis={getSynthesis(eid)}
                expanded={openThreads.has(eid)}
                loading={threadLoading.has(eid)}
                submitting={threadSubmitting.has(eid)}
                error={threadErrors.get(eid) || ''}
                draft={threadDrafts.get(eid) || ''}
                userPublicKey={identity?.publicKey || ''}
                isUnlocked={identity?.isUnlocked ?? false}
                hasIdentity={!!identity}
                {aiAvailable}
                {activeProviderName}
                draftLoading={draftingInProgress.has(eid)}
                enrichLoading={enrichingInProgress.has(eid)}
                summarizeLoading={aiResponseLoading.has(`summarize-thread:${eid}`)}
                summaryHtml={renderMarkdown(aiResponses.get(`summarize-thread:${eid}`) ?? '')}
                showSummary={aiResponses.has(`summarize-thread:${eid}`)}
                ontoggle={() => toggleCommentThread(eid)}
                onsubmit={() => handleSubmitComment(eid)}
                ondraftchange={({ text }: { text: string }) => { threadDrafts.set(eid, text); threadDrafts = new Map(threadDrafts); }}
                ondraft={() => handleDraftFocal(eid, item.title, composeLegislationContext(item))}
                onenrich={() => handleEnrichFocal(eid, item.title)}
                onsummarize={() => handleSummarize(eid, item.title)}
              />
            {/if}
            {#if isLegislative}
              <div class="ai-action-row">
                {#if aiAvailable}
                  <button
                    class="ai-action-btn ai-action-ask"
                    class:active={aiResponses.has(`ask-leg:${item.id || item.title}`)}
                    disabled={aiResponseLoading.has(`ask-leg:${item.id || item.title}`)}
                    onclick={() => askFocalAI(`ask-leg:${item.id || item.title}`, composeLegislationContext(item))}
                  >
                    <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-leg:${item.id || item.title}`) ? 'Thinking...' : aiResponses.has(`ask-leg:${item.id || item.title}`) ? 'Hide' : 'Summary'}
                  </button>
                {/if}
                {#if onopenexternalai}
                  <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: composeLegislationContext(item), event: e }); shakingCardId = item.id || item.title; setTimeout(() => { shakingCardId = null; }, 2500); }}>
                    Claude <span class="ext-icon">&#x2197;</span>
                  </button>
                {/if}
              </div>
              {#if shakingCardId === (item.id || item.title)}
                <div class="drag-hint">
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  Drag this card into Claude's input
                </div>
              {/if}
              {#if aiResponses.has(`ask-leg:${item.id || item.title}`)}
                <div class="ai-response">
                  <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-leg:${item.id || item.title}`) ?? '')}</div>
                  {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                </div>
              {/if}
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<!-- Recent Outcomes / Bill Status -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('outcomes')}>
    <span class="section-title">
      {outcomesLabel}
      {#if filteredOutcomes.length > 0}
        <span class="count-badge">{filteredOutcomes.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.outcomes}></span>
  </button>
  {#if expanded.outcomes}
    <div class="section-body">
      {#if outcomesHint}
        <div class="section-hint">{outcomesHint}</div>
      {/if}
      {#if filteredOutcomes.length === 0}
        <div class="empty-section">{emptyOutcomes}</div>
      {:else}
        {#each filteredOutcomes as outcome}
          {@const eid = outcome.id ? billEntityId(outcome.id) : ''}
          {@const counts = eid ? voiceCounts.get(eid) : undefined}
          <div class="card" class:dragging={draggingId === (outcome.id || outcome.title)}
               draggable="true"
               ondragstart={(e: DragEvent) => handleDragStart(e, composeOutcomeContext(outcome), outcome.id || outcome.title)}
               ondragend={handleDragEnd}>
            {#if isLegislative}
              <CivicProcessBar level={level as 'state' | 'federal'} stage={outcomeToStage(outcome.outcome)} />
            {/if}
            <div class="card-title">
              <span class="outcome-icon {outcomeClass(outcome.outcome)}">{outcomeIcon(outcome.outcome)}</span>
              {#if isLegislative && outcome.official_url}
                <a href={outcome.official_url} target="_blank" rel="noopener" class="card-link">{outcome.title}</a>
              {:else}
                {outcome.title}
              {/if}
            </div>
            <div class="card-meta">
              <span class="meta-date">{formatRelativeDate(outcome.date)}</span>
              {#if outcome.outcome}
                <span class="meta-sep">&middot;</span>
                <span class="outcome-label">{outcome.outcome.replace(/_/g, ' ')}</span>
              {/if}
              {#if counts && counts.total > 0}
                <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
              {/if}
            </div>
            {#if isLegislative && outcome.summary}
              <div class="card-summary">
                {#if outcome.summary.length > 150 && !expandedAbstracts.has(`out:${outcome.id || outcome.title}`)}
                  {truncate(outcome.summary, 150)}
                  <button class="expand-btn" onclick={() => { expandedAbstracts.add(`out:${outcome.id || outcome.title}`); expandedAbstracts = new Set(expandedAbstracts); }}>more</button>
                {:else}
                  {outcome.summary}
                {/if}
              </div>
            {/if}
            {#if getTopics(outcome.id || outcome.title).length > 0}
              <div class="card-topics">
                {#each getTopics(outcome.id || outcome.title).slice(0, 3) as topic}
                  <span class="topic-tag">{topic}</span>
                {/each}
              </div>
            {/if}
            {#if eid && onvoice && outcome.is_upcoming}
              <div class="card-voice">
                <CivicVoiceButtons
                  entityId={eid}
                  userStance={userStances.get(eid) ?? null}
                  disabled={votingInProgress.has(eid)}
                  locked={!identity?.isUnlocked}
                  {onvoice}
                />
              </div>
            {/if}
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

{#if children}
  <div class="group-header">Public</div>
  {@render children()}
{/if}

<footer class="pulse-footer">
  <span class="footer-ts">Updated {new Date(data.generated_at).toLocaleTimeString()}</span>
</footer>

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

  .feed-section { margin-bottom: 4px; }
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
  .section-title { display: flex; align-items: center; gap: 6px; }
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
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid var(--civic-text-disabled);
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }
  .section-body { padding: 4px 0 8px; }
  .empty-section {
    padding: 12px 8px;
    color: var(--civic-text-disabled);
    font-size: 12px;
    font-style: italic;
  }
  .card {
    background: var(--civic-surface-card);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 4px;
    border: 1px solid var(--civic-surface-elevated);
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: grab;
  }
  .card:hover {
    border-color: var(--civic-border-default);
  }
  .card:active { cursor: grabbing; }
  .card.dragging {
    opacity: 0.4;
    border-color: var(--civic-text-disabled);
  }
  .card.shaking {
    animation: card-shake 0.5s ease-in-out;
  }
  @keyframes card-shake {
    0%, 100% { transform: translateX(0); }
    15% { transform: translateX(-3px); }
    30% { transform: translateX(3px); }
    45% { transform: translateX(-2px); }
    60% { transform: translateX(2px); }
    75% { transform: translateX(-1px); }
    90% { transform: translateX(1px); }
  }
  .drag-hint {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--civic-text-muted);
    padding: 6px 10px;
    background: var(--civic-overlay-subtle);
    border-radius: 6px;
    margin-top: 4px;
    animation: hint-fade 2.5s ease-out forwards;
  }
  @keyframes hint-fade {
    0% { opacity: 0; transform: translateY(-4px); }
    10% { opacity: 1; transform: translateY(0); }
    70% { opacity: 1; }
    100% { opacity: 0; }
  }
  .card-title {
    color: var(--civic-text-secondary);
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
  }
  .card-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--civic-text-dim);
    margin-top: 4px;
    flex-wrap: wrap;
  }
  .meta-sep { color: var(--civic-text-disabled); }
  .item-type {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--civic-border-default);
    color: var(--civic-text-muted);
  }
  .status-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--civic-accent-primary-bg-active);
    color: var(--civic-accent-primary-light);
    font-weight: 500;
  }
  .card-link {
    color: inherit;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.15s ease;
  }
  .card-link:hover {
    border-bottom-color: var(--civic-accent-primary-light);
    color: var(--civic-accent-primary-bright);
  }
  .card-summary {
    color: var(--civic-text-body);
    font-size: 12px;
    line-height: 1.4;
    margin-top: 6px;
  }
  .expand-btn {
    background: none;
    border: none;
    color: var(--civic-accent-primary-light);
    font-size: 12px;
    cursor: pointer;
    padding: 0 2px;
    text-decoration: underline;
  }
  .expand-btn:hover {
    color: var(--civic-accent-primary-bright);
  }
  .closed-results {
    margin-top: 6px;
    opacity: 0.7;
  }
  .doc-type-tag {
    font-size: 10px;
    text-transform: capitalize;
    color: var(--civic-accent-indigo);
    background: var(--civic-accent-primary-bg-badge);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .card-topics {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }
  .topic-tag {
    font-size: 10px;
    color: var(--civic-text-muted);
    background: var(--civic-status-neutral-bg-badge);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .card-leverage {
    color: var(--civic-accent-primary-light);
    font-size: 11px;
    line-height: 1.4;
    margin-top: 4px;
    padding: 4px 8px;
    background: var(--civic-accent-primary-bg-subtle);
    border-left: 2px solid var(--civic-accent-primary);
    border-radius: 0 4px 4px 0;
  }
  .outcome-icon {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
    margin-right: 4px;
    vertical-align: middle;
  }
  .outcome-icon.passed { background: var(--civic-status-success-bg); color: var(--civic-status-success-light); }
  .outcome-icon.failed { background: var(--civic-status-error-bg); color: var(--civic-status-error-light); }
  .outcome-icon.upcoming { background: var(--civic-accent-primary-dark); color: var(--civic-accent-primary-light); }
  .outcome-icon.other { background: var(--civic-border-default); color: var(--civic-text-muted); }
  .outcome-label {
    font-weight: 500;
    text-transform: capitalize;
  }
  .topic-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }
  .topic-card {
    background: var(--civic-surface-elevated);
    border-radius: 8px;
    padding: 10px 12px;
    border: 1px solid var(--civic-border-default);
  }
  .topic-name {
    color: var(--civic-text-primary);
    font-size: 13px;
    font-weight: 500;
  }
  .topic-count {
    color: var(--civic-accent-primary-light);
    font-size: 11px;
    font-weight: 600;
    margin-top: 2px;
  }
  .topic-breakdown {
    color: var(--civic-text-dim);
    font-size: 10px;
    margin-top: 2px;
  }
  .card-desc {
    color: var(--civic-text-muted);
    font-size: 12px;
    line-height: 1.4;
    margin-top: 6px;
  }
  .card-voice {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--civic-border-default);
  }
  .voice-count-badge {
    font-size: 10px;
    color: var(--civic-accent-primary-light);
    font-weight: 500;
  }
  .card-subtitle {
    color: var(--civic-text-body);
    font-size: 12px;
    line-height: 1.3;
    margin-top: 2px;
  }
  .deadline-tag {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .deadline-tag.urgent-critical {
    background: var(--civic-status-error-bg-badge);
    color: var(--civic-status-error-light);
  }
  .deadline-tag.urgent-soon {
    background: var(--civic-status-warning-bg-subtle);
    color: var(--civic-status-warning-light);
  }
  .deadline-tag.urgent-normal {
    background: var(--civic-accent-primary-bg-active);
    color: var(--civic-accent-primary-light);
  }
  .deadline-tag.urgent-closed {
    background: var(--civic-status-neutral-bg-badge);
    color: var(--civic-text-dim);
  }
  .card-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .action-link {
    font-size: 11px;
    font-weight: 500;
    color: var(--civic-accent-primary-light);
    text-decoration: none;
    padding: 3px 8px;
    border-radius: 4px;
    background: var(--civic-accent-primary-bg-summary);
    border: 1px solid var(--civic-accent-primary-border-subtle);
    transition: all 0.15s ease;
  }
  .action-link:hover {
    background: var(--civic-accent-primary-bg-hover);
    border-color: var(--civic-accent-primary);
    color: var(--civic-accent-primary-bright);
  }
  .action-link.comment-link {
    color: var(--civic-status-success-light);
    background: var(--civic-status-success-bg-action);
    border-color: var(--civic-status-success-border-action);
  }
  .action-link.comment-link:hover {
    background: var(--civic-status-success-bg-action-strong);
    border-color: var(--civic-status-success-light);
    color: var(--civic-status-success-bright);
  }
  /* === Action button row (matches city tab CivicAgendaView) === */
  .action-btn-row {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .action-btn {
    flex: 1;
    padding: 5px 0;
    font-size: 11px;
    font-weight: 500;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: center;
    text-decoration: none;
    font-family: inherit;
  }
  .action-btn-draft {
    color: var(--civic-ai-accent);
    background: var(--civic-ai-bg-subtle);
    border: 1px solid var(--civic-ai-border-medium);
  }
  .action-btn-draft:hover:not(:disabled) {
    background: var(--civic-ai-bg-hover);
    border-color: var(--civic-ai-accent);
    color: var(--civic-ai-accent);
  }
  .action-btn-draft:disabled { opacity: 0.6; cursor: default; }
  .action-btn-official {
    color: var(--civic-status-success-light);
    background: var(--civic-status-success-bg-action);
    border: 1px solid var(--civic-status-success-border-action);
  }
  .action-btn-official:hover {
    background: var(--civic-status-success-bg-action-hover);
    border-color: var(--civic-status-success-light);
    color: var(--civic-status-success-bright);
  }
  .action-btn-unofficial {
    color: var(--civic-text-muted);
    background: var(--civic-overlay-subtle);
    border: 1px solid var(--civic-overlay-light);
  }
  .action-btn-unofficial:hover {
    background: var(--civic-overlay-light);
    border-color: var(--civic-overlay-medium);
    color: var(--civic-text-body);
  }
  .action-btn-unofficial.active {
    background: var(--civic-overlay-light);
    border-color: var(--civic-overlay-medium);
    color: var(--civic-text-secondary);
  }
  .action-btn .sparkle { font-size: 10px; opacity: 0.7; }
  .action-btn-icon { opacity: 0.6; flex-shrink: 0; vertical-align: -2.5px; }
  .action-btn-count {
    font-size: 10px;
    font-weight: 600;
    background: var(--civic-overlay-light);
    padding: 0 5px;
    border-radius: 8px;
    margin-left: 2px;
    font-variant-numeric: tabular-nums;
  }
  .action-btn-chevron {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid currentColor;
    opacity: 0.5;
    margin-left: 2px;
    transition: transform 0.15s ease;
    flex-shrink: 0;
  }
  .action-btn-chevron.open { transform: rotate(180deg); }
  /* Secondary links (Read Rule, PDF, View Bill) */
  .card-secondary-links {
    display: flex;
    gap: 12px;
    margin-top: 6px;
    padding-left: 2px;
  }
  .secondary-link {
    font-size: 10px;
    color: var(--civic-text-dim);
    text-decoration: none;
    transition: color 0.15s ease;
  }
  .secondary-link:hover {
    color: var(--civic-text-muted);
    text-decoration: underline;
  }
  /* Group headers (Official / Public) */
  .group-header {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--civic-text-disabled);
    padding: 14px 4px 4px;
  }
  /* Attention bar */
  .attention-bar {
    background: linear-gradient(135deg, var(--civic-surface-card-alt) 0%, var(--civic-accent-primary-dark) 100%);
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
  /* Thread clarifier */
  .thread-clarifier {
    font-size: 9px;
    color: var(--civic-text-dim);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 6px 0 0;
  }
  /* Official comment drafting */
  .draft-official-btn {
    cursor: pointer;
    font-family: inherit;
  }
  .draft-official-btn:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .official-draft {
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--civic-status-success-bg-action);
    border: 1px solid var(--civic-status-success-bg-action-hover);
    border-radius: 8px;
  }
  .official-draft-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .official-draft-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--civic-status-success-light);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .official-draft-actions {
    display: flex;
    gap: 8px;
  }
  .official-draft-copy {
    font-size: 11px;
    font-weight: 500;
    color: var(--civic-status-success-light);
    background: var(--civic-status-success-bg-action);
    border: 1px solid var(--civic-status-success-border-action);
    border-radius: 4px;
    padding: 2px 10px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .official-draft-copy:hover {
    background: var(--civic-status-success-border-action);
    border-color: var(--civic-status-success-light);
  }
  .official-draft-discard {
    font-size: 11px;
    color: var(--civic-text-dim);
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 4px;
  }
  .official-draft-discard:hover { color: var(--civic-text-muted); }
  .official-draft-text {
    width: 100%;
    min-height: 100px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--civic-text-secondary);
    background: var(--civic-surface-overlay);
    border: 1px solid var(--civic-border-default);
    border-radius: 6px;
    padding: 8px 10px;
    resize: vertical;
    font-family: inherit;
  }
  .official-draft-text:focus {
    outline: none;
    border-color: var(--civic-status-success-light);
  }
  .official-draft-submit {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
  }
  .official-draft-hint {
    font-size: 11px;
    color: var(--civic-text-muted);
  }
  .section-hint {
    font-size: 11px;
    color: var(--civic-text-muted);
    padding: 2px 8px 6px;
    font-style: italic;
  }
  .focal-agenda-preview {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--civic-border-default);
  }
  .focal-agenda-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--civic-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 4px;
  }
  .focal-agenda-item {
    font-size: 12px;
    color: var(--civic-text-body);
    line-height: 1.4;
    padding: 2px 0;
  }
  .focal-agenda-bullet {
    color: var(--civic-text-dim);
    margin-right: 4px;
    font-weight: 700;
  }
  /* Calendar button (hearings) */
  .meeting-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 6px;
  }
  .cal-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: var(--civic-text-dim);
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover { color: var(--civic-accent-primary-light); background: var(--civic-border-default); }
  .cal-dropdown {
    display: flex;
    gap: 8px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--civic-border-default);
  }
  .cal-option {
    font-size: 11px;
    color: var(--civic-accent-primary);
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-decoration: none;
  }
  .cal-option:hover { color: var(--civic-accent-primary-light); text-decoration: underline; }
  /* AI action row */
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
    color: var(--civic-accent-primary-light);
    background: var(--civic-accent-primary-bg-subtle);
    border: 1px solid var(--civic-accent-primary)30;
  }
  .ai-action-ask:hover:not(:disabled) {
    background: var(--civic-accent-primary-bg-hover);
    border-color: var(--civic-accent-primary);
    color: var(--civic-accent-primary-bright);
  }
  .ai-action-ask:disabled { opacity: 0.6; cursor: default; }
  .ai-action-ask.active {
    background: var(--civic-accent-primary-bg-active);
    border-color: var(--civic-accent-primary);
  }
  .ai-action-claude {
    color: var(--civic-accent-claude);
    background: var(--civic-accent-claude-bg-subtle);
    border: 1px solid var(--civic-accent-claude)30;
  }
  .ai-action-claude:hover {
    background: var(--civic-accent-claude-bg-hover);
    border-color: var(--civic-accent-claude);
    color: var(--civic-accent-claude-hover);
  }
  .ai-action-claude.solo { flex: 1; }
  .sparkle { font-size: 10px; opacity: 0.7; }
  .ext-icon { font-size: 9px; }
  /* AI response */
  .ai-response {
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--civic-ai-bg-subtle);
    border: 1px solid var(--civic-ai-border-subtle);
    border-radius: 8px;
  }
  .ai-response-text {
    font-size: 12px;
    color: var(--civic-text-body);
    line-height: 1.5;
  }
  .ai-response-text.prose :global(p) { margin: 0 0 8px; }
  .ai-response-text.prose :global(p:last-child) { margin-bottom: 0; }
  .ai-response-text.prose :global(strong) { color: var(--civic-text-secondary); font-weight: 600; }
  .ai-response-text.prose :global(ul), .ai-response-text.prose :global(ol) {
    margin: 4px 0 8px;
    padding-left: 18px;
  }
  .ai-response-text.prose :global(li) { margin-bottom: 2px; }
  .ai-response-provider {
    display: block;
    margin-top: 6px;
    font-size: 10px;
    color: var(--civic-text-dim);
  }
  /* Congressional Votes */
  .votes-member-group {
    padding: 8px 10px;
    border-bottom: 1px solid var(--civic-border-default);
  }
  .votes-member-group:last-child { border-bottom: none; }
  .votes-member-name {
    font-weight: 600;
    font-size: 12px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .party-tag {
    font-size: 10px;
    font-weight: 500;
    padding: 1px 5px;
    border-radius: 3px;
    color: var(--civic-text-secondary);
    background: var(--civic-surface-elevated);
  }
  .party-tag.party-D { color: #2563eb; background: #dbeafe; }
  .party-tag.party-R { color: #dc2626; background: #fee2e2; }
  .party-tag.party-I { color: #7c3aed; background: #ede9fe; }
  .chamber-tag {
    font-size: 10px;
    color: var(--civic-text-dim);
  }
  .vote-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    padding: 2px 0;
    font-size: 11px;
    line-height: 1.4;
  }
  .vote-position {
    font-weight: 600;
    font-size: 10px;
    min-width: 28px;
    text-align: center;
    padding: 1px 4px;
    border-radius: 3px;
  }
  .vote-position.vote-yea { color: #16a34a; background: #dcfce7; }
  .vote-position.vote-nay { color: #dc2626; background: #fee2e2; }
  .vote-position.vote-not-voting { color: #9ca3af; background: #f3f4f6; }
  .vote-position.vote-present { color: #d97706; background: #fef3c7; }
  .vote-bill {
    font-weight: 500;
    color: var(--civic-text-secondary);
    white-space: nowrap;
  }
  .vote-title {
    color: var(--civic-text-primary);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .vote-date {
    color: var(--civic-text-dim);
    font-size: 10px;
    white-space: nowrap;
  }

  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid var(--civic-border-default);
    font-size: 10px;
    color: var(--civic-text-disabled);
  }
</style>

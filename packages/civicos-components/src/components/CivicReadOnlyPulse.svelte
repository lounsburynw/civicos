<script lang="ts">
  import CivicMeetingCard from './CivicMeetingCard.svelte';
  import CivicVoiceButtons from './CivicVoiceButtons.svelte';
  import CivicCommentThread from './CivicCommentThread.svelte';
  import { outcomeIcon, outcomeClass, formatRelativeDate, googleCalendarUrl, downloadIcs } from '../utils/civic-helpers.js';

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
  let expandedAbstracts = $state(new Set<string>());

  function truncate(text: string, max: number): string {
    if (text.length <= max) return text;
    return text.slice(0, max).replace(/\s+\S*$/, '') + '...';
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

  // Reference time for relative date calculations (uses data timestamp for consistency with mock data)
  const referenceTime = $derived(data.generated_at ? new Date(data.generated_at) : new Date());

  // City focal points: meetings happening within 7 days
  const cityFocalMeetings = $derived(
    !isLegislative
      ? data.decisions_this_week.filter(m => {
          if (!m.meeting_datetime) return false;
          const meetingDate = new Date(m.meeting_datetime);
          const diffMs = meetingDate.getTime() - referenceTime.getTime();
          const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
          return diffDays >= 0 && diffDays <= 7;
        }).map(m => {
          const meetingDate = new Date(m.meeting_datetime);
          const diffMs = meetingDate.getTime() - referenceTime.getTime();
          const daysUntil = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
          const agendaItems = (data.upcoming_items || []).filter(i => i.meeting_title === m.title);
          return { ...m, days_until: daysUntil, agendaItems };
        })
      : []
  );
  const hasCityFocal = $derived(cityFocalMeetings.length > 0);
  const hasFocalPoints = $derived(hasCommentPeriods || hasHearings || hasGovernorsDesk || hasCityFocal);

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

  function urgencyClass(days: number): string {
    if (days <= 0) return 'urgent-closed';
    if (days <= 3) return 'urgent-critical';
    if (days <= 7) return 'urgent-soon';
    return 'urgent-normal';
  }

  // Look up meeting days_until for a city agenda item
  function meetingDaysUntil(meetingTitle: string): number | null {
    if (isLegislative) return null;
    const meeting = data.decisions_this_week.find(m => m.title === meetingTitle);
    if (!meeting?.meeting_datetime) return null;
    const meetingDate = new Date(meeting.meeting_datetime);
    const diffMs = meetingDate.getTime() - referenceTime.getTime();
    const days = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
    return days >= 0 ? days : null;
  }

  let expanded: Record<string, boolean> = $state({
    meetings: true,
    items: true,
    outcomes: false,
    commentPeriods: true,
    hearings: true,
    governorsDesk: true,
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
      const ok = await api.castComment(entityId, draft, jurisdiction, userStance);

      if (ok) {
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

<!-- Focal Points: Time-sensitive participation opportunities (shown first) -->
{#if hasFocalPoints}
  <div class="focal-points-group">
    <div class="focal-points-label">Take Action</div>

    <!-- Comment Periods (Federal) -->
    {#if hasCommentPeriods}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('commentPeriods')}>
          <span class="section-title">
            Comment Periods
            <span class="count-badge focal-badge">{data.comment_periods!.length}</span>
          </span>
          <span class="chevron" class:open={expanded.commentPeriods}></span>
        </button>
        {#if expanded.commentPeriods}
          <div class="section-body">
            <div class="section-hint">Your comment directly shapes federal policy — the agency must read and respond</div>
            {#each data.comment_periods! as period}
              {@const eid = `rule:${period.document_number}`}
              {@const counts = voiceCounts.get(eid)}
              <div class="card focal-card" class:dragging={draggingId === period.document_number}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeCommentPeriodContext(period), period.document_number)}
                   ondragend={handleDragEnd}>
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
                <div class="card-actions">
                  {#if period.comment_url && period.days_remaining >= 0}
                    <a href={period.comment_url} target="_blank" rel="noopener" class="action-link comment-link">Submit Official Comment</a>
                  {/if}
                  {#if period.html_url}
                    <a href={period.html_url} target="_blank" rel="noopener" class="action-link">Read Rule</a>
                  {/if}
                  {#if period.pdf_url}
                    <a href={period.pdf_url} target="_blank" rel="noopener" class="action-link">PDF</a>
                  {/if}
                </div>
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
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${period.document_number}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${period.document_number}`) ? 'Hide' : activeProviderName || 'Ask AI'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: composeCommentPeriodContext(period), event: e })}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
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
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('hearings')}>
          <span class="section-title">
            Upcoming Hearings
            <span class="count-badge focal-badge">{data.upcoming_hearings!.length}</span>
          </span>
          <span class="chevron" class:open={expanded.hearings}></span>
        </button>
        {#if expanded.hearings}
          <div class="section-body">
            <div class="section-hint">Hearings are open to public testimony — attend or submit written comments</div>
            {#each data.upcoming_hearings! as hearing}
              {@const eid = billEntityId(hearing.bill_id)}
              {@const counts = voiceCounts.get(eid)}
              <div class="card focal-card" class:dragging={draggingId === hearing.bill_id}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeHearingContext(hearing), hearing.bill_id)}
                   ondragend={handleDragEnd}>
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
                {#if hearing.official_url}
                  <div class="card-actions">
                    <a href={hearing.official_url} target="_blank" rel="noopener" class="action-link">View Bill</a>
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
                <!-- AI action row -->
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${hearing.bill_id}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${hearing.bill_id}`)}
                      onclick={() => askFocalAI(`ask-focal:${hearing.bill_id}`, composeHearingContext(hearing))}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${hearing.bill_id}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${hearing.bill_id}`) ? 'Hide' : activeProviderName || 'Ask AI'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: composeHearingContext(hearing), event: e })}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
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
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('governorsDesk')}>
          <span class="section-title">
            Awaiting Governor's Signature
            <span class="count-badge action-badge">{data.governors_desk!.length}</span>
          </span>
          <span class="chevron" class:open={expanded.governorsDesk}></span>
        </button>
        {#if expanded.governorsDesk}
          <div class="section-body">
            <div class="section-hint">Bills awaiting governor's signature — call now to influence the outcome</div>
            {#each data.governors_desk! as bill}
              {@const eid = billEntityId(bill.bill_id)}
              {@const counts = voiceCounts.get(eid)}
              <div class="card focal-card" class:dragging={draggingId === bill.bill_id}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeGovernorsDeskContext(bill), bill.bill_id)}
                   ondragend={handleDragEnd}>
                <div class="card-title">{bill.bill_number || bill.bill_id}</div>
                {#if bill.bill_name}
                  <div class="card-subtitle">{bill.bill_name}</div>
                {/if}
                {#if bill.summary}
                  <div class="card-summary">{bill.summary}</div>
                {/if}
                <div class="card-leverage">Call the Governor's office to express support or opposition</div>
                {#if counts && counts.total > 0}
                  <div class="card-meta">
                    <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
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
                <!-- AI action row -->
                <div class="ai-action-row">
                  {#if aiAvailable}
                    <button
                      class="ai-action-btn ai-action-ask"
                      class:active={aiResponses.has(`ask-focal:${bill.bill_id}`)}
                      disabled={aiResponseLoading.has(`ask-focal:${bill.bill_id}`)}
                      onclick={() => askFocalAI(`ask-focal:${bill.bill_id}`, composeGovernorsDeskContext(bill))}
                    >
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${bill.bill_id}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${bill.bill_id}`) ? 'Hide' : activeProviderName || 'Ask AI'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: composeGovernorsDeskContext(bill), event: e })}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
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

    <!-- Upcoming City Meetings (City) -->
    {#if hasCityFocal}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('cityFocal')}>
          <span class="section-title">
            Upcoming Meetings
            <span class="count-badge focal-badge">{cityFocalMeetings.length}</span>
          </span>
          <span class="chevron" class:open={expanded.cityFocal}></span>
        </button>
        {#if expanded.cityFocal}
          <div class="section-body">
            <div class="section-hint">Your voice shapes local decisions — attend or submit written comments</div>
            {#each cityFocalMeetings as meeting}
              {@const meetingId = `meeting:${meeting.title.toLowerCase().replace(/\s+/g, '-')}`}
              {@const focalContext = composeCityMeetingFocalContext(meeting)}
              <div class="card focal-card" class:dragging={draggingId === meetingId}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, focalContext, meetingId)}
                   ondragend={handleDragEnd}>
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
                      <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-focal:${meetingId}`) ? 'Thinking...' : aiResponses.has(`ask-focal:${meetingId}`) ? 'Hide' : activeProviderName || 'Ask AI'}
                    </button>
                  {/if}
                  {#if onopenexternalai}
                    <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: focalContext, event: e })}>
                      Claude <span class="ext-icon">&#x2197;</span>
                    </button>
                  {/if}
                </div>
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
  </div>
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
      {#if data.upcoming_items && data.upcoming_items.length > 0}
        <span class="count-badge">{data.upcoming_items.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.items}></span>
  </button>
  {#if expanded.items}
    <div class="section-body">
      {#if itemsHint}
        <div class="section-hint">{itemsHint}</div>
      {/if}
      {#if !data.upcoming_items || data.upcoming_items.length === 0}
        <div class="empty-section">{emptyItems}</div>
      {:else}
        {#each data.upcoming_items as item}
          {@const eid = item.id ? billEntityId(item.id) : ''}
          {@const counts = eid ? voiceCounts.get(eid) : undefined}
          {@const itemDaysUntil = item.meeting_title ? meetingDaysUntil(item.meeting_title) : null}
          <div class="card" class:dragging={draggingId === (item.id || item.title)}
               draggable="true"
               ondragstart={(e: DragEvent) => handleDragStart(e, composeLegislationContext(item), item.id || item.title)}
               ondragend={handleDragEnd}>
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
            {#if isLegislative}
              <div class="ai-action-row">
                {#if aiAvailable}
                  <button
                    class="ai-action-btn ai-action-ask"
                    class:active={aiResponses.has(`ask-leg:${item.id || item.title}`)}
                    disabled={aiResponseLoading.has(`ask-leg:${item.id || item.title}`)}
                    onclick={() => askFocalAI(`ask-leg:${item.id || item.title}`, composeLegislationContext(item))}
                  >
                    <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-leg:${item.id || item.title}`) ? 'Thinking...' : aiResponses.has(`ask-leg:${item.id || item.title}`) ? 'Hide' : activeProviderName || 'Ask AI'}
                  </button>
                {/if}
                {#if onopenexternalai}
                  <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: composeLegislationContext(item), event: e })}>
                    Claude <span class="ext-icon">&#x2197;</span>
                  </button>
                {/if}
              </div>
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
      {#if data.recent_outcomes.length > 0}
        <span class="count-badge">{data.recent_outcomes.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.outcomes}></span>
  </button>
  {#if expanded.outcomes}
    <div class="section-body">
      {#if outcomesHint}
        <div class="section-hint">{outcomesHint}</div>
      {/if}
      {#if data.recent_outcomes.length === 0}
        <div class="empty-section">{emptyOutcomes}</div>
      {:else}
        {#each data.recent_outcomes as outcome}
          {@const eid = outcome.id ? billEntityId(outcome.id) : ''}
          {@const counts = eid ? voiceCounts.get(eid) : undefined}
          <div class="card" class:dragging={draggingId === (outcome.id || outcome.title)}
               draggable="true"
               ondragstart={(e: DragEvent) => handleDragStart(e, composeOutcomeContext(outcome), outcome.id || outcome.title)}
               ondragend={handleDragEnd}>
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
  {@render children()}
{/if}

<footer class="pulse-footer">
  <span class="footer-ts">Updated {new Date(data.generated_at).toLocaleTimeString()}</span>
</footer>

<style>
  .feed-section { margin-bottom: 4px; }
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
  .section-title { display: flex; align-items: center; gap: 6px; }
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
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6b7280;
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }
  .section-body { padding: 4px 0 8px; }
  .empty-section {
    padding: 12px 8px;
    color: #4b5563;
    font-size: 12px;
    font-style: italic;
  }
  .card {
    background: #262626;
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 6px;
    border: 1px solid #374151;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: grab;
  }
  .card:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59,130,246,0.1);
  }
  .card:active { cursor: grabbing; }
  .card.dragging {
    opacity: 0.4;
    border-color: #3b82f6;
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
  .item-type {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: #374151;
    color: #9ca3af;
  }
  .status-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(59, 130, 246, 0.12);
    color: #60a5fa;
    font-weight: 500;
  }
  .card-link {
    color: inherit;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.15s ease;
  }
  .card-link:hover {
    border-bottom-color: #60a5fa;
    color: #93c5fd;
  }
  .card-summary {
    color: #d1d5db;
    font-size: 12px;
    line-height: 1.4;
    margin-top: 6px;
  }
  .expand-btn {
    background: none;
    border: none;
    color: #60a5fa;
    font-size: 12px;
    cursor: pointer;
    padding: 0 2px;
    text-decoration: underline;
  }
  .expand-btn:hover {
    color: #93bbfd;
  }
  .closed-results {
    margin-top: 6px;
    opacity: 0.7;
  }
  .doc-type-tag {
    font-size: 10px;
    text-transform: capitalize;
    color: #a5b4fc;
    background: rgba(99, 102, 241, 0.1);
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
    color: #9ca3af;
    background: rgba(107, 114, 128, 0.15);
    padding: 1px 6px;
    border-radius: 3px;
  }
  .card-leverage {
    color: #60a5fa;
    font-size: 11px;
    line-height: 1.4;
    margin-top: 4px;
    padding: 4px 8px;
    background: rgba(59, 130, 246, 0.06);
    border-left: 2px solid #3b82f6;
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
  .outcome-icon.passed { background: #14532d; color: #4ade80; }
  .outcome-icon.failed { background: #7f1d1d; color: #f87171; }
  .outcome-icon.upcoming { background: #1e3a5f; color: #60a5fa; }
  .outcome-icon.other { background: #374151; color: #9ca3af; }
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
    background: #262626;
    border-radius: 8px;
    padding: 10px 12px;
    border: 1px solid #374151;
  }
  .topic-name {
    color: #eee;
    font-size: 13px;
    font-weight: 500;
  }
  .topic-count {
    color: #60a5fa;
    font-size: 11px;
    font-weight: 600;
    margin-top: 2px;
  }
  .topic-breakdown {
    color: #6b7280;
    font-size: 10px;
    margin-top: 2px;
  }
  .card-desc {
    color: #9ca3af;
    font-size: 12px;
    line-height: 1.4;
    margin-top: 6px;
  }
  .card-voice {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid #374151;
  }
  .voice-count-badge {
    font-size: 10px;
    color: #60a5fa;
    font-weight: 500;
  }
  .card-subtitle {
    color: #d1d5db;
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
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
  }
  .deadline-tag.urgent-soon {
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
  }
  .deadline-tag.urgent-normal {
    background: rgba(59, 130, 246, 0.12);
    color: #60a5fa;
  }
  .deadline-tag.urgent-closed {
    background: rgba(107, 114, 128, 0.15);
    color: #6b7280;
  }
  .card-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .action-link {
    font-size: 11px;
    font-weight: 500;
    color: #60a5fa;
    text-decoration: none;
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.2);
    transition: all 0.15s ease;
  }
  .action-link:hover {
    background: rgba(59, 130, 246, 0.16);
    border-color: #3b82f6;
    color: #93c5fd;
  }
  .action-link.comment-link {
    color: #4ade80;
    background: rgba(74, 222, 128, 0.08);
    border-color: rgba(74, 222, 128, 0.2);
  }
  .action-link.comment-link:hover {
    background: rgba(74, 222, 128, 0.16);
    border-color: #4ade80;
    color: #86efac;
  }
  .action-badge {
    background: rgba(245, 158, 11, 0.15) !important;
    color: #fbbf24 !important;
  }
  .focal-points-group {
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #374151;
  }
  .focal-points-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #f59e0b;
    padding: 4px 4px 2px;
  }
  .voice-disclaimer {
    font-size: 11px;
    color: #9ca3af;
    font-style: italic;
    padding: 8px 8px 4px;
    margin-top: 4px;
    line-height: 1.4;
    border-top: 1px solid rgba(107, 114, 128, 0.2);
  }
  .focal-badge {
    background: rgba(245, 158, 11, 0.15) !important;
    color: #fbbf24 !important;
  }
  .focal-card {
    border-color: rgba(245, 158, 11, 0.2);
  }
  .focal-card:hover {
    border-color: #f59e0b;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.1);
  }
  .section-hint {
    font-size: 11px;
    color: #9ca3af;
    padding: 2px 8px 6px;
    font-style: italic;
  }
  .focal-agenda-preview {
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid #374151;
  }
  .focal-agenda-label {
    font-size: 10px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 4px;
  }
  .focal-agenda-item {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.4;
    padding: 2px 0;
  }
  .focal-agenda-bullet {
    color: #f59e0b;
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
    color: #6b7280;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover { color: #60a5fa; background: #374151; }
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
  .ai-action-claude.solo { flex: 1; }
  .sparkle { font-size: 10px; opacity: 0.7; }
  .ext-icon { font-size: 9px; }
  /* AI response */
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
  .ai-response-text.prose :global(ul), .ai-response-text.prose :global(ol) {
    margin: 4px 0 8px;
    padding-left: 18px;
  }
  .ai-response-text.prose :global(li) { margin-bottom: 2px; }
  .ai-response-provider {
    display: block;
    margin-top: 6px;
    font-size: 10px;
    color: #64748b;
  }
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
</style>

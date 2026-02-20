<script lang="ts">
  import CivicAgendaItemCard from './CivicAgendaItemCard.svelte';
  import CivicCommentThread from './CivicCommentThread.svelte';
  import CivicProcessBar from './CivicProcessBar.svelte';
  import { meetingDaysUntil, classifyTopics } from '../utils/civic-helpers.js';

  // Local type declarations (mirrors @civicos/client types)
  interface PulseAgendaItem {
    id: string;
    meeting_id: string;
    item_number: string;
    title: string;
    project_type?: string;
    stance_eligible: boolean;
    comment_eligible: boolean;
    description: string;
    why_it_matters: string;
    meeting_title: string;
    meeting_date: string;
  }

  interface VoiceCounts {
    support: number;
    oppose: number;
    watching: number;
    total: number;
    attested?: number;
    unattested?: number;
  }

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

  type Stance = 'support' | 'oppose' | 'watching';

  // --- Props (shared state from parent) ---

  let {
    items = [] as PulseAgendaItem[],
    voiceCounts = new Map<string, VoiceCounts>(),
    userStances = new Map<string, Stance>(),
    votingInProgress = new Set<string>(),
    commentCounts = new Map<string, CommentCounts>(),
    synthData: parentSynthData = new Map<string, CommentSynthesis>(),
    identity = null as { publicKey: string; isUnlocked?: boolean } | null,
    aiAvailable = false,
    activeProviderName = '',
    jurisdiction = '',
    clerkEmail = '',
    session = null as any,
    api = null as any,
    renderMarkdown = (text: string) => text,
    // Meeting data for urgency badges
    meetings = [] as Array<{ title: string; meeting_datetime: string }>,
    generatedAt = '',
    // Callbacks to parent
    onvoice = undefined as ((detail: { entityId: string; stance: Stance }) => void) | undefined,
    onopenexternalai = undefined as ((detail: { context: string; event: MouseEvent }) => void) | undefined,
    ontoast = undefined as ((message: string) => void) | undefined,
    oncommentcountchange = undefined as ((entityId: string, counts: CommentCounts) => void) | undefined,
    highlightedCardId = null as string | null,
  } = $props();

  const referenceTime = $derived(generatedAt ? new Date(generatedAt) : new Date());

  function getItemDaysUntil(meetingTitle: string): number | null {
    if (!meetings.length) return null;
    return meetingDaysUntil(meetingTitle, meetings, referenceTime);
  }

  function getItemStage(item: PulseAgendaItem): 'posted' | 'comment' | 'vote' {
    const days = getItemDaysUntil(item.meeting_title);
    if (days !== null && days <= 0) return 'vote';
    if (item.comment_eligible) return 'comment';
    return 'posted';
  }

  // --- Topic classification & filtering ---

  let itemTopics = $derived(new Map(items.map(i => [i.id, classifyTopics(i.title, i.description)])));

  let availableTopics = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const topics of itemTopics.values()) {
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

  let filteredItems = $derived.by(() => {
    if (selectedTopics.size === 0) return items;
    return items.filter(i => {
      const topics = itemTopics.get(i.id) || [];
      return topics.some(t => selectedTopics.has(t));
    });
  });

  // --- Internal state (owned by this component) ---

  let openThreads = $state(new Set<string>());
  let threadComments = $state(new Map<string, Comment[]>());
  let threadDrafts = $state(new Map<string, string>());
  let threadSubmitting = $state(new Set<string>());
  let threadLoading = $state(new Set<string>());
  let threadErrors = $state(new Map<string, string>());
  let localSynthData = $state(new Map<string, CommentSynthesis>());
  let draftingInProgress = $state(new Set<string>());
  let enrichingInProgress = $state(new Set<string>());
  let aiResponses = $state(new Map<string, string>());
  let aiResponseLoading = $state(new Set<string>());
  let aiResponseHidden = $state(new Set<string>());
  let cardDrafts = $state(new Map<string, string>());
  let shakingCardId: string | null = $state(null);

  // Merge parent synth data with locally-loaded synth data (local wins)
  function getSynthesis(entityId: string): CommentSynthesis | null {
    return localSynthData.get(entityId) ?? parentSynthData.get(entityId) ?? null;
  }

  // --- Comment Thread Handlers ---

  async function toggleCommentThread(entityId: string) {
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
        // Pre-fill draft with user's existing comment for editing
        if (identity?.publicKey) {
          const mine = thread.comments.find((c: Comment) => c.public_key === identity!.publicKey);
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
          jurisdiction: jurisdiction,
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
          const prev = commentCounts.get(entityId) || { entity: entityId, count: 0 };
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

  // --- AI Handlers ---

  async function askAI(key: string, context: string) {
    // Toggle visibility if already cached
    if (aiResponses.has(key)) {
      if (aiResponseHidden.has(key)) {
        aiResponseHidden.delete(key);
      } else {
        aiResponseHidden.add(key);
      }
      aiResponseHidden = new Set(aiResponseHidden);
      return;
    }

    if (!aiAvailable) return;

    aiResponseLoading.add(key);
    aiResponseLoading = new Set(aiResponseLoading);

    try {
      const answer = await session.askQuestion(context);
      if (answer) {
        aiResponses.set(key, answer);
        aiResponses = new Map(aiResponses);
        aiResponseHidden.delete(key);
        aiResponseHidden = new Set(aiResponseHidden);
      } else {
        ontoast?.('AI request failed');
      }
    } catch (err: unknown) {
      ontoast?.(`AI request failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    }

    aiResponseLoading.delete(key);
    aiResponseLoading = new Set(aiResponseLoading);
  }

  async function regenerateAI(key: string, context: string) {
    aiResponses.delete(key);
    aiResponses = new Map(aiResponses);
    aiResponseHidden.delete(key);
    aiResponseHidden = new Set(aiResponseHidden);
    await askAI(key, context);
  }

  async function handleDraftWithAI(entityId: string, item: PulseAgendaItem) {
    draftingInProgress.add(entityId);
    draftingInProgress = new Set(draftingInProgress);

    try {
      const stance = userStances.get(entityId);
      const counts = voiceCounts.get(entityId);
      const draft = await session.draftComment(item, stance, counts);

      if (!draft) {
        ontoast?.('AI drafting failed');
        draftingInProgress.delete(entityId);
        draftingInProgress = new Set(draftingInProgress);
        return;
      }

      threadDrafts.set(entityId, draft);
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
          } catch {
            // Non-critical — draft is already in textarea
          }
          threadLoading.delete(entityId);
          threadLoading = new Set(threadLoading);
        }
      }
    } catch {
      ontoast?.('AI drafting failed — try again');
    }

    draftingInProgress.delete(entityId);
    draftingInProgress = new Set(draftingInProgress);
  }

  async function handleEnrichDraft(entityId: string, item: PulseAgendaItem) {
    const draft = (threadDrafts.get(entityId) || '').trim();
    if (!draft) return;

    enrichingInProgress.add(entityId);
    enrichingInProgress = new Set(enrichingInProgress);

    try {
      const enriched = await session.enrichDraft(draft, item.id);
      if (!enriched) {
        ontoast?.('Enrichment failed');
        enrichingInProgress.delete(entityId);
        enrichingInProgress = new Set(enrichingInProgress);
        return;
      }

      threadDrafts.set(entityId, enriched);
      threadDrafts = new Map(threadDrafts);
    } catch {
      ontoast?.('Enrichment failed — server may be unavailable');
    }

    enrichingInProgress.delete(entityId);
    enrichingInProgress = new Set(enrichingInProgress);
  }

  // --- Drag-to-AI ---

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  let draggingItem = $state<string | null>(null);

  function handleDragStart(e: DragEvent, item: PulseAgendaItem) {
    const markdown = composeAgendaContext(item);
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    draggingItem = item.id;
  }

  function handleDragEnd() {
    draggingItem = null;
  }

  // --- Context Composition ---

  function composeSentimentBlock(entityId: string): string[] {
    const lines: string[] = [];
    const counts = voiceCounts.get(entityId);
    const synth = getSynthesis(entityId);
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
        const shown = Math.min(visible.length, 8);
        lines.push('', `Resident comments (showing ${shown} of ${visible.length}, most recent first):`);
        for (const c of visible.slice(0, 8)) {
          const stanceTag = c.stance ? ` [${c.stance}]` : '';
          lines.push(`- "${c.comment_text}"${stanceTag}`);
        }
      }
    }
    return lines;
  }

  function composeAgendaContext(item: PulseAgendaItem): string {
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || 'my city';
    const lines = [
      `--- CivicOS Context: Agenda Item ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${item.title}**`,
      `Meeting: ${item.meeting_title} (${item.meeting_date})`,
    ];
    if (item.item_number) lines.push(`Item #${item.item_number}`);
    if (item.project_type) lines.push(`Type: ${item.project_type}`);
    if (item.description) lines.push('', item.description);
    if (item.why_it_matters) lines.push('', `Why it matters: ${item.why_it_matters}`);
    lines.push(...composeSentimentBlock(`agenda-item:${item.id}`));
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What are the key implications for residents? If community sentiment data is available, summarize what residents are saying and the key themes. What questions should I ask at the public hearing?');
    return lines.join('\n');
  }

  function composeThreadSummary(item: PulseAgendaItem, entityId: string): string {
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

  function getMailtoLink(item: PulseAgendaItem, draft?: string): string {
    if (!clerkEmail) return '';
    const subject = `Public Comment - Item ${item.item_number}: ${item.title} - ${item.meeting_title} ${item.meeting_date}`;
    const body = draft
      ? `${draft}\n\n---\nRegarding: ${item.title}\nMeeting: ${item.meeting_title}, ${item.meeting_date}\nItem: ${item.item_number}`
      : `[Your comment here]\n\nRegarding: ${item.title}\nMeeting: ${item.meeting_title}, ${item.meeting_date}\nItem: ${item.item_number}`;
    return `mailto:${encodeURIComponent(clerkEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }

  async function handleCardDraft(entityId: string, item: PulseAgendaItem) {
    draftingInProgress.add(entityId);
    draftingInProgress = new Set(draftingInProgress);

    try {
      const stance = userStances.get(entityId);
      const counts = voiceCounts.get(entityId);
      const draft = await session.draftComment(item, stance, counts);

      if (draft) {
        cardDrafts.set(entityId, draft);
        cardDrafts = new Map(cardDrafts);
      } else {
        ontoast?.('AI drafting failed');
      }
    } catch {
      ontoast?.('AI drafting failed — try again');
    }

    draftingInProgress.delete(entityId);
    draftingInProgress = new Set(draftingInProgress);
  }

  function routeDraftToThread(entityId: string) {
    const draft = cardDrafts.get(entityId);
    if (!draft) return;

    threadDrafts.set(entityId, draft);
    threadDrafts = new Map(threadDrafts);

    cardDrafts.delete(entityId);
    cardDrafts = new Map(cardDrafts);

    if (!openThreads.has(entityId)) {
      openThreads.add(entityId);
      openThreads = new Set(openThreads);
      if (!threadComments.has(entityId)) {
        threadLoading.add(entityId);
        threadLoading = new Set(threadLoading);
        session.loadCommentThread(entityId)
          .then((thread: { comments: Comment[]; synthesis?: CommentSynthesis }) => {
            threadComments.set(entityId, thread.comments);
            threadComments = new Map(threadComments);
            if (thread.synthesis) {
              localSynthData.set(entityId, thread.synthesis);
              localSynthData = new Map(localSynthData);
            }
          })
          .catch(() => {})
          .finally(() => {
            threadLoading.delete(entityId);
            threadLoading = new Set(threadLoading);
          });
      }
    }
  }
</script>

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

{#each filteredItems as item}
  <div class="card item-card" id="card-{item.id}"
       class:dragging={draggingItem === item.id}
       class:highlighted={highlightedCardId === item.id}
       class:shaking={shakingCardId === item.id}
       draggable="true"
       ondragstart={(e: DragEvent) => handleDragStart(e, item)}
       ondragend={handleDragEnd}>
    <CivicProcessBar level="city" stage={getItemStage(item)} />
    <CivicAgendaItemCard
      {item}
      topics={itemTopics.get(item.id) || []}
      voiceCounts={voiceCounts.get(`agenda-item:${item.id}`) ?? null}
      userStance={userStances.get(`agenda-item:${item.id}`) ?? null}
      votingDisabled={votingInProgress.has(`agenda-item:${item.id}`)}
      locked={identity ? !identity.isUnlocked : true}
      showVoice={item.stance_eligible && !!identity}
      daysUntil={getItemDaysUntil(item.meeting_title)}
      onvoice={({ entityId, stance }: { entityId: string; stance: Stance }) => onvoice?.({ entityId, stance })}
    />
    <!-- Draft with AI + Official Comment row -->
    {#if item.comment_eligible}
      {@const commentEntityId = `agenda-item:${item.id}`}
      {#if !cardDrafts.has(commentEntityId)}
        <div class="action-btn-row">
          {#if aiAvailable}
            <button class="action-btn action-btn-draft" onclick={() => handleCardDraft(commentEntityId, item)} disabled={draftingInProgress.has(commentEntityId)}>
              <span class="sparkle">&#x2726;</span> {draftingInProgress.has(commentEntityId) ? 'Drafting...' : 'Draft with AI'}
            </button>
          {/if}
          {#if clerkEmail}
            <a class="action-btn action-btn-official" href={getMailtoLink(item)}>
              <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 4l6 4 6-4M2 4v8h12V4H2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
              Submit Official Comment
            </a>
          {/if}
          <button class="action-btn action-btn-unofficial" class:active={openThreads.has(commentEntityId)} onclick={() => toggleCommentThread(commentEntityId)}>
            <svg class="action-btn-icon" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
            Unofficial Comment
            {#if (commentCounts.get(commentEntityId)?.count || 0) > 0}<span class="action-btn-count">{commentCounts.get(commentEntityId)?.count}</span>{/if}
            <span class="action-btn-chevron" class:open={openThreads.has(commentEntityId)}></span>
          </button>
        </div>
      {/if}
      {#if cardDrafts.has(commentEntityId)}
        <div class="card-draft">
          <textarea class="card-draft-text" rows={4} value={cardDrafts.get(commentEntityId)} oninput={(e: Event) => { cardDrafts.set(commentEntityId, (e.target as HTMLTextAreaElement).value); cardDrafts = new Map(cardDrafts); }}></textarea>
          <div class="card-draft-actions">
            {#if clerkEmail}
              <a class="card-draft-btn card-draft-official" href={getMailtoLink(item, cardDrafts.get(commentEntityId))} onclick={() => { cardDrafts.delete(commentEntityId); cardDrafts = new Map(cardDrafts); }}>
                Submit as Official Comment
              </a>
            {/if}
            <button class="card-draft-btn card-draft-community" onclick={() => routeDraftToThread(commentEntityId)}>
              Post as Community Comment
            </button>
            <button class="card-draft-btn card-draft-discard" onclick={() => { cardDrafts.delete(commentEntityId); cardDrafts = new Map(cardDrafts); }}>Discard</button>
          </div>
        </div>
      {/if}

      <!-- Comment Thread -->
      <CivicCommentThread
        entityId={commentEntityId}
        commentCount={commentCounts.get(commentEntityId)?.count || 0}
        attestedCount={commentCounts.get(commentEntityId)?.attested ?? 0}
        comments={threadComments.get(commentEntityId) || []}
        synthesis={getSynthesis(commentEntityId)}
        expanded={openThreads.has(commentEntityId)}
        loading={threadLoading.has(commentEntityId)}
        submitting={threadSubmitting.has(commentEntityId)}
        error={threadErrors.get(commentEntityId) || ''}
        draft={threadDrafts.get(commentEntityId) || ''}
        userPublicKey={identity?.publicKey || ''}
        isUnlocked={identity?.isUnlocked ?? false}
        hasIdentity={!!identity}
        {aiAvailable}
        {activeProviderName}
        draftLoading={draftingInProgress.has(commentEntityId)}
        enrichLoading={enrichingInProgress.has(commentEntityId)}
        summarizeLoading={aiResponseLoading.has(`summarize-thread:${commentEntityId}`)}
        summaryHtml={renderMarkdown(aiResponses.get(`summarize-thread:${commentEntityId}`) ?? '')}
        showSummary={aiResponses.has(`summarize-thread:${commentEntityId}`)}
        {clerkEmail}
        mailtoHref={clerkEmail ? getMailtoLink(item) : ''}
        ontoggle={() => toggleCommentThread(commentEntityId)}
        onsubmit={() => handleSubmitComment(commentEntityId)}
        ondraftchange={({ text }: { text: string }) => { threadDrafts.set(commentEntityId, text); threadDrafts = new Map(threadDrafts); }}
        ondraft={() => handleDraftWithAI(commentEntityId, item)}
        onenrich={() => handleEnrichDraft(commentEntityId, item)}
        onsummarize={() => askAI(`summarize-thread:${commentEntityId}`, composeThreadSummary(item, commentEntityId))}
      />
    {/if}

    <div class="ai-action-row">
      {#if aiAvailable}
        <button
          class="ai-action-btn ai-action-ask"
          class:active={aiResponses.has(`ask-agenda:${item.id}`) && !aiResponseHidden.has(`ask-agenda:${item.id}`)}
          disabled={aiResponseLoading.has(`ask-agenda:${item.id}`)}
          onclick={() => askAI(`ask-agenda:${item.id}`, composeAgendaContext(item))}
        >
          <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-agenda:${item.id}`) ? 'Thinking...' : aiResponses.has(`ask-agenda:${item.id}`) && !aiResponseHidden.has(`ask-agenda:${item.id}`) ? 'Hide' : 'Summary'}
        </button>
      {/if}
      <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => { onopenexternalai?.({ context: composeAgendaContext(item), event: e }); shakingCardId = item.id; setTimeout(() => { shakingCardId = null; }, 2500); }}>
        Claude <span class="ext-icon">&#x2197;</span>
      </button>
    </div>
    {#if shakingCardId === item.id}
      <div class="drag-hint">
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M8 2L5 5M8 2l3 3M2 8h12M2 8l3-3M2 8l3 3M14 8l-3-3M14 8l-3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Drag this card into Claude's input
      </div>
    {/if}
    {#if aiResponses.has(`ask-agenda:${item.id}`) && !aiResponseHidden.has(`ask-agenda:${item.id}`)}
      <div class="ai-response">
        <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(`ask-agenda:${item.id}`) ?? '')}</div>
        <div class="ai-response-footer">
          {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
          <button class="ai-regenerate-btn" onclick={() => regenerateAI(`ask-agenda:${item.id}`, composeAgendaContext(item))} disabled={aiResponseLoading.has(`ask-agenda:${item.id}`)}>
            Regenerate
          </button>
        </div>
      </div>
    {/if}
  </div>
{/each}

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
    border: 1px solid #333;
    background: transparent;
    color: #6b7280;
    font-size: 10px;
    font-weight: 500;
    cursor: pointer;
    transition: all 150ms;
    font-family: inherit;
  }
  .topic-filter-pill:hover {
    color: #9ca3af;
    border-color: #4b5563;
  }
  .topic-filter-pill.active {
    background: rgba(96, 165, 250, 0.1);
    border-color: rgba(96, 165, 250, 0.3);
    color: #60a5fa;
  }
  .topic-filter-clear {
    padding: 3px 8px;
    border-radius: 10px;
    border: none;
    background: none;
    color: #4b5563;
    font-size: 10px;
    cursor: pointer;
    font-family: inherit;
  }
  .topic-filter-clear:hover { color: #6b7280; }

  .card {
    background: #1e1e1e;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 4px;
    border: 1px solid #262626;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: grab;
  }
  .card:hover {
    border-color: #374151;
  }
  .card:active { cursor: grabbing; }
  .card.dragging {
    opacity: 0.4;
    border-color: #4b5563;
  }
  .card.highlighted {
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.2);
    border-color: #4b5563;
    animation: highlight-fade 2s ease-out forwards;
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
    color: #9ca3af;
    padding: 6px 10px;
    background: rgba(255, 255, 255, 0.04);
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
  @keyframes highlight-fade {
    0% { box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.3); }
    100% { box-shadow: none; border-color: #262626; }
  }
  .card.highlighted {
    border-color: #4b5563;
    box-shadow: inset 3px 0 0 #fff, 0 0 12px rgba(255,255,255,0.06);
    transition: border-color 0.15s ease, box-shadow 0.3s ease, opacity 0.15s ease;
  }

  /* === Draft / Official Comment row (matches ai-action-row) === */
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
    color: #a78bfa;
    background: rgba(139,92,246,0.06);
    border: 1px solid rgba(139,92,246,0.2);
  }
  .action-btn-draft:hover:not(:disabled) {
    background: rgba(139,92,246,0.14);
    border-color: #a78bfa;
    color: #c4b5fd;
  }
  .action-btn-draft:disabled { opacity: 0.6; cursor: default; }
  .action-btn-official {
    color: #4ade80;
    background: rgba(74,222,128,0.06);
    border: 1px solid rgba(74,222,128,0.2);
  }
  .action-btn-official:hover {
    background: rgba(74,222,128,0.14);
    border-color: #4ade80;
    color: #86efac;
  }
  .action-btn-unofficial {
    color: #9ca3af;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .action-btn-unofficial:hover {
    background: rgba(255,255,255,0.08);
    border-color: rgba(255,255,255,0.15);
    color: #d1d5db;
  }
  .action-btn-unofficial.active {
    background: rgba(255,255,255,0.08);
    border-color: rgba(255,255,255,0.15);
    color: #e5e7eb;
  }
  .action-btn .sparkle { font-size: 10px; opacity: 0.7; }
  .action-btn-icon { opacity: 0.6; flex-shrink: 0; vertical-align: -2.5px; }
  .action-btn-count {
    font-size: 10px;
    font-weight: 600;
    background: rgba(255, 255, 255, 0.08);
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

  /* === Card-level draft area === */
  .card-draft {
    margin-top: 8px;
    border: 1px solid rgba(139, 92, 246, 0.15);
    border-radius: 8px;
    padding: 8px;
    background: rgba(139, 92, 246, 0.04);
  }
  .card-draft-text {
    width: 100%;
    background: transparent;
    border: none;
    color: #d1d5db;
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
    font-family: inherit;
    outline: none;
    box-sizing: border-box;
  }
  .card-draft-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }
  .card-draft-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 500;
    padding: 5px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    text-decoration: none;
    font-family: inherit;
  }
  .card-draft-official {
    color: #4ade80;
    background: rgba(74, 222, 128, 0.08);
    border: 1px solid rgba(74, 222, 128, 0.2);
  }
  .card-draft-official:hover {
    background: rgba(74, 222, 128, 0.16);
    border-color: #4ade80;
  }
  .card-draft-community {
    color: #9ca3af;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
  }
  .card-draft-community:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.15);
    color: #d1d5db;
  }
  .card-draft-discard {
    color: #6b7280;
    background: none;
    border: none;
    margin-left: auto;
  }
  .card-draft-discard:hover { color: #9ca3af; }
  .card-draft-btn svg { opacity: 0.7; }

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
  .ai-response-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 6px;
  }
  .ai-response-provider {
    font-size: 10px;
    color: #64748b;
  }
  .ai-regenerate-btn {
    font-size: 10px;
    color: #6b7280;
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;
    transition: color 0.15s, background 0.15s;
  }
  .ai-regenerate-btn:hover:not(:disabled) {
    color: #9ca3af;
    background: rgba(255,255,255,0.06);
  }
  .ai-regenerate-btn:disabled { opacity: 0.5; cursor: default; }
</style>

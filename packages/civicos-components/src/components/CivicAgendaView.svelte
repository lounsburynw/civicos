<script lang="ts">
  import CivicAgendaItemCard from './CivicAgendaItemCard.svelte';
  import CivicCommentThread from './CivicCommentThread.svelte';
  import { meetingDaysUntil } from '../utils/civic-helpers.js';

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
  } = $props();

  const referenceTime = $derived(generatedAt ? new Date(generatedAt) : new Date());

  function getItemDaysUntil(meetingTitle: string): number | null {
    if (!meetings.length) return null;
    return meetingDaysUntil(meetingTitle, meetings, referenceTime);
  }

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
    if (aiResponses.has(key)) {
      aiResponses.delete(key);
      aiResponses = new Map(aiResponses);
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
      } else {
        ontoast?.('AI request failed');
      }
    } catch (err: unknown) {
      ontoast?.(`AI request failed: ${err instanceof Error ? err.message : 'unknown error'}`);
    }

    aiResponseLoading.delete(key);
    aiResponseLoading = new Set(aiResponseLoading);
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

  function getMailtoLink(item: PulseAgendaItem): string {
    if (!clerkEmail) return '';
    const subject = `Public Comment - Item ${item.item_number}: ${item.title} - ${item.meeting_title} ${item.meeting_date}`;
    const body = `[Paste your drafted comment here]\n\nRegarding: ${item.title}\nMeeting: ${item.meeting_title}, ${item.meeting_date}\nItem: ${item.item_number}`;
    return `mailto:${encodeURIComponent(clerkEmail)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }
</script>

{#each items as item}
  <div class="card item-card" class:dragging={draggingItem === item.id}
       draggable="true"
       ondragstart={(e: DragEvent) => handleDragStart(e, item)}
       ondragend={handleDragEnd}>
    <CivicAgendaItemCard
      {item}
      voiceCounts={voiceCounts.get(`agenda-item:${item.id}`) ?? null}
      userStance={userStances.get(`agenda-item:${item.id}`) ?? null}
      votingDisabled={votingInProgress.has(`agenda-item:${item.id}`)}
      locked={identity ? !identity.isUnlocked : true}
      showVoice={item.stance_eligible && !!identity}
      daysUntil={getItemDaysUntil(item.meeting_title)}
      onvoice={({ entityId, stance }: { entityId: string; stance: Stance }) => onvoice?.({ entityId, stance })}
    />
    <!-- Comment Thread -->
    {#if item.comment_eligible}
      {@const commentEntityId = `agenda-item:${item.id}`}
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
          <span class="sparkle">&#x2726;</span> {aiResponseLoading.has(`ask-agenda:${item.id}`) ? 'Thinking...' : aiResponses.has(`ask-agenda:${item.id}`) ? 'Hide' : activeProviderName}
        </button>
      {/if}
      <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: composeAgendaContext(item), event: e })}>
        Claude <span class="ext-icon">&#x2197;</span>
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

<style>
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
  .ai-response-provider {
    display: block;
    margin-top: 6px;
    font-size: 10px;
    color: #64748b;
  }
</style>

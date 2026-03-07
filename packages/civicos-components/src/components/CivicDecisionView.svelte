<script lang="ts">
  import CivicDecisionCard from './CivicDecisionCard.svelte';
  import CivicProcessBar from './CivicProcessBar.svelte';
  import { classifyTopics } from '../utils/civic-helpers.js';

  // Local type declarations (mirrors @civicos/client types)
  interface PulseOutcome {
    id: string;
    title: string;
    outcome: string;
    outcome_description?: string;
    is_upcoming?: boolean;
    vote_tally?: string;
    date: string;
  }

  interface VoiceCounts {
    support: number;
    oppose: number;
    watching: number;
    total: number;
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

  interface TestimonyComment {
    speaker: string;
    text: string;
    video_url?: string;
    start_timestamp?: string;
  }

  interface DecisionDetailData {
    found: boolean;
    summary?: string;
    is_upcoming?: boolean;
    decision?: {
      id: string;
      title: string;
      outcome: string;
      outcome_description?: string;
      date: string;
      body?: string;
      votes?: Record<string, number>;
    };
    testimony?: {
      public_comments?: TestimonyComment[];
      council_discussion?: TestimonyComment[];
    };
    related_decisions?: Array<{
      title: string;
      outcome: string;
      date: string;
    }>;
  }

  type Stance = 'support' | 'oppose' | 'watching';

  // --- Props (shared state from parent) ---

  let {
    decisions = [] as PulseOutcome[],
    voiceCounts = new Map<string, VoiceCounts>(),
    userStances = new Map<string, Stance>(),
    votingInProgress = new Set<string>(),
    synthData = new Map<string, CommentSynthesis>(),
    identity = null as { publicKey: string; isUnlocked?: boolean } | null,
    aiAvailable = false,
    activeProviderName = '',
    jurisdiction = '',
    session = null as any,
    renderMarkdown = (text: string) => text,
    // Callbacks to parent
    onvoice = undefined as ((detail: { entityId: string; stance: Stance }) => void) | undefined,
    onopenexternalai = undefined as ((detail: { context: string; event: MouseEvent }) => void) | undefined,
    ontoast = undefined as ((message: string) => void) | undefined,
  } = $props();

  // --- Topic classification & filtering ---

  let decisionTopics = $derived(new Map(decisions.map(d => [d.id, classifyTopics(d.title, d.outcome_description)])));

  let availableTopics = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const topics of decisionTopics.values()) {
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

  let filteredDecisions = $derived.by(() => {
    if (selectedTopics.size === 0) return decisions;
    return decisions.filter(d => {
      const topics = decisionTopics.get(d.id) || [];
      return topics.some(t => selectedTopics.has(t));
    });
  });

  // --- Internal state (owned by this component) ---

  let expandedDecisions = $state(new Set<string>());
  let decisionDetails = $state(new Map<string, DecisionDetailData>());
  let decisionLoading = $state(new Set<string>());
  let expandedTestimony = $state(new Set<string>());
  let expandedCouncil = $state(new Set<string>());
  let aiResponses = $state(new Map<string, string>());
  let aiResponseLoading = $state(new Set<string>());

  // --- Decision Detail Handler ---

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
        const detail = await session.loadDecisionDetail(title);
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

  // --- Drag-to-AI ---

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  let draggingDecision = $state<string | null>(null);

  function handleDragStart(e: DragEvent, decision: PulseOutcome) {
    const markdown = composeDecisionContext(decision);
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    draggingDecision = decision.id;
  }

  function handleDragEnd() {
    draggingDecision = null;
  }

  // --- Context Composition ---

  function composeSentimentBlock(entityId: string): string[] {
    const lines: string[] = [];
    const counts = voiceCounts.get(entityId);
    const synth = synthData.get(entityId);

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
    return lines;
  }

  function composeDecisionContext(decision: PulseOutcome): string {
    const detail = decisionDetails.get(decision.title);
    const today = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const source = jurisdiction || 'my city';
    const lines = [
      `--- CivicOS Context: Decision ---`,
      `Source: CivicOS (${source}) | ${today}`,
      '',
      `**${decision.title}**`,
      `Outcome: ${decision.outcome}`,
      `Date: ${decision.date}`,
    ];
    if (decision.vote_tally) lines.push(`Vote: ${decision.vote_tally}`);
    if (detail?.decision?.body) lines.push('', detail.decision.body);
    if (detail?.testimony?.public_comments && detail.testimony.public_comments.length > 0) {
      const total = detail.testimony.public_comments.length;
      const shown = Math.min(total, 8);
      lines.push('', `--- Public Testimony (showing ${shown} of ${total} speakers) ---`);
      for (const c of detail.testimony.public_comments.slice(0, 8)) {
        lines.push(`- **${c.speaker}:** ${c.text}`);
      }
    }
    if (detail?.testimony?.council_discussion && detail.testimony.council_discussion.length > 0) {
      const total = detail.testimony.council_discussion.length;
      const shown = Math.min(total, 6);
      lines.push('', `--- Council Discussion (showing ${shown} of ${total} excerpts) ---`);
      for (const c of detail.testimony.council_discussion.slice(0, 6)) {
        lines.push(`- **${c.speaker}:** ${c.text}`);
      }
    }
    lines.push(...composeSentimentBlock(decision.id));
    lines.push('', '--- End Context ---');
    lines.push('', 'Suggested question: What are the implications of this decision for residents? If testimony or community sentiment data is available, summarize the key themes and concerns raised. What should I know about this issue going forward?');
    return lines.join('\n');
  }

  function composeTestimonySummary(decision: PulseOutcome, comments: TestimonyComment[]): string {
    const lines = [
      `Summarize the public testimony from this civic decision in ${jurisdiction || 'my city'}:`,
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
</script>

{#if decisions.length === 0}
  <div class="empty-section">No recent decisions</div>
{:else}
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
  {#each filteredDecisions as decision}
    <div class="card decision-card" class:expanded-card={expandedDecisions.has(decision.title)}
         class:dragging={draggingDecision === decision.id}
         draggable="true"
         ondragstart={(e: DragEvent) => handleDragStart(e, decision)}
         ondragend={handleDragEnd}>
      <CivicProcessBar level="city" stage="vote" />
      <CivicDecisionCard
        {decision}
        topics={decisionTopics.get(decision.id) || []}
        expanded={expandedDecisions.has(decision.title)}
        detail={decisionDetails.get(decision.title) ?? null}
        detailLoading={decisionLoading.has(decision.title)}
        voiceCounts={voiceCounts.get(decision.id) ?? null}
        userStance={userStances.get(decision.id) ?? null}
        votingDisabled={votingInProgress.has(decision.id)}
        locked={identity ? !identity.isUnlocked : true}
        showVoice={!!identity}
        expandedTestimony={expandedTestimony.has(decision.title)}
        expandedCouncil={expandedCouncil.has(decision.title)}
        {aiAvailable}
        {activeProviderName}
        decisionAiLoading={aiResponseLoading.has(`ask-decision:${decision.id}`)}
        decisionAiHtml={aiResponses.has(`ask-decision:${decision.id}`) ? renderMarkdown(aiResponses.get(`ask-decision:${decision.id}`) ?? '') : ''}
        testimonyAiLoading={aiResponseLoading.has(`ask-testimony:${decision.id}`)}
        testimonyAiHtml={aiResponses.has(`ask-testimony:${decision.id}`) ? renderMarkdown(aiResponses.get(`ask-testimony:${decision.id}`) ?? '') : ''}
        onexpand={() => toggleDecisionDetail(decision.title)}
        onvoice={({ entityId, stance }) => onvoice?.({ entityId, stance })}
        onaskdecision={() => askAI(`ask-decision:${decision.id}`, composeDecisionContext(decision))}
        onasktestimony={() => { const t = decisionDetails.get(decision.title)?.testimony?.public_comments ?? []; askAI(`ask-testimony:${decision.id}`, composeTestimonySummary(decision, t)); }}
        onexternaldecision={(e) => onopenexternalai?.({ context: composeDecisionContext(decision), event: e })}
        onexternaltestimony={(e) => { const t = decisionDetails.get(decision.title)?.testimony?.public_comments ?? []; onopenexternalai?.({ context: composeTestimonySummary(decision, t), event: e }); }}
        ontoggletestimony={() => { if (expandedTestimony.has(decision.title)) { expandedTestimony.delete(decision.title); } else { expandedTestimony.add(decision.title); } expandedTestimony = new Set(expandedTestimony); }}
        ontogglecouncil={() => { if (expandedCouncil.has(decision.title)) { expandedCouncil.delete(decision.title); } else { expandedCouncil.add(decision.title); } expandedCouncil = new Set(expandedCouncil); }}
      />
    </div>
  {/each}
{/if}

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
  .expanded-card {
    border: 1px solid var(--civic-surface-elevated);
  }
  .empty-section {
    color: var(--civic-text-dim);
    font-size: 12px;
    padding: 8px 0;
    text-align: center;
  }
</style>

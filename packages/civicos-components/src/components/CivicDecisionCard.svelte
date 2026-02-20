<svelte:options customElement="civic-decision-card" />

<script lang="ts">
  import CivicVoiceButtons from './CivicVoiceButtons.svelte';
  import { outcomeIcon, outcomeClass } from '../utils/civic-helpers.js';

  type Stance = 'support' | 'oppose' | 'watching';

  interface TestimonyComment {
    speaker: string;
    text: string;
    video_url?: string;
    start_timestamp?: string;
  }

  interface DecisionDetail {
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

  let {
    decision,
    expanded = false,
    detail = null as DecisionDetail | null,
    detailLoading = false,
    voiceCounts = null,
    userStance = null as Stance | null,
    votingDisabled = false,
    locked = false,
    showVoice = false,
    expandedTestimony = false,
    expandedCouncil = false,
    aiAvailable = false,
    activeProviderName = '',
    decisionAiLoading = false,
    decisionAiHtml = '',
    testimonyAiLoading = false,
    testimonyAiHtml = '',
    onexpand,
    onvoice,
    onaskdecision,
    onasktestimony,
    onexternaldecision,
    onexternaltestimony,
    ontoggletestimony,
    ontogglecouncil,
  }: {
    decision: {
      id: string;
      title: string;
      outcome: string;
      outcome_description?: string;
      is_upcoming?: boolean;
      vote_tally?: string;
      date: string;
    };
    expanded?: boolean;
    detail?: DecisionDetail | null;
    detailLoading?: boolean;
    voiceCounts?: { support: number; oppose: number; watching: number; total: number; attested?: number | null } | null;
    userStance?: Stance | null;
    votingDisabled?: boolean;
    locked?: boolean;
    showVoice?: boolean;
    expandedTestimony?: boolean;
    expandedCouncil?: boolean;
    aiAvailable?: boolean;
    activeProviderName?: string;
    decisionAiLoading?: boolean;
    decisionAiHtml?: string;
    testimonyAiLoading?: boolean;
    testimonyAiHtml?: string;
    onexpand?: () => void;
    onvoice?: (detail: { entityId: string; stance: Stance }) => void;
    onaskdecision?: () => void;
    onasktestimony?: () => void;
    onexternaldecision?: (event: MouseEvent) => void;
    onexternaltestimony?: (event: MouseEvent) => void;
    ontoggletestimony?: () => void;
    ontogglecouncil?: () => void;
  } = $props();

  let testimonies = $derived(detail?.testimony?.public_comments ?? []);
  let displayTestimonies = $derived(expandedTestimony ? testimonies : testimonies.slice(0, 3));
  let councilExcerpts = $derived(detail?.testimony?.council_discussion ?? []);
  let displayCouncil = $derived(expandedCouncil ? councilExcerpts : councilExcerpts.slice(0, 3));
</script>

<div class="decision-content">
  <!-- Collapsed header -->
  <button class="decision-row decision-toggle" onclick={() => onexpand?.()}>
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
        {#if voiceCounts && voiceCounts.total > 0}
          <span class="meta-sep">&middot;</span>
          <span class="voice-inline">{voiceCounts.total} voices{#if voiceCounts.attested != null && voiceCounts.attested > 0} <svg width="10" height="10" viewBox="0 0 16 16" fill="#4ade80" style="vertical-align: -1px;"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>{voiceCounts.attested}{/if}</span>
        {/if}
      </div>
    </div>
    <span class="expand-chevron" class:open={expanded}></span>
  </button>

  <!-- Expanded detail -->
  {#if expanded}
    <div class="decision-detail">
      {#if detailLoading}
        <div class="detail-loading">Loading details...</div>
      {:else if detail?.found && detail.decision}
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
        {#if testimonies.length > 0}
          <div class="detail-section">
            <div class="detail-label-row">
              <div class="detail-label">Public Testimony ({testimonies.length})</div>
              {#if aiAvailable}
                <button
                  class="summarize-btn"
                  disabled={testimonyAiLoading}
                  onclick={() => onasktestimony?.()}
                >
                  {testimonyAiLoading ? 'Summarizing...' : testimonyAiHtml ? 'Hide summary' : 'Summarize'}
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
              <button class="detail-expand-btn" onclick={() => ontoggletestimony?.()}>
                {expandedTestimony ? 'Show less' : `+${testimonies.length - 3} more`}
              </button>
            {/if}
            {#if testimonyAiHtml}
              <div class="ai-response">
                <div class="ai-response-text prose">{@html testimonyAiHtml}</div>
                {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
              </div>
            {/if}
            <div class="ai-action-row">
              <button class="ai-action-btn ai-action-claude solo" onclick={(e: MouseEvent) => onexternaltestimony?.(e)}>
                Discuss testimony in Claude <span class="ext-icon">&#8599;</span>
              </button>
            </div>
          </div>
        {/if}

        <!-- Council Discussion -->
        {#if councilExcerpts.length > 0}
          <div class="detail-section">
            <div class="detail-label">Council Discussion ({councilExcerpts.length})</div>
            {#each displayCouncil as excerpt}
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
            {#if councilExcerpts.length > 3}
              <button class="detail-expand-btn" onclick={() => ontogglecouncil?.()}>
                {expandedCouncil ? 'Show less' : `+${councilExcerpts.length - 3} more`}
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

        <!-- Voice buttons -->
        {#if showVoice}
          <CivicVoiceButtons
            entityId={decision.id}
            {userStance}
            disabled={votingDisabled}
            {locked}
            {onvoice}
          />
        {/if}

        <!-- AI action row -->
        <div class="ai-action-row">
          {#if aiAvailable}
            <button
              class="ai-action-btn ai-action-ask"
              class:active={!!decisionAiHtml}
              disabled={decisionAiLoading}
              onclick={() => onaskdecision?.()}
            >
              <span class="sparkle">&#10022;</span> {decisionAiLoading ? 'Thinking...' : decisionAiHtml ? 'Hide' : activeProviderName}
            </button>
          {/if}
          <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onexternaldecision?.(e)}>
            Claude <span class="ext-icon">&#8599;</span>
          </button>
        </div>
        {#if decisionAiHtml}
          <div class="ai-response">
            <div class="ai-response-text prose">{@html decisionAiHtml}</div>
            {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
          </div>
        {/if}
      {:else if detail && !detail.found}
        <div class="detail-empty">No details available</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .decision-content {}
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

  /* === Decision header === */
  .decision-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }
  .decision-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }
  .decision-toggle:hover .card-title { color: #60a5fa; }
  .decision-info { flex: 1; min-width: 0; }

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

  .outcome-label {
    font-weight: 500;
    text-transform: capitalize;
  }
  .outcome-label.passed { color: #4ade80; }
  .outcome-label.failed { color: #f87171; }
  .outcome-label.upcoming { color: #60a5fa; }
  .outcome-label.other { color: #9ca3af; }

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

  .voice-inline {
    color: #60a5fa;
    font-size: 10px;
  }

  /* === Detail section === */
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
  .detail-empty {
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
  .detail-label-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }
  .detail-label-row .detail-label {
    margin-bottom: 0;
  }

  /* === Testimony === */
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
    font-family: inherit;
  }
  .detail-expand-btn:hover { color: #60a5fa; }

  /* === Related decisions === */
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

  /* === AI actions === */
  .summarize-btn {
    font-size: 10px;
    color: #3b82f6;
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 6px;
    font-family: inherit;
  }
  .summarize-btn:hover:not(:disabled) { color: #60a5fa; }
  .summarize-btn:disabled { opacity: 0.5; cursor: default; }

  .ai-action-row {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }
  .ai-action-btn {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid #374151;
    background: transparent;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
  }
  .ai-action-btn:hover:not(:disabled) {
    border-color: #4b5563;
    color: #eee;
  }
  .ai-action-btn:disabled { opacity: 0.5; cursor: default; }
  .ai-action-ask.active {
    background: rgba(59, 130, 246, 0.1);
    border-color: #3b82f6;
    color: #60a5fa;
  }
  .ai-action-claude {
    border-color: #d97706;
    color: #fbbf24;
  }
  .ai-action-claude:hover {
    border-color: #f59e0b;
    color: #fcd34d;
  }
  .ai-action-claude.solo { margin-left: auto; }
  .sparkle { font-size: 10px; }
  .ext-icon { font-size: 9px; }

  .ai-response {
    margin-top: 8px;
    padding: 8px 10px;
    background: rgba(59, 130, 246, 0.06);
    border-radius: 6px;
    border: 1px solid rgba(59, 130, 246, 0.15);
  }
  .ai-response-text {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.5;
  }
  .ai-response-provider {
    display: block;
    font-size: 9px;
    color: #4b5563;
    margin-top: 4px;
    text-align: right;
  }
</style>

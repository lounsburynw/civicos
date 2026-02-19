<svelte:options customElement="civic-comment-thread" />

<script lang="ts">
  import CivicSynthesisBar from './CivicSynthesisBar.svelte';

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

  let {
    entityId = '',
    commentCount = 0,
    attestedCount = 0,
    comments = [] as Comment[],
    synthesis = null as { support: number; oppose: number; neutral: number } | null,
    expanded = false,
    loading = false,
    submitting = false,
    error = '',
    draft = '',
    userPublicKey = '',
    isUnlocked = false,
    hasIdentity = false,
    aiAvailable = false,
    activeProviderName = '',
    draftLoading = false,
    enrichLoading = false,
    summarizeLoading = false,
    summaryHtml = '',
    showSummary = false,
    clerkEmail = '',
    itemTitle = '',
    mailtoHref = '',
    ontoggle,
    onsubmit,
    ondraftchange,
    ondraft,
    onenrich,
    onsummarize,
  }: {
    entityId?: string;
    commentCount?: number;
    attestedCount?: number;
    comments?: Comment[];
    synthesis?: { support: number; oppose: number; neutral: number } | null;
    expanded?: boolean;
    loading?: boolean;
    submitting?: boolean;
    error?: string;
    draft?: string;
    userPublicKey?: string;
    isUnlocked?: boolean;
    hasIdentity?: boolean;
    aiAvailable?: boolean;
    activeProviderName?: string;
    draftLoading?: boolean;
    enrichLoading?: boolean;
    summarizeLoading?: boolean;
    summaryHtml?: string;
    showSummary?: boolean;
    clerkEmail?: string;
    itemTitle?: string;
    mailtoHref?: string;
    ontoggle?: () => void;
    onsubmit?: (detail: { entityId: string; text: string }) => void;
    ondraftchange?: (detail: { entityId: string; text: string }) => void;
    ondraft?: (detail: { entityId: string }) => void;
    onenrich?: (detail: { entityId: string }) => void;
    onsummarize?: (detail: { entityId: string }) => void;
  } = $props();

  let userComment = $derived(
    userPublicKey ? comments.find(c => c.public_key === userPublicKey) : undefined
  );

  let draftLength = $derived((draft || '').length);

  function handleInput(e: Event) {
    const value = (e.target as HTMLTextAreaElement).value;
    ondraftchange?.({ entityId, text: value });
  }
</script>

<div class="comment-section">
  <div class="comment-actions-row">
    <button class="comment-toggle" onclick={() => ontoggle?.()}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 3h12v7H5l-3 3V3z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
      {commentCount} {commentCount === 1 ? 'comment' : 'comments'}{#if attestedCount > 0}&nbsp;({attestedCount} attested){/if}
      <span class="chevron-sm" class:open={expanded}></span>
    </button>
    {#if clerkEmail && mailtoHref}
      <a class="email-clerk-btn" href={mailtoHref} title="Email your comment to the City Clerk">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 4l6 4 6-4M2 4v8h12V4H2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
        Email Clerk
      </a>
    {/if}
  </div>

  {#if expanded}
    <div class="comment-thread">
      {#if loading}
        <div class="thread-loading">Loading comments...</div>
      {:else}
        <!-- Synthesis bar -->
        {#if synthesis}
          <CivicSynthesisBar
            support={synthesis.support}
            oppose={synthesis.oppose}
            neutral={synthesis.neutral}
          />
        {/if}

        <!-- Summarize thread button -->
        {#if aiAvailable && comments.length >= 2}
          <div class="thread-summarize-row">
            <button
              class="summarize-btn"
              disabled={summarizeLoading}
              onclick={() => onsummarize?.({ entityId })}
            >
              <span class="sparkle">✦</span>
              {summarizeLoading ? 'Summarizing...' : showSummary ? 'Hide summary' : 'Summarize'}
            </button>
          </div>
          {#if showSummary && summaryHtml}
            <div class="ai-response thread-summary-response">
              <div class="ai-response-text prose">{@html summaryHtml}</div>
            </div>
          {/if}
        {/if}

        <!-- Comment list -->
        {#if comments.length > 0}
          <div class="thread-list">
            {#each comments as comment}
              <div class="thread-comment" class:stance-support={comment.stance === 'support'} class:stance-oppose={comment.stance === 'oppose'}>
                <div class="thread-comment-meta">
                  <span class="thread-author">{userPublicKey && comment.public_key === userPublicKey ? 'You' : comment.public_key.slice(0, 8) + '...'}</span>
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
        {#if isUnlocked}
          <div class="thread-compose">
            {#if aiAvailable}
              <div class="draft-toolbar">
                <button
                  class="draft-btn"
                  disabled={draftLoading}
                  onclick={() => ondraft?.({ entityId })}
                  title={activeProviderName ? `via ${activeProviderName}` : ''}
                >
                  {draftLoading ? 'Drafting...' : 'Draft with AI'}
                </button>
                {#if (draft || '').trim()}
                  <button
                    class="enrich-btn"
                    disabled={enrichLoading}
                    onclick={() => onenrich?.({ entityId })}
                  >
                    {enrichLoading ? 'Enriching...' : 'Enrich with context'}
                  </button>
                {/if}
                {#if activeProviderName}
                  <span class="ai-provider-tag">via {activeProviderName}</span>
                {/if}
              </div>
            {/if}
            <textarea
              class="thread-textarea"
              class:ai-loading={draftLoading || enrichLoading}
              placeholder={userComment ? 'Edit your comment...' : 'Add a comment...'}
              rows={2}
              maxlength={500}
              value={draft || ''}
              oninput={handleInput}
            ></textarea>
            <div class="thread-compose-footer">
              <span class="char-count" class:near-limit={draftLength > 400}>
                {draftLength}/500
              </span>
              <button
                class="thread-submit"
                disabled={!(draft || '').trim() || submitting}
                onclick={() => onsubmit?.({ entityId, text: (draft || '').trim() })}
              >
                {#if submitting}
                  {userComment ? 'Updating...' : 'Posting...'}
                {:else}
                  {userComment ? 'Update' : 'Post'}
                {/if}
              </button>
            </div>
          </div>
        {:else if hasIdentity}
          <div class="thread-locked">Unlock to comment</div>
        {/if}

        {#if error}
          <div class="thread-error">{error}</div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
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

  /* Summarize */
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
  .summarize-btn:disabled { opacity: 0.5; cursor: default; }
  .sparkle { margin-right: 2px; }
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
    font-family: inherit;
  }
  .draft-btn:hover:not(:disabled) {
    background: rgba(139, 92, 246, 0.2);
    border-color: #a78bfa;
  }
  .draft-btn:disabled { opacity: 0.5; cursor: default; }
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
    font-family: inherit;
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
  .thread-textarea.ai-loading {
    animation: ai-pulse 1.5s ease-in-out infinite;
  }
  @keyframes ai-pulse {
    0%, 100% { border-color: #374151; }
    50% { border-color: #a78bfa; }
  }
  .thread-compose-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 4px;
  }
  .char-count {
    display: block;
    text-align: right;
    font-size: 10px;
    color: #6b7280;
    margin-top: 2px;
  }
  .char-count.near-limit { color: #dc2626; }
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
    font-family: inherit;
  }
  .thread-submit:hover:not(:disabled) { background: #2563eb; }
  .thread-submit:disabled { opacity: 0.4; cursor: default; }
  .thread-error {
    font-size: 10px;
    color: #ef4444;
    margin-top: 4px;
  }
</style>

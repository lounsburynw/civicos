<script lang="ts">
  import type { CivicSession } from '@civicos/client';
  import type { AIChatResult, ChatUserContext } from '@civicos/client';

  let {
    session,
    jurisdiction = '',
    aiAvailable = false,
    userContext = undefined as ChatUserContext | undefined,
    renderMarkdown,
    ontoast,
    onnavigate,
  }: {
    session: CivicSession;
    jurisdiction?: string;
    aiAvailable?: boolean;
    userContext?: ChatUserContext;
    renderMarkdown?: (text: string) => string;
    ontoast?: (message: string) => void;
    onnavigate?: (tool: string) => void;
  } = $props();

  let question = $state('');
  let loading = $state(false);
  let result: AIChatResult | null = $state(null);
  let error: string | null = $state(null);

  const TOOL_LABELS: Record<string, string> = {
    search_meeting_history: 'Meetings',
    get_upcoming_meetings: 'Calendar',
    search_budget: 'Budget',
    get_public_testimony: 'Testimony',
    search_legislation: 'Legislation',
    find_similar_issues: 'Issues',
  };

  // Suggested queries for discoverability (shown when input is empty)
  const SUGGESTED_QUERIES = [
    'Upcoming meetings',
    'Housing updates',
    'Budget for parks',
    'Recent public testimony',
  ];

  // Tools that can navigate to panel sections
  const NAVIGABLE_TOOLS: Record<string, string> = {
    search_meeting_history: 'View in Outcomes',
    get_upcoming_meetings: 'View in Meetings',
    search_budget: 'View Budget',
    get_public_testimony: 'View in Meetings',
    search_legislation: 'View Legislation',
    find_similar_issues: 'View Issue Map',
  };

  async function handleSubmit() {
    const q = question.trim();
    if (!q || loading) return;

    loading = true;
    error = null;
    result = null;

    try {
      const chatResult = await session.chat(q, jurisdiction, userContext);
      if (!chatResult) {
        error = 'AI not available';
      } else if (!chatResult.success) {
        error = chatResult.error || 'Search failed';
      } else {
        result = chatResult;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Search failed';
    } finally {
      loading = false;
    }
  }

  function submitSuggestion(query: string) {
    question = query;
    handleSubmit();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function clear() {
    result = null;
    error = null;
    question = '';
  }
</script>

{#if aiAvailable}
  <div class="chat-bar">
    <div class="chat-input-row">
      <input
        type="text"
        class="chat-input"
        placeholder="Ask about meetings, budget, legislation..."
        bind:value={question}
        onkeydown={handleKeydown}
        disabled={loading}
      />
      <button
        class="chat-send"
        onclick={handleSubmit}
        disabled={loading || !question.trim()}
        title="Search civic data"
      >
        {#if loading}
          <span class="chat-spinner"></span>
        {:else}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
        {/if}
      </button>
    </div>

    {#if !loading && !result && !error && !question.trim()}
      <div class="chat-suggestions">
        {#each SUGGESTED_QUERIES as query}
          <button class="chat-pill" onclick={() => submitSuggestion(query)}>
            {query}
          </button>
        {/each}
      </div>
    {/if}

    {#if loading}
      <div class="chat-status">Searching civic data...</div>
    {/if}

    {#if error}
      <div class="chat-error">{error}</div>
    {/if}

    {#if result?.text}
      <div class="chat-result">
        {#if result.toolUsed}
          <span class="chat-tool-badge">{TOOL_LABELS[result.toolUsed] || result.toolUsed}</span>
        {/if}
        <div class="chat-answer">
          {#if renderMarkdown}
            {@html renderMarkdown(result.text)}
          {:else}
            {result.text}
          {/if}
        </div>
        <div class="chat-actions">
          {#if result.toolUsed && onnavigate && NAVIGABLE_TOOLS[result.toolUsed]}
            <button class="chat-navigate" onclick={() => onnavigate?.(result!.toolUsed!)}>
              {NAVIGABLE_TOOLS[result.toolUsed!]}
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M7 17l9.2-9.2M17 17V7H7" />
              </svg>
            </button>
          {/if}
          <button class="chat-clear" onclick={clear} title="Clear">Clear</button>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .chat-bar {
    margin-bottom: 12px;
  }

  .chat-input-row {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  .chat-input {
    flex: 1;
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 8px;
    color: #e5e7eb;
    font-size: 12px;
    padding: 8px 12px;
    outline: none;
    transition: border-color 0.15s;
  }
  .chat-input:focus {
    border-color: #4b5563;
  }
  .chat-input::placeholder {
    color: #4b5563;
  }
  .chat-input:disabled {
    opacity: 0.6;
  }

  .chat-send {
    background: #262626;
    border: 1px solid #333;
    border-radius: 8px;
    color: #9ca3af;
    padding: 7px 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
    flex-shrink: 0;
  }
  .chat-send:hover:not(:disabled) {
    background: #333;
    color: #e5e7eb;
  }
  .chat-send:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .chat-spinner {
    width: 14px;
    height: 14px;
    border: 2px solid #374151;
    border-top-color: #60a5fa;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  .chat-status {
    font-size: 11px;
    color: #6b7280;
    padding: 6px 4px 0;
    animation: pulse-opacity 1.5s ease-in-out infinite;
  }

  .chat-error {
    font-size: 11px;
    color: #ef4444;
    padding: 6px 4px 0;
  }

  .chat-result {
    margin-top: 8px;
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 10px 12px;
  }

  .chat-tool-badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #60a5fa;
    background: rgba(59, 130, 246, 0.1);
    border: 1px solid rgba(59, 130, 246, 0.2);
    border-radius: 4px;
    padding: 1px 6px;
    margin-bottom: 6px;
  }

  .chat-answer {
    font-size: 12px;
    color: #d1d5db;
    line-height: 1.5;
  }
  .chat-answer :global(p) {
    margin: 0 0 8px;
  }
  .chat-answer :global(p:last-child) {
    margin-bottom: 0;
  }
  .chat-answer :global(ul),
  .chat-answer :global(ol) {
    margin: 4px 0;
    padding-left: 18px;
  }
  .chat-answer :global(li) {
    margin-bottom: 2px;
  }
  .chat-answer :global(strong) {
    color: #e5e7eb;
  }

  .chat-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 0 0;
  }

  .chat-pill {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 12px;
    color: #9ca3af;
    font-size: 10px;
    padding: 3px 10px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .chat-pill:hover {
    border-color: #60a5fa;
    color: #e5e7eb;
    background: rgba(96, 165, 250, 0.08);
  }

  .chat-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
  }

  .chat-navigate {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: rgba(96, 165, 250, 0.08);
    border: 1px solid rgba(96, 165, 250, 0.2);
    border-radius: 6px;
    color: #60a5fa;
    font-size: 10px;
    font-weight: 500;
    padding: 3px 8px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .chat-navigate:hover {
    background: rgba(96, 165, 250, 0.15);
    border-color: rgba(96, 165, 250, 0.4);
  }

  .chat-clear {
    background: none;
    border: none;
    color: #6b7280;
    font-size: 10px;
    cursor: pointer;
    padding: 0;
  }
  .chat-clear:hover {
    color: #9ca3af;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes pulse-opacity {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
</style>

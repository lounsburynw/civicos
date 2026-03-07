<script lang="ts">
  import { computeCityFocalMeetings, urgencyClass, googleCalendarUrl, downloadIcs } from '../utils/civic-helpers.js';
  import type { FocalMeeting } from '../utils/civic-helpers.js';

  let {
    meetings = [],
    upcomingItems = [],
    generatedAt = '',
    jurisdiction = '',
    aiAvailable = false,
    activeProviderName = '',
    renderMarkdown = (text: string) => text,
    onaskai,
    onopenexternalai,
  }: {
    meetings: Array<{ title: string; date: string; time: string; location: string; meeting_datetime: string }>;
    upcomingItems?: Array<{ id?: string; title: string; meeting_title?: string; project_type?: string }>;
    generatedAt?: string;
    jurisdiction?: string;
    aiAvailable?: boolean;
    activeProviderName?: string;
    renderMarkdown?: (text: string) => string;
    onaskai?: (detail: { key: string; context: string }) => void;
    onopenexternalai?: (detail: { context: string; event: MouseEvent }) => void;
  } = $props();

  const referenceTime = $derived(generatedAt ? new Date(generatedAt) : new Date());
  const focalMeetings = $derived(computeCityFocalMeetings(meetings, upcomingItems || [], referenceTime));

  let calendarOpen = $state(new Set<string>());
  let aiResponses = $state(new Map<string, string>());
  let aiLoading = $state(new Set<string>());

  // Drag-to-AI
  let draggingId = $state<string | null>(null);

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  function meetingId(meeting: FocalMeeting): string {
    return `meeting:${meeting.title.toLowerCase().replace(/\s+/g, '-')}`;
  }

  function composeFocalContext(meeting: FocalMeeting): string {
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

  function handleDragStart(e: DragEvent, markdown: string, id: string) {
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    draggingId = id;
  }

  function handleDragEnd() {
    draggingId = null;
  }

  let expanded = $state(true);
</script>

{#if focalMeetings.length > 0}
  <div class="focal-points-group">
    <div class="focal-points-label">Take Action</div>
    <section class="feed-section">
      <button class="section-header" onclick={() => expanded = !expanded}>
        <span class="section-title">
          Upcoming Meetings
          <span class="count-badge focal-badge">{focalMeetings.length}</span>
        </span>
        <span class="chevron" class:open={expanded}></span>
      </button>
      {#if expanded}
        <div class="section-body">
          <div class="section-hint">Your voice shapes local decisions — attend or submit written comments</div>
          {#each focalMeetings as meeting}
            {@const mid = meetingId(meeting)}
            {@const ctx = composeFocalContext(meeting)}
            <div class="card focal-card" class:dragging={draggingId === mid}
                 draggable="true"
                 ondragstart={(e: DragEvent) => handleDragStart(e, ctx, mid)}
                 ondragend={handleDragEnd}>
              <div class="meeting-top-row">
                <div class="card-title">{meeting.title}</div>
                <button class="cal-btn" onclick={() => { calendarOpen.has(mid) ? calendarOpen.delete(mid) : calendarOpen.add(mid); calendarOpen = new Set(calendarOpen); }} title="Add to calendar">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                </button>
              </div>
              {#if calendarOpen.has(mid)}
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
                {#if aiAvailable && onaskai}
                  <button
                    class="ai-action-btn ai-action-ask"
                    class:active={aiResponses.has(mid)}
                    disabled={aiLoading.has(mid)}
                    onclick={() => onaskai?.({ key: mid, context: ctx })}
                  >
                    <span class="sparkle">&#x2726;</span> {aiLoading.has(mid) ? 'Thinking...' : aiResponses.has(mid) ? 'Hide' : activeProviderName || 'Ask AI'}
                  </button>
                {/if}
                {#if onopenexternalai}
                  <button class="ai-action-btn ai-action-claude" class:solo={!aiAvailable} onclick={(e: MouseEvent) => onopenexternalai?.({ context: ctx, event: e })}>
                    Claude <span class="ext-icon">&#x2197;</span>
                  </button>
                {/if}
              </div>
              {#if aiResponses.has(mid)}
                <div class="ai-response">
                  <div class="ai-response-text prose">{@html renderMarkdown(aiResponses.get(mid) ?? '')}</div>
                  {#if activeProviderName}<span class="ai-response-provider">via {activeProviderName}</span>{/if}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>
  </div>
{/if}

<style>
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
    border-top: 5px solid var(--civic-text-dim);
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }
  .section-body { padding: 4px 0 8px; }
  .section-hint {
    font-size: 11px;
    color: var(--civic-text-muted);
    padding: 2px 8px 6px;
    font-style: italic;
  }
  .card {
    background: var(--civic-surface-card);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 6px;
    border: 1px solid var(--civic-surface-elevated);
    transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    cursor: grab;
  }
  .card:hover {
    border-color: var(--civic-border-default);
  }
  .card:active { cursor: grabbing; }
  .card.dragging { opacity: 0.4; border-color: var(--civic-accent-primary); }
  .card-title {
    color: var(--civic-text-primary);
    font-size: 14px;
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
  .focal-points-group {
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--civic-surface-elevated);
  }
  .focal-points-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--civic-status-warning);
    padding: 4px 4px 2px;
  }
  .focal-badge {
    background: var(--civic-status-warning-bg-subtle) !important;
    color: var(--civic-status-warning-light) !important;
  }
  .focal-card {
    border-color: var(--civic-status-warning-bg-subtle);
  }
  .focal-card:hover {
    border-color: var(--civic-status-warning);
    box-shadow: 0 2px 8px var(--civic-status-warning-bg-subtle);
  }
  .deadline-tag {
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
  }
  .deadline-tag.urgent-critical { background: var(--civic-status-error-bg-badge); color: var(--civic-status-error-light); }
  .deadline-tag.urgent-soon { background: var(--civic-status-warning-bg-subtle); color: var(--civic-status-warning-light); }
  .deadline-tag.urgent-normal { background: var(--civic-accent-primary-bg-active); color: var(--civic-accent-primary-light); }
  .deadline-tag.urgent-closed { background: var(--civic-status-neutral-bg-badge); color: var(--civic-text-dim); }
  .item-type {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--civic-border-default);
    color: var(--civic-text-muted);
  }
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
    color: var(--civic-status-warning);
    margin-right: 4px;
    font-weight: 700;
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
    color: var(--civic-accent-primary-light);
    background: var(--civic-accent-primary-bg-subtle);
    border: 1px solid var(--civic-accent-primary)30;
  }
  .ai-action-ask:hover:not(:disabled) { background: var(--civic-accent-primary-bg-hover); border-color: var(--civic-accent-primary); color: var(--civic-accent-primary-bright); }
  .ai-action-ask:disabled { opacity: 0.6; cursor: default; }
  .ai-action-ask.active { background: var(--civic-accent-primary-bg-active); border-color: var(--civic-accent-primary); }
  .ai-action-claude {
    color: var(--civic-accent-claude);
    background: var(--civic-accent-claude-bg-subtle);
    border: 1px solid var(--civic-accent-claude)30;
  }
  .ai-action-claude:hover { background: var(--civic-accent-claude-bg-hover); border-color: var(--civic-accent-claude); color: var(--civic-accent-claude-hover); }
  .ai-action-claude.solo { flex: 1; }
  .sparkle { font-size: 10px; opacity: 0.7; }
  .ext-icon { font-size: 9px; }
  .ai-response {
    margin-top: 8px;
    padding: 10px 12px;
    background: var(--civic-ai-bg-subtle);
    border: 1px solid var(--civic-ai-border-subtle);
    border-radius: 8px;
  }
  .ai-response-text { font-size: 12px; color: var(--civic-text-body); line-height: 1.5; }
  .ai-response-text.prose :global(p) { margin: 0 0 8px; }
  .ai-response-text.prose :global(p:last-child) { margin-bottom: 0; }
  .ai-response-provider { display: block; margin-top: 6px; font-size: 10px; color: var(--civic-text-dim); }
</style>

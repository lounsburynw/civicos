<script lang="ts">
  import { isPastMeeting, formatMeetingTime, googleCalendarUrl, downloadIcs } from '../utils/civic-helpers.js';

  type Meeting = {
    title: string;
    date: string;
    time: string;
    location: string;
    meeting_datetime: string;
  };

  let {
    meeting,
    showCalendar = true,
  }: {
    meeting: Meeting;
    showCalendar?: boolean;
  } = $props();

  let calendarOpen = $state(false);
  let past = $derived(isPastMeeting(meeting));
  let dragging = $state(false);

  function escapeHtml(text: string): string {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  }

  function composeMeetingContext(): string {
    const lines = [
      `**${meeting.title}**`,
      `Date: ${meeting.date}`,
    ];
    if (meeting.time) lines.push(`Time: ${meeting.time}`);
    if (meeting.location) lines.push(`Location: ${meeting.location}`);
    lines.push('', 'What should I know about this meeting? What topics are likely on the agenda?');
    return lines.join('\n');
  }

  function handleDragStart(e: DragEvent) {
    const markdown = composeMeetingContext();
    e.dataTransfer!.effectAllowed = 'all';
    e.dataTransfer!.setData('text/html', '<pre>' + escapeHtml(markdown) + '</pre>');
    e.dataTransfer!.setData('text/plain', markdown);
    dragging = true;
  }

  function handleDragEnd() {
    dragging = false;
  }
</script>

<div class="card meeting-card" class:past-meeting={past} class:dragging
     draggable="true"
     ondragstart={handleDragStart}
     ondragend={handleDragEnd}>
  <div class="meeting-top-row">
    <div class="card-title">
      {#if past}<span class="past-icon" title="Past meeting">&#128337;</span>{/if}
      {meeting.title}
    </div>
    {#if showCalendar}
      <button class="cal-btn" onclick={() => calendarOpen = !calendarOpen} title="Add to calendar" disabled={past}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
        </svg>
      </button>
    {/if}
  </div>
  <div class="card-meta">
    <span class="meta-date">{formatMeetingTime(meeting)}</span>
    {#if meeting.location}
      <span class="meta-sep">&middot;</span>
      <span class="meta-location">{meeting.location}</span>
    {/if}
  </div>
  {#if showCalendar && calendarOpen}
    <div class="cal-dropdown">
      <a href={googleCalendarUrl(meeting)} target="_blank" rel="noopener" class="cal-option">Google Calendar</a>
      <button class="cal-option" onclick={() => downloadIcs(meeting)}>Download .ics</button>
    </div>
  {/if}
</div>

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
  .past-meeting { opacity: 0.65; }
  .past-icon { font-size: 12px; margin-right: 4px; }
  .meeting-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 6px;
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
  .cal-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover:not(:disabled) { color: #60a5fa; background: #374151; }
  .cal-btn:disabled { opacity: 0.3; cursor: default; }
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
</style>

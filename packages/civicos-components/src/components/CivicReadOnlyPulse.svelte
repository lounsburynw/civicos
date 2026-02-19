<script lang="ts">
  import CivicMeetingCard from './CivicMeetingCard.svelte';
  import { outcomeIcon, outcomeClass, formatRelativeDate } from '../utils/civic-helpers.js';

  type PulseData = {
    decisions_this_week: Array<{ title: string; date: string; time: string; location: string; meeting_datetime: string }>;
    upcoming_items?: Array<{ title: string; meeting_title?: string; project_type?: string }>;
    recent_outcomes: Array<{ title: string; date: string; outcome: string }>;
    generated_at: string;
  };

  let {
    data,
    showCalendar = false,
  }: {
    data: PulseData;
    showCalendar?: boolean;
  } = $props();

  let expanded: Record<string, boolean> = $state({
    meetings: true,
    items: true,
    outcomes: true,
  });

  function toggle(section: string) {
    expanded[section] = !expanded[section];
  }
</script>

<!-- Meetings -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('meetings')}>
    <span class="section-title">
      Meetings
      {#if data.decisions_this_week.length > 0}
        <span class="count-badge">{data.decisions_this_week.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.meetings}></span>
  </button>
  {#if expanded.meetings}
    <div class="section-body">
      {#if data.decisions_this_week.length === 0}
        <div class="empty-section">No upcoming meetings</div>
      {:else}
        {#each data.decisions_this_week as meeting}
          <CivicMeetingCard {meeting} {showCalendar} />
        {/each}
      {/if}
    </div>
  {/if}
</section>

<!-- Agenda Items -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('items')}>
    <span class="section-title">
      Agenda Items
      {#if data.upcoming_items && data.upcoming_items.length > 0}
        <span class="count-badge">{data.upcoming_items.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.items}></span>
  </button>
  {#if expanded.items}
    <div class="section-body">
      {#if !data.upcoming_items || data.upcoming_items.length === 0}
        <div class="empty-section">No upcoming agenda items</div>
      {:else}
        {#each data.upcoming_items as item}
          <div class="card">
            <div class="card-title">{item.title}</div>
            <div class="card-meta">
              {#if item.meeting_title}
                <span>{item.meeting_title}</span>
              {/if}
              {#if item.project_type}
                <span class="item-type">{item.project_type}</span>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<!-- Recent Outcomes -->
<section class="feed-section">
  <button class="section-header" onclick={() => toggle('outcomes')}>
    <span class="section-title">
      Recent Outcomes
      {#if data.recent_outcomes.length > 0}
        <span class="count-badge">{data.recent_outcomes.length}</span>
      {/if}
    </span>
    <span class="chevron" class:open={expanded.outcomes}></span>
  </button>
  {#if expanded.outcomes}
    <div class="section-body">
      {#if data.recent_outcomes.length === 0}
        <div class="empty-section">No recent outcomes</div>
      {:else}
        {#each data.recent_outcomes as outcome}
          <div class="card">
            <div class="card-title">
              <span class="outcome-icon {outcomeClass(outcome.outcome)}">{outcomeIcon(outcome.outcome)}</span>
              {outcome.title}
            </div>
            <div class="card-meta">
              <span class="meta-date">{formatRelativeDate(outcome.date)}</span>
              {#if outcome.outcome}
                <span class="meta-sep">&middot;</span>
                <span class="outcome-label">{outcome.outcome.replace(/_/g, ' ')}</span>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

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
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .card:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59,130,246,0.1);
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

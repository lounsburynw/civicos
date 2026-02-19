<script lang="ts">
  import CivicMeetingCard from './CivicMeetingCard.svelte';
  import CivicVoiceButtons from './CivicVoiceButtons.svelte';
  import { outcomeIcon, outcomeClass, formatRelativeDate } from '../utils/civic-helpers.js';

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
    comment_periods?: Array<{ document_number: string; title: string; abstract?: string; agency_names: string[]; comments_close_on: string; comment_url?: string; html_url?: string; days_remaining: number }>;
    upcoming_hearings?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string; description?: string; days_until: number }>;
    governors_desk?: Array<{ bill_id: string; bill_number?: string; bill_name?: string; summary?: string; enrolled_date?: string }>;
  };

  type JurisdictionLevel = 'federal' | 'state' | 'city' | string;
  type IdentityInfo = { isUnlocked?: boolean } | null;

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
    onvoice,
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
    onvoice?: (detail: { entityId: string; stance: Stance }) => void;
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
  const hasFocalPoints = $derived(hasCommentPeriods || hasHearings || hasGovernorsDesk);

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

  function composeHearingContext(hearing: { bill_id: string; bill_number?: string; bill_name?: string; event_date: string; committee?: string; location?: string; description?: string; days_until: number }): string {
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
    if (hearing.description) lines.push('', hearing.description);
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

  function urgencyClass(days: number): string {
    if (days <= 0) return 'urgent-closed';
    if (days <= 3) return 'urgent-critical';
    if (days <= 7) return 'urgent-soon';
    return 'urgent-normal';
  }

  let expanded: Record<string, boolean> = $state({
    meetings: true,
    items: true,
    outcomes: true,
    commentPeriods: true,
    hearings: true,
    governorsDesk: true,
  });

  function toggle(section: string) {
    expanded[section] = !expanded[section];
  }
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
            {#each data.comment_periods! as period}
              <div class="card focal-card" class:dragging={draggingId === period.document_number}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeCommentPeriodContext(period), period.document_number)}
                   ondragend={handleDragEnd}>
                <div class="card-title">{period.title}</div>
                <div class="card-meta">
                  <span>{period.agency_names.join(', ')}</span>
                  <span class="deadline-tag {urgencyClass(period.days_remaining)}">
                    {#if period.days_remaining <= 0}
                      Closed
                    {:else if period.days_remaining === 1}
                      1 day left
                    {:else}
                      {period.days_remaining} days left
                    {/if}
                  </span>
                </div>
                {#if period.abstract}
                  <div class="card-summary">{period.abstract}</div>
                {/if}
                <div class="card-actions">
                  {#if period.comment_url}
                    <a href={period.comment_url} target="_blank" rel="noopener" class="action-link comment-link">Submit Comment</a>
                  {/if}
                  {#if period.html_url}
                    <a href={period.html_url} target="_blank" rel="noopener" class="action-link">Read Rule</a>
                  {/if}
                </div>
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
            {#each data.upcoming_hearings! as hearing}
              <div class="card focal-card" class:dragging={draggingId === hearing.bill_id}
                   draggable="true"
                   ondragstart={(e: DragEvent) => handleDragStart(e, composeHearingContext(hearing), hearing.bill_id)}
                   ondragend={handleDragEnd}>
                <div class="card-title">{hearing.bill_number || hearing.bill_id}</div>
                {#if hearing.bill_name}
                  <div class="card-subtitle">{hearing.bill_name}</div>
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
                </div>
                {#if hearing.description}
                  <div class="card-summary">{hearing.description}</div>
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
            Governor's Desk
            <span class="count-badge action-badge">{data.governors_desk!.length}</span>
          </span>
          <span class="chevron" class:open={expanded.governorsDesk}></span>
        </button>
        {#if expanded.governorsDesk}
          <div class="section-body">
            <div class="section-hint">Bills awaiting governor's signature — call now to influence the outcome</div>
            {#each data.governors_desk! as bill}
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
      {#if !data.upcoming_items || data.upcoming_items.length === 0}
        <div class="empty-section">{emptyItems}</div>
      {:else}
        {#each data.upcoming_items as item}
          {@const eid = item.id ? billEntityId(item.id) : ''}
          {@const counts = eid ? voiceCounts.get(eid) : undefined}
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
              {#if counts && counts.total > 0}
                <span class="voice-count-badge">{counts.total} voice{counts.total !== 1 ? 's' : ''}</span>
              {/if}
            </div>
            {#if isLegislative && item.summary}
              <div class="card-summary">{item.summary}</div>
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
              <div class="card-summary">{outcome.summary}</div>
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

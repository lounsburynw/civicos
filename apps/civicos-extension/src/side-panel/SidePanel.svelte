<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import { getCityPulse } from '../lib/api.js';
  import type { IdentityInfo } from '../lib/providers/types.js';
  import type { CityPulseData } from '../lib/types.js';

  let identity: (IdentityInfo & { isUnlocked?: boolean }) | null = $state(null);
  let loading = $state(true);
  let pulseData: CityPulseData | null = $state(null);
  let pulseError: string | null = $state(null);
  let pulseLoading = $state(true);

  // Collapsible section state
  let expanded: Record<string, boolean> = $state({
    meetings: true,
    items: true,
    outcomes: true,
    community: false,
  });

  function toggle(section: string) {
    expanded[section] = !expanded[section];
  }

  async function loadIdentity() {
    loading = true;
    const response = await sendMessage<(IdentityInfo & { isUnlocked?: boolean }) | null>({
      type: 'GET_IDENTITY',
    });
    if (response.success) {
      identity = response.data;
    }
    loading = false;
  }

  async function loadCityPulse() {
    pulseLoading = true;
    pulseError = null;
    try {
      pulseData = await getCityPulse();
    } catch (err) {
      pulseError = err instanceof Error ? err.message : 'Failed to load civic data';
    }
    pulseLoading = false;
  }

  function openOptions() {
    chrome.runtime.openOptionsPage();
  }

  function truncateNpub(npub: string): string {
    if (npub.length <= 16) return npub;
    return npub.slice(0, 10) + '...' + npub.slice(-6);
  }

  function formatMeetingTime(meeting: { date: string; time: string }): string {
    return meeting.time ? `${meeting.date} @ ${meeting.time}` : meeting.date;
  }

  function outcomeIcon(outcome: string): string {
    const lower = outcome.toLowerCase();
    if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted')) return '\u2713';
    if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected')) return '\u2717';
    if (lower.includes('continued') || lower.includes('tabled')) return '\u21BB';
    return '\u2022';
  }

  function outcomeClass(outcome: string): string {
    const lower = outcome.toLowerCase();
    if (lower.includes('approved') || lower.includes('passed') || lower.includes('adopted')) return 'passed';
    if (lower.includes('denied') || lower.includes('failed') || lower.includes('rejected')) return 'failed';
    return 'other';
  }

  // Load on mount
  loadIdentity();
  loadCityPulse();
</script>

<div class="panel">
  <header>
    <div class="header-left">
      <h1>City Pulse</h1>
      {#if pulseData}
        <span class="jurisdiction">{pulseData.jurisdiction}</span>
      {/if}
    </div>
    <div class="header-actions">
      <button class="icon-btn" onclick={loadCityPulse} title="Refresh" disabled={pulseLoading}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             class:spinning={pulseLoading}>
          <path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16" />
        </svg>
      </button>
      <button class="icon-btn" onclick={openOptions} title="Settings">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
        </svg>
      </button>
    </div>
  </header>

  <!-- Identity chip -->
  {#if loading}
    <div class="identity-chip skeleton">&nbsp;</div>
  {:else if identity}
    <div class="identity-chip">
      <div class="chip-row">
        <span class="tier-badge" class:easy={identity.tier === 'easy'} class:private={identity.tier === 'private'}>
          {identity.tier}
        </span>
        <span class="lock-status" class:unlocked={identity.isUnlocked}>
          {identity.isUnlocked ? 'unlocked' : 'locked'}
        </span>
      </div>
      <div class="npub">{truncateNpub(identity.npub)}</div>
    </div>
  {:else}
    <div class="identity-chip empty">
      <span>No identity</span>
      <button class="link-btn" onclick={openOptions}>Set up</button>
    </div>
  {/if}

  <!-- City Pulse content -->
  {#if pulseLoading && !pulseData}
    <div class="loading-state">
      <div class="pulse-anim"></div>
      <span>Loading civic data...</span>
    </div>
  {:else if pulseError && !pulseData}
    <div class="error-state">
      <span class="error-icon">!</span>
      <p>{pulseError}</p>
      <button class="btn-retry" onclick={loadCityPulse}>Retry</button>
    </div>
  {:else if pulseData}
    <!-- Upcoming Meetings -->
    <section class="feed-section">
      <button class="section-header" onclick={() => toggle('meetings')}>
        <span class="section-title">
          Upcoming Meetings
          {#if pulseData.decisions_this_week.length > 0}
            <span class="count-badge">{pulseData.decisions_this_week.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.meetings}></span>
      </button>
      {#if expanded.meetings}
        <div class="section-body">
          {#if pulseData.decisions_this_week.length === 0}
            <div class="empty-section">No upcoming meetings</div>
          {:else}
            {#each pulseData.decisions_this_week as meeting}
              <div class="card meeting-card">
                <div class="card-title">{meeting.title}</div>
                <div class="card-meta">
                  <span class="meta-date">{formatMeetingTime(meeting)}</span>
                  {#if meeting.location}
                    <span class="meta-sep">&middot;</span>
                    <span class="meta-location">{meeting.location}</span>
                  {/if}
                </div>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </section>

    <!-- Upcoming Agenda Items -->
    {#if pulseData.upcoming_items && pulseData.upcoming_items.length > 0}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('items')}>
          <span class="section-title">
            Agenda Items
            <span class="count-badge">{pulseData.upcoming_items.length}</span>
          </span>
          <span class="chevron" class:open={expanded.items}></span>
        </button>
        {#if expanded.items}
          <div class="section-body">
            {#each pulseData.upcoming_items as item}
              <div class="card item-card">
                <div class="card-top-row">
                  {#if item.item_number}
                    <span class="item-number">#{item.item_number}</span>
                  {/if}
                  <span class="item-meeting">{item.meeting_title} &middot; {item.meeting_date}</span>
                </div>
                <div class="card-title">{item.title}</div>
                {#if item.description}
                  <div class="card-desc">{item.description}</div>
                {/if}
                <div class="card-tags">
                  {#if item.stance_eligible}
                    <span class="tag tag-voice">Voice eligible</span>
                  {/if}
                  {#if item.comment_eligible}
                    <span class="tag tag-comment">Comment eligible</span>
                  {/if}
                  {#if item.project_type}
                    <span class="tag">{item.project_type}</span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </section>
    {/if}

    <!-- Recent Decisions -->
    <section class="feed-section">
      <button class="section-header" onclick={() => toggle('outcomes')}>
        <span class="section-title">
          Recent Decisions
          {#if pulseData.recent_outcomes.length > 0}
            <span class="count-badge">{pulseData.recent_outcomes.length}</span>
          {/if}
        </span>
        <span class="chevron" class:open={expanded.outcomes}></span>
      </button>
      {#if expanded.outcomes}
        <div class="section-body">
          {#if pulseData.recent_outcomes.length === 0}
            <div class="empty-section">No recent decisions</div>
          {:else}
            {#each pulseData.recent_outcomes as decision}
              <div class="card decision-card">
                <div class="decision-row">
                  <span class="outcome-icon {outcomeClass(decision.outcome)}">
                    {outcomeIcon(decision.outcome)}
                  </span>
                  <div class="decision-info">
                    <div class="card-title">{decision.title}</div>
                    <div class="card-meta">
                      <span class="outcome-label {outcomeClass(decision.outcome)}">{decision.outcome}</span>
                      {#if decision.vote_tally}
                        <span class="meta-sep">&middot;</span>
                        <span>{decision.vote_tally}</span>
                      {/if}
                      <span class="meta-sep">&middot;</span>
                      <span>{decision.date}</span>
                    </div>
                  </div>
                </div>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </section>

    <!-- Community Pulse -->
    {#if pulseData.community_pulse && pulseData.community_pulse.total_issues}
      <section class="feed-section">
        <button class="section-header" onclick={() => toggle('community')}>
          <span class="section-title">
            Community Issues
            <span class="count-badge">{pulseData.community_pulse.total_issues}</span>
          </span>
          <span class="chevron" class:open={expanded.community}></span>
        </button>
        {#if expanded.community}
          <div class="section-body">
            <div class="issue-stats">
              {#if pulseData.community_pulse.top_types}
                {#each Object.entries(pulseData.community_pulse.top_types) as [type, count]}
                  <div class="issue-type-row">
                    <span class="issue-type-name">{type}</span>
                    <span class="issue-type-count">{count}</span>
                  </div>
                {/each}
              {/if}
            </div>
          </div>
        {/if}
      </section>
    {/if}

    <!-- Footer -->
    <footer class="pulse-footer">
      {#if pulseData.clerk_email}
        <a href="mailto:{pulseData.clerk_email}" class="footer-link">Contact City Clerk</a>
      {/if}
      <span class="footer-ts">Updated {new Date(pulseData.generated_at).toLocaleTimeString()}</span>
    </footer>
  {/if}
</div>

<style>
  /* === Base === */
  .panel {
    padding: 12px;
    min-height: 100vh;
    font-size: 13px;
    line-height: 1.4;
  }

  /* === Header === */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid #1e293b;
  }

  .header-left {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  h1 {
    font-size: 16px;
    font-weight: 700;
    color: #f8fafc;
    margin: 0;
  }

  .jurisdiction {
    font-size: 11px;
    color: #64748b;
  }

  .header-actions {
    display: flex;
    gap: 4px;
  }

  .icon-btn {
    background: none;
    border: none;
    color: #94a3b8;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .icon-btn:hover { color: #e2e8f0; background: #1e293b; }
  .icon-btn:disabled { opacity: 0.5; cursor: default; }

  .spinning {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* === Identity Chip === */
  .identity-chip {
    background: #1e293b;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .identity-chip.skeleton {
    height: 48px;
    animation: pulse 1.5s infinite;
  }
  .identity-chip.empty {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #64748b;
    font-size: 12px;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 0.3; }
  }

  .chip-row {
    display: flex;
    gap: 8px;
    align-items: center;
    margin-bottom: 4px;
  }

  .tier-badge {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 3px;
    background: #374151;
    color: #9ca3af;
  }
  .tier-badge.easy { background: #1e3a5f; color: #60a5fa; }
  .tier-badge.private { background: #3b1f4b; color: #c084fc; }

  .lock-status {
    font-size: 10px;
    color: #ef4444;
  }
  .lock-status.unlocked { color: #22c55e; }

  .npub {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 11px;
    color: #64748b;
  }

  .link-btn {
    background: none;
    border: none;
    color: #6366f1;
    cursor: pointer;
    font-size: 12px;
    text-decoration: underline;
  }
  .link-btn:hover { color: #818cf8; }

  /* === Loading / Error states === */
  .loading-state {
    text-align: center;
    padding: 40px 16px;
    color: #94a3b8;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
  }

  .pulse-anim {
    width: 32px;
    height: 32px;
    border: 2px solid #334155;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .error-state {
    text-align: center;
    padding: 32px 16px;
    color: #94a3b8;
  }
  .error-state .error-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #7f1d1d;
    color: #fca5a5;
    font-weight: 700;
    font-size: 16px;
    margin-bottom: 8px;
  }
  .error-state p {
    font-size: 12px;
    margin-bottom: 12px;
    color: #ef4444;
  }

  .btn-retry {
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-retry:hover { background: #334155; }

  /* === Feed Sections === */
  .feed-section {
    margin-bottom: 4px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    background: none;
    border: none;
    color: #e2e8f0;
    padding: 8px 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #1e293b;
  }
  .section-header:hover { color: #f8fafc; }

  .section-title {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .count-badge {
    background: #334155;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 500;
    padding: 1px 5px;
    border-radius: 8px;
    text-transform: none;
    letter-spacing: 0;
  }

  .chevron {
    display: inline-block;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    transition: transform 0.15s ease;
  }
  .chevron.open { transform: rotate(180deg); }

  .section-body {
    padding: 4px 0 8px;
  }

  .empty-section {
    padding: 12px 8px;
    color: #475569;
    font-size: 12px;
    font-style: italic;
  }

  /* === Cards === */
  .card {
    background: #1e293b;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 6px;
  }

  .card-title {
    color: #f1f5f9;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: #64748b;
    margin-top: 4px;
    flex-wrap: wrap;
  }

  .meta-sep { color: #475569; }

  .card-desc {
    color: #94a3b8;
    font-size: 12px;
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .card-top-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 11px;
    color: #64748b;
  }

  .item-number {
    color: #818cf8;
    font-weight: 600;
  }

  .card-tags {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    flex-wrap: wrap;
  }

  .tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 3px;
    background: #334155;
    color: #94a3b8;
  }
  .tag-voice { background: #1e3a5f; color: #60a5fa; }
  .tag-comment { background: #1a332e; color: #34d399; }

  /* === Decision cards === */
  .decision-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }

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
  .outcome-icon.other { background: #334155; color: #94a3b8; }

  .decision-info { flex: 1; min-width: 0; }

  .outcome-label {
    font-weight: 500;
    text-transform: capitalize;
  }
  .outcome-label.passed { color: #4ade80; }
  .outcome-label.failed { color: #f87171; }
  .outcome-label.other { color: #94a3b8; }

  /* === Community Issues === */
  .issue-stats {
    padding: 4px 0;
  }

  .issue-type-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    font-size: 12px;
  }
  .issue-type-row:nth-child(odd) { background: #1e293b; border-radius: 4px; }

  .issue-type-name { color: #cbd5e1; }
  .issue-type-count { color: #64748b; font-variant-numeric: tabular-nums; }

  /* === Footer === */
  .pulse-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 4px 4px;
    margin-top: 8px;
    border-top: 1px solid #1e293b;
    font-size: 10px;
    color: #475569;
  }

  .footer-link {
    color: #6366f1;
    text-decoration: none;
  }
  .footer-link:hover { text-decoration: underline; }
</style>

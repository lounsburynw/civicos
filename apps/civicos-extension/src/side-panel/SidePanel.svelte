<script lang="ts">
  import { sendMessage } from '../lib/messaging.js';
  import { getCityPulse, getDecisionDetail, getDataProvenance, getVoiceCountsBatch, submitVoice, revokeVoice } from '../lib/api.js';
  import type { IdentityInfo, NostrEvent, SignedNostrEvent } from '../lib/providers/types.js';
  import { CivicEventKinds, createVoiceContent, createVoiceTags } from '../lib/providers/types.js';
  import type { CityPulseData, DecisionDetailData, DataProvenance, VoiceCounts } from '../lib/types.js';

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

  // Decision detail expansion
  let expandedDecisions = $state(new Set<string>());
  let decisionDetails = $state(new Map<string, DecisionDetailData>());
  let decisionLoading = $state(new Set<string>());

  // Data provenance
  let showProvenance = $state(false);
  let provenanceData: DataProvenance | null = $state(null);
  let provenanceLoading = $state(false);

  // Voice counts
  let voiceCounts = $state(new Map<string, VoiceCounts>());

  // Voice submission state
  type Stance = 'support' | 'oppose' | 'watching';
  let userStances = $state(new Map<string, Stance>());
  let votingInProgress = $state(new Set<string>());
  const STANCES_STORAGE_KEY = 'civicos_user_stances';

  // Calendar dropdown
  let calendarOpen: string | null = $state(null);

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
      // Load voice counts in background after pulse data arrives
      loadVoiceCounts();
    } catch (err) {
      pulseError = err instanceof Error ? err.message : 'Failed to load civic data';
    }
    pulseLoading = false;
  }

  async function loadVoiceCounts() {
    if (!pulseData) return;
    const ids: string[] = [];
    if (pulseData.recent_outcomes) {
      ids.push(...pulseData.recent_outcomes.map(d => d.id).filter(Boolean));
    }
    if (pulseData.upcoming_items) {
      ids.push(...pulseData.upcoming_items.filter(i => i.stance_eligible).map(i => `agenda-item:${i.id}`));
    }
    if (ids.length > 0) {
      voiceCounts = await getVoiceCountsBatch(ids);
    }
  }

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
        const detail = await getDecisionDetail(title);
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

  async function toggleProvenance() {
    showProvenance = !showProvenance;
    if (showProvenance && !provenanceData && !provenanceLoading) {
      provenanceLoading = true;
      try {
        provenanceData = await getDataProvenance();
      } catch (e) {
        console.error('Failed to load provenance:', e);
      } finally {
        provenanceLoading = false;
      }
    }
  }

  function isPastMeeting(meeting: { meeting_datetime: string }): boolean {
    return new Date(meeting.meeting_datetime) < new Date();
  }

  function googleCalendarUrl(meeting: { title: string; date: string; time: string; location: string; meeting_datetime: string }): string {
    const start = new Date(meeting.meeting_datetime);
    const end = new Date(start.getTime() + 2 * 60 * 60 * 1000); // assume 2hr
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    return `https://www.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(meeting.title)}&dates=${fmt(start)}/${fmt(end)}&location=${encodeURIComponent(meeting.location || '')}`;
  }

  function downloadIcs(meeting: { title: string; location: string; meeting_datetime: string }) {
    const start = new Date(meeting.meeting_datetime);
    const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
    const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const ics = `BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nDTSTART:${fmt(start)}\nDTEND:${fmt(end)}\nSUMMARY:${meeting.title}\nLOCATION:${meeting.location || ''}\nEND:VEVENT\nEND:VCALENDAR`;
    const blob = new Blob([ics], { type: 'text/calendar' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${meeting.title.replace(/[^a-zA-Z0-9]/g, '_')}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleCalendar(meetingTitle: string) {
    calendarOpen = calendarOpen === meetingTitle ? null : meetingTitle;
  }

  async function loadStances() {
    try {
      const result = await chrome.storage.local.get(STANCES_STORAGE_KEY);
      if (result[STANCES_STORAGE_KEY]) {
        userStances = new Map(Object.entries(result[STANCES_STORAGE_KEY]) as [string, Stance][]);
      }
    } catch {
      // Ignore load errors
    }
  }

  async function persistStances() {
    try {
      const obj: Record<string, string> = {};
      userStances.forEach((v, k) => { obj[k] = v; });
      await chrome.storage.local.set({ [STANCES_STORAGE_KEY]: obj });
    } catch {
      // Ignore persist errors
    }
  }

  async function handleVoice(entityId: string, stance: Stance) {
    if (votingInProgress.has(entityId)) return;
    if (!identity?.isUnlocked) return;

    votingInProgress.add(entityId);
    votingInProgress = new Set(votingInProgress);

    const prevStance = userStances.get(entityId);
    const prevCounts = voiceCounts.get(entityId) || { support: 0, oppose: 0, watching: 0, total: 0 };

    // Re-click same stance = revoke (toggle off)
    if (prevStance === stance) {
      const newCounts = { ...prevCounts };
      newCounts[stance] = Math.max(0, newCounts[stance] - 1);
      newCounts.total = newCounts.support + newCounts.oppose + newCounts.watching;

      voiceCounts.set(entityId, newCounts);
      voiceCounts = new Map(voiceCounts);
      userStances.delete(entityId);
      userStances = new Map(userStances);
      persistStances();

      // Sign and submit revoke (fire-and-forget)
      try {
        const createdAt = Math.floor(Date.now() / 1000);
        const unsigned: NostrEvent = {
          created_at: createdAt,
          kind: CivicEventKinds.VOICE,
          tags: [['d', entityId]],
          content: `civicos:voice:v1:${entityId}:revoke:${createdAt}`,
        };
        const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
        if (signResult.success) {
          revokeVoice(entityId, signResult.data.pubkey, signResult.data.sig, createdAt);
        }
      } catch {
        // Fire-and-forget
      }

      votingInProgress.delete(entityId);
      votingInProgress = new Set(votingInProgress);
      return;
    }

    // Different stance — optimistic update
    const newCounts = { ...prevCounts };
    if (prevStance) {
      newCounts[prevStance] = Math.max(0, newCounts[prevStance] - 1);
    }
    newCounts[stance] += 1;
    newCounts.total = newCounts.support + newCounts.oppose + newCounts.watching;

    voiceCounts.set(entityId, newCounts);
    voiceCounts = new Map(voiceCounts);
    userStances.set(entityId, stance);
    userStances = new Map(userStances);
    persistStances();

    // Sign and submit
    try {
      const jurisdiction = pulseData?.jurisdiction || 'city-san-rafael';
      const createdAt = Math.floor(Date.now() / 1000);
      const unsigned: NostrEvent = {
        created_at: createdAt,
        kind: CivicEventKinds.VOICE,
        tags: createVoiceTags(entityId, jurisdiction, stance),
        content: createVoiceContent(entityId, stance, createdAt),
      };

      const signResult = await sendMessage<SignedNostrEvent>({ type: 'SIGN_EVENT', event: unsigned });
      if (!signResult.success) {
        throw new Error('Signing failed');
      }

      const ok = await submitVoice(entityId, stance, jurisdiction, signResult.data.pubkey, signResult.data.sig, createdAt);
      if (!ok) {
        throw new Error('Relay submission failed');
      }
    } catch {
      // Revert on failure
      voiceCounts.set(entityId, prevCounts);
      voiceCounts = new Map(voiceCounts);
      if (prevStance) {
        userStances.set(entityId, prevStance);
      } else {
        userStances.delete(entityId);
      }
      userStances = new Map(userStances);
      persistStances();
    }

    votingInProgress.delete(entityId);
    votingInProgress = new Set(votingInProgress);
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

  function formatRelativeDate(dateStr: string | null): string {
    if (!dateStr) return 'unknown';
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 30) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  }

  // Load on mount
  loadIdentity();
  loadCityPulse();
  loadStances();
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
      <button class="icon-btn" onclick={toggleProvenance} title="Data Sources" class:active={showProvenance}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
      </button>
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

  <!-- Data Provenance Panel -->
  {#if showProvenance}
    <div class="provenance-panel">
      {#if provenanceLoading}
        <div class="prov-loading">Loading data sources...</div>
      {:else if provenanceData}
        <div class="prov-header">
          <span class="prov-title">Data Sources</span>
          <span class="prov-jurisdiction">{provenanceData.jurisdiction}</span>
        </div>
        <div class="prov-stats">
          <span>{provenanceData.corpora.length} data types</span>
          <span class="meta-sep">&middot;</span>
          <span>{provenanceData.total_vector_docs.toLocaleString()} indexed docs</span>
          {#if provenanceData.overall_coverage_percent != null}
            <span class="meta-sep">&middot;</span>
            <span>{provenanceData.overall_coverage_percent}% coverage</span>
          {/if}
        </div>
        <div class="prov-corpora">
          {#each provenanceData.corpora as corpus}
            <div class="corpus-row">
              <span class="corpus-name">{corpus.display_name}</span>
              <span class="corpus-count">{corpus.storage_count.toLocaleString()}</span>
            </div>
          {/each}
        </div>
        {#if provenanceData.freshness.last_updated}
          <div class="prov-freshness">
            Updated {formatRelativeDate(provenanceData.freshness.last_updated)}
          </div>
        {/if}
      {:else}
        <div class="prov-loading">Unable to load data sources</div>
      {/if}
    </div>
  {/if}

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
              <div class="card meeting-card" class:past-meeting={isPastMeeting(meeting)}>
                <div class="meeting-top-row">
                  <div class="card-title">
                    {#if isPastMeeting(meeting)}<span class="past-icon" title="Past meeting">&#128337;</span>{/if}
                    {meeting.title}
                  </div>
                  <button class="cal-btn" onclick={() => toggleCalendar(meeting.title)} title="Add to calendar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
                    </svg>
                  </button>
                </div>
                <div class="card-meta">
                  <span class="meta-date">{formatMeetingTime(meeting)}</span>
                  {#if meeting.location}
                    <span class="meta-sep">&middot;</span>
                    <span class="meta-location">{meeting.location}</span>
                  {/if}
                </div>
                {#if calendarOpen === meeting.title}
                  <div class="cal-dropdown">
                    <a href={googleCalendarUrl(meeting)} target="_blank" rel="noopener" class="cal-option">Google Calendar</a>
                    <button class="cal-option" onclick={() => downloadIcs(meeting)}>Download .ics</button>
                  </div>
                {/if}
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
                {#if voiceCounts.has(`agenda-item:${item.id}`)}
                  {@const counts = voiceCounts.get(`agenda-item:${item.id}`)!}
                  <div class="voice-counts">
                    {#if counts.support > 0}<span class="vc vc-support">{counts.support} support</span>{/if}
                    {#if counts.oppose > 0}<span class="vc vc-oppose">{counts.oppose} oppose</span>{/if}
                    {#if counts.watching > 0}<span class="vc vc-watch">{counts.watching} watching</span>{/if}
                  </div>
                {/if}
                {#if item.stance_eligible}
                  <div class="voice-actions">
                    {#if identity?.isUnlocked}
                      {@const eid = `agenda-item:${item.id}`}
                      <button
                        class="voice-btn vb-support"
                        class:active={userStances.get(eid) === 'support'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'support')}
                      >Support</button>
                      <button
                        class="voice-btn vb-oppose"
                        class:active={userStances.get(eid) === 'oppose'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'oppose')}
                      >Oppose</button>
                      <button
                        class="voice-btn vb-watch"
                        class:active={userStances.get(eid) === 'watching'}
                        disabled={votingInProgress.has(eid)}
                        onclick={() => handleVoice(eid, 'watching')}
                      >Watch</button>
                    {:else if identity}
                      <span class="voice-locked">Unlock to vote</span>
                    {/if}
                  </div>
                {/if}
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
              <div class="card decision-card" class:expanded-card={expandedDecisions.has(decision.title)}>
                <button class="decision-row decision-toggle" onclick={() => toggleDecisionDetail(decision.title)}>
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
                      {#if voiceCounts.has(decision.id)}
                        {@const counts = voiceCounts.get(decision.id)!}
                        {#if counts.total > 0}
                          <span class="meta-sep">&middot;</span>
                          <span class="voice-inline">{counts.total} voices</span>
                        {/if}
                      {/if}
                    </div>
                  </div>
                  <span class="expand-chevron" class:open={expandedDecisions.has(decision.title)}></span>
                </button>

                {#if expandedDecisions.has(decision.title)}
                  <div class="decision-detail">
                    {#if decisionLoading.has(decision.title)}
                      <div class="detail-loading">Loading details...</div>
                    {:else if decisionDetails.has(decision.title)}
                      {@const detail = decisionDetails.get(decision.title)!}
                      {#if detail.found && detail.decision}
                        {#if detail.decision.body}
                          <div class="detail-body">{detail.decision.body}</div>
                        {/if}
                        {#if detail.testimony?.public_comments && detail.testimony.public_comments.length > 0}
                          <div class="detail-section">
                            <div class="detail-label">Public Testimony ({detail.testimony.public_comments.length})</div>
                            {#each detail.testimony.public_comments.slice(0, 3) as comment}
                              <div class="testimony-item">
                                <span class="testimony-speaker">{comment.speaker}</span>
                                <span class="testimony-text">{comment.text}</span>
                              </div>
                            {/each}
                            {#if detail.testimony.public_comments.length > 3}
                              <div class="detail-more">+{detail.testimony.public_comments.length - 3} more</div>
                            {/if}
                          </div>
                        {/if}
                        {#if detail.related_decisions && detail.related_decisions.length > 0}
                          <div class="detail-section">
                            <div class="detail-label">Related Decisions</div>
                            {#each detail.related_decisions.slice(0, 3) as related}
                              <div class="related-item">
                                <span class="outcome-dot {outcomeClass(related.outcome)}"></span>
                                <span class="related-title">{related.title}</span>
                                <span class="related-date">{related.date}</span>
                              </div>
                            {/each}
                          </div>
                        {/if}
                        <!-- Voice buttons for decisions -->
                        <div class="voice-actions detail-voice">
                          {#if identity?.isUnlocked}
                            <button
                              class="voice-btn vb-support"
                              class:active={userStances.get(decision.id) === 'support'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'support')}
                            >Support</button>
                            <button
                              class="voice-btn vb-oppose"
                              class:active={userStances.get(decision.id) === 'oppose'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'oppose')}
                            >Oppose</button>
                            <button
                              class="voice-btn vb-watch"
                              class:active={userStances.get(decision.id) === 'watching'}
                              disabled={votingInProgress.has(decision.id)}
                              onclick={() => handleVoice(decision.id, 'watching')}
                            >Watch</button>
                          {:else if identity}
                            <span class="voice-locked">Unlock to vote</span>
                          {/if}
                        </div>
                      {:else}
                        <div class="detail-empty">No details available</div>
                      {/if}
                    {/if}
                  </div>
                {/if}
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

  /* === Provenance Panel === */
  .provenance-panel {
    background: #1e293b;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 12px;
    border: 1px solid #334155;
  }
  .prov-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .prov-title {
    font-size: 12px;
    font-weight: 600;
    color: #e2e8f0;
  }
  .prov-jurisdiction {
    font-size: 10px;
    color: #64748b;
  }
  .prov-stats {
    display: flex;
    gap: 4px;
    font-size: 11px;
    color: #94a3b8;
    margin-bottom: 8px;
  }
  .prov-corpora {
    border-top: 1px solid #334155;
    padding-top: 6px;
  }
  .corpus-row {
    display: flex;
    justify-content: space-between;
    padding: 3px 0;
    font-size: 11px;
  }
  .corpus-name { color: #cbd5e1; }
  .corpus-count { color: #64748b; font-variant-numeric: tabular-nums; }
  .prov-freshness {
    border-top: 1px solid #334155;
    padding-top: 6px;
    margin-top: 6px;
    font-size: 10px;
    color: #475569;
  }
  .prov-loading {
    font-size: 11px;
    color: #64748b;
    padding: 8px 0;
  }

  .icon-btn.active { color: #818cf8; background: #1e293b; }

  /* === Past Meeting === */
  .past-meeting {
    opacity: 0.65;
  }
  .past-icon {
    font-size: 12px;
    margin-right: 4px;
  }
  .meeting-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 6px;
  }

  /* === Calendar === */
  .cal-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #64748b;
    cursor: pointer;
    padding: 2px;
    border-radius: 3px;
  }
  .cal-btn:hover { color: #818cf8; background: #334155; }

  .cal-dropdown {
    display: flex;
    gap: 8px;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #334155;
  }
  .cal-option {
    font-size: 11px;
    color: #6366f1;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-decoration: none;
  }
  .cal-option:hover { color: #818cf8; text-decoration: underline; }

  /* === Voice Counts === */
  .voice-counts {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    font-size: 10px;
  }
  .vc {
    padding: 1px 5px;
    border-radius: 3px;
  }
  .vc-support { background: #14532d; color: #4ade80; }
  .vc-oppose { background: #7f1d1d; color: #f87171; }
  .vc-watch { background: #334155; color: #94a3b8; }

  .voice-inline {
    color: #818cf8;
    font-size: 10px;
  }

  /* === Decision Expansion === */
  .decision-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
  }
  .decision-toggle:hover .card-title { color: #818cf8; }

  .expand-chevron {
    display: inline-block;
    flex-shrink: 0;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #475569;
    transition: transform 0.15s ease;
    margin-left: 6px;
    margin-top: 6px;
  }
  .expand-chevron.open { transform: rotate(180deg); }

  .expanded-card {
    border: 1px solid #334155;
  }

  .decision-detail {
    border-top: 1px solid #334155;
    padding-top: 8px;
    margin-top: 8px;
  }
  .detail-loading {
    font-size: 11px;
    color: #64748b;
    padding: 4px 0;
  }
  .detail-body {
    font-size: 12px;
    color: #94a3b8;
    line-height: 1.4;
    margin-bottom: 8px;
  }
  .detail-section {
    margin-bottom: 8px;
  }
  .detail-label {
    font-size: 10px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }
  .testimony-item {
    font-size: 11px;
    padding: 4px 0;
    border-bottom: 1px solid #1e293b;
  }
  .testimony-speaker {
    color: #cbd5e1;
    font-weight: 500;
    margin-right: 4px;
  }
  .testimony-speaker::after { content: ':'; }
  .testimony-text {
    color: #94a3b8;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .detail-more {
    font-size: 10px;
    color: #6366f1;
    margin-top: 4px;
  }
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
  .outcome-dot.other { background: #94a3b8; }
  .related-title { color: #cbd5e1; flex: 1; }
  .related-date { color: #475569; }
  .detail-empty {
    font-size: 11px;
    color: #475569;
    font-style: italic;
  }

  /* === Voice Action Buttons === */
  .voice-actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
  }
  .detail-voice {
    border-top: 1px solid #334155;
    padding-top: 8px;
    margin-top: 8px;
  }
  .voice-btn {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 12px;
    border: 1px solid #334155;
    background: transparent;
    color: #94a3b8;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .voice-btn:hover:not(:disabled) {
    border-color: #475569;
    color: #e2e8f0;
  }
  .voice-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .vb-support.active {
    background: #14532d;
    border-color: #22c55e;
    color: #4ade80;
  }
  .vb-oppose.active {
    background: #7f1d1d;
    border-color: #ef4444;
    color: #f87171;
  }
  .vb-watch.active {
    background: #1e3a5f;
    border-color: #3b82f6;
    color: #60a5fa;
  }
  .voice-locked {
    font-size: 10px;
    color: #64748b;
    font-style: italic;
  }
</style>

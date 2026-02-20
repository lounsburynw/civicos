<svelte:options customElement="civic-initiative-card" />

<script lang="ts">
  interface Initiative {
    id: string;
    topic: string;
    title: string;
    description: string;
    coordination_url?: string;
    voice_count: number;
    creator_attested?: boolean;
    attested_voice_count?: number;
  }

  interface CivicAction {
    id: string;
    action_type: string;
    description: string;
    target?: string;
    deadline?: string;
    template?: string;
  }

  interface ActionProgress {
    commitment_count: number;
    completion_count: number;
    target_count?: number;
    progress_percent?: number;
  }

  let {
    initiative,
    expanded = false,
    actions = [] as CivicAction[],
    actionsLoading = false,
    actionProgress = {} as Record<string, ActionProgress>,
    committedActionIds = [] as string[],
    completedActionIds = [] as string[],
    actionInProgressIds = [] as string[],
    isUnlocked = false,
    hasIdentity = false,
    showAddAction = true,
    ontoggle,
    oncommit,
    oncomplete,
    onwithdraw,
    oncopytemplate,
    onaddaction,
  }: {
    initiative: Initiative;
    expanded?: boolean;
    actions?: CivicAction[];
    actionsLoading?: boolean;
    actionProgress?: Record<string, ActionProgress>;
    committedActionIds?: string[];
    completedActionIds?: string[];
    actionInProgressIds?: string[];
    isUnlocked?: boolean;
    hasIdentity?: boolean;
    showAddAction?: boolean;
    ontoggle?: () => void;
    oncommit?: (detail: { actionId: string }) => void;
    oncomplete?: (detail: { actionId: string }) => void;
    onwithdraw?: (detail: { actionId: string }) => void;
    oncopytemplate?: (detail: { template: string }) => void;
    onaddaction?: () => void;
  } = $props();

  let committedSet = $derived(new Set(committedActionIds));
  let completedSet = $derived(new Set(completedActionIds));
  let inProgressSet = $derived(new Set(actionInProgressIds));

  let stats = $derived.by(() => {
    let committed = 0, completed = 0;
    for (const a of actions) {
      const p = actionProgress[a.id];
      if (p) {
        committed += p.commitment_count;
        completed += p.completion_count;
      }
    }
    return { committed, completed };
  });

  function deadlineDaysLeft(deadline: string): number {
    const d = new Date(deadline);
    const now = new Date();
    return Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  }

  function deadlineLabel(deadline: string): string {
    const days = deadlineDaysLeft(deadline);
    if (days < 0) return 'overdue';
    if (days === 0) return 'due today';
    if (days === 1) return 'due tomorrow';
    return `${days}d left`;
  }

  function deadlineClass(deadline: string): string {
    const days = deadlineDaysLeft(deadline);
    if (days < 0) return 'overdue';
    if (days <= 3) return 'urgent';
    return 'normal';
  }

  function actionTypeLabel(type: string): string {
    const labels: Record<string, string> = {
      written_comment: 'Write Comment',
      attend_meeting: 'Attend Meeting',
      public_comment: 'Public Comment',
      contact_official: 'Contact Official',
      signature: 'Sign Petition',
      share: 'Share',
      custom: 'Action',
    };
    return labels[type] || type;
  }
</script>

<div class="initiative-content">
  <button class="ini-card-toggle" onclick={() => ontoggle?.()}>
    <div class="ini-card-top">
      <span class="ini-topic-pill">
        {initiative.topic}
        {#if initiative.creator_attested}
          <svg class="ini-attested-check" viewBox="0 0 16 16" fill="currentColor" title="Verified creator"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>
        {/if}
      </span>
      <div class="ini-card-badges">
        {#if initiative.voice_count > 0}
          <span class="ini-voice-inline">
            <svg class="ini-voice-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M6.956 1.745C7.021.81 7.908.087 8.864.325l.261.066c.463.116.874.456 1.012.965.22.816.533 2.511.062 4.51a10 10 0 0 1 .443-.051c.713-.065 1.669-.072 2.516.21.518.173.994.681 1.2 1.273.184.532.16 1.162-.234 1.733q.086.18.138.363c.077.27.113.567.113.856s-.036.586-.113.856c-.039.135-.09.273-.16.404.169.387.107.82-.003 1.149a3.2 3.2 0 0 1-.488.901c.054.152.076.312.076.465 0 .305-.089.625-.253.912C13.1 15.522 12.437 16 11.5 16H8c-.605 0-1.07-.081-1.466-.218a4.8 4.8 0 0 1-.97-.484l-.048-.03c-.504-.307-.999-.609-2.068-.722C2.682 14.464 2 13.846 2 13V9c0-.85.685-1.432 1.357-1.615.849-.232 1.574-.787 2.132-1.41.56-.627.914-1.28 1.039-1.639.199-.575.356-1.539.428-2.59z"/></svg>
            <span class="ini-voice-num">{initiative.voice_count}</span>
          </span>
        {/if}
        {#if initiative.coordination_url}
          <svg class="ini-coord-icon" viewBox="0 0 16 16" fill="none"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2L7 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        {/if}
        <svg class="ini-expand-chevron" class:expanded={expanded} viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/></svg>
      </div>
    </div>
    <div class="ini-card-title">{initiative.title}</div>
    <div class="ini-card-desc">{initiative.description}</div>
    {#if stats.committed > 0 || stats.completed > 0}
      <div class="ini-card-stats">
        {#if stats.committed > 0}<span class="ini-stat">{stats.committed} committed</span>{/if}
        {#if stats.completed > 0}<span class="ini-stat ini-stat-done">{stats.completed} done</span>{/if}
      </div>
    {/if}
  </button>

  {#if expanded}
    <div class="ini-detail">
      {#if initiative.coordination_url}
        <a href={initiative.coordination_url} target="_blank" rel="noopener" class="ini-coord-link">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6 3H3v10h10v-3M9 2h5v5M14 2L7 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Join coordination channel
        </a>
      {/if}

      {#if actionsLoading}
        <div class="ini-detail-msg">Loading actions...</div>
      {:else}
        {#if actions.length === 0 && showAddAction}
          <div class="ini-detail-msg">No civic actions defined yet</div>
        {/if}
        {#if actions.length > 0}
          <div class="ini-detail-label">Civic Actions</div>
          {#each actions as action}
            <div class="ini-action">
              <div class="ini-action-top">
                <span class="ini-action-type">{actionTypeLabel(action.action_type)}</span>
                {#if action.deadline}
                  <span class="ini-deadline {deadlineClass(action.deadline)}">
                    {deadlineLabel(action.deadline)}
                  </span>
                {/if}
              </div>
              <div class="ini-action-desc">{action.description}</div>
              {#if action.target}
                <div class="ini-action-target">Target: {action.target}</div>
              {/if}

              {#if actionProgress[action.id]}
                {@const progress = actionProgress[action.id]}
                <div class="ini-progress">
                  <div class="ini-progress-bar">
                    <div class="ini-progress-fill" style="width: {progress.progress_percent ?? 0}%"></div>
                  </div>
                  <span class="ini-progress-text">
                    {progress.completion_count}/{progress.target_count ?? '?'}
                    {#if progress.commitment_count > 0}
                      ({progress.commitment_count} committed)
                    {/if}
                  </span>
                </div>
              {/if}

              <div class="ini-action-btns">
                {#if isUnlocked}
                  {#if completedSet.has(action.id)}
                    <span class="ini-completed-label">
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                      Done
                    </span>
                  {:else if committedSet.has(action.id)}
                    <button class="ini-btn-primary ini-btn-sm" disabled={inProgressSet.has(action.id)} onclick={() => oncomplete?.({ actionId: action.id })}>Mark Done</button>
                    <button class="ini-btn-cancel ini-btn-sm" disabled={inProgressSet.has(action.id)} onclick={() => onwithdraw?.({ actionId: action.id })}>Withdraw</button>
                  {:else}
                    <button class="ini-btn-primary ini-btn-sm" disabled={inProgressSet.has(action.id)} onclick={() => oncommit?.({ actionId: action.id })}>Commit</button>
                  {/if}
                {:else if hasIdentity}
                  <span class="ini-locked-hint">Unlock to participate</span>
                {/if}
              </div>

              {#if action.template}
                <div class="ini-draft">
                  <textarea class="ini-draft-text" readonly>{action.template}</textarea>
                  <div class="ini-draft-actions">
                    <button class="ini-btn-sm ini-btn-copy" onclick={() => oncopytemplate?.({ template: action.template! })}>Copy</button>
                  </div>
                </div>
              {/if}
            </div>
          {/each}
        {/if}
        {#if showAddAction}
          <button class="ini-add-action" onclick={() => onaddaction?.()}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            Add Action
          </button>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .initiative-content {}

  /* === Toggle button (collapsed view) === */
  .ini-card-toggle {
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }
  .ini-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
    gap: 8px;
  }
  .ini-topic-pill {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    background: rgba(255, 255, 255, 0.06);
    color: #9ca3af;
    font-size: 10px;
    font-weight: 600;
    border-radius: 10px;
    text-transform: capitalize;
    letter-spacing: 0.02em;
  }
  .ini-attested-check {
    width: 10px;
    height: 10px;
    color: #4ade80;
    flex-shrink: 0;
  }
  .ini-card-badges {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .ini-voice-inline {
    display: flex;
    align-items: center;
    gap: 3px;
    color: #9ca3af;
  }
  .ini-voice-icon {
    width: 13px;
    height: 13px;
    color: #6b7280;
  }
  .ini-voice-num {
    font-size: 11px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: #9ca3af;
  }
  .ini-coord-icon {
    width: 13px;
    height: 13px;
    color: #6b7280;
    flex-shrink: 0;
  }
  .ini-expand-chevron {
    width: 12px;
    height: 12px;
    color: #6b7280;
    flex-shrink: 0;
    transition: transform 150ms ease;
  }
  .ini-expand-chevron.expanded {
    transform: rotate(180deg);
  }
  .ini-card-title {
    color: #eee;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
  }
  .ini-card-toggle:hover .ini-card-title { color: #e5e7eb; }
  .ini-card-toggle:hover .ini-expand-chevron { color: #9ca3af; }
  .ini-card-toggle:hover .ini-coord-icon { color: #9ca3af; }
  .ini-card-desc {
    color: #6b7280;
    font-size: 12px;
    margin-top: 3px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    line-height: 1.4;
  }

  /* === Stats row === */
  .ini-card-stats {
    display: flex;
    gap: 8px;
    margin-top: 4px;
    font-size: 10px;
  }
  .ini-stat { color: #9ca3af; }
  .ini-stat.ini-stat-done { color: #4ade80; }

  /* === Expanded detail === */
  .ini-detail {
    border-top: 1px solid #262626;
    padding-top: 10px;
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .ini-coord-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #9ca3af;
    text-decoration: none;
    transition: color 0.15s;
  }
  .ini-coord-link:hover { color: #d1d5db; text-decoration: underline; }
  .ini-detail-msg { font-size: 12px; color: #6b7280; font-style: italic; }
  .ini-detail-label {
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  /* === Action cards === */
  .ini-action {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 12px;
    position: relative;
  }
  .ini-action-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .ini-action-type {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.06);
    color: #9ca3af;
  }
  .ini-deadline {
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 6px;
  }
  .ini-deadline.normal { background: rgba(107, 114, 128, 0.12); color: #9ca3af; }
  .ini-deadline.urgent { background: rgba(251, 191, 36, 0.12); color: #fbbf24; }
  .ini-deadline.overdue { background: rgba(239, 68, 68, 0.12); color: #f87171; }
  .ini-action-desc { font-size: 13px; color: #d1d5db; line-height: 1.4; }
  .ini-action-target { font-size: 12px; color: #6b7280; margin-top: 2px; }

  /* === Progress bar === */
  .ini-progress {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 6px;
  }
  .ini-progress-bar {
    flex: 1;
    height: 6px;
    background: #333;
    border-radius: 3px;
    overflow: hidden;
  }
  .ini-progress-fill {
    height: 100%;
    background: #6b7280;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .ini-progress-text { font-size: 11px; color: #6b7280; white-space: nowrap; }

  /* === Action buttons === */
  .ini-action-btns {
    display: flex;
    gap: 6px;
    margin-top: 8px;
    align-items: center;
  }
  .ini-btn-primary {
    padding: 8px 16px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.1);
    color: #e5e7eb;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    font-family: inherit;
  }
  .ini-btn-primary:hover:not(:disabled) { background: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.25); }
  .ini-btn-primary:disabled { opacity: 0.4; cursor: default; }
  .ini-btn-cancel {
    padding: 8px 14px;
    border: 1px solid #374151;
    border-radius: 8px;
    background: transparent;
    color: #9ca3af;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
    font-family: inherit;
  }
  .ini-btn-cancel:hover { border-color: #4b5563; color: #d1d5db; }
  .ini-btn-sm { padding: 5px 12px; font-size: 12px; }
  .ini-completed-label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 600;
    color: #4ade80;
    padding: 3px 10px;
    background: rgba(34, 197, 94, 0.1);
    border-radius: 6px;
  }
  .ini-locked-hint {
    font-size: 11px;
    color: #6b7280;
    font-style: italic;
  }

  /* === Template draft === */
  .ini-draft {
    margin-top: 8px;
    border: 1px solid rgba(139, 92, 246, 0.2);
    border-radius: 8px;
    padding: 8px;
    background: rgba(139, 92, 246, 0.05);
  }
  .ini-draft-text {
    width: 100%;
    min-height: 120px;
    background: transparent;
    border: none;
    color: #d1d5db;
    font-size: 12px;
    line-height: 1.5;
    resize: vertical;
    font-family: inherit;
    outline: none;
    box-sizing: border-box;
  }
  .ini-draft-actions {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  .ini-btn-copy {
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 500;
    color: #a78bfa;
    background: rgba(139, 92, 246, 0.15);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 6px;
    cursor: pointer;
    font-family: inherit;
  }
  .ini-btn-copy:hover { background: rgba(139, 92, 246, 0.25); }

  /* === Add Action button === */
  .ini-add-action {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    background: transparent;
    border: 1px dashed #374151;
    border-radius: 8px;
    color: #6b7280;
    font-size: 12px;
    padding: 8px;
    cursor: pointer;
    transition: all 0.15s;
    font-family: inherit;
  }
  .ini-add-action:hover { color: #3b82f6; border-color: #3b82f6; }
</style>

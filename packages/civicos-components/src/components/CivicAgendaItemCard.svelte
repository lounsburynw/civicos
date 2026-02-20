<svelte:options customElement="civic-agenda-item-card" />

<script lang="ts">
  import CivicVoiceButtons from './CivicVoiceButtons.svelte';
  import { urgencyClass } from '../utils/civic-helpers.js';

  type Stance = 'support' | 'oppose' | 'watching';

  let {
    item,
    voiceCounts = null,
    userStance = null as Stance | null,
    votingDisabled = false,
    locked = false,
    showVoice = false,
    daysUntil = null as number | null,
    onvoice,
  }: {
    item: {
      id: string;
      item_number?: string;
      title: string;
      description?: string;
      why_it_matters?: string;
      meeting_title: string;
      meeting_date: string;
      project_type?: string;
      stance_eligible: boolean;
      comment_eligible: boolean;
    };
    voiceCounts?: {
      support: number;
      oppose: number;
      watching: number;
      attested?: number | null;
      unattested?: number | null;
    } | null;
    userStance?: Stance | null;
    votingDisabled?: boolean;
    locked?: boolean;
    showVoice?: boolean;
    daysUntil?: number | null;
    onvoice?: (detail: { entityId: string; stance: Stance }) => void;
  } = $props();

  let entityId = $derived(`agenda-item:${item.id}`);
</script>

<div class="agenda-item-content">
  <div class="card-top-row">
    {#if item.item_number}
      <span class="item-number">#{item.item_number}</span>
    {/if}
    <span class="item-meeting">{item.meeting_title} &middot; {item.meeting_date}</span>
    {#if daysUntil !== null}
      <span class="deadline-tag {urgencyClass(daysUntil)}">
        {#if daysUntil === 0}Meeting today{:else if daysUntil === 1}Tomorrow{:else}In {daysUntil} days{/if}
      </span>
    {/if}
  </div>
  <div class="card-title">{item.title}</div>
  {#if item.description}
    <div class="card-desc">{item.description}</div>
  {/if}
  {#if item.why_it_matters}
    <div class="card-why"><strong>Why it matters:</strong> <em>{item.why_it_matters}</em></div>
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
  {#if voiceCounts}
    <div class="voice-counts">
      {#if voiceCounts.support > 0}<span class="vc vc-support">{voiceCounts.support} support</span>{/if}
      {#if voiceCounts.oppose > 0}<span class="vc vc-oppose">{voiceCounts.oppose} oppose</span>{/if}
      {#if voiceCounts.watching > 0}<span class="vc vc-watch">{voiceCounts.watching} watching</span>{/if}
      {#if voiceCounts.attested != null && voiceCounts.attested > 0}
        <span class="vc vc-attested" title="{voiceCounts.attested} verified, {voiceCounts.unattested ?? 0} unverified">
          <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>
          {voiceCounts.attested}
        </span>
      {/if}
    </div>
  {/if}
  {#if showVoice}
    <CivicVoiceButtons
      entityId={entityId}
      userStance={userStance}
      disabled={votingDisabled}
      {locked}
      {onvoice}
    />
  {/if}
</div>

<style>
  .agenda-item-content {}
  .card-top-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 11px;
    color: #6b7280;
  }
  .item-number {
    color: #9ca3af;
    font-weight: 600;
  }
  .card-title {
    color: #e5e7eb;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.3;
  }
  .card-desc {
    color: #9ca3af;
    font-size: 12px;
    margin-top: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .card-why {
    color: #9ca3af;
    font-size: 12px;
    margin-top: 4px;
    line-height: 1.45;
  }
  .card-why strong { color: #d1d5db; }
  .card-tags {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    flex-wrap: wrap;
  }
  .tag {
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.04);
    color: #6b7280;
    font-weight: 500;
  }
  .tag-voice { background: rgba(255, 255, 255, 0.08); color: #d1d5db; }
  .tag-comment { background: rgba(255, 255, 255, 0.08); color: #d1d5db; }
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
  .vc-watch { background: #374151; color: #9ca3af; }
  .vc-attested { display: inline-flex; align-items: center; gap: 2px; background: rgba(34, 197, 94, 0.12); color: #22c55e; }
  .deadline-tag { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 3px; }
  .deadline-tag.urgent-critical { background: rgba(255, 255, 255, 0.06); color: #e5e7eb; }
  .deadline-tag.urgent-soon { background: rgba(255, 255, 255, 0.04); color: #d1d5db; }
  .deadline-tag.urgent-normal { background: rgba(255, 255, 255, 0.03); color: #9ca3af; font-weight: 500; }
  .deadline-tag.urgent-closed { background: rgba(255, 255, 255, 0.02); color: #6b7280; font-weight: 500; }
</style>

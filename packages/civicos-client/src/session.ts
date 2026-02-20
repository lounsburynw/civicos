/**
 * CivicSession — high-level orchestration for civic data loading and AI operations.
 *
 * Composes ApiClient + RegistryClient + optional AIManager to provide
 * ready-to-use data loading patterns that any surface can consume.
 * Stateless: returns data, does not manage reactive UI state.
 */

import type { ApiClient } from './api.js';
import type { RegistryClient } from './registry.js';
import type { AIManager } from './ai/manager.js';
import type {
  CityPulseData,
  VoiceCounts,
  CommentCounts,
  CommentSynthesis,
  DecisionDetailData,
  DataProvenance,
  PulseAgendaItem,
  Initiative,
  CivicAction,
  CivicActionProgress,
  Comment,
} from './types.js';
import type { AIChatResult } from './ai/types.js';
import { composeDraftPrompt, composeEnrichPrompt, SYSTEM_PROMPT, QA_SYSTEM_PROMPT } from './ai/prompts.js';

type Stance = 'support' | 'oppose' | 'watching';

/** Full pulse data bundle with voice counts, comment counts, syntheses, and initiatives. */
export interface PulseBundle {
  pulse: CityPulseData;
  voiceCounts: Map<string, VoiceCounts>;
  commentCounts: Map<string, CommentCounts>;
  syntheses: Map<string, CommentSynthesis>;
  initiatives: Initiative[];
}

/** Comment thread with comments and optional synthesis. */
export interface CommentThread {
  comments: Comment[];
  synthesis: CommentSynthesis | null;
}

/** Initiative detail with actions and their progress. */
export interface InitiativeDetail {
  actions: CivicAction[];
  progress: Map<string, CivicActionProgress>;
}

export class CivicSession {
  constructor(
    private api: ApiClient,
    private registry: RegistryClient,
    private ai?: AIManager,
  ) {}

  // === Full data loading ===

  /**
   * Load pulse data with all enrichments in parallel.
   * This is the "load everything for a jurisdiction" pattern.
   */
  async loadPulseBundle(options?: { daysAhead?: number; daysBack?: number }): Promise<PulseBundle> {
    const pulse = await this.loadPulse(options);
    const jurisdiction = pulse.jurisdiction;

    const voiceIds = CivicSession.extractVoiceEntityIds(pulse);
    const commentIds = CivicSession.extractCommentEntityIds(pulse);

    const [voiceCounts, commentCounts, initiatives] = await Promise.all([
      voiceIds.length > 0
        ? this.api.getVoiceCountsBatch(voiceIds, jurisdiction)
        : Promise.resolve(new Map<string, VoiceCounts>()),
      commentIds.length > 0
        ? this.api.getCommentCountsBatch(commentIds, jurisdiction)
        : Promise.resolve(new Map<string, CommentCounts>()),
      this.api.getInitiatives(jurisdiction),
    ]);

    const syntheses = await this.loadCommentSyntheses(commentCounts);

    return { pulse, voiceCounts, commentCounts, syntheses, initiatives };
  }

  // === Individual loading (for lazy/incremental patterns) ===

  /** Load pulse data for the active jurisdiction. Refreshes registry and configures relay. */
  async loadPulse(options?: { daysAhead?: number; daysBack?: number }): Promise<CityPulseData> {
    try { await this.registry.getRegistryServers(true); } catch { /* keep existing servers */ }
    const pulse = await this.api.getCityPulse(options?.daysAhead, options?.daysBack);
    if (pulse.relay_url) {
      this.registry.setRelayUrl(pulse.relay_url);
    }
    return pulse;
  }

  /** Load voice counts for entities in the pulse data. */
  async loadVoiceCounts(pulse: CityPulseData): Promise<Map<string, VoiceCounts>> {
    const ids = CivicSession.extractVoiceEntityIds(pulse);
    if (ids.length === 0) return new Map();
    return this.api.getVoiceCountsBatch(ids, pulse.jurisdiction);
  }

  /** Load comment counts for entities in the pulse data. */
  async loadCommentCounts(pulse: CityPulseData): Promise<Map<string, CommentCounts>> {
    const ids = CivicSession.extractCommentEntityIds(pulse);
    if (ids.length === 0) return new Map();
    return this.api.getCommentCountsBatch(ids, pulse.jurisdiction);
  }

  /** Load comment syntheses for entities that have comments. */
  async loadCommentSyntheses(commentCounts: Map<string, CommentCounts>): Promise<Map<string, CommentSynthesis>> {
    const syntheses = new Map<string, CommentSynthesis>();
    const withComments = [...commentCounts].filter(([, cc]) => cc.count > 0);
    await Promise.all(
      withComments.map(async ([entityId]) => {
        const synth = await this.api.getCommentSynthesis(entityId);
        if (synth) syntheses.set(entityId, synth);
      }),
    );
    return syntheses;
  }

  /** Load decision detail by title. */
  async loadDecisionDetail(title: string): Promise<DecisionDetailData> {
    return this.api.getDecisionDetail(title);
  }

  /** Load comments and synthesis for an entity. */
  async loadCommentThread(entityId: string): Promise<CommentThread> {
    const [comments, synthesis] = await Promise.all([
      this.api.getComments(entityId).catch((err) => {
        console.error('[CivicSession] getComments failed for', entityId, err);
        throw err; // Re-throw so caller can handle
      }),
      this.api.getCommentSynthesis(entityId),
    ]);
    return { comments, synthesis };
  }

  /** Load actions and their progress for an initiative. */
  async loadInitiativeDetail(initiativeId: string): Promise<InitiativeDetail> {
    const actions = await this.api.getCivicActions(initiativeId);
    const progress = new Map<string, CivicActionProgress>();
    await Promise.all(
      actions.map(async (action) => {
        const p = await this.api.getCivicActionProgress(action.id);
        if (p) progress.set(action.id, p);
      }),
    );
    return { actions, progress };
  }

  /** Load actions and progress for all initiatives. */
  async loadAllInitiativeDetails(initiatives: Initiative[]): Promise<Map<string, InitiativeDetail>> {
    const results = new Map<string, InitiativeDetail>();
    await Promise.all(
      initiatives.map(async (ini) => {
        const detail = await this.loadInitiativeDetail(ini.id);
        results.set(ini.id, detail);
      }),
    );
    return results;
  }

  /** Load data provenance information. */
  async loadProvenance(): Promise<DataProvenance> {
    return this.api.getDataProvenance();
  }

  // === AI operations ===

  /** Draft a public comment for an agenda item using AI. */
  async draftComment(
    item: PulseAgendaItem,
    stance?: Stance,
    counts?: VoiceCounts,
  ): Promise<string | null> {
    if (!this.ai) return null;
    const prompt = composeDraftPrompt(item, stance, counts);
    const result = await this.ai.complete(prompt, SYSTEM_PROMPT);
    return result.success ? result.text! : null;
  }

  /** Enrich an existing draft with contextual information. */
  async enrichDraft(draft: string, itemId: string): Promise<string | null> {
    if (!this.ai) return null;
    const context = await this.api.getItemContext(itemId, ['history', 'regulatory', 'testimony']);
    const prompt = composeEnrichPrompt(draft, context);
    const result = await this.ai.complete(prompt, SYSTEM_PROMPT);
    return result.success ? result.text! : null;
  }

  /** Ask a question about civic context using AI. */
  async askQuestion(question: string): Promise<string | null> {
    if (!this.ai) return null;
    const result = await this.ai.complete(question, QA_SYSTEM_PROMPT);
    return result.success ? result.text! : null;
  }

  /** Ask a civic question with tool-backed search (uses server-side tool execution). */
  async chat(question: string, jurisdiction?: string): Promise<AIChatResult | null> {
    if (!this.ai) return null;
    return this.ai.chat(question, jurisdiction);
  }

  // === Entity ID extraction (static helpers) ===

  /** Extract entity IDs that need voice counts from pulse data. */
  static extractVoiceEntityIds(pulse: CityPulseData): string[] {
    const ids: string[] = [];
    if (pulse.recent_outcomes) {
      ids.push(...pulse.recent_outcomes.map(d => d.id).filter(Boolean));
    }
    if (pulse.upcoming_items) {
      ids.push(...pulse.upcoming_items.filter(i => i.stance_eligible).map(i => `agenda-item:${i.id}`));
    }
    return ids;
  }

  /** Extract entity IDs that need comment counts from pulse data. */
  static extractCommentEntityIds(pulse: CityPulseData): string[] {
    const ids: string[] = [];
    if (pulse.upcoming_items) {
      ids.push(...pulse.upcoming_items.filter(i => i.comment_eligible).map(i => `agenda-item:${i.id}`));
    }
    return ids;
  }

  /** Extract entity IDs from focal point data (comment periods, hearings, governor's desk). */
  static extractFocalPointEntityIds(pulse: CityPulseData): string[] {
    const ids: string[] = [];
    const p = pulse as any;
    if (p.comment_periods) {
      for (const period of p.comment_periods) {
        if (period.document_number) ids.push(`rule:${period.document_number}`);
      }
    }
    if (p.upcoming_hearings) {
      for (const hearing of p.upcoming_hearings) {
        if (hearing.bill_id) ids.push(`bill:${hearing.bill_id}`);
      }
    }
    if (p.governors_desk) {
      for (const bill of p.governors_desk) {
        if (bill.bill_id) ids.push(`bill:${bill.bill_id}`);
      }
    }
    return ids;
  }
}

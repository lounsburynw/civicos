/**
 * CivicOS API client — platform-agnostic REST + relay API access.
 *
 * All endpoint resolution is handled by the injected RegistryClient.
 * No browser-specific dependencies.
 */

import type { RegistryClient } from './registry.js';
import type { Signer } from './interfaces.js';
import type {
  CityPulseData,
  DecisionDetailData,
  DataProvenance,
  VoiceCounts,
  ToolResponse,
  Initiative,
  CivicAction,
  CivicActionProgress,
  IssueGeography,
  BudgetSummary,
  Comment,
  CommentCounts,
  CommentSynthesis,
  ContextBundle,
} from './types.js';
import {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createRevokeContent,
  createCommentTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
  createWithdrawalContent,
  createWithdrawalTags,
  createInitiativeContent,
  createInitiativeTags,
  createCivicActionContent,
  createCivicActionTags,
  createAttestationContent,
  createAttestationTags,
} from './events.js';

export class ApiClient {
  private signer?: Signer;

  constructor(registry: RegistryClient, signer?: Signer);
  constructor(private registry: RegistryClient, signerOrUndefined?: Signer) {
    this.signer = signerOrUndefined;
  }

  setSigner(signer: Signer): void {
    this.signer = signer;
  }

  private requireSigner(): Signer {
    if (!this.signer) throw new Error('Signer required for authenticated operations');
    return this.signer;
  }

  // === MCP REST API ===

  async getCityPulse(daysAhead = 14, daysBack = 30): Promise<CityPulseData> {
    return this.apiRequest<CityPulseData>('/api/tools/city-pulse', {
      method: 'POST',
      body: JSON.stringify({ days_ahead: daysAhead, days_back: daysBack }),
    });
  }

  async getCityPulseFromServer(serverBaseUrl: string, daysAhead = 14, daysBack = 30): Promise<CityPulseData> {
    const url = `${serverBaseUrl}/api/tools/city-pulse`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days_ahead: daysAhead, days_back: daysBack }),
    });
    if (!response.ok) {
      throw new Error(`API error ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (!result.success) {
      throw new Error(result.error || 'API returned an error');
    }
    return result.data;
  }

  async getDecisionDetail(title: string): Promise<DecisionDetailData> {
    return this.apiRequest<DecisionDetailData>('/api/tools/decision-detail', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  }

  async getDataProvenance(): Promise<DataProvenance> {
    return this.apiRequest<DataProvenance>('/api/tools/data-provenance');
  }

  async getIssueGeography(limit = 500): Promise<IssueGeography> {
    return this.apiRequest<IssueGeography>(`/api/tools/issue-geography?limit=${limit}`);
  }

  async getBudgetSummary(groupBy = 'department'): Promise<BudgetSummary> {
    return this.apiRequest<BudgetSummary>(`/api/tools/budget-summary?group_by=${groupBy}`);
  }

  async getItemContext(
    itemId: string,
    sections?: string[],
    depth = 'standard',
  ): Promise<ContextBundle> {
    return this.apiRequest<ContextBundle>('/api/tools/get-item-context', {
      method: 'POST',
      body: JSON.stringify({
        item_type: 'agenda_item',
        item_id: itemId,
        depth,
        sections: sections ? sections.join(',') : undefined,
      }),
    });
  }

  async getCommentSynthesis(entityId: string): Promise<CommentSynthesis | null> {
    try {
      return await this.apiRequest<CommentSynthesis>('/api/tools/comment-synthesis', {
        method: 'POST',
        body: JSON.stringify({ entity_id: entityId }),
      });
    } catch {
      return null;
    }
  }

  async generateActionDraft(
    actionType: string,
    topic: string,
    description: string,
    target?: string,
    template?: string,
  ): Promise<{ draft: string; description?: string; citations: string[] } | null> {
    try {
      return await this.apiRequest<{ draft: string; description?: string; citations: string[] }>(
        '/api/tools/action-draft',
        {
          method: 'POST',
          body: JSON.stringify({
            action_type: actionType,
            topic,
            description,
            target: target || null,
            template: template || null,
          }),
        },
      );
    } catch (err) {
      console.error('[CivicOS] generateActionDraft error:', err);
      return null;
    }
  }

  // === Relay coordination API ===

  async getVoiceCountsBatch(entityIds: string[], jurisdiction?: string): Promise<Map<string, VoiceCounts>> {
    const result = new Map<string, VoiceCounts>();
    if (entityIds.length === 0) return result;
    const j = jurisdiction || await this.registry.getActiveJurisdiction();

    try {
      const relayUrl = await this.registry.getRelayUrl();
      const promises = entityIds.map(async (id) => {
        try {
          const url = `${relayUrl}/coordination/voice/counts/${encodeURIComponent(id)}?jurisdiction=${encodeURIComponent(j)}`;
          const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
          });
          if (response.ok) {
            const data: VoiceCounts & { entity: string } = await response.json();
            result.set(id, {
              support: data.support,
              oppose: data.oppose,
              watching: data.watching,
              total: data.total,
              attested: data.attested ?? undefined,
              unattested: data.unattested ?? undefined,
            });
          }
        } catch {
          // Silently skip unavailable voice counts
        }
      });
      await Promise.all(promises);
    } catch {
      // Voice counts are optional — return empty map
    }
    return result;
  }

  async submitVoice(
    entityId: string,
    stance: 'support' | 'oppose' | 'watching',
    jurisdiction: string,
    publicKey: string,
    signature: string,
    createdAt: number,
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(`${relayUrl}/coordination/voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity: entityId,
          stance,
          public_key: publicKey,
          signature,
          created_at: createdAt,
          jurisdiction,
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  async revokeVoice(
    entityId: string,
    publicKey: string,
    signature: string,
    createdAt: number,
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(`${relayUrl}/coordination/voice/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity: entityId,
          public_key: publicKey,
          signature,
          created_at: createdAt,
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  // === Initiatives & Civic Actions ===

  async getInitiatives(
    jurisdiction: string,
    topic?: string,
    status?: string,
    limit = 10,
  ): Promise<Initiative[]> {
    const relayUrl = await this.registry.getRelayUrl();
    const params = new URLSearchParams({ limit: String(limit) });
    if (topic) params.set('topic', topic);
    if (status) params.set('status', status);
    const response = await fetch(
      `${relayUrl}/coordination/initiatives/${encodeURIComponent(jurisdiction)}?${params}`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    if (!response.ok) return [];
    const data = await response.json();
    return Array.isArray(data) ? data : data.initiatives || [];
  }

  async getCivicActions(initiativeId: string): Promise<CivicAction[]> {
    const relayUrl = await this.registry.getRelayUrl();
    const response = await fetch(
      `${relayUrl}/coordination/civic-actions/${encodeURIComponent(initiativeId)}`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    if (!response.ok) return [];
    const data = await response.json();
    return data.actions || [];
  }

  async getCivicActionProgress(actionId: string): Promise<CivicActionProgress | null> {
    const relayUrl = await this.registry.getRelayUrl();
    const response = await fetch(
      `${relayUrl}/coordination/civic-action/${encodeURIComponent(actionId)}/progress`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    if (!response.ok) return null;
    return response.json();
  }

  async commitToCivicAction(
    actionId: string,
    publicKey: string,
    signature: string,
    createdAt: number,
    jurisdiction: string,
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(
        `${relayUrl}/coordination/civic-action/${encodeURIComponent(actionId)}/commit`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            public_key: publicKey,
            signature,
            created_at: createdAt,
            jurisdiction,
          }),
        },
      );
      if (!response.ok) {
        console.error('[CivicOS] commitToCivicAction failed:', response.status, await response.text());
      }
      return response.ok;
    } catch (err) {
      console.error('[CivicOS] commitToCivicAction error:', err);
      return false;
    }
  }

  async completeCivicAction(
    actionId: string,
    publicKey: string,
    signature: string,
    createdAt: number,
    jurisdiction: string,
    evidenceType = 'self_report',
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(
        `${relayUrl}/coordination/civic-action/${encodeURIComponent(actionId)}/complete`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            public_key: publicKey,
            signature,
            created_at: createdAt,
            jurisdiction,
            evidence_type: evidenceType,
          }),
        },
      );
      if (!response.ok) {
        console.error('[CivicOS] completeCivicAction failed:', response.status, await response.text());
      }
      return response.ok;
    } catch (err) {
      console.error('[CivicOS] completeCivicAction error:', err);
      return false;
    }
  }

  async withdrawCivicAction(
    actionId: string,
    publicKey: string,
    signature: string,
    createdAt: number,
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(
        `${relayUrl}/coordination/civic-action/${encodeURIComponent(actionId)}/withdraw`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            public_key: publicKey,
            signature,
            created_at: createdAt,
          }),
        },
      );
      if (!response.ok) {
        console.error('[CivicOS] withdrawCivicAction failed:', response.status, await response.text());
      }
      return response.ok;
    } catch (err) {
      console.error('[CivicOS] withdrawCivicAction error:', err);
      return false;
    }
  }

  async createInitiative(
    jurisdiction: string,
    topic: string,
    title: string,
    description: string,
    publicKey: string,
    signature: string,
    createdAt: number,
    location?: string,
    coordinationUrl?: string,
  ): Promise<Initiative | null> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const url = `${relayUrl}/coordination/initiative`;
      const body = {
        jurisdiction,
        topic,
        title,
        description,
        location: location || null,
        coordination_url: coordinationUrl || null,
        public_key: publicKey,
        signature,
        created_at: createdAt,
      };
      console.log('[CivicOS] createInitiative POST', url, body);
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const errorText = await response.text();
        console.error('[CivicOS] createInitiative failed:', response.status, errorText);
        throw new Error(`Relay error ${response.status}: ${errorText}`);
      }
      return response.json();
    } catch (err) {
      console.error('[CivicOS] createInitiative error:', err);
      throw err;
    }
  }

  async createCivicAction(
    initiativeId: string,
    actionType: string,
    description: string,
    publicKey: string,
    signature: string,
    createdAt: number,
    target?: string,
    deadline?: string,
    targetCount?: number,
    template?: string,
    deadlineContext?: string,
  ): Promise<CivicAction | null> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(`${relayUrl}/coordination/civic-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          initiative_id: initiativeId,
          action_type: actionType,
          description,
          public_key: publicKey,
          signature,
          created_at: createdAt,
          target: target || null,
          deadline: deadline || null,
          target_count: targetCount ?? null,
          template: template || null,
          deadline_context: deadlineContext || null,
        }),
      });
      if (!response.ok) {
        console.error('[CivicOS] createCivicAction failed:', response.status, await response.text());
        return null;
      }
      return response.json();
    } catch (err) {
      console.error('[CivicOS] createCivicAction error:', err);
      return null;
    }
  }

  // === Comments ===

  async getComments(entityId: string, jurisdiction?: string): Promise<Comment[]> {
    const j = jurisdiction || await this.registry.getActiveJurisdiction();
    const relayUrl = await this.registry.getRelayUrl();
    const response = await fetch(
      `${relayUrl}/coordination/comments/${encodeURIComponent(entityId)}?jurisdiction=${encodeURIComponent(j)}`,
      { headers: { 'Content-Type': 'application/json' } },
    );
    if (!response.ok) {
      throw new Error(`Comments unavailable (${response.status})`);
    }
    return response.json();
  }

  async getCommentCounts(entityId: string, jurisdiction?: string): Promise<CommentCounts | null> {
    const j = jurisdiction || await this.registry.getActiveJurisdiction();
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(
        `${relayUrl}/coordination/comment/counts/${encodeURIComponent(entityId)}?jurisdiction=${encodeURIComponent(j)}`,
        { headers: { 'Content-Type': 'application/json' } },
      );
      if (!response.ok) return null;
      return response.json();
    } catch {
      return null;
    }
  }

  async getCommentCountsBatch(entityIds: string[], jurisdiction?: string): Promise<Map<string, CommentCounts>> {
    const result = new Map<string, CommentCounts>();
    if (entityIds.length === 0) return result;
    try {
      const promises = entityIds.map(async (id) => {
        const counts = await this.getCommentCounts(id, jurisdiction);
        if (counts && counts.count > 0) {
          result.set(id, counts);
        }
      });
      await Promise.all(promises);
    } catch {
      // Comment counts are optional
    }
    return result;
  }

  async submitComment(
    entityId: string,
    commentText: string,
    publicKey: string,
    signature: string,
    createdAt: number,
    jurisdiction: string,
    stance?: string,
  ): Promise<boolean> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(`${relayUrl}/coordination/comment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity: entityId,
          comment_text: commentText,
          public_key: publicKey,
          signature,
          created_at: createdAt,
          jurisdiction,
          stance: stance || null,
        }),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  // === Attestation ===

  async getAttestationStatus(
    publicKey: string,
    jurisdiction?: string,
  ): Promise<{ attested: boolean; attestation_event?: Record<string, unknown>; attested_at?: string }> {
    const j = jurisdiction || await this.registry.getActiveJurisdiction();
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(
        `${relayUrl}/coordination/attestation/${encodeURIComponent(publicKey)}?jurisdiction=${encodeURIComponent(j)}`,
        { headers: { 'Content-Type': 'application/json' } },
      );
      if (!response.ok) return { attested: false };
      return response.json();
    } catch {
      return { attested: false };
    }
  }

  async redeemAttestationCode(
    code: string,
    publicKey: string,
    signature: string,
    createdAt: number,
  ): Promise<{ success: boolean; attestation_event?: Record<string, unknown>; error?: string }> {
    try {
      const relayUrl = await this.registry.getRelayUrl();
      const response = await fetch(`${relayUrl}/coordination/attest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          public_key: publicKey,
          signature,
          created_at: createdAt,
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: response.statusText }));
        return { success: false, error: data.detail || `Error ${response.status}` };
      }
      return response.json();
    } catch (err) {
      return { success: false, error: err instanceof Error ? err.message : 'Network error' };
    }
  }

  // === Signer-aware high-level methods ===
  // These combine event construction + signing + submission.
  // Require a Signer to be set via constructor or setSigner().

  async castVoice(
    entityId: string,
    stance: 'support' | 'oppose' | 'watching',
    jurisdiction: string,
  ): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.VOICE,
      tags: createVoiceTags(entityId, jurisdiction, stance),
      content: createVoiceContent(entityId, stance, createdAt),
      created_at: createdAt,
    });
    return this.submitVoice(entityId, stance, jurisdiction, signed.pubkey, signed.sig, createdAt);
  }

  async castRevokeVoice(entityId: string): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.VOICE,
      tags: [['d', entityId]],
      content: createRevokeContent(entityId, createdAt),
      created_at: createdAt,
    });
    return this.revokeVoice(entityId, signed.pubkey, signed.sig, createdAt);
  }

  async castComment(
    entityId: string,
    commentText: string,
    jurisdiction: string,
    stance?: string,
  ): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.COMMENT,
      tags: createCommentTags(entityId, jurisdiction, stance),
      content: commentText,
      created_at: createdAt,
    });
    return this.submitComment(entityId, commentText, signed.pubkey, signed.sig, createdAt, jurisdiction, stance);
  }

  async castCommitment(actionId: string, jurisdiction: string): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.ACTION_COMMITMENT,
      tags: createCommitmentTags(actionId, jurisdiction),
      content: createCommitmentContent(actionId, createdAt),
      created_at: createdAt,
    });
    return this.commitToCivicAction(actionId, signed.pubkey, signed.sig, createdAt, jurisdiction);
  }

  async castCompletion(
    actionId: string,
    jurisdiction: string,
    evidenceType = 'self_report',
  ): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.ACTION_COMPLETION,
      tags: createCompletionTags(actionId, jurisdiction),
      content: createCompletionContent(actionId, createdAt),
      created_at: createdAt,
    });
    return this.completeCivicAction(actionId, signed.pubkey, signed.sig, createdAt, jurisdiction, evidenceType);
  }

  async castWithdrawal(actionId: string): Promise<boolean> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.ACTION_COMMITMENT,
      tags: createWithdrawalTags(actionId),
      content: createWithdrawalContent(actionId, createdAt),
      created_at: createdAt,
    });
    return this.withdrawCivicAction(actionId, signed.pubkey, signed.sig, createdAt);
  }

  async castInitiative(
    jurisdiction: string,
    topic: string,
    title: string,
    description: string,
    coordinationUrl?: string,
  ): Promise<Initiative | null> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.VOICE,
      tags: createInitiativeTags(jurisdiction, topic),
      content: createInitiativeContent(jurisdiction, topic, createdAt),
      created_at: createdAt,
    });
    return this.createInitiative(
      jurisdiction, topic, title, description,
      signed.pubkey, signed.sig, createdAt,
      undefined, coordinationUrl,
    );
  }

  async castCivicAction(
    initiativeId: string,
    actionType: string,
    description: string,
    options?: {
      target?: string;
      deadline?: string;
      targetCount?: number;
      template?: string;
      deadlineContext?: string;
    },
  ): Promise<CivicAction | null> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.ACTION_EVENT,
      tags: createCivicActionTags(initiativeId, actionType),
      content: createCivicActionContent(initiativeId, actionType, createdAt),
      created_at: createdAt,
    });
    return this.createCivicAction(
      initiativeId, actionType, description,
      signed.pubkey, signed.sig, createdAt,
      options?.target, options?.deadline, options?.targetCount,
      options?.template, options?.deadlineContext,
    );
  }

  async castRedeemAttestation(
    code: string,
  ): Promise<{ success: boolean; attestation_event?: Record<string, unknown>; error?: string }> {
    const signer = this.requireSigner();
    const createdAt = Math.floor(Date.now() / 1000);
    const signed = await signer.signEvent({
      kind: CivicEventKinds.ATTESTATION,
      tags: createAttestationTags(code),
      content: createAttestationContent(code, createdAt),
      created_at: createdAt,
    });
    return this.redeemAttestationCode(code, signed.pubkey, signed.sig, createdAt);
  }

  // === Internal ===

  private async apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
    const baseUrl = await this.registry.getMcpUrl();
    const url = `${baseUrl}${path}`;

    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`API error ${response.status}: ${response.statusText}`);
    }

    const result: ToolResponse<T> = await response.json();
    if (!result.success) {
      throw new Error(result.error || 'API returned an error');
    }
    return result.data;
  }
}

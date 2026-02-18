/**
 * Civic event kinds and construction helpers.
 *
 * These follow the Nostr NIP-01 extension for civic coordination.
 * Moved from extension providers/types.ts — platform-agnostic.
 */

export const CivicEventKinds = {
  VOICE: 30800,
  COMMITMENT: 30801,
  COMPLETION: 30802,
  COMMENT: 30803,
  ACTION_EVENT: 30810,
  ACTION_COMMITMENT: 30811,
  ACTION_COMPLETION: 30812,
  ATTESTATION: 30850,
} as const;

// === Voice events ===

export function createVoiceContent(
  entity: string,
  stance: 'support' | 'oppose' | 'watching',
  timestamp: number,
): string {
  return `civicos:voice:v1:${entity}:${stance}:${timestamp}`;
}

export function createVoiceTags(
  entity: string,
  jurisdiction: string,
  stance: 'support' | 'oppose' | 'watching',
): string[][] {
  return [
    ['d', entity],
    ['j', jurisdiction],
    ['stance', stance],
  ];
}

export function createRevokeContent(entity: string, timestamp: number): string {
  return `civicos:voice:v1:${entity}:revoke:${timestamp}`;
}

// === Comment events ===

export function createCommentTags(
  entity: string,
  jurisdiction: string,
  stance?: string,
): string[][] {
  const tags: string[][] = [['d', entity], ['j', jurisdiction]];
  if (stance) tags.push(['stance', stance]);
  return tags;
}

// === Commitment events ===

export function createCommitmentContent(actionId: string, timestamp: number): string {
  return `civicos:action:v1:${actionId}:commitment:${timestamp}`;
}

export function createCommitmentTags(actionId: string, jurisdiction: string): string[][] {
  return [
    ['d', actionId],
    ['j', jurisdiction],
    ['action', 'commitment'],
  ];
}

// === Completion events ===

export function createCompletionContent(
  actionId: string,
  timestamp: number,
  evidenceUrl?: string,
): string {
  const base = `civicos:action:v1:${actionId}:completion:${timestamp}`;
  return evidenceUrl ? `${base}:${evidenceUrl}` : base;
}

export function createCompletionTags(
  actionId: string,
  jurisdiction: string,
  evidenceUrl?: string,
): string[][] {
  const tags: string[][] = [
    ['d', actionId],
    ['j', jurisdiction],
    ['action', 'completion'],
  ];
  if (evidenceUrl) tags.push(['evidence', evidenceUrl]);
  return tags;
}

// === Withdrawal events ===

export function createWithdrawalContent(actionId: string, timestamp: number): string {
  return `civicos:withdraw:v1:${actionId}:${timestamp}`;
}

export function createWithdrawalTags(actionId: string): string[][] {
  return [
    ['d', actionId],
    ['action', 'withdraw'],
  ];
}

// === Initiative events ===

export function createInitiativeContent(
  jurisdiction: string,
  topic: string,
  timestamp: number,
): string {
  return `civicos:initiative:v1:${jurisdiction}:${topic}:${timestamp}`;
}

export function createInitiativeTags(jurisdiction: string, topic: string): string[][] {
  return [
    ['d', `initiative:${jurisdiction}:${topic}`],
    ['j', jurisdiction],
  ];
}

// === Civic action events ===

export function createCivicActionContent(
  initiativeId: string,
  actionType: string,
  timestamp: number,
): string {
  return `civicos:action:v1:${initiativeId}:${actionType}:${timestamp}`;
}

export function createCivicActionTags(
  initiativeId: string,
  actionType: string,
): string[][] {
  return [
    ['d', `action:${initiativeId}:${actionType}`],
    ['initiative', initiativeId],
  ];
}

// === Attestation events ===

export function createAttestationContent(code: string, timestamp: number): string {
  return `civicos:attestation:v1:${code}:${timestamp}`;
}

export function createAttestationTags(code: string): string[][] {
  return [
    ['d', `attestation:${code}`],
    ['action', 'redeem'],
  ];
}

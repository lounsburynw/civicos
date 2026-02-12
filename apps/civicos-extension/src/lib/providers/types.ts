/**
 * Identity tier levels for signing providers.
 *
 * - easy: WebAuthn passkey with PRF (cloud-synced, lowest friction)
 * - private: BIP-39 mnemonic with password encryption (local only)
 * - sovereign: NIP-07 extension, hardware wallet, or manual signing
 */
export type IdentityTier = 'easy' | 'private' | 'sovereign';

/**
 * Nostr event structure per NIP-01.
 */
export interface NostrEvent {
  id?: string;
  pubkey?: string;
  created_at: number;
  kind: number;
  tags: string[][];
  content: string;
  sig?: string;
}

/**
 * A fully signed Nostr event ready for broadcast.
 */
export interface SignedNostrEvent extends NostrEvent {
  id: string;
  pubkey: string;
  sig: string;
}

/**
 * Result of a signing operation.
 */
export interface SigningResult {
  success: boolean;
  event?: SignedNostrEvent;
  error?: string;
}

/**
 * Identity information without exposing private keys.
 */
export interface IdentityInfo {
  tier: IdentityTier;
  publicKey: string; // hex-encoded
  npub: string; // bech32-encoded (NIP-19)
  createdAt: number;
  lastUsed?: number;
}

/**
 * Options for creating a new identity.
 */
export interface CreateIdentityOptions {
  tier: IdentityTier;
  password?: string; // Required for 'private' tier
  mnemonic?: string; // Optional: import existing mnemonic for 'private' tier
}

/**
 * Options for unlocking an identity.
 */
export interface UnlockOptions {
  password?: string; // Required for 'private' tier
  timeout?: number; // Auto-lock after N milliseconds (default: 5 minutes)
}

/**
 * Core interface for all signing providers.
 *
 * Implementations:
 * - PasskeyProvider: WebAuthn PRF -> HKDF -> secp256k1 (Easy mode)
 * - LocalWalletProvider: BIP-39 + PBKDF2 + AES-GCM (Private mode)
 * - NIP07Provider: Delegate to window.nostr extension (Sovereign mode)
 * - HardwareWalletProvider: WebUSB/WebHID (Sovereign mode)
 * - ManualSigningProvider: Display/paste signatures (Sovereign/Airgap mode)
 */
export interface SigningProvider {
  /** The identity tier this provider implements */
  readonly tier: IdentityTier;

  /** Human-readable name for UI */
  readonly name: string;

  /**
   * Check if this provider is available in the current environment.
   * e.g., NIP-07 checks for window.nostr, WebAuthn checks for credentials API
   */
  isAvailable(): Promise<boolean>;

  /**
   * Check if an identity exists (keys have been created/imported).
   */
  hasIdentity(): Promise<boolean>;

  /**
   * Get identity info without exposing private keys.
   * Returns null if no identity exists.
   */
  getIdentity(): Promise<IdentityInfo | null>;

  /**
   * Get the public key in hex format.
   * Returns null if no identity exists or not unlocked.
   */
  getPublicKey(): Promise<string | null>;

  /**
   * Create a new identity with this provider.
   * For 'private' tier, returns the mnemonic (MUST be shown to user for backup).
   */
  createIdentity(options: CreateIdentityOptions): Promise<{
    identity: IdentityInfo;
    mnemonic?: string; // Only for 'private' tier - user must back this up
  }>;

  /**
   * Import an existing identity (e.g., from mnemonic or nsec).
   */
  importIdentity(options: CreateIdentityOptions): Promise<IdentityInfo>;

  /**
   * Unlock the identity for signing operations.
   * May prompt user for password, biometric, or extension approval.
   */
  unlock(options?: UnlockOptions): Promise<boolean>;

  /**
   * Check if the identity is currently unlocked.
   */
  isUnlocked(): boolean;

  /**
   * Lock the identity, clearing any cached keys from memory.
   */
  lock(): void;

  /**
   * Sign a Nostr event.
   * Returns the fully signed event with id, pubkey, and sig fields populated.
   */
  signEvent(event: NostrEvent): Promise<SigningResult>;

  /**
   * Delete the identity and all associated data.
   * This is destructive and cannot be undone.
   */
  deleteIdentity(): Promise<void>;
}

/**
 * Civic-specific event kinds per NIP-01 extension.
 */
export const CivicEventKinds = {
  VOICE: 30800, // Voice/stance on a decision
  COMMITMENT: 30801, // Simple commitment to take action
  COMPLETION: 30802, // Simple completion report
  ACTION_EVENT: 30810, // Full Nostr action event (defines the action)
  ACTION_COMMITMENT: 30811, // Commitment to a 30810 action
  ACTION_COMPLETION: 30812, // Completion of a 30810 action with evidence
  ATTESTATION: 30850, // Identity attestation (city -> resident)
} as const;

/**
 * Type of civic action that can be taken.
 * Matches Python CivicActionType enum in civicos_relay.voice.models.
 */
export type CivicActionType =
  | 'written_comment'
  | 'attend_meeting'
  | 'public_comment'
  | 'contact_official'
  | 'signature'
  | 'share'
  | 'custom';

export const CIVIC_ACTION_TYPES: readonly CivicActionType[] = [
  'written_comment',
  'attend_meeting',
  'public_comment',
  'contact_official',
  'signature',
  'share',
  'custom',
] as const;

/**
 * Type of evidence provided for action completion.
 * Matches Python EvidenceType enum in civicos_relay.voice.models.
 */
export type EvidenceType =
  | 'self_report'
  | 'email_confirmation'
  | 'attendance_check'
  | 'verified';

export const EVIDENCE_TYPES: readonly EvidenceType[] = [
  'self_report',
  'email_confirmation',
  'attendance_check',
  'verified',
] as const;

/**
 * Canonical message format for civic voices.
 * Used for deterministic signing verification.
 */
export function createVoiceContent(
  entity: string,
  stance: 'support' | 'oppose' | 'watching',
  timestamp: number
): string {
  return `civicos:voice:v1:${entity}:${stance}:${timestamp}`;
}

/**
 * Create tags for a civic voice event.
 */
export function createVoiceTags(
  entity: string,
  jurisdiction: string,
  stance: 'support' | 'oppose' | 'watching'
): string[][] {
  return [
    ['d', entity], // Addressable event identifier
    ['j', jurisdiction], // Jurisdiction tag
    ['stance', stance], // Position
  ];
}

/**
 * Canonical message format for civic action commitments.
 * Used for deterministic signing verification.
 */
export function createCommitmentContent(
  actionId: string,
  timestamp: number
): string {
  return `civicos:action:v1:${actionId}:commitment:${timestamp}`;
}

/**
 * Create tags for a civic commitment event.
 */
export function createCommitmentTags(
  actionId: string,
  jurisdiction: string
): string[][] {
  return [
    ['d', actionId], // Addressable event identifier
    ['j', jurisdiction], // Jurisdiction tag
    ['action', 'commitment'], // Action type
  ];
}

/**
 * Canonical message format for civic action completions.
 * Used for deterministic signing verification.
 */
export function createCompletionContent(
  actionId: string,
  timestamp: number,
  evidenceUrl?: string
): string {
  const base = `civicos:action:v1:${actionId}:completion:${timestamp}`;
  return evidenceUrl ? `${base}:${evidenceUrl}` : base;
}

/**
 * Create tags for a civic completion event.
 */
export function createCompletionTags(
  actionId: string,
  jurisdiction: string,
  evidenceUrl?: string
): string[][] {
  const tags: string[][] = [
    ['d', actionId], // Addressable event identifier
    ['j', jurisdiction], // Jurisdiction tag
    ['action', 'completion'], // Action type
  ];
  if (evidenceUrl) {
    tags.push(['evidence', evidenceUrl]);
  }
  return tags;
}

// ============================================================================
// Full Nostr Action Event Helpers (Kinds 30810, 30811, 30812)
// ============================================================================

/**
 * Generate a deterministic action ID.
 * Matches Python CivicActionService._generate_action_id().
 */
export function generateActionId(
  initiativeId: string,
  actionType: string,
  descriptionHashPrefix: string
): string {
  return `action:${initiativeId}:${actionType}:${descriptionHashPrefix}`;
}

/**
 * Generate a commitment ID.
 * Matches Python CivicActionService.commit_to_action() pattern.
 */
export function generateCommitmentId(
  publicKeyPrefix: string,
  actionId: string
): string {
  return `commit:${publicKeyPrefix}:${actionId}`;
}

/**
 * Generate a completion ID.
 * Matches Python CivicActionService.complete_action() pattern.
 */
export function generateCompletionId(
  publicKeyPrefix: string,
  actionId: string
): string {
  return `complete:${publicKeyPrefix}:${actionId}`;
}

/**
 * Generate an action reference (a-tag format).
 * Format: 30810:{creator_pubkey}:{action_id}
 */
export function generateActionRef(
  creatorPubkey: string,
  actionId: string
): string {
  return `30810:${creatorPubkey}:${actionId}`;
}

/**
 * Canonical content for action event (kind 30810).
 * Matches Python CivicActionService._create_action_message().
 */
export function createActionEventContent(
  actionId: string,
  actionType: string,
  descriptionHashPrefix: string,
  timestamp: number
): string {
  return `civicos:action:v1:${actionId}:${actionType}:${descriptionHashPrefix}:${timestamp}`;
}

/**
 * Create tags for an action event (kind 30810).
 */
export function createActionEventTags(
  actionId: string,
  initiativeId: string,
  actionType: string,
  jurisdiction: string,
  options?: {
    description?: string;
    target?: string;
    deadline?: string;
    template?: string;
    targetCount?: number;
  }
): string[][] {
  const tags: string[][] = [
    ['d', actionId],
    ['j', jurisdiction],
    ['initiative', initiativeId],
    ['action_type', actionType],
  ];
  if (options?.description) {
    tags.push(['description', options.description]);
  }
  if (options?.target) {
    tags.push(['target', options.target]);
  }
  if (options?.deadline) {
    tags.push(['deadline', options.deadline]);
  }
  if (options?.template) {
    tags.push(['template', options.template]);
  }
  if (options?.targetCount !== undefined) {
    tags.push(['target_count', String(options.targetCount)]);
  }
  return tags;
}

/**
 * Canonical content for action commitment (kind 30811).
 * Matches Python CivicActionService.verify_commitment_signature().
 */
export function createActionCommitmentContent(
  commitmentId: string,
  actionRef: string
): string {
  return `civicos:commitment:v1:${commitmentId}:${actionRef}`;
}

/**
 * Create tags for an action commitment (kind 30811).
 */
export function createActionCommitmentTags(
  commitmentId: string,
  actionRef: string,
  jurisdiction: string
): string[][] {
  return [
    ['d', commitmentId],
    ['a', actionRef],
    ['j', jurisdiction],
  ];
}

/**
 * Canonical content for action completion (kind 30812).
 * Matches Python CivicActionService.verify_completion_signature().
 */
export function createActionCompletionContent(
  completionId: string,
  actionRef: string,
  evidenceType: string
): string {
  return `civicos:completion:v1:${completionId}:${actionRef}:${evidenceType}`;
}

/**
 * Create tags for an action completion (kind 30812).
 */
export function createActionCompletionTags(
  completionId: string,
  actionRef: string,
  jurisdiction: string,
  evidenceType: string,
  evidenceContent?: string
): string[][] {
  const tags: string[][] = [
    ['d', completionId],
    ['a', actionRef],
    ['j', jurisdiction],
    ['evidence_type', evidenceType],
  ];
  if (evidenceContent) {
    tags.push(['evidence', evidenceContent]);
  }
  return tags;
}

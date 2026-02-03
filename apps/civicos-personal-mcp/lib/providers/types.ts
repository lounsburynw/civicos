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
 * - PasskeyProvider: WebAuthn PRF → HKDF → secp256k1 (Easy mode)
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
  COMMITMENT: 30801, // Commitment to take action
  COMPLETION: 30802, // Report action completed
  ATTESTATION: 30850, // Identity attestation (city → resident)
} as const;

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

/**
 * Signing providers for client-side Nostr identity management.
 *
 * Three identity tiers:
 * - Easy (PasskeyProvider): WebAuthn + PRF, lowest friction
 * - Private (LocalWalletProvider): BIP-39 + password, medium friction
 * - Sovereign (NIP07Provider, etc.): Full self-custody, highest security
 */

// Types
export type {
  IdentityTier,
  NostrEvent,
  SignedNostrEvent,
  SigningResult,
  IdentityInfo,
  CreateIdentityOptions,
  UnlockOptions,
  SigningProvider,
  CivicActionType,
  EvidenceType,
} from './types.js';

export {
  CivicEventKinds,
  createVoiceContent,
  createVoiceTags,
  createCommitmentContent,
  createCommitmentTags,
  createCompletionContent,
  createCompletionTags,
  generateActionId,
  generateCommitmentId,
  generateCompletionId,
  generateActionRef,
  createActionEventContent,
  createActionEventTags,
  createActionCommitmentContent,
  createActionCommitmentTags,
  createActionCompletionContent,
  createActionCompletionTags,
  CIVIC_ACTION_TYPES,
  EVIDENCE_TYPES,
} from './types.js';

// Crypto utilities
export {
  generatePrivateKey,
  getPublicKey,
  publicKeyToHex,
  privateKeyToHex,
  hexToPrivateKey,
  computeEventId,
  schnorrSign,
  schnorrVerify,
  signNostrEvent,
  verifyNostrEvent,
  publicKeyToNpub,
  npubToPublicKey,
  privateKeyToNsec,
  nsecToPrivateKey,
  sha256Hex,
} from './crypto.js';

// Providers
export {
  LocalWalletProvider,
  IndexedDBStorage,
  MemoryStorage,
  type WalletStorage,
} from './local-wallet.js';

export {
  PasskeyProvider,
  LocalStoragePasskeyStorage,
  MemoryPasskeyStorage,
  type PasskeyStorage,
} from './passkey.js';
